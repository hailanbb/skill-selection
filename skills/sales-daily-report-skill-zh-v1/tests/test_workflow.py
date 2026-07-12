#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import json
import shutil

# Paths
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(SKILL_DIR, "scripts", "manage_reports.py")

# Real environment paths to backup/restore
REAL_BASE_DIR = os.path.abspath(os.path.join(SKILL_DIR, "..", "日报管理"))
REAL_CONFIG_PATH = os.path.join(REAL_BASE_DIR, "config.json")
REAL_SUMMARY_PATH = os.path.abspath(os.path.join(REAL_BASE_DIR, "..", "日报汇总.md"))
REAL_TEMP_DIR = os.path.join(REAL_BASE_DIR, "temp")

# Mock configs and data
MOCK_REPORTS = {
    "Sales_A": "汇报人： Alice（销售A）\n今日工作进展：完成系统升级和调试。",
    "Sales_B": "汇报人： Bob（销售B）\n今日工作进展：拜访新客户，沟通意向。"
}

def run_cmd(args):
    cmd = [sys.executable, SCRIPT_PATH] + args
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env)
    if result.returncode != 0:
        print(f"Error executing command: {' '.join(cmd)}")
        print(f"Stderr: {result.stderr}")
        sys.exit(1)
    return json.loads(result.stdout)

