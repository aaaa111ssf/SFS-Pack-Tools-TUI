#!/usr/bin/env python3
"""SFS Pack Tool 终端版：不装 Qt 也能用的命令行工具。

复用 sfs_pack_core / sfs_pack_tool_logic 的现有能力，不重复实现业务。
命令：
  scan / info / extract / translate / strip / export / dedupe / repair17 /
  check / repair-dangling / selfcheck / cache
其中 export 需要 AssetRipper（内置版在 third_party/assetripper-*）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import sfs_pack_core as core          # noqa: E402
import sfs_pack_tool_logic as logic   # noqa: E402
import sfs_project_exporter as exporter  # noqa: E402

GUID_RE = re.compile(r"guid:\s*([0-9a-fA-F]{32})")
META_GUID_RE = re.compile(r"^guid:\s*([0-9a-fA-F]{32})", re.M)
BUILTIN_GUIDS = {"0000000000000000f000000000000000"}
TEXT_EXTS = {".prefab", ".asset", ".mat", ".unity", ".controller", ".anim", ".playable"}
PLATFORM_MAP = {
    "win": "WindowsBuild", "windows": "WindowsBuild",
    "mac": "MacBuild", "osx": "MacBuild",
    "android": "AndroidBuild", "ios": "IOS_Build",
}


def log(msg: str) -> None:
    """一行一条打到终端。"""
    print(msg, flush=True)


def human(num: float) -> str:
    """字节数转成人能看的单位。"""
    return logic.human_size(num)


def make_translate(locale: str):
    """做一个极简 i18n 函数，给 logic 里的文案用。"""
    table = logic.TEXT.get(locale) or logic.TEXT["zh"]
    zh = logic.TEXT["zh"]

    def t(key: str, **kw) -> str:
        """按 key 取文案，缺了就退回中文，再缺就原样返回。"""
        s = table.get(key) or zh.get(key) or key
        try:
            return s.format(**kw)
        except Exception:
            return s

    return t


def assets_of(path: str) -> Path:
    """把用户给的路径规整到 Assets 目录。"""
    p = Path(path)
    return p / "Assets" if (p / "Assets").is_dir() else p


def parse_platforms(text: str) -> list[str]:
    """把 win,mac 这类简写转成游戏内部的 Build 键。"""
    keys: list[str] = []
    for raw in (text or "").split(","):
        name = raw.strip().lower()
        if not name:
            continue
        if name not in PLATFORM_MAP:
            raise argparse.ArgumentTypeError(f"未知平台: {raw}（可选 win/mac/android/ios）")
        key = PLATFORM_MAP[name]
        if key not in keys:
            keys.append(key)
    return keys


def scan_dangling(assets: Path) -> dict[str, list[str]]:
    """扫出 Assets 里指向不存在资产的 GUID 引用。"""
    known: set[str] = set()
    for meta in assets.rglob("*.meta"):
        try:
            m = META_GUID_RE.search(meta.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        if m:
            known.add(m.group(1).lower())
    dangling: dict[str, list[str]] = {}
    for f in assets.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in TEXT_EXTS:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for g in GUID_RE.findall(text):
            gl = g.lower()
            if gl in BUILTIN_GUIDS or gl in known:
                continue
            dangling.setdefault(gl, []).append(f.relative_to(assets).as_posix())
    return dangling


# ---------------- 命令 ----------------

SCAN_LABELS = {
    "zh": {"pack": "包", "yes": "有", "no": "无", "custom": "自定义类", "route": "建议路线"},
    "en": {"pack": "Pack", "yes": "yes", "no": "none", "custom": "Custom classes", "route": "Route"},
}


def cmd_scan(args) -> int:
    """扫描包：平台、CodeAssembly、自定义类、建议路线。"""
    rep = core.scan_pack(Path(args.pack), toolkit_root=args.toolkit, log=None)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0 if not rep.get("error") else 1
    lb = SCAN_LABELS.get(getattr(args, "lang", "zh"), SCAN_LABELS["zh"])
    if rep.get("error"):
        log(f"{lb['pack']}: {rep['pack']}")
        log(f"  [!] {rep['error']}")
        return 1
    log(f"{lb['pack']}: {rep['pack']}")
    for name, info in rep["platforms"].items():
        state = (lb["yes"] + " " + human(info["bytes"])) if info["present"] else lb["no"]
        log(f"  {name}: {state}")
    ca = rep["code_assembly"]
    tfm = f" ({ca.get('target_framework')})" if ca.get("target_framework") else ""
    ca_state = (lb["yes"] + " " + human(ca["bytes"]) + tfm) if ca["present"] else lb["no"]
    log(f"  CodeAssembly: {ca_state}")
    custom = rep.get("custom_classes") or []
    log(f"  {lb['custom']}: " + (", ".join(custom) if custom else lb["no"]))
    unknown = rep.get("unknown_classes") or []
    if unknown:
        log(f"  {'缺失类' if lb['pack'] == '包' else 'Missing in toolkit'}: " + ", ".join(unknown))
    log(f"  {lb['route']}: {rep['route']}")
    for w in rep.get("warnings", []):
        log(f"  [!] {w}")
    return 0


def cmd_info(args) -> int:
    """概览包：各平台解压体积与部件数量。"""
    logic.analyze_pack(args.pack, make_translate(args.lang), log)
    return 0


def cmd_extract(args) -> int:
    """把包里的可翻译文本抽成 JSON。"""
    pack = Path(args.pack)
    out = args.output or str(pack.with_name(pack.stem + ".texts.json"))
    logic.extract_texts(args.pack, out, make_translate(args.lang), log)
    return 0 if Path(out).is_file() else 1


def cmd_translate(args) -> int:
    """把翻译 JSON 写回包，生成 -CN.pack。"""
    pack = Path(args.pack)
    logic.write_translation(args.pack, args.json, args.author, make_translate(args.lang), log)
    default_out = pack.with_name(pack.stem + "-CN.pack")
    if args.output and default_out.is_file():
        target = Path(args.output)
        if target.resolve() != default_out.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            default_out.replace(target)
            log(f"[完成] 已输出到 {target}")
            return 0
    return 0 if default_out.is_file() else 1


def cmd_strip(args) -> int:
    """剥离到指定平台，减小包体。"""
    keys = parse_platforms(args.platforms)
    logic.strip_pack(args.pack, args.output, keys, make_translate(args.lang), log)
    return 0


def cmd_dedupe(args) -> int:
    """对导出工程去重（X 与 X_0 这类副本）。"""
    assets = assets_of(args.path)
    backup = args.backup or str(assets.parent / "_DEDUPE_BACKUP")
    rep = core.dedupe_export_assets(assets, log=log, backup_dir=Path(backup))
    log(f"[去重] 组 {rep.get('groups')} / 移除 {rep.get('removed')} / 改引用 {rep.get('redirected_refs')}")
    return 0


def cmd_repair17(args) -> int:
    """给旧 mod 的引擎组件补 1.7 新字段。"""
    assets = assets_of(args.path)
    backup = args.backup or str(assets.parent / "_ENGINE17_BACKUP")
    rep = core.repair_engine_modules_for_17(
        assets, Path(args.toolkit) if args.toolkit else None,
        log=log, backup_dir=Path(backup))
    if rep.get("error"):
        log(f"[1.7修复] 失败: {rep['error']}")
        return 1
    return 0


def cmd_check(args) -> int:
    """检查工程里有多少悬空 GUID 引用。"""
    assets = assets_of(args.path)
    dangling = scan_dangling(assets)
    total_refs = sum(len(v) for v in dangling.values())
    log(f"[检查] 悬空 GUID {len(dangling)} 种 / 引用 {total_refs} 处")
    for g, files in sorted(dangling.items(), key=lambda x: -len(x[1]))[:args.limit]:
        log(f"  {g}  x{len(files)}  例: {files[0]}")
    return 0 if not dangling else 2


def cmd_repair_dangling(args) -> int:
    """修复 Toolkit 里的悬空引用（可给原始 mod 工程目录）。"""
    rep = core.repair_toolkit_dangling_refs(
        args.toolkit, package_assets=args.package, log=log, backup=not args.no_backup)
    if rep.get("error"):
        log(f"[悬空修复] 失败: {rep['error']}")
        return 1
    return 0


def cmd_selfcheck(args) -> int:
    """自检 Toolkit：自带部件能否命中自己的脚本 GUID。"""
    rep = core.verify_toolkit_self(args.toolkit)
    log(f"[自检] 部件 {rep.get('prefabs')} / 引用 {rep.get('refs')} / 未命中 {rep.get('missing')}")
    return 0 if not rep.get("missing") else 2


def cmd_cache(args) -> int:
    """列出或清理缓存。"""
    items = logic.scan_cache(args.toolkit or "")
    if args.action == "list":
        if not items:
            log("[缓存] 没有可清理项")
        for it in items:
            flag = "★" if it.get("risky") else " "
            log(f"  {flag} {it['key']:8} {human(it['size']):>10}  {it['path']}")
        return 0
    keys = {k.strip() for k in (args.keys or "").split(",") if k.strip()}
    if not keys:
        log("[缓存] 请用 --keys 指定要清理的 key")
        return 1
    if not args.yes:
        log("[缓存] 清理会删文件，确认请加 --yes")
        return 1
    freed, errors = logic.clean_cache_items(items, keys)
    log(f"[缓存] 释放 {human(freed)}")
    for err in errors:
        log(f"  [!] {err}")
    return 0 if not errors else 2


class CliHost(logic.LogicMixin):
    """把 LogicMixin 当纯逻辑用：补上它需要的"界面外壳"。"""

    def __init__(self, lang: str = "zh"):
        """只准备导出流程会用到的属性。"""
        self.settings: dict = {}
        self.input_file = ""
        self.output_dir = ""
        self.t = make_translate(lang)
        self.tlog = log
        self._ui = lambda fn: fn()
        self.install_var = SimpleNamespace(get=lambda: False)
        self.toolkit_dir_var = SimpleNamespace(get=lambda: "")
        self.package_dir_var = SimpleNamespace(get=lambda: "")

    def set_progress(self, frac: float, msg: str = "") -> None:
        """终端不画进度条，进度写日志即可。"""
        if msg:
            log(f"[进度] {int(frac * 100):3d}%  {msg}")

    def _export_index_path(self) -> Path:
        """增量索引放输出目录，绝不写 C 盘。"""
        if self.output_dir:
            base = Path(self.output_dir)
        elif self.input_file:
            base = Path(self.input_file).parent
        else:
            base = Path.cwd()
        return base / ".sfs_export_index.json"

    def _after_scan_notices(self, scan: dict, log) -> None:
        """终端不弹窗，把扫描提示写成日志。"""
        for w in scan.get("warnings") or []:
            log(f"[扫描] [!] {w}")

    def _gate_popup(self, n: int, refs: int, classes: list[str], path: str) -> None:
        """合并闸门被拦：终端只打日志。"""
        log(f"[闸门] {n} 类脚本未解析（{refs} 处），清单: {path}")

    def _assembly_conflict_popup(self, conflicts: list[dict], package_dir: Path) -> None:
        """同名程序集冲突：终端只打日志。"""
        log(f"[冲突] 同名程序集 {len(conflicts)} 组，见 {package_dir}")

    def _asm_scan_failed_popup(self, package_dir: Path) -> None:
        """程序集扫描失败：终端只打日志。"""
        log("[冲突] 程序集扫描失败")

    def _source_conflict_popup(self, conflicts: list[dict], package_dir: Path) -> None:
        """源程序集冲突：终端只打日志。"""
        log(f"[冲突] 源程序集冲突 {len(conflicts)} 组")


def resolve_ripper_path(value: str | None) -> str:
    """用户给的可以是目录也可以是 exe；是目录就在里面找可执行文件。"""
    if not value:
        return ""
    p = Path(value).expanduser()
    if p.is_file():
        return str(p)
    if p.is_dir():
        for cand in exporter.executable_candidates(p):
            return str(cand)
    return ""


def cmd_export(args) -> int:
    """导出 Unity 工程（需要可用的 AssetRipper）。"""
    pack = Path(args.pack)
    if not pack.is_file():
        log(f"[导出] 包不存在: {pack}")
        return 1
    tk_raw = (args.toolkit or "").strip()
    if not tk_raw:
        log("[导出] 必须指定 Toolkit 目录（解包结果要落到哪个 Toolkit）")
        return 1
    tk = Path(tk_raw).expanduser()
    if tk.name.lower() == "assets" and (tk / "Scripts").is_dir():
        tk = tk.parent
    if not (tk / "Assets").is_dir():
        log(f"[导出] Toolkit 目录无效: {tk_raw}（应包含 Assets 子目录）")
        return 1
    log(f"[导出] Toolkit: {tk}")
    host = CliHost(args.lang)
    host.input_file = str(pack)
    raw_ripper = getattr(args, "ripper_dir", None) or args.ripper_path
    ripper = resolve_ripper_path(raw_ripper)
    mode = "custom" if ripper else args.ripper_mode
    if raw_ripper and not ripper:
        log(f"[导出] 这个目录里没找到 AssetRipper 可执行文件: {raw_ripper}")
        return 1
    host.settings = {
        "asset_ripper_mode": mode,
        "asset_ripper_version": args.ripper_version or "",
        "asset_ripper_path": ripper,
    }
    host.toolkit_dir_var = SimpleNamespace(get=lambda: str(tk))
    output = args.output or str(pack.parent / (pack.stem + "_export"))
    host.output_dir = str(Path(output).parent)
    try:
        host.export_project(log, output, str(tk),
                            install=bool(args.install),
                            strip_custom=bool(args.strip_custom))
    except Exception as exc:
        log(f"[导出] 失败: {exc}")
        return 1
    return 0 if Path(output).is_dir() else 1


def build_parser() -> argparse.ArgumentParser:
    """搭命令行参数。"""
    p = argparse.ArgumentParser(
        prog="sfs-pack-tool",
        description="SFS Pack Tool 终端版（第一批：扫描/汉化/剥离/修复）")
    p.add_argument("--lang", choices=("zh", "en"), default="zh", help="终端文案语言")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="扫描包信息")
    s.add_argument("pack")
    s.add_argument("--toolkit", help="Toolkit 目录（用于判定自定义类）")
    s.add_argument("--json", action="store_true", help="输出 JSON")
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("info", help="概览各平台体积与部件数")
    s.add_argument("pack")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("extract", help="提取可翻译文本")
    s.add_argument("pack")
    s.add_argument("-o", "--output", help="输出 JSON 路径")
    s.set_defaults(func=cmd_extract)

    s = sub.add_parser("translate", help="写回翻译并生成 -CN.pack")
    s.add_argument("pack")
    s.add_argument("json")
    s.add_argument("-a", "--author", default="", help="追加到作者名后的汉化署名")
    s.add_argument("-o", "--output", help="输出 pack 路径")
    s.set_defaults(func=cmd_translate)

    s = sub.add_parser("strip", help="剥离到指定平台")
    s.add_argument("pack")
    s.add_argument("--platforms", default="win", help="win/mac/android/ios，逗号分隔")
    s.add_argument("-o", "--output", help="输出 pack 路径")
    s.set_defaults(func=cmd_strip)

    s = sub.add_parser("export", help="导出 Unity 工程（需要 AssetRipper）")
    s.add_argument("pack")
    s.add_argument("-o", "--output", help="导出目录（默认 <包名>_export）")
    s.add_argument("--toolkit", required=True, help="Toolkit 目录（必填，解包结果落到这里）")
    s.add_argument("--install", action="store_true", help="同时合并进 Toolkit")
    s.add_argument("--strip-custom", action="store_true", help="剥离自定义脚本组件")
    s.add_argument("--ripper-mode", choices=("bundled", "version", "custom"), default="bundled")
    s.add_argument("--ripper-version", help="指定 AssetRipper 版本（如 1.1.4）")
    s.add_argument("--ripper-path", help="AssetRipper 可执行文件或解压目录")
    s.add_argument("--ripper-dir", help="AssetRipper 解压目录（等同 --ripper-path 传目录）")
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("dedupe", help="导出工程去重")
    s.add_argument("path", help="工程根目录或 Assets 目录")
    s.add_argument("--backup", help="备份目录（默认在 Assets 同级）")
    s.set_defaults(func=cmd_dedupe)

    s = sub.add_parser("repair17", help="1.7 引擎组件自动修复")
    s.add_argument("path", help="工程根目录或 Assets 目录")
    s.add_argument("--toolkit", required=True, help="1.7 Toolkit 目录")
    s.add_argument("--backup", help="备份目录（默认在 Assets 同级）")
    s.set_defaults(func=cmd_repair17)

    s = sub.add_parser("check", help="检查悬空 GUID 引用")
    s.add_argument("path", help="工程根目录或 Assets 目录")
    s.add_argument("--limit", type=int, default=20, help="最多列出多少种")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("repair-dangling", help="修复 Toolkit 悬空引用")
    s.add_argument("toolkit", help="Toolkit 目录")
    s.add_argument("--package", help="原始 mod 工程目录（提供才能真修）")
    s.add_argument("--no-backup", action="store_true", help="不备份（不建议）")
    s.set_defaults(func=cmd_repair_dangling)

    s = sub.add_parser("selfcheck", help="自检 Toolkit 脚本引用")
    s.add_argument("toolkit", help="Toolkit 目录")
    s.set_defaults(func=cmd_selfcheck)

    s = sub.add_parser("cache", help="列出/清理缓存")
    s.add_argument("action", choices=("list", "clean"))
    s.add_argument("--toolkit", help="Toolkit 目录（扫它的备份）")
    s.add_argument("--keys", help="要清理的 key，逗号分隔")
    s.add_argument("--yes", action="store_true", help="确认真的删")
    s.set_defaults(func=cmd_cache)
    return p


def main(argv: list[str] | None = None) -> int:
    """入口：解析参数并执行。"""
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        log("[中断] 用户取消")
        return 130
    except Exception as exc:  # 终端版不吞异常，直接给可读信息
        log(f"[错误] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
