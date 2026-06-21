# -*- coding: utf-8 -*-
# [FILE] run_all.py
# [Length] ~280 lines, [Version] v1.0 (phase_b)
# [Purpose] Single entry point for Phase B measurement on user PC (Windows).
#           All logic in Python to avoid BAT encoding/line-ending issues.
#
# Flow:
#   1. Environment check (Python, packages)
#   2. Data file check (../Merged_Data.csv)
#   3. Existing model check + reuse prompt
#   4. Backup model if retrain
#   5. Training (calls train_phase_b.py)
#   6. Unit tests (calls test_v7_phase_a.py)
#   7. Measurement (calls measure_v34_phase_b.py)
#   8. Show output location
#
# CLI options:
#   --auto-yes   : Skip prompts, retrain by default
#   --skip-train : Skip training step
#   --skip-test  : Skip unit test step

import os
import sys
import time
import subprocess
import shutil

# Force UTF-8 stdout (Windows cp949 environment compatibility)
try:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(WORK_DIR, "..", "Merged_Data.csv")
MODEL_PATH = os.path.join(WORK_DIR, "PautoV75_XGB_3class_v2.json")
META_PATH = os.path.join(WORK_DIR, "PautoV75_XGB_3class_v2_meta.json")
OUTPUT_DIR = os.path.join(WORK_DIR, "outputs_stage_1")


def print_header(text):
    line = "=" * 70
    print("\n" + line)
    print("  " + text)
    print(line)


def print_step(num, total, text):
    print("\n[Step " + str(num) + "/" + str(total) + "] " + text)


def ask_yn(question, default_no=True, auto_yes=False):
    if auto_yes:
        print(question + " [auto: N - retrain]")
        return False
    suffix = "(y/N)" if default_no else "(Y/n)"
    try:
        answer = input(question + " " + suffix + ": ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n  No input - using default")
        return not default_no
    if not answer:
        return not default_no
    return answer.startswith('y')


def check_environment():
    print_step(1, 7, "Environment check")
    py_ver = sys.version_info
    print("  Python: " + str(py_ver.major) + "." + str(py_ver.minor) + "." + str(py_ver.micro))
    if py_ver.major < 3 or (py_ver.major == 3 and py_ver.minor < 8):
        print("  X Python 3.8+ required")
        return False
    required = ['pandas', 'numpy', 'xgboost', 'scipy']
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
            print("  OK " + pkg)
        except ImportError:
            print("  X " + pkg + " (not installed)")
            missing.append(pkg)
    if missing:
        print("\n  Install missing packages:")
        print("  pip install " + ' '.join(missing))
        return False
    return True


def check_data():
    print_step(2, 7, "Data file check")
    if not os.path.exists(DATA_PATH):
        print("  X Not found: " + DATA_PATH)
        print("     Expected: " + os.path.abspath(DATA_PATH))
        print("     Place Merged_Data.csv in: D:\\ML\\Verify\\ (parent folder)")
        return False
    size_mb = os.path.getsize(DATA_PATH) / 1024 / 1024
    print("  OK Found: " + DATA_PATH)
    print("     Size: " + ("%.1f" % size_mb) + " MB")
    return True


def handle_model(auto_yes=False, skip_train=False):
    print_step(3, 7, "Model check")
    if skip_train:
        print("  --skip-train flag set, skipping training")
        if os.path.exists(MODEL_PATH):
            print("  OK Existing model will be used: " + MODEL_PATH)
            return 'reuse'
        print("  X No existing model and --skip-train set. Cannot proceed.")
        return 'skip'
    if os.path.exists(MODEL_PATH):
        size_mb = os.path.getsize(MODEL_PATH) / 1024 / 1024
        print("  Existing model found: " + MODEL_PATH)
        print("  Size: " + ("%.2f" % size_mb) + " MB")
        if ask_yn("  Reuse existing model?", default_no=True, auto_yes=auto_yes):
            return 'reuse'
        backup_dir = os.path.join(WORK_DIR, "..", "model_backups")
        os.makedirs(backup_dir, exist_ok=True)
        backup_name = "PautoV75_XGB_3class_v2_backup_" + time.strftime('%Y-%m-%d_%H%M%S') + ".json"
        backup_path = os.path.join(backup_dir, backup_name)
        try:
            shutil.move(MODEL_PATH, backup_path)
            print("  Backed up to: " + backup_path)
            if os.path.exists(META_PATH):
                meta_backup = backup_path.replace('.json', '_meta.json')
                shutil.move(META_PATH, meta_backup)
        except Exception as e:
            print("  ! Backup failed: " + str(e))
        return 'retrain'
    print("  No existing model. Will train.")
    return 'retrain'