def test_workflow():
    print("--- [START] Starting Daily Report Skill Integration Test ---")
    
    # 1. Back up existing real environment configurations and summaries
    print("[1/8] Backing up real configurations...")
    config_backed_up = False
    summary_backed_up = False
    
    config_bak = REAL_CONFIG_PATH + ".bak_test"
    summary_bak = REAL_SUMMARY_PATH + ".bak_test"
    
    if os.path.exists(REAL_CONFIG_PATH):
        shutil.copy2(REAL_CONFIG_PATH, config_bak)
        config_backed_up = True
        print(f"  Backed up {REAL_CONFIG_PATH} to {config_bak}")
        
    if os.path.exists(REAL_SUMMARY_PATH):
        shutil.copy2(REAL_SUMMARY_PATH, summary_bak)
        summary_backed_up = True
        print(f"  Backed up {REAL_SUMMARY_PATH} to {summary_bak}")
        
    try:
        # 2. Initialize default test configuration
        print("[2/8] Initializing default test configuration...")
        init_res = run_cmd(["--init"])
        assert init_res["success"] is True
        assert len(init_res["config"]["reporters"]) == 2
        print("  Initialization passed. Default reporters: Alice and Bob.")
        
        # 3. Check initial status
        print("[3/8] Checking status on fresh config...")
        status = run_cmd(["--status"])
        assert status["total_submitted"] == 0
        assert status["all_submitted"] is False
        assert status["total_active_members"] == 2
        assert "Alice（销售A）" in status["missing"]
        assert "Bob（销售B）" in status["missing"]
        print("  Initial status passed.")
        
        # 4. Save reports incrementally
        print("[4/8] Simulating report saving...")
        res_a = run_cmd(["--save", "--content", MOCK_REPORTS["Sales_A"]])
        assert res_a["success"] is True
        assert res_a["reporter_key"] == "Sales_A"
        
        status_1 = run_cmd(["--status"])
        assert status_1["total_submitted"] == 1
        assert "Alice（销售A）" in status_1["submitted"]
        assert "Bob（销售B）" in status_1["missing"]
        
        res_b = run_cmd(["--save", "--content", MOCK_REPORTS["Sales_B"]])
        assert res_b["success"] is True
        
        status_all = run_cmd(["--status"])
        assert status_all["all_submitted"] is True
        assert status_all["total_submitted"] == 2
        print("  Incremental report saving and status checking passed.")
        
        # 5. Test adding a reporter and changing status (leave / active)
        print("[5/8] Testing adding a new reporter & modifying status...")
        add_res = run_cmd(["--add-reporter", "--key", "Sales_C", "--fullname", "Charlie（销售C）", "--aliases", "charlie,销售c"])
        assert add_res["success"] is True
        assert add_res["reporter"]["key"] == "Sales_C"
        
        status_after_add = run_cmd(["--status"])
        assert status_after_add["all_submitted"] is False
        assert status_after_add["total_active_members"] == 3
        assert "Charlie（销售C）" in status_after_add["missing"]
        
        # Set Sales_C on leave
        leave_res = run_cmd(["--set-status", "--key", "Sales_C", "--rep-status", "leave"])
        assert leave_res["success"] is True
        
        status_after_leave = run_cmd(["--status"])
        assert status_after_leave["all_submitted"] is True # Since Sales_C is on leave, 2/2 submitted
        assert status_after_leave["total_active_members"] == 2
        assert "Charlie（销售C）" in status_after_leave["leaves"]
        print("  Adding reporter and changing status to 'leave' passed.")
        
        # 6. Test reports collection content and ordering
        print("[6/8] Checking combined reports formatting & 'leave' placeholder...")
        all_reports = run_cmd(["--get-all"])
        assert len(all_reports) == 3 # Alice, Bob, Charlie
        assert all_reports[0]["key"] == "Sales_A"
        assert all_reports[1]["key"] == "Sales_B"
        assert all_reports[2]["key"] == "Sales_C"
        assert all_reports[2]["content"] == "【请假】"
        print("  Combined reports validation passed.")
        
        # 7. Modify configuration parameters (name-color, output-format)
        print("[7/8] Modifying config parameters...")
        conf_res = run_cmd(["--config", "--name-color", "#ff5722", "--output-format", "copy_only"])
        assert conf_res["success"] is True
        assert conf_res["name_color"] == "#ff5722"
        assert conf_res["output_format"] == "copy_only"
        print("  Config modification passed.")
        
        # 8. Test archiving, summary appending, and file clearing
        print("[8/8] Testing archive summary appending & temp folder cleanup...")
        test_summary_content = "## 测试日报预览版\n\n- 测试内容1\n- 测试内容2"
        
        # Clean up any summary file from previous failed runs if any
        if os.path.exists(REAL_SUMMARY_PATH):
            os.remove(REAL_SUMMARY_PATH)
            
        archive_res = run_cmd(["--archive", "--content", test_summary_content, "--date", "2026-07-12"])
        assert archive_res["success"] is True
        assert archive_res["summary_written"] is True
        
        # Check if the summary file was created and contains the test summary
        assert os.path.exists(REAL_SUMMARY_PATH)
        with open(REAL_SUMMARY_PATH, "r", encoding="utf-8") as f:
            written_summary = f.read()
        assert "测试日报预览版" in written_summary
        
        # Check if temp folder is empty
        temp_files = [f for f in os.listdir(REAL_TEMP_DIR) if f.startswith("temp_") and f.endswith(".txt")]
        assert len(temp_files) == 0, f"Temp files remained: {temp_files}"
        print("  Archive summary appending and temp directory cleanup passed.")
        
        print("--- [SUCCESS] All Integration Tests Passed Successfully! ---")
        
    finally:
        # Restore real configurations and summaries
        print("Cleaning up test artifacts and restoring backups...")
        
        # Remove temporary test summary
        if os.path.exists(REAL_SUMMARY_PATH):
            os.remove(REAL_SUMMARY_PATH)
            
        # Clean test archives created during testing
        test_archive_dir = os.path.join(REAL_BASE_DIR, "归档", "2026-07-12")
        if os.path.exists(test_archive_dir):
            shutil.rmtree(test_archive_dir)
            
        # Restore config
        if os.path.exists(REAL_CONFIG_PATH):
            os.remove(REAL_CONFIG_PATH)
        if config_backed_up:
            shutil.move(config_bak, REAL_CONFIG_PATH)
            print(f"  Restored {REAL_CONFIG_PATH} from backup.")
            
        # Restore summary
        if summary_backed_up:
            shutil.move(summary_bak, REAL_SUMMARY_PATH)
            print(f"  Restored {REAL_SUMMARY_PATH} from backup.")

if __name__ == "__main__":
    test_workflow()
