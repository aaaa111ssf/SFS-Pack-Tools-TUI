#!/usr/bin/env python3
"""体检（doctor）+ 安全修复（fix）。

只做「能从数据里判定」的问题，不猜、不改代码：
  · 包内类名在 Toolkit 里找不到（进游戏会 Missing Script）
  · 包内组件指向的脚本对象不存在
  · [Required] 的引用字段为空（parachute / heatHitbox 这类）
  · PackData 的 ShowIcon 与 Icon 自相矛盾
  · 工程里 prefab 的 m_Script 指向不存在的 GUID
  · Assets 下同名托管程序集（Unity 会卸载其中一个）

fix 只做两种不会损坏数据的操作，且动手前先备份：
  · PackData 图标标志归一化
  · 同名程序集副本迁出 Assets
"""
from __future__ import annotations

import base64
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

import sfs_pack_core as core

META_GUID = re.compile(r"^guid:[ ]*([0-9a-f]{32})", re.M)
M_SCRIPT = re.compile(r"m_Script:[ ]*\{fileID:[ ]*11500000,[ ]*guid:[ ]*([0-9a-f]{32})")
GUID_ANY = re.compile(r"guid:[ ]*([0-9a-f]{32})")

# Unity 内置资源（Default-Material / 内置贴图等）不属于工程资产，别当悬空
BUILTIN_GUIDS = {
    "0000000000000000f000000000000000",
    "0000000000000000e000000000000000",
    "0000000000000000d000000000000000",
}
# 插件包按平台分目录放同名 dll，这是正常的，不算冲突
VARIANT_DIRS = {"noeditor", "noemitandnoeditor", "editor", "x86_64", "x86", "arm64"}

# 类名 -> 必须指向真实对象的字段（空白就是空引用隐患）
REQUIRED_REFS = {
    "ParachuteModule": ["parachute"],
    "EngineModule": ["heatHitbox"],
    "BoosterModule": ["heatHitbox"],
}


def _issue(code: str, level: str, title: str, detail: list[str] | None = None) -> dict:
    """拼一条问题记录。"""
    items = detail or []
    return {"code": code, "level": level, "title": title, "count": len(items), "detail": items}


def _is_empty_pptr(node) -> bool:
    """PPtr 是否指向空：必须真的是 PPtr（有 m_PathID 键），别把普通结构体当空引用。"""
    return (isinstance(node, dict)
            and "m_PathID" in node
            and node.get("m_FileID", 0) == 0
            and node.get("m_PathID", 0) == 0)


def _walk_required(node, cls: str, out: list[str], path: str = "") -> None:
    """在组件数据里找必填字段是不是空的。"""
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        here = f"{path}.{key}" if path else key
        if key in REQUIRED_REFS.get(cls, []) and _is_empty_pptr(value):
            out.append(f"{cls}.{here}")
        if isinstance(value, dict):
            _walk_required(value, cls, out, here)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                _walk_required(item, cls, out, f"{here}[{i}]")


