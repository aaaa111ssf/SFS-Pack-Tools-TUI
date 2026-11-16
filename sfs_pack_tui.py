#!/usr/bin/env python3
"""SFS Pack Tool 终端版 · 中文。

用法：python sfs_pack_tui.py
英文版：python sfs_pack_tui_en.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import sfs_pack_tui_core as core  # noqa: E402

TEXT = {
    "app_title": "SFS Pack Tool · 终端版",
    "hint": "↑/↓ 移动    Enter 确认    数字/字母直达    Q 退出",
    "status": "AssetRipper：{ripper}",
    "ripper_unset": "未设置（先按 d）",
    "ripper_bad": "目录无效（{path}）",
    "ripper_ready": "{name}",
    "menu_scan": ("扫描包", "平台 / 脚本 / 建议路线"),
    "menu_info": ("包信息", "体积 / 部件数"),
    "menu_extract": ("提取文本", "生成 texts.json"),
    "menu_translate": ("写回汉化", "生成 -CN.pack"),
    "menu_strip": ("剥离平台", "只保留指定平台"),
    "menu_export": ("解包导出", "转 Unity 工程（需 Toolkit）"),
    "menu_dedupe": ("工程去重", "X / X_0 副本"),
    "menu_repair17": ("1.7 引擎修复", "补 heatHitbox 等字段"),
    "menu_check": ("悬空检查", "找缺失 GUID 引用"),
    "menu_repair_dangling": ("悬空修复", "修 Toolkit 悬空引用"),
    "menu_selfcheck": ("Toolkit 自检", "脚本 GUID 是否对得上"),
    "menu_cache": ("缓存管理", "列出 / 清理"),
    "menu_doctor": ("体检", "包或工程：列出能确定的问题"),
    "menu_fix": ("安全修复", "只修不会丢数据的项（先备份）"),
    "menu_strip_scripts": ("摘掉不认的脚本", "先列清单，确认后摘除（先备份）"),
    "p_strip_classes": "要摘的类名（逗号分隔，留空放弃）",
    "q_strip_confirm": "摘掉 {names} ？会先备份 {path}",
    "p_doctor_target": "体检对象（.pack 或工程目录）",
    "q_fix_confirm": "对 {path} 做安全修复？会先备份",
    "menu_settings": ("设置", "AssetRipper 目录"),
    "p_pack": "包路径",
    "p_toolkit": "Toolkit 目录",
    "p_toolkit_opt": "Toolkit 目录（可空）",
    "p_toolkit_required": "Toolkit 目录（必填：解包要落到哪个 Toolkit）",
    "p_json_out": "输出 JSON",
    "p_orig_pack": "原始包",
    "p_trans_json": "翻译 JSON",
    "p_author": "汉化署名（追加到作者后）",
    "p_out_pack": "输出包",
    "p_platforms": "保留平台（win/mac/android/ios，逗号分隔）",
    "p_export_dir": "解包导出目录",
    "p_install": "同时合并进 Toolkit",
    "p_strip_custom": "剥离自定义脚本组件",
    "p_project": "工程目录（或 Assets）",
    "p_toolkit17": "1.7 Toolkit 目录",
    "p_pkg_opt": "原始 mod 工程目录（可空，提供才能真修）",
    "p_cache_mode": "list=列出 / clean=清理",
    "p_cache_keys": "要清理的 key（如 stage,tmp,ripper）",
    "q_confirm_delete": "确认删除 {keys}？不可恢复",
    "t_using_ripper": "[导出] AssetRipper：{path}",
    "t_toolkit_ok": "[导出] Toolkit：{path}",
    "e_ripper_first": "[导出] 还没设置 AssetRipper 目录。\n         请先到 AssetRipper 的 GitHub Releases 下载并解压，然后按 d 填解压目录。",
    "e_toolkit_bad": "[导出] Toolkit 目录无效：{path}\n         请填包含 Assets 子目录的工程根目录（例如 ...\\156）。",
    "set_current": "当前 AssetRipper 目录：{path}",
    "set_ripper_dir": "AssetRipper 解压目录（含 AssetRipper.GUI.Free.exe）",
    "set_path_bad": "这个目录里没找到 AssetRipper 可执行文件：{path}",
    "set_path_ok": "已设置：{path}\n         版本：{version}",
    "set_need_exe": "         解压后应能看到 AssetRipper.GUI.Free.exe，直接填那一层的目录。",
    "e_cli_build": "[!] 这个目录里是 {name}（命令行版），它不带网页界面，本工具用不了。\n         请下载带 GUI 的那个压缩包（AssetRipper_win_x64.zip）。",
    "set_unchanged": "没有改动",
    "need_value": "[必填] {name}，请重新输入（Ctrl+C 返回菜单）",
    "cancel": "[取消]",
    "error": "[错误] {error}",
    "press_enter": "\n按回车返回菜单…",
    "bye": "再见。",
}


def main() -> int:
    """启动中文界面。"""
    core.configure("zh", TEXT)
    return core.main()


if __name__ == "__main__":
    raise SystemExit(main())
