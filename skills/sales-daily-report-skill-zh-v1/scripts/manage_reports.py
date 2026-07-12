#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import argparse
import shutil
from datetime import datetime

# Base directory for storing daily reports and config
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "日报管理"))
TEMP_DIR = os.path.join(BASE_DIR, "temp")
ARCHIVE_DIR = os.path.join(BASE_DIR, "归档")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
SUMMARY_FILE_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "日报汇总.md"))

# Default de-identified configuration template (GitHub safe)
DEFAULT_CONFIG = {
    "name_color": "#1a73e8",
    "output_format": "both",
    "reporters": [
        {
            "key": "Sales_A",
            "fullname": "Alice（销售A）",
            "aliases": ["alice", "销售a", "销售A"],
            "status": "active"
        },
        {
            "key": "Sales_B",
            "fullname": "Bob（销售B）",
            "aliases": ["bob", "销售b", "销售B"],
            "status": "active"
        }
    ]
}

def ensure_dirs():
    os.makedirs(TEMP_DIR, exist_ok=True)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

def load_config():
    ensure_dirs()
    if not os.path.exists(CONFIG_PATH):
        # Save default safe config
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading config.json: {e}", file=sys.stderr)
        return DEFAULT_CONFIG

def save_config(config_data):
    ensure_dirs()
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving config.json: {e}", file=sys.stderr)
        return False

def find_reporter_by_name(config, name_str):
    if not name_str:
        return None, None
    name_lower = name_str.lower().strip()
    reporters = config.get("reporters", [])
    for rep in reporters:
        if rep.get("status") == "inactive":
            continue
        key = rep.get("key")
        fullname = rep.get("fullname")
        aliases = rep.get("aliases", [])
        if key.lower() == name_lower:
            return key, fullname
        for alias in aliases:
            if alias.lower() in name_lower or name_lower in alias.lower():
                return key, fullname
    return None, None

def detect_reporter_from_text(config, text):
    if not text:
        return None, None
    lines = text.split("\n")
    search_scope = "\n".join(lines[:10]).lower()
    
    reporters = config.get("reporters", [])
    
    # Try exact match in search scope first
    for rep in reporters:
        if rep.get("status") == "inactive":
            continue
        key = rep.get("key")
        fullname = rep.get("fullname")
        aliases = rep.get("aliases", [])
        for alias in aliases:
            if alias.lower() in search_scope:
                return key, fullname
                
    # Search the whole text
    search_scope_all = text.lower()
    for rep in reporters:
        if rep.get("status") == "inactive":
            continue
        key = rep.get("key")
        fullname = rep.get("fullname")
        aliases = rep.get("aliases", [])
        for alias in aliases:
            if alias.lower() in search_scope_all:
                return key, fullname
                
    return None, None

def get_status(config):
    ensure_dirs()
    submitted = []
    missing = []
    leaves = []
    
    reporters = config.get("reporters", [])
    active_count = 0
    
    for rep in reporters:
        status = rep.get("status", "active")
        if status == "inactive":
            continue
            
        key = rep.get("key")
        fullname = rep.get("fullname")
        
        if status == "leave":
            leaves.append(fullname)
            # If they are on leave, they don't count as active reporters for daily reporting
            continue
            
        active_count += 1
        file_path = os.path.join(TEMP_DIR, f"temp_{key}.txt")
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            submitted.append(fullname)
        else:
            missing.append(fullname)
            
    return {
        "submitted": submitted,
        "missing": missing,
        "leaves": leaves,
        "all_submitted": len(missing) == 0,
        "total_submitted": len(submitted),
        "total_active_members": active_count,
        "total_leaves": len(leaves)
    }