def inspect_pack(pack: Path, toolkit_root: str = "") -> dict:
    """体检一个 .pack。"""
    pack = Path(pack)
    issues: list[dict] = []
    stats: dict = {}
    try:
        data = json.loads(pack.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "kind": "pack", "target": str(pack),
                "issues": [_issue("read", "error", f"读不了这个包：{exc}")], "stats": {}}

    platforms = [k for k in ("WindowsBuild", "AndroidBuild", "MacBuild", "IOS_Build")
                 if isinstance(data.get(k), str) and data[k]]
    stats["platforms"] = platforms
    if not platforms:
        issues.append(_issue("no_platform", "error", "四个平台包都是空的"))

    # 缺哪些类的定义
    try:
        classes = core.collect_monoscript_classes(pack)
    except Exception as exc:
        classes = set()
        issues.append(_issue("class_read", "warn", f"读不出包内类名：{exc}"))
    stats["classes"] = len(classes)
    if toolkit_root:
        native = core.toolkit_script_classes(toolkit_root)
        if native:
            # mod 自带 dll 提供的类本来就不在 Toolkit 里，别算成“游戏缺”
            try:
                own = core.custom_monoscript_classes(pack)
            except Exception:
                own = set()
            unknown = sorted(classes - native - own)
            if unknown:
                issues.append(_issue(
                    "unknown_class", "error",
                    f"{len(unknown)} 个类在 Toolkit 里找不到（游戏里很可能没有）",
                    unknown))
        else:
            issues.append(_issue("no_toolkit_scripts", "warn",
                                 "Toolkit 里没有 Assets/Scripts，无法核对类名"))

    # 逐平台看 bundle 内部
    import UnityPy
    for key in platforms:
        try:
            env = UnityPy.load(base64.b64decode(data[key]))
        except Exception as exc:
            issues.append(_issue("bundle_read", "error", f"{key} 解析失败：{exc}"))
            continue
        scripts = {}
        for obj in env.objects:
            if obj.type.name == "MonoScript":
                try:
                    tt = obj.read_typetree()
                except Exception:
                    continue
                scripts[obj.path_id] = tt.get("m_ClassName") or ""
        orphan_scripts = []
        empty_refs: list[str] = []
        packdata_icon = []
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                tt = obj.read_typetree()
            except Exception:
                continue
            pid = (tt.get("m_Script") or {}).get("m_PathID")
            cls = scripts.get(pid)
            if pid not in scripts:
                orphan_scripts.append(f"{key}: 组件 &{obj.path_id} 指向不存在的脚本对象")
                continue
            _walk_required(tt, cls or "", empty_refs)
            if cls == "PackData":
                show = tt.get("ShowIcon")
                icon = tt.get("Icon") or {}
                if show and _is_empty_pptr(icon):
                    packdata_icon.append(f"{key}: {tt.get('m_Name')!r} ShowIcon=1 但 Icon 为空")
        if orphan_scripts:
            issues.append(_issue("orphan_script", "error",
                                 f"{key}: {len(orphan_scripts)} 个组件指向不存在的脚本",
                                 orphan_scripts[:10]))
        if empty_refs:
            issues.append(_issue("empty_required", "warn",
                                 f"{key}: {len(empty_refs)} 个必填引用为空",
                                 sorted(set(empty_refs))[:10]))
        if packdata_icon:
            issues.append(_issue("packdata_icon", "warn",
                                 f"{key}: PackData 图标标志自相矛盾", packdata_icon))

    return {"ok": True, "kind": "pack", "target": str(pack), "issues": issues, "stats": stats}


