#!/usr/bin/env python3
"""SFS Pack Tool 终端版共用逻辑（不直接运行）。

中文入口 sfs_pack_tui.py、英文入口 sfs_pack_tui_en.py 各自带一份文案，
启动时 configure(lang, TEXT) 注入，其余流程完全一致。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import sfs_pack_cli as cli            # noqa: E402
import sfs_pack_toolbox as toolbox   # noqa: E402
import sfs_project_exporter as exporter  # noqa: E402

STATE_PATH = HERE / "_tui_state.json"
STATE: dict = {}
INTERACTIVE = sys.stdin.isatty()

_LANG = "zh"
_TEXT: dict = {}


def configure(lang: str, text: dict) -> None:
    """入口注入语言和文案表。"""
    global _LANG, _TEXT
    _LANG = lang
    _TEXT = text


def lang() -> str:
    """当前界面语言。"""
    return _LANG


def T(key: str, **kw) -> str:
    """取一条文案（元组取第一项）。"""
    value = _TEXT.get(key, key)
    if isinstance(value, tuple):
        return value[0]
    try:
        return str(value).format(**kw)
    except (KeyError, IndexError):
        return str(value)


def TD(key: str) -> tuple:
    """取菜单项的（标题, 说明）。"""
    value = _TEXT.get(key)
    if isinstance(value, tuple):
        return value
    return (str(value or key), "")


# ---------------- 状态与输入 ----------------

def load_state() -> dict:
    """读上次填过的路径与设置，省得每次重输。"""
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state() -> None:
    """把常用路径与设置记在工具目录，不碰 C 盘。"""
    try:
        STATE_PATH.write_text(json.dumps(STATE, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def clear() -> None:
    """清屏重画菜单。"""
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()


def getch() -> str:
    """读一个键，方向键统一成 ESC[A/ESC[B。"""
    if os.name == "nt":
        try:
            import msvcrt
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                ch2 = msvcrt.getwch()
                return {"H": "\x1b[A", "P": "\x1b[B"}.get(ch2, "")
            return ch
        except Exception:
            pass
    try:
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch += sys.stdin.read(2)
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        return ""


def read_key() -> str:
    """读一个选择键；非交互环境退回整行输入。"""
    if INTERACTIVE:
        k = getch()
        if k:
            return k
    try:
        line = input("> ").strip()
    except EOFError:
        return "q"
    return line or "\r"


_EOF = False


def ask(prompt: str, default: str = "") -> str:
    """问一个值，直接回车就用默认。"""
    global _EOF
    hint = f" [{default}]" if default else ""
    try:
        v = input(f"{prompt}{hint}: ").strip()
    except EOFError:
        _EOF = True
        return default
    return v or default


def ask_required(prompt: str, default: str = "") -> str:
    """必填项：一直问到非空为止；输入流结束就放弃，避免死循环。"""
    while not _EOF:
        v = ask(prompt, default).strip().strip('"')
        if v:
            return v
        print(T("need_value", name=prompt))
    return ""


def ask_yes(prompt: str) -> bool:
    """问是否，默认否。"""
    yes_words = ("y", "yes", "1", "是")
    return ask(prompt + " (y/N)", "").lower() in yes_words


# ---------------- Toolkit / AssetRipper 校验 ----------------

def normalize_toolkit(path: str) -> Path | None:
    """把用户给的路径规范成 Toolkit 根目录；不像 Toolkit 就返回 None。

    允许直接给 `.../156/Assets`，自动退回上一级。
    """
    raw = (path or "").strip().strip('"')
    if not raw:
        return None
    p = Path(raw).expanduser()
    if not p.is_dir():
        return None
    if p.name.lower() == "assets" and (p / "Scripts").is_dir():
        p = p.parent
    if (p / "Assets").is_dir():
        return p
    return None


def toolkit_fingerprint(root: Path) -> str:
    """取 Toolkit 版本指纹，失败就当空。"""
    try:
        return str(toolbox.probe_toolkit_version(root).get("fingerprint", "") or "")
    except Exception:
        return ""


def find_ripper_exe(value: str) -> Path | None:
    """用户给的可以是目录也可以是 exe；是目录就在里面找 AssetRipper。"""
    raw = (value or "").strip().strip('"')
    if not raw:
        return None
    p = Path(raw).expanduser()
    if p.is_file():
        return p
    if p.is_dir():
        for cand in exporter.executable_candidates(p):
            return cand
    return None


def cli_hint(value: str) -> str:
    """目录里只有 CLI 版 exe 时，专门提示一句（那个没网页界面，用不了）。"""
    p = Path(value or "").expanduser()
    if p.is_dir():
        builds = exporter.cli_only_builds(p)
        if builds:
            return T("e_cli_build", name=builds[0].name)
    return ""


def ripper_dir_setting() -> str:
    """当前保存的 AssetRipper 目录（兼容旧版存的 exe 路径）。"""
    raw = str(STATE.get("ripper_dir") or "").strip()
    if raw:
        return raw
    legacy = str((STATE.get("ripper") or {}).get("path") or "").strip()
    if legacy:
        p = Path(legacy)
        return str(p.parent if p.is_file() else p)
    return ""


def ripper_summary() -> str:
    """菜单顶部那行 AssetRipper 摘要。"""
    raw = ripper_dir_setting()
    if not raw:
        return T("ripper_unset")
    exe = find_ripper_exe(raw)
    if exe is None:
        return T("ripper_bad", path=raw)
    return T("ripper_ready", name=exe.name)


# ---------------- 各菜单动作 ----------------

def act_scan() -> None:
    """扫描包。"""
    pack = ask_required(T("p_pack"), STATE.get("pack", ""))
    STATE["pack"] = pack
    tk = ask(T("p_toolkit_opt"), STATE.get("toolkit", ""))
    STATE["toolkit"] = tk
    cli.cmd_scan(SimpleNamespace(pack=pack, toolkit=tk or None, json=False, lang=lang()))


def act_info() -> None:
    """看包概览。"""
    pack = ask_required(T("p_pack"), STATE.get("pack", ""))
    STATE["pack"] = pack
    cli.cmd_info(SimpleNamespace(pack=pack, lang=lang()))


def act_extract() -> None:
    """提取文本。"""
    pack = ask_required(T("p_pack"), STATE.get("pack", ""))
    STATE["pack"] = pack
    default = str(Path(pack).with_suffix("")) + ".texts.json"
    out = ask(T("p_json_out"), default)
    cli.cmd_extract(SimpleNamespace(pack=pack, output=out, lang=lang()))


def act_translate() -> None:
    """写回汉化。"""
    pack = ask_required(T("p_orig_pack"), STATE.get("pack", ""))
    STATE["pack"] = pack
    js = ask_required(T("p_trans_json"), STATE.get("json", ""))
    STATE["json"] = js
    author = ask(T("p_author"), "A Future star")
    out = ask(T("p_out_pack"), str(Path(pack).with_suffix("")) + "-CN.pack")
    cli.cmd_translate(SimpleNamespace(pack=pack, json=js, author=author,
                                      output=out, lang=lang()))


def act_strip() -> None:
    """剥离平台。"""
    pack = ask_required(T("p_pack"), STATE.get("pack", ""))
    STATE["pack"] = pack
    plats = ask(T("p_platforms"), "win")
    out = ask(T("p_out_pack"), str(Path(pack).with_suffix("")) + "-strip.pack")
    cli.cmd_strip(SimpleNamespace(pack=pack, platforms=plats, output=out, lang=lang()))


def act_export() -> None:
    """导出 Unity 工程：Toolkit 与 AssetRipper 都必须有。"""
    exe = find_ripper_exe(ripper_dir_setting())
    if exe is None:
        print(T("e_ripper_first"))
        hint = cli_hint(ripper_dir_setting())
        if hint:
            print(hint)
        return
    print(T("t_using_ripper", path=str(exe)))

    pack = ask_required(T("p_pack"), STATE.get("pack", ""))
    STATE["pack"] = pack
    out = ask(T("p_export_dir"), str(Path(pack).with_suffix("")) + "_export")

    raw_tk = ask_required(T("p_toolkit_required"), STATE.get("toolkit", ""))
    tk = normalize_toolkit(raw_tk)
    if tk is None:
        print(T("e_toolkit_bad", path=raw_tk))
        return
    STATE["toolkit"] = str(tk)
    print(T("t_toolkit_ok", path=str(tk)))
    fp = toolkit_fingerprint(tk)
    if fp:
        print(f"          fingerprint {fp}")

    install = ask_yes(T("p_install"))
    strip = ask_yes(T("p_strip_custom"))
    cli.cmd_export(SimpleNamespace(
        pack=pack, output=out, toolkit=str(tk), install=install, strip_custom=strip,
        ripper_mode="custom", ripper_version=None, ripper_path=str(exe),
        lang=lang()))


def act_dedupe() -> None:
    """工程去重。"""
    path = ask_required(T("p_project"), STATE.get("project", ""))
    STATE["project"] = path
    backup = str(Path(path) / "_DEDUPE_BACKUP")
    cli.cmd_dedupe(SimpleNamespace(path=path, backup=backup))


def act_repair17() -> None:
    """1.7 引擎修复。"""
    path = ask_required(T("p_project"), STATE.get("project", ""))
    STATE["project"] = path
    tk = ask_required(T("p_toolkit17"), STATE.get("toolkit17", ""))
    STATE["toolkit17"] = tk
    cli.cmd_repair17(SimpleNamespace(path=path, toolkit=tk,
                                     backup=str(Path(path) / "_ENGINE17_BACKUP")))


def act_check() -> None:
    """悬空检查。"""
    path = ask_required(T("p_project"), STATE.get("project", ""))
    STATE["project"] = path
    cli.cmd_check(SimpleNamespace(path=path, limit=20))


def act_repair_dangling() -> None:
    """悬空修复。"""
    tk = ask_required(T("p_toolkit"), STATE.get("toolkit", ""))
    STATE["toolkit"] = tk
    pkg = ask(T("p_pkg_opt"), STATE.get("package", ""))
    STATE["package"] = pkg
    cli.cmd_repair_dangling(SimpleNamespace(toolkit=tk, package=pkg or None,
                                            no_backup=False))


def act_selfcheck() -> None:
    """Toolkit 自检。"""
    tk = ask_required(T("p_toolkit"), STATE.get("toolkit", ""))
    STATE["toolkit"] = tk
    cli.cmd_selfcheck(SimpleNamespace(toolkit=tk))


def act_cache() -> None:
    """缓存管理。"""
    tk = ask(T("p_toolkit_opt"), STATE.get("toolkit", ""))
    mode = ask(T("p_cache_mode"), "list").lower()
    if mode.startswith("c"):
        keys = ask(T("p_cache_keys"), "")
        if keys and ask_yes(T("q_confirm_delete", keys=keys)):
            cli.cmd_cache(SimpleNamespace(action="clean", toolkit=tk, keys=keys, yes=True))
            return
    cli.cmd_cache(SimpleNamespace(action="list", toolkit=tk, keys=None, yes=False))


def print_ripper_status(value: str) -> None:
    """打印这个目录解析出的 exe 与版本，给用户确认选对了没。"""
    exe = find_ripper_exe(value)
    if exe is None:
        print(T("set_path_bad", path=value or "(empty)"))
        return
    try:
        info = toolbox.resolve_asset_ripper_version(exe)
    except Exception:
        info = {}
    ver = info.get("version") or "?"
    print(T("set_path_ok", path=str(exe), version=ver))


def act_settings() -> None:
    """设置：AssetRipper 目录（持久化）。"""
    current = ripper_dir_setting()
    print(T("set_current", path=current or T("ripper_unset")))
    raw = ask(T("set_ripper_dir"), current).strip().strip('"')
    if not raw:
        print(T("set_unchanged"))
        return
    exe = find_ripper_exe(raw)
    if exe is None:
        print(T("set_path_bad", path=raw))
        print(cli_hint(raw) or T("set_need_exe"))
        return
    STATE["ripper_dir"] = str(Path(raw).expanduser())
    save_state()
    print_ripper_status(STATE["ripper_dir"])


def act_doctor() -> None:
    """体检：包或工程，只报告不改。"""
    target = ask_required(T("p_doctor_target"), STATE.get("doctor_target", "") or STATE.get("pack", ""))
    if not target:
        return
    STATE["doctor_target"] = target
    cli.cmd_doctor(SimpleNamespace(path=target, toolkit=STATE.get("toolkit", "")))


def act_fix() -> None:
    """安全修复：会先备份。"""
    target = ask_required(T("p_doctor_target"), STATE.get("doctor_target", "") or STATE.get("pack", ""))
    if not target:
        return
    STATE["doctor_target"] = target
    if not ask_yes(T("q_fix_confirm", path=target)):
        return
    cli.cmd_fix(SimpleNamespace(path=target, yes=True))


def act_strip_scripts() -> None:
    """摘掉游戏不认的脚本组件（先列清单，再确认）。"""
    target = ask_required(T("p_doctor_target"), STATE.get("doctor_target", "") or STATE.get("pack", ""))
    if not target:
        return
    STATE["doctor_target"] = target
    toolkit = STATE.get("toolkit", "")
    cli.cmd_strip_scripts(SimpleNamespace(path=target, classes="", toolkit=toolkit, yes=False))
    names = ask(T("p_strip_classes"), "")
    if not names:
        return
    if not ask_yes(T("q_strip_confirm", names=names, path=target)):
        return
    cli.cmd_strip_scripts(SimpleNamespace(path=target, classes=names,
                                          toolkit=toolkit, yes=True))


ITEMS = [
    {"key": "1", "title": "menu_scan", "fn": act_scan},
    {"key": "2", "title": "menu_info", "fn": act_info},
    {"key": "3", "title": "menu_extract", "fn": act_extract},
    {"key": "4", "title": "menu_translate", "fn": act_translate},
    {"key": "5", "title": "menu_strip", "fn": act_strip},
    {"key": "6", "title": "menu_export", "fn": act_export},
    {"key": "7", "title": "menu_dedupe", "fn": act_dedupe},
    {"key": "8", "title": "menu_repair17", "fn": act_repair17},
    {"key": "9", "title": "menu_check", "fn": act_check},
    {"key": "a", "title": "menu_repair_dangling", "fn": act_repair_dangling},
    {"key": "b", "title": "menu_selfcheck", "fn": act_selfcheck},
    {"key": "c", "title": "menu_cache", "fn": act_cache},
    {"key": "d", "title": "menu_settings", "fn": act_settings},
    {"key": "e", "title": "menu_doctor", "fn": act_doctor},
    {"key": "f", "title": "menu_fix", "fn": act_fix},
    {"key": "g", "title": "menu_strip_scripts", "fn": act_strip_scripts},
]


def draw(items: list[dict], idx: int) -> None:
    """画一屏菜单。"""
    clear()
    print(T("app_title"))
    print("─" * 62)
    print(T("hint"))
    print(T("status", ripper=ripper_summary()))
    print("─" * 62)
    for i, it in enumerate(items):
        mark = "▸" if i == idx else " "
        title, desc = TD(it["title"])
        line = f" {mark} [{it['key']}] {title}  —  {desc}"
        if i == idx:
            print(f"\x1b[7m{line}\x1b[0m")
        else:
            print(line)
    print("─" * 62)


def run_item(item: dict) -> None:
    """执行一个菜单项，结束后停一下。"""
    print(f"\n── {TD(item['title'])[0]} ──")
    try:
        item["fn"]()
    except KeyboardInterrupt:
        print("\n" + T("cancel"))
    except Exception as exc:  # 终端里直接把错误给用户看
        print(T("error", error=exc))
    print(T("press_enter"))
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass


def main() -> int:
    """入口：菜单循环。"""
    global STATE
    STATE = load_state()
    idx = 0
    try:
        while True:
            draw(ITEMS, idx)
            key = read_key()
            low = key.lower()
            if low in ("q", "quit", "exit"):
                break
            if key in ("\x1b[A", "w", "k"):
                idx = (idx - 1) % len(ITEMS)
                continue
            if key in ("\x1b[B", "s", "j"):
                idx = (idx + 1) % len(ITEMS)
                continue
            if key in ("\r", "\n", "\r\n", ""):
                run_item(ITEMS[idx])
                continue
            hit = next((it for it in ITEMS if it["key"] == low), None)
            if hit:
                run_item(hit)
    except KeyboardInterrupt:
        pass
    finally:
        save_state()
    print(T("bye"))
    return 0