def save_report(config, content, name=None):
    ensure_dirs()
    key, fullname = None, None
    
    if name:
        key, fullname = find_reporter_by_name(config, name)
        
    if not key:
        key, fullname = detect_reporter_from_text(config, content)
        
    if not key:
        return {
            "success": False,
            "error": "Could not identify reporter. Please specify the reporter's name explicitly using --name."
        }
        
    file_path = os.path.join(TEMP_DIR, f"temp_{key}.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content.strip())
        
    status = get_status(config)
    return {
        "success": True,
        "reporter_key": key,
        "reporter_fullname": fullname,
        "saved_path": file_path,
        "status": status
    }

def get_all_reports(config):
    ensure_dirs()
    combined_reports = []
    reporters = config.get("reporters", [])
    
    for rep in reporters:
        status = rep.get("status", "active")
        if status == "inactive":
            continue
            
        key = rep.get("key")
        fullname = rep.get("fullname")
        
        file_path = os.path.join(TEMP_DIR, f"temp_{key}.txt")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            combined_reports.append({
                "key": key,
                "fullname": fullname,
                "content": content
            })
        elif status == "leave":
            combined_reports.append({
                "key": key,
                "fullname": fullname,
                "content": "【请假】"
            })
        else:
            combined_reports.append({
                "key": key,
                "fullname": fullname,
                "content": "【未提交日报】"
            })
            
    return combined_reports

def append_to_summary_file(content):
    date_str = datetime.now().strftime("%Y-%m-%d")
    header = f"## 销售日报汇总 ({date_str})\n\n"
    new_entry = f"{header}{content.strip()}\n\n---\n\n"
    
    old_content = ""
    if os.path.exists(SUMMARY_FILE_PATH):
        try:
            with open(SUMMARY_FILE_PATH, "r", encoding="utf-8") as f:
                old_content = f.read()
        except Exception as e:
            print(f"Error reading existing summary file: {e}", file=sys.stderr)
            
    # Prepend new entry
    try:
        with open(SUMMARY_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(new_entry + old_content)
        return True
    except Exception as e:
        print(f"Error writing summary file: {e}", file=sys.stderr)
        return False

def archive_reports(config, date_str=None, summary_content=None):
    ensure_dirs()
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        
    target_archive_dir = os.path.join(ARCHIVE_DIR, date_str)
    os.makedirs(target_archive_dir, exist_ok=True)
    
    reporters = config.get("reporters", [])
    archived_files = []
    
    for rep in reporters:
        if rep.get("status") == "inactive":
            continue
        key = rep.get("key")
        src_path = os.path.join(TEMP_DIR, f"temp_{key}.txt")
        if os.path.exists(src_path):
            dest_path = os.path.join(target_archive_dir, f"{key}.txt")
            shutil.move(src_path, dest_path)
            archived_files.append(dest_path)
            
    # Append to summary file if content provided
    summary_written = False
    if summary_content:
        summary_written = append_to_summary_file(summary_content)
        
    # Clear any residual temporary files in temp directory
    clear_all(config)
    
    return {
        "success": True,
        "archive_directory": target_archive_dir,
        "archived_files_count": len(archived_files),
        "summary_written": summary_written,
        "summary_file_path": SUMMARY_FILE_PATH if summary_written else None
    }

def clear_all(config):
    ensure_dirs()
    cleared = []
    reporters = config.get("reporters", [])
    for rep in reporters:
        key = rep.get("key")
        file_path = os.path.join(TEMP_DIR, f"temp_{key}.txt")
        if os.path.exists(file_path):
            os.remove(file_path)
            cleared.append(key)
            
    # Also clean up any loose temp_*.txt files in TEMP_DIR
    try:
        for f in os.listdir(TEMP_DIR):
            if f.startswith("temp_") and f.endswith(".txt"):
                os.remove(os.path.join(TEMP_DIR, f))
    except Exception:
        pass
        
    return {
        "success": True,
        "cleared_reporters": cleared
    }

def check_environment():
    status = {
        "python_version": sys.version,
        "python_ok": sys.version_info >= (3, 6),
        "dir_writable": False,
        "dir_path": BASE_DIR,
        "humanizer_installed": False,
        "humanizer_paths_checked": []
    }
    
    # Check directory writability
    try:
        ensure_dirs()
        test_file = os.path.join(BASE_DIR, "write_test.tmp")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        status["dir_writable"] = True
    except Exception:
        status["dir_writable"] = False
        
    # Check humanizer-zh skill
    possible_paths = [
        os.path.abspath(os.path.join(os.environ.get("USERPROFILE", "C:\\Users\\HiWin11"), ".gemini", "config", "skills", "humanizer-zh")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".agents", "skills", "humanizer-zh"))
    ]
    status["humanizer_paths_checked"] = possible_paths
    for path in possible_paths:
        if os.path.exists(path) and os.path.exists(os.path.join(path, "SKILL.md")):
            status["humanizer_installed"] = True
            break
            
    return status

def add_reporter(config, key, fullname, aliases_str):
    reporters = config.setdefault("reporters", [])
    
    # Check if key already exists
    for rep in reporters:
        if rep.get("key").lower() == key.lower():
            return {"success": False, "error": f"Reporter with key '{key}' already exists."}
            
    # Parse aliases
    aliases = [a.strip() for a in aliases_str.split(",") if a.strip()]
    
    # Create new reporter
    new_rep = {
        "key": key,
        "fullname": fullname,
        "aliases": aliases,
        "status": "active"
    }
    
    reporters.append(new_rep)
    save_config(config)
    return {"success": True, "reporter": new_rep}

def set_reporter_status(config, key, status):
    if status not in ["active", "leave", "inactive"]:
        return {"success": False, "error": f"Invalid status '{status}'. Must be active, leave, or inactive."}
        
    reporters = config.get("reporters", [])
    found = False
    for rep in reporters:
        if rep.get("key").lower() == key.lower():
            rep["status"] = status
            found = True
            break
            
    if not found:
        return {"success": False, "error": f"Reporter with key '{key}' not found."}
        
    save_config(config)
    return {"success": True, "key": key, "new_status": status}

def update_config(config, name_color=None, output_format=None):
    if name_color:
        config["name_color"] = name_color
    if output_format:
        if output_format not in ["both", "copy_only"]:
            return {"success": False, "error": "output_format must be 'both' or 'copy_only'."}
        config["output_format"] = output_format
        
    save_config(config)
    return {"success": True, "name_color": config.get("name_color"), "output_format": config.get("output_format")}

def main():
    parser = argparse.ArgumentParser(description="Sales Daily Report State Manager")
    parser.add_argument("--save", action="store_true", help="Save a report")
    parser.add_argument("--content", type=str, help="Daily report content / or summary content for --archive")
    parser.add_argument("--name", type=str, help="Reporter name (optional with --save)")
    parser.add_argument("--status", action="store_true", help="Get current completeness status")
    parser.add_argument("--get-all", action="store_true", help="Get all submitted reports combined")
    parser.add_argument("--archive", action="store_true", help="Archive current reports and clear temp")
    parser.add_argument("--date", type=str, help="Archive date in YYYY-MM-DD format (optional with --archive)")
    parser.add_argument("--clear", action="store_true", help="Force clear all temporary files")
    
    # New options
    parser.add_argument("--check-env", action="store_true", help="Check running environment and skills")
    parser.add_argument("--init", action="store_true", help="Initialize/reset config file to defaults")
    parser.add_argument("--add-reporter", action="store_true", help="Add a new reporter")
    parser.add_argument("--key", type=str, help="Unique reporter key (required for --add-reporter / --set-status)")
    parser.add_argument("--fullname", type=str, help="Full display name (required for --add-reporter)")
    parser.add_argument("--aliases", type=str, help="Comma-separated aliases (required for --add-reporter)")
    parser.add_argument("--set-status", action="store_true", help="Set reporter status (active, leave, inactive)")
    parser.add_argument("--rep-status", type=str, help="Status value: active, leave, inactive (required for --set-status)")
    parser.add_argument("--config", action="store_true", help="Modify general settings")
    parser.add_argument("--name-color", type=str, help="HEX color code for name highlighting (optional with --config)")
    parser.add_argument("--output-format", type=str, help="output format: both, copy_only (optional with --config)")
    
    args = parser.parse_args()
    
    # Always load config unless initializing to default
    config = load_config()
    
    if args.check_env:
        res = check_environment()
        print(json.dumps(res, ensure_ascii=False, indent=2))
        
    elif args.init:
        # Force default config overwrite
        res = save_config(DEFAULT_CONFIG)
        print(json.dumps({"success": res, "config": DEFAULT_CONFIG}, ensure_ascii=False, indent=2))
        
    elif args.add_reporter:
        if not args.key or not args.fullname or not args.aliases:
            print(json.dumps({"success": False, "error": "--key, --fullname, and --aliases are required to add a reporter"}))
            sys.exit(1)
        res = add_reporter(config, args.key, args.fullname, args.aliases)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        
    elif args.set_status:
        if not args.key or not args.rep_status:
            print(json.dumps({"success": False, "error": "--key and --rep-status are required to set status"}))
            sys.exit(1)
        res = set_reporter_status(config, args.key, args.rep_status)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        
    elif args.config:
        if not args.name_color and not args.output_format:
            print(json.dumps({"success": False, "error": "Provide --name-color or --output-format with --config"}))
            sys.exit(1)
        res = update_config(config, args.name_color, args.output_format)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        
    elif args.save:
        if not args.content:
            print(json.dumps({"success": False, "error": "--content is required when saving"}))
            sys.exit(1)
        res = save_report(config, args.content, args.name)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        
    elif args.status:
        res = get_status(config)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        
    elif args.get_all:
        res = get_all_reports(config)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        
    elif args.archive:
        # --content is optional here, representing the optimized summary markdown to write to '日报汇总.md'
        res = archive_reports(config, args.date, args.content)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        
    elif args.clear:
        res = clear_all(config)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
