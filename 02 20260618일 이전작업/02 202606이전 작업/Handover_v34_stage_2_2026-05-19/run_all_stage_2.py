# -*- coding: utf-8 -*-
"""
[파일명] run_all_stage_2.py
[코드길이] 약 280줄
[목적] Stage 2 측정 일괄 실행 — 사용자 PC entry point

[흐름]
  1. 환경 검사 (Python, packages)
  2. 데이터 파일 검사 (../Merged_Data.csv)
  3. 기존 모델 검사 + 재사용 prompt
  4. 모델 backup (재학습 시)
  5. 학습 (--skip-train 가능)
  6. 단위 테스트 (test_v9_stage_2.py)
  7. 측정 (measure_v34_stage_2.py)
  8. 결과 안내

[CLI options]
  --auto-yes   : prompt 스킵, 재학습 기본
  --skip-train : 학습 단계 스킵
  --skip-test  : 단위 테스트 스킵
"""
import os
import sys
import time
import subprocess
import shutil

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
OUTPUT_DIR = os.path.join(WORK_DIR, "outputs_stage_2")


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
        print("     Place Merged_Data.csv in parent folder.")
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
        if ask_yn("  Reuse existing model? (Stage 2 uses same model as Stage 1)",
                  default_no=False, auto_yes=auto_yes):
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
        print("  X Training completed but model file not created")
        return False
    print("  OK Training done in " + ("%.1f" % (elapsed/60)) + " min")
    return True


def run_unit_tests():
    print_step(5, 7, "Unit tests (v9 Stage 2, ~30 sec)")
    ok, elapsed = _run_subprocess("test_v9_stage_2.py", "Unit tests")
    if not ok:
        return False
    print("  OK Unit tests done in " + ("%.0f" % elapsed) + "s")
    return True


def run_measurement():
    print_step(6, 7, "Measurement (4 scenarios — OB TF grid, expected 1-3 hours)")
    ok, elapsed = _run_subprocess("measure_v34_stage_2.py", "Measurement")
    if not ok:
        return False
    summary_path = os.path.join(OUTPUT_DIR, "all_scenarios_stage_2.csv")
    if not os.path.exists(summary_path):
        print("  X Summary CSV not created")
        return False
    print("  OK Measurement done in " + ("%.1f" % (elapsed/60)) + " min")
    return True


def show_completion():
    print_step(7, 7, "Completion")
    print("\n  Results location: " + OUTPUT_DIR)
    if os.path.exists(OUTPUT_DIR):
        files = sorted(os.listdir(OUTPUT_DIR))
        print("  Files generated: " + str(len(files)))
        for f in files[:10]:
            full = os.path.join(OUTPUT_DIR, f)
            size_kb = os.path.getsize(full) / 1024
            print("    - " + f + " (" + ("%.1f" % size_kb) + " KB)")
        if len(files) > 10:
            print("    ... and " + str(len(files)-10) + " more")
    print("\n  Next: zip the entire 'outputs_stage_2' folder and upload.")


def main():
    args = sys.argv[1:]
    auto_yes = '--auto-yes' in args
    skip_train = '--skip-train' in args
    skip_test = '--skip-test' in args

    print_header("Rauto V34 Stage 2 - New Rules + OB TF Grid")
    print("  Working dir: " + WORK_DIR)
    print("  Grid: 4 scenarios (OB TF 15m / 30m / 60m / 240m)")
    print("  Rules: TP-less trailing system, 3-step Fibonacci, 4H timeout, 2H wait entry")
    print("  Flags: auto_yes=" + str(auto_yes) + ", skip_train=" + str(skip_train) + ", skip_test=" + str(skip_test))

    if not check_environment():
        print("\nX Environment check failed.")
        return 1
    if not check_data():
        print("\nX Data file check failed.")
        return 1

    model_action = handle_model(auto_yes=auto_yes, skip_train=skip_train)
    if model_action == 'skip':
        return 1

    if model_action == 'retrain':
        if not run_training():
            print("\nX Training failed.")
            return 1
    else:
        print_step(4, 7, "Training skipped (reusing model)")

    if not skip_test:
        ok = run_unit_tests()
        if not ok and not auto_yes:
            cont = ask_yn("  Continue despite unit test failure?", default_no=True)
            if not cont:
                return 1
    else:
        print_step(5, 7, "Unit tests skipped (--skip-test)")

    if not run_measurement():
        print("\nX Measurement failed.")
        return 1

    show_completion()
    print_header("All done!")
    return 0


if __name__ == "__main__":
    exit_code = main()
    if exit_code != 0:
        print("\n[Exit code " + str(exit_code) + "]")
    sys.exit(exit_code)