def _run_subprocess(script_name, label, expected_min=None):
    script = os.path.join(WORK_DIR, script_name)
    if not os.path.exists(script):
        print("  X " + script_name + " not found: " + script)
        return False, 0
    if expected_min:
        print("  Expected time: " + expected_min)
    t0 = time.time()
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    result = subprocess.run([sys.executable, script], cwd=WORK_DIR, env=env)
    elapsed = time.time() - t0
    if result.returncode != 0:
        print("  X " + label + " failed (return code " + str(result.returncode) + ")")
        return False, elapsed
    return True, elapsed


def run_training():
    print_step(4, 7, "Training (auto 70% IS split)")
    ok, elapsed = _run_subprocess("train_phase_b.py", "Training", "10-20 minutes")
    if not ok:
        return False
    if not os.path.exists(MODEL_PATH):
        print("  X Training completed but model file not created: " + MODEL_PATH)
        return False
    print("  OK Training done in " + ("%.1f" % (elapsed/60)) + " min")
    return True


def run_unit_tests():
    print_step(5, 7, "Unit tests (v8 Stage 1, ~3 min)")
    ok, elapsed = _run_subprocess("test_v8_stage_1.py", "Unit tests")
    if not ok:
        return False
    print("  OK Unit tests done in " + ("%.0f" % elapsed) + "s")
    return True


def run_measurement():
    print_step(6, 7, "Measurement (9 scenarios, expected 2-3 hours)")
    ok, elapsed = _run_subprocess("measure_v34_stage_1.py", "Measurement")
    if not ok:
        return False
    summary_path = os.path.join(OUTPUT_DIR, "all_scenarios_stage_1.csv")
    if not os.path.exists(summary_path):
        print("  X Summary CSV not created: " + summary_path)
        return False
    print("  OK Measurement done in " + ("%.1f" % (elapsed/60)) + " min")
    return True


def show_completion():
    print_step(7, 7, "Completion")
    print("\n  Results location: " + OUTPUT_DIR)
    if os.path.exists(OUTPUT_DIR):
        files = sorted(os.listdir(OUTPUT_DIR))
        print("  Files generated: " + str(len(files)))
        for f in files[:5]:
            full = os.path.join(OUTPUT_DIR, f)
            size_kb = os.path.getsize(full) / 1024
            print("    - " + f + " (" + ("%.1f" % size_kb) + " KB)")
        if len(files) > 5:
            print("    ... and " + str(len(files)-5) + " more")
    print("\n  Next: zip the entire 'outputs_stage_1' folder and upload.")


def main():
    args = sys.argv[1:]
    auto_yes = '--auto-yes' in args
    skip_train = '--skip-train' in args
    skip_test = '--skip-test' in args

    print_header("Rauto V34 Stage 1 - Plan X (fib_trigger ATR × N)")
    print("  Working dir: " + WORK_DIR)
    print("  Grid: 9 scenarios (fib_trigger × SL multi, SL>=fib)")
    print("  Flags: auto_yes=" + str(auto_yes) + ", skip_train=" + str(skip_train) + ", skip_test=" + str(skip_test))

    if not check_environment():
        print("\nX Environment check failed. Aborting.")
        return 1
    if not check_data():
        print("\nX Data file check failed. Aborting.")
        return 1

    model_action = handle_model(auto_yes=auto_yes, skip_train=skip_train)
    if model_action == 'skip':
        return 1

    if model_action == 'retrain':
        if not run_training():
            print("\nX Training failed. Aborting.")
            return 1
    else:
        print_step(4, 7, "Training skipped (reusing model)")

    if not skip_test:
        ok = run_unit_tests()
        if not ok and not auto_yes:
            cont = ask_yn("  Continue despite unit test issues?", default_no=True)
            if not cont:
                print("\nX User aborted after unit test failure.")
                return 1
    else:
        print_step(5, 7, "Unit tests skipped (--skip-test)")

    if not run_measurement():
        print("\nX Measurement failed. Aborting.")
        return 1

    show_completion()
    print_header("All done!")
    return 0


if __name__ == "__main__":
    exit_code = main()
    if exit_code != 0:
        print("\n[Exit code " + str(exit_code) + "]")
    sys.exit(exit_code)