def inspect_project(root: Path) -> dict:
    """体检一个 Unity 工程（给工程根或 Assets 都行）。"""
    root = Path(root)
    assets = root / "Assets" if (root / "Assets").is_dir() else root
    issues: list[dict] = []
    stats: dict = {"assets": str(assets)}

    known: set[str] = set()
    for meta in assets.rglob("*.meta"):
        try:
            hit = META_GUID.search(meta.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        if hit:
            known.add(hit.group(1))
    stats["guids"] = len(known)
    if not known:
        return {"ok": False, "kind": "project", "target": str(assets),
                "issues": [_issue("no_meta", "error", "没找到任何 .meta，路径可能给错了")],
                "stats": stats}

    dead_scripts: dict[str, list[str]] = defaultdict(list)
    for prefab in assets.rglob("*.prefab"):
        try:
            text = prefab.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for guid in M_SCRIPT.findall(text):
            if guid not in known:
                dead_scripts[guid].append(prefab.name)
    if dead_scripts:
        detail = [f"{g} ×{len(v)}（例：{v[0]}）" for g, v in
                  sorted(dead_scripts.items(), key=lambda x: -len(x[1]))[:10]]
        issues.append(_issue("dead_script", "error",
                             f"{len(dead_scripts)} 种脚本 GUID 指向不存在的脚本", detail))

    dead_assets: dict[str, list[str]] = defaultdict(list)
    for mat in assets.rglob("*.mat"):
        try:
            text = mat.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for guid in GUID_ANY.findall(text):
            if guid not in known and guid not in BUILTIN_GUIDS:
                dead_assets[guid].append(mat.name)
    if dead_assets:
        detail = [f"{g} ×{len(v)}（例：{v[0]}）" for g, v in
                  sorted(dead_assets.items(), key=lambda x: -len(x[1]))[:10]]
        # 材质常引用游戏内置 shader，那类引用在 Toolkit 工程里本来就查不到，只作提示
        issues.append(_issue("dead_asset", "info",
                             f"{len(dead_assets)} 种资产 GUID 在工程里查不到（可能是游戏内置 shader）",
                             detail))

    asm: dict[str, list[str]] = defaultdict(list)
    for dll in assets.rglob("*.dll"):
        # 平台变体目录（Odin 等插件）里的同名 dll 是正常布局
        if any(part.lower() in VARIANT_DIRS for part in dll.parts[:-1]):
            continue
        try:
            import sfs_assembly_rename as rn
            name = rn.read_assembly_name(dll)
        except Exception:
            name = dll.name
        asm[name].append(dll.relative_to(assets).as_posix())
    dup = {k: v for k, v in asm.items() if len(v) > 1}
    if dup:
        issues.append(_issue("dup_assembly", "error",
                             f"{len(dup)} 组同名程序集（Unity 会卸载其中一个）",
                             [f"{k}: {', '.join(v)}" for k, v in dup.items()]))

    return {"ok": True, "kind": "project", "target": str(assets), "issues": issues, "stats": stats}


def fix_safe(target: Path) -> tuple[list[str], list[str]]:
    """只做不会损坏数据的修复，返回（做成的, 没做的原因）。"""
    target = Path(target)
    done: list[str] = []
    skipped: list[str] = []
    if target.is_dir():
        assets = target / "Assets" if (target / "Assets").is_dir() else target
        moved = core._relocate_duplicate_code_assemblies(assets, log=lambda m: None)
        if moved:
            done += [f"同名程序集副本已迁出 Assets：{m}" for m in moved]
        else:
            skipped.append("没有需要迁出的同名程序集副本")
        return done, skipped

    # 包：只修 PackData 的图标标志
    try:
        data = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return done, [f"读不了这个包：{exc}"]
    import UnityPy
    changed = False
    for key in ("WindowsBuild", "AndroidBuild", "MacBuild", "IOS_Build"):
        raw = data.get(key)
        if not isinstance(raw, str) or not raw:
            continue
        env = UnityPy.load(base64.b64decode(raw))
        touched = 0
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                tt = obj.read_typetree()
            except Exception:
                continue
            if tt.get("ShowIcon") and _is_empty_pptr(tt.get("Icon") or {}):
                tt["ShowIcon"] = 0
                obj.save_typetree(tt)
                touched += 1
        if touched:
            data[key] = base64.b64encode(env.file.save(packer="lz4")).decode("ascii")
            changed = True
            done.append(f"{key}: {touched} 个 PackData 的 ShowIcon 改成 0（图标本来就是空的）")
    if changed:
        backup = target.with_suffix(target.suffix + ".bak")
        if not backup.exists():
            shutil.copy2(target, backup)
        target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        done.append(f"已写回 {target}（原文件备份为 {backup.name}）")
    elif not done:
        skipped.append("这个包没有需要安全修复的问题")
    return done, skipped


# --------------------------------------------------------------------------- #
# 摘掉「游戏不认的脚本」：先列清单，由人勾选，再动手
# --------------------------------------------------------------------------- #

# 每个类被摘掉之后会失去什么（给人做决定用）
CONSEQUENCES = {
    "RenderSortingModule": "发光/光晕的渲染层级排序失效：光效可能穿透箭体，或前后遮挡顺序错乱",
    "MathModule": "依赖它的变量运算与条件判断不再执行，相关联动/自动化失效",
    "MultiStepToggleSequenceModule": "多段开关失效，只能停在默认状态（例如分级展开不再逐段推进）",
    "RepeatMoveModule": "循环移动动画失效，部件停在初始位置",
    "FlapModule": "襟翼/翼面开合动画失效",
    "BalloonModule": "气球膨胀/浮力表现失效",
    "GravityRingModule": "重力环效果失效",
    "SurfaceShadingModule": "表面明暗着色失效，外观可能偏平或偏暗",
    "AtmosphericFlameModule": "大气层内的火焰表现失效",
    "ExternalVariableModule": "对外暴露的变量失效，其他部件读不到它",
    "VariableConverterModule": "变量换算失效",
    "DisableOnNoFlow": "断流时自动禁用失效（部件可能一直保持启用）",
    "PartVisualizer": "编辑器里的部件外观可视化失效（不影响飞行）",
    "VariablesDrawer": "变量面板绘制失效（不影响飞行）",
    "PartContextMenu": "部件右键菜单项失效",
}
GENERIC_CONSEQUENCE = ("该组件对应的功能会完全失效；如果它正好是部件核心模块"
                       "（Part / 资源 / 引擎 / 碰撞），这个部件可能放不上或直接坏掉")


def consequence_for(name: str) -> str:
    """给一个类名，返回摘掉它的后果说明。"""
    return CONSEQUENCES.get(name, GENERIC_CONSEQUENCE)


def _script_class_map(env) -> dict[int, str]:
    """bundle 里 MonoScript pathID -> 类名。"""
    out: dict[int, str] = {}
    for obj in env.objects:
        if obj.type.name != "MonoScript":
            continue
        try:
            tt = obj.read_typetree()
        except Exception:
            continue
        out[obj.path_id] = tt.get("m_ClassName") or ""
    return out


def find_unknown_components(target: Path, toolkit_root: str = "") -> list[dict]:
    """列出「游戏里没有的脚本组件」，包和工程都支持。

    包：按类名聚合（类名来自 MonoScript），附带挂载对象名。
    工程：按脚本 GUID 聚合（工程里没有 .cs 时拿不到类名）。
    """
    target = Path(target)
    entries: list[dict] = []
    if target.is_dir():
        assets = target / "Assets" if (target / "Assets").is_dir() else target
        known: set[str] = set()
        for meta in assets.rglob("*.meta"):
            try:
                hit = META_GUID.search(meta.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
            if hit:
                known.add(hit.group(1))
        dead: dict[str, list[str]] = defaultdict(list)
        for prefab in assets.rglob("*.prefab"):
            try:
                text = prefab.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for guid in M_SCRIPT.findall(text):
                if guid not in known:
                    dead[guid].append(prefab.name)
        for guid, files in dead.items():
            entries.append({"key": guid, "label": f"未知脚本 {guid[:8]}…", "kind": "project",
                            "count": len(files), "where": sorted(set(files))})
        return entries

    # 包
    import UnityPy
    try:
        data = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return entries
    native = core.toolkit_script_classes(toolkit_root) if toolkit_root else set()
    if not native:
        # 没有 Toolkit 就没法判断哪些是「游戏不认的」，不猜
        return entries
    try:
        own = core.custom_monoscript_classes(target)
    except Exception:
        own = set()

    agg: dict[str, dict] = {}
    for key in ("WindowsBuild", "AndroidBuild", "MacBuild", "IOS_Build"):
        raw = data.get(key)
        if not isinstance(raw, str) or not raw:
            continue
        try:
            env = UnityPy.load(base64.b64decode(raw))
        except Exception:
            continue
        scripts = _script_class_map(env)
        gos: dict[int, str] = {}
        for obj in env.objects:
            if obj.type.name == "GameObject":
                try:
                    gos[obj.path_id] = obj.read_typetree().get("m_Name") or ""
                except Exception:
                    continue
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                tt = obj.read_typetree()
            except Exception:
                continue
            cls = scripts.get((tt.get("m_Script") or {}).get("m_PathID"))
            if not cls or cls in native or cls in own:
                continue
            slot = agg.setdefault(cls, {"key": cls, "label": cls, "kind": "pack",
                                        "count": 0, "platforms": [], "where": []})
            slot["count"] += 1
            if key not in slot["platforms"]:
                slot["platforms"].append(key)
            name = gos.get((tt.get("m_GameObject") or {}).get("m_PathID"), "")
            if name and len(slot["where"]) < 8:
                slot["where"].append(name)
    entries = list(agg.values())
    entries.sort(key=lambda x: -x["count"])
    return entries


def strip_unknown(target: Path, keys: list[str]) -> tuple[list[str], list[str]]:
    """把选中的脚本组件摘掉。包改 bundle，工程改 prefab 文本；改前备份。"""
    target = Path(target)
    keys = [k for k in keys if k]
    done: list[str] = []
    errors: list[str] = []
    if not keys:
        return done, ["没有勾选任何项"]

    if target.is_dir():
        return _strip_project(target, keys)
    return _strip_pack(target, keys)


def _strip_pack(pack: Path, classes: list[str]) -> tuple[list[str], list[str]]:
    """包里摘组件：断开关联并清空槽位，组件对象留作孤儿。"""
    import UnityPy
    done: list[str] = []
    errors: list[str] = []
    try:
        data = json.loads(pack.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return done, [f"读不了这个包：{exc}"]

    total = 0
    for key in ("WindowsBuild", "AndroidBuild", "MacBuild", "IOS_Build"):
        raw = data.get(key)
        if not isinstance(raw, str) or not raw:
            continue
        try:
            env = UnityPy.load(base64.b64decode(raw))
        except Exception as exc:
            errors.append(f"{key} 解析失败：{exc}")
            continue
        scripts = _script_class_map(env)
        victims: dict[int, int] = {}
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                tt = obj.read_typetree()
            except Exception:
                continue
            cls = scripts.get((tt.get("m_Script") or {}).get("m_PathID"))
            if cls in classes:
                victims[obj.path_id] = (tt.get("m_GameObject") or {}).get("m_PathID")
        if not victims:
            continue
        for obj in env.objects:
            if obj.type.name != "GameObject":
                continue
            try:
                tt = obj.read_typetree()
            except Exception:
                continue
            comps = tt.get("m_Component") or []
            keep = [c for c in comps
                    if (c.get("component") or {}).get("m_PathID") not in victims]
            if len(keep) != len(comps):
                tt["m_Component"] = keep
                obj.save_typetree(tt)
        for pid in victims:
            for obj in env.objects:
                if obj.path_id != pid:
                    continue
                tt = obj.read_typetree()
                tt["m_GameObject"] = {"m_FileID": 0, "m_PathID": 0}
                obj.save_typetree(tt)
                break
        data[key] = base64.b64encode(env.file.save(packer="lz4")).decode("ascii")
        total += len(victims)
        done.append(f"{key}: 摘掉 {len(victims)} 个组件")

    if not total:
        return done, ["这个包里没找到要摘的组件"]
    backup = pack.with_suffix(pack.suffix + ".bak")
    if not backup.exists():
        shutil.copy2(pack, backup)
    pack.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    done.append(f"已写回 {pack}（备份 {backup.name}），共摘 {total} 个")
    return done, errors


def _strip_project(root: Path, guids: list[str]) -> tuple[list[str], list[str]]:
    """工程里摘组件：整段删掉 MonoBehaviour 文档，并清掉 GameObject 里的引用。"""
    assets = root / "Assets" if (root / "Assets").is_dir() else root
    done: list[str] = []
    errors: list[str] = []
    targets = set(guids)
    block = re.compile(r"(?m)^--- !u!114 &(-?\d+)[^\n]*\n")
    touched = 0
    for prefab in assets.rglob("*.prefab"):
        try:
            text = prefab.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        heads = list(block.finditer(text))
        if not heads:
            continue
        kill: set[str] = set()
        for i, m in enumerate(heads):
            start = m.start()
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            seg = text[start:end]
            hit = M_SCRIPT.search(seg)
            if hit and hit.group(1) in targets:
                kill.add(m.group(1))
        if not kill:
            continue
        pieces = []
        cursor = 0
        for i, m in enumerate(heads):
            start = m.start()
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            if m.group(1) in kill:
                pieces.append(text[cursor:start])
                cursor = end
        pieces.append(text[cursor:])
        new_text = "".join(pieces)
        for pid in kill:
            new_text = re.sub(r"(?m)^\s*- component: \{fileID: %s\}\n" % re.escape(pid), "", new_text)
        backup = prefab.with_suffix(".prefab.bak")
        if not backup.exists():
            shutil.copy2(prefab, backup)
        prefab.write_text(new_text, encoding="utf-8")
        touched += 1
        done.append(f"{prefab.name}: 摘掉 {len(kill)} 个组件")
    if not touched:
        errors.append("工程里没找到要摘的组件")
    return done, errors

