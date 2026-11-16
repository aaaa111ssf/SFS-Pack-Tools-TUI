#!/usr/bin/env python3
"""SFS Pack Tool Terminal · English.

Usage: python sfs_pack_tui_en.py
Chinese: python sfs_pack_tui.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import sfs_pack_tui_core as core  # noqa: E402

TEXT = {
    "app_title": "SFS Pack Tool · Terminal",
    "hint": "↑/↓ move    Enter select    1-9/a-d jump    Q quit",
    "status": "AssetRipper: {ripper}",
    "ripper_unset": "not set (press d)",
    "ripper_bad": "invalid folder ({path})",
    "ripper_ready": "{name}",
    "menu_scan": ("Scan pack", "platforms / scripts / route"),
    "menu_info": ("Pack info", "size / part count"),
    "menu_extract": ("Extract texts", "writes texts.json"),
    "menu_translate": ("Write translation", "produces -CN.pack"),
    "menu_strip": ("Strip platforms", "keep selected platforms only"),
    "menu_export": ("Unpack / export", "Unity project (needs Toolkit)"),
    "menu_dedupe": ("Dedupe project", "X / X_0 duplicates"),
    "menu_repair17": ("1.7 engine repair", "adds heatHitbox etc."),
    "menu_check": ("Dangling check", "find missing GUID refs"),
    "menu_repair_dangling": ("Dangling repair", "fix Toolkit refs"),
    "menu_selfcheck": ("Toolkit self-check", "script GUIDs resolvable"),
    "menu_cache": ("Cache manager", "list / clean"),
    "menu_doctor": ("Inspect", "pack or project: list detectable issues"),
    "menu_fix": ("Safe repair", "only non-destructive fixes (backs up)"),
    "p_doctor_target": "Target (.pack or project folder)",
    "q_fix_confirm": "Safe-repair {path}? The original will be backed up.",
    "menu_settings": ("Settings", "AssetRipper folder"),
    "p_pack": "Pack path",
    "p_toolkit": "Toolkit dir",
    "p_toolkit_opt": "Toolkit dir (optional)",
    "p_toolkit_required": "Toolkit dir (required: where the export goes)",
    "p_json_out": "Output JSON",
    "p_orig_pack": "Source pack",
    "p_trans_json": "Translation JSON",
    "p_author": "Translation credit (appended to author)",
    "p_out_pack": "Output pack",
    "p_platforms": "Keep platforms (win/mac/android/ios, comma separated)",
    "p_export_dir": "Export output dir",
    "p_install": "Also merge into Toolkit",
    "p_strip_custom": "Strip custom-script components",
    "p_project": "Project dir (or Assets)",
    "p_toolkit17": "1.7 Toolkit dir",
    "p_pkg_opt": "Source mod project (optional, needed to really fix)",
    "p_cache_mode": "list / clean",
    "p_cache_keys": "Keys to clean (e.g. stage,tmp,ripper)",
    "q_confirm_delete": "Delete {keys}? This cannot be undone",
    "t_using_ripper": "[export] AssetRipper: {path}",
    "t_toolkit_ok": "[export] Toolkit: {path}",
    "e_ripper_first": "[export] AssetRipper folder is not set yet.\n         Download it from AssetRipper GitHub Releases, unzip, then press d and point to that folder.",
    "e_toolkit_bad": "[export] Invalid Toolkit dir: {path}\n         Point to the project root that contains an Assets folder (e.g. ...\\156).",
    "set_current": "Current AssetRipper folder: {path}",
    "set_ripper_dir": "AssetRipper folder (contains AssetRipper.GUI.Free.exe)",
    "set_path_bad": "No AssetRipper executable found in: {path}",
    "set_path_ok": "Saved: {path}\n         version: {version}",
    "set_need_exe": "         After unzipping you should see AssetRipper.GUI.Free.exe; pick that folder.",
    "e_cli_build": "[!] That folder contains {name} (the CLI build), which has no web UI and cannot be used here.\n         Please download the GUI archive (AssetRipper_win_x64.zip).",
    "set_unchanged": "Nothing changed",
    "need_value": "[required] {name}; please type it again (Ctrl+C to go back)",
    "cancel": "[cancelled]",
    "error": "[error] {error}",
    "press_enter": "\nPress Enter to return to the menu...",
    "bye": "Bye.",
}


def main() -> int:
    """Start the English UI."""
    core.configure("en", TEXT)
    return core.main()


if __name__ == "__main__":
    raise SystemExit(main())
