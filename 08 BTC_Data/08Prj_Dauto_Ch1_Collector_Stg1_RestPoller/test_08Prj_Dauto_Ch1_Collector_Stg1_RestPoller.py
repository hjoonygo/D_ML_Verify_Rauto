# -*- coding: utf-8 -*-
# [파일명] test_08Prj_Dauto_Ch1_Collector_Stg1_RestPoller.py
# 코드길이: 약 150줄 | PASS 기준(캡틴 확정) 실측 — ★사전 컨테이너 검증 불가(실시간 API)이므로
#                     이 PC 실측이 곧 사전실행이다.
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   dauto_collector.py 를 실제로 돌려 캡틴 PASS 기준을 숫자로 검증한다.
#   ① PHASE_A: 수집기 서브프로세스 30분 구동 → 구동창 안의 live 행수 = 30±1, 필수필드 결측 0
#   ② PHASE_B: 프로세스 강제종료 → 3분 구멍 만들기 → 재시작 → 구멍 자동백필 확인
#   ③ 결과를 test_result.txt 로 저장(check.py가 읽음). 전량 파일 보고.
#   시간 단축 디버그용: 환경변수 DAUTO_TEST_A_MIN(기본30)/DAUTO_TEST_GAP_MIN(기본3).
# [함수 In->Out]
#   rows_between(a_ms,b_ms)  ms구간 -> 그 구간 봉시작 행 list(dict)
#   wait_minutes(n)          n분 -> 진행표시하며 대기
#   main()                   PHASE_A/B 실행 -> test_result.txt (PASS n/4)
# ==============================================================================
import os, sys, csv, time, subprocess, datetime as dt

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = r"C:\BinanceData"
SYMBOL = "BTCUSDT"
A_MIN = int(os.environ.get("DAUTO_TEST_A_MIN", "30"))
GAP_MIN = int(os.environ.get("DAUTO_TEST_GAP_MIN", "3"))
B_WAIT_SEC = 150 + 60 * 2          # 재시작 후 백필+라이브 2분 확인 여유
REQUIRED_LIVE = ["ts_utc", "open", "high", "low", "close", "volume", "taker_buy_volume",
                 "open_interest", "mark_price", "index_price", "funding_rate_8h",
                 "next_funding_time", "oi_src"]
MIN_MS = 60_000


def now_min_ms():
    return int(time.time() * 1000) // MIN_MS * MIN_MS


def rows_between(a_ms, b_ms):
    out = []
    if not os.path.isdir(ROOT):
        return out
    for f in sorted(os.listdir(ROOT)):
        if not (f.startswith(f"{SYMBOL}_1m_") and f.endswith(".csv")):
            continue
        with open(os.path.join(ROOT, f), "r", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                ts = int(dt.datetime.strptime(row["ts_utc"], "%Y-%m-%d %H:%M:%S")
                         .replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
                if a_ms <= ts <= b_ms:
                    out.append(row)
    return out


def start_collector():
    return subprocess.Popen([sys.executable, os.path.join(HERE, "dauto_collector.py")],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_minutes(n, label):
    for i in range(n):
        time.sleep(60)
        print(f"  [{label}] {i + 1}/{n}분 경과", flush=True)


def main():
    results = []
    print(f"[TEST] PHASE_A={A_MIN}분 구동 / GAP={GAP_MIN}분 — PC 실측 = 사전실행")

    # ── PHASE_A: 30분 구동 ──
    proc = start_collector()
    t0 = now_min_ms() + MIN_MS          # 다음 분부터 측정(부분 분 제외)
    wait_minutes(A_MIN, "PHASE_A")
    t1 = now_min_ms() - MIN_MS          # 마지막 확정 분까지
    time.sleep(10)                       # :05 폴링 여유
    expected = (t1 - t0) // MIN_MS + 1
    rows_a = [r for r in rows_between(t0, t1) if r.get("oi_src") == "live"]
    ok_count = abs(len(rows_a) - expected) <= 1
    results.append(("A1_30분행수", ok_count, f"live {len(rows_a)}행 / 기대 {expected}±1"))
    missing = sum(1 for r in rows_a for c in REQUIRED_LIVE if not str(r.get(c, "")).strip())
    results.append(("A2_결측0", missing == 0, f"live행 결측 {missing}건"))

    # ── PHASE_B: 강제종료 → 구멍 → 재시작 백필 ──
    proc.kill(); proc.wait()
    print("[TEST] 수집기 강제종료(kill) — 구멍 생성 중")
    gap_a = now_min_ms() + MIN_MS
    wait_minutes(GAP_MIN, "GAP")
    gap_b = now_min_ms() - MIN_MS
    proc = start_collector()
    print(f"[TEST] 재시작 — 백필 대기 {B_WAIT_SEC}s")
    time.sleep(B_WAIT_SEC)
    rows_g = rows_between(gap_a, gap_b)
    n_gap_exp = (gap_b - gap_a) // MIN_MS + 1
    ok_fill = len(rows_g) >= n_gap_exp
    srcs = sorted(set(r.get("oi_src", "") for r in rows_g))
    results.append(("B1_구멍백필", ok_fill, f"구멍 {n_gap_exp}분 중 {len(rows_g)}행 복구, oi_src={srcs}"))
    ok_flag = all(r.get("oi_src") in ("hist", "live", "na") for r in rows_g) and len(rows_g) > 0
    results.append(("B2_oi_src플래그", ok_flag, f"플래그 유효성({srcs})"))
    proc.kill(); proc.wait()
    print("[TEST] 수집기 종료(상시구동은 run_collector.bat 사용)")

    # ── 저장 ──
    n_pass = sum(1 for _, ok, _ in results if ok)
    lines = [f"[{('PASS' if ok else 'FAIL')}] {name} | {note}" for name, ok, note in results]
    verdict = f"VERDICT {n_pass}/{len(results)} PASS | A={A_MIN}min GAP={GAP_MIN}min | root={ROOT}"
    out = os.path.join(HERE, "test_result.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(verdict + "\n" + "\n".join(lines) + "\n")
    print(verdict)
    for l in lines:
        print(l)


if __name__ == "__main__":
    main()
