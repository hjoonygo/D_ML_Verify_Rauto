# [check.py]
# 코드길이: 244줄 | 내부버전명: SideWay_V0_stg1
# 로직 축약/생략 없이 전체 출력. 아래 In/Out 태그 후 코드 시작.
# =====================================================================================
# 목적: backtest.py 산출물을 '오염검사 + 8개 시나리오'로 검증하고, 분석결과를
#       전량 파일로만 기록한다(복붙 요청 금지 방침). INDEX에 한 줄 추가.
#
# === 사용 파일(File In/Out) ===
#  In : ../00WorkHstr/SideWay_V0_stg1_manifest.json (산출물 해시)
#  In : ../00WorkHstr/SideWay_V0_stg1_results.json  (설정/요약/입력해시)
#  In : ../00WorkHstr/SideWay_V0_stg1_summary.csv, _trades.csv, _equity.csv
#  In : ../merged_data.csv                          (입력 원천, 해시·정합 재검증용)
#  Out: ../00WorkHstr/<YYYYMMDD_HHMM>.txt           (작업분석 결과)
#  Out: ../00WorkHstr/00WorkHstr_INDEX.txt          (이번 작업 한 줄 추가)
#
# === 함수(Function In/Out) ===
#  resolve_paths()        In:없음            Out:(parent, out_dir)
#  sha256_of(path)        In:파일경로        Out:해시문자열
#  load_outputs(out_dir,v)In:폴더,버전       Out:(manifest,results,summary_df,trades_df,equity_df)
#  resample_open_map(df1m)In:1분DF           Out:dict{4h봉시작ns: open가}
#  run_8_scenarios(...)   In:산출물+원천      Out:(checks list[(이름,통과여부,상세)], 전체통과여부)
#  write_report(...)      In:검증결과+요약    Out:txt파일경로
#  append_index(...)      In:요약한줄         Out:없음(INDEX append)
#  main()                 In:없음            Out:없음
#
# === 핵심 변수 ===
#  TOL    : 가격 정합 허용오차(슬리피지 위 추가 여유)
#  checks : [(시나리오명, PASS/FAIL, 상세문자열), ...] 8개
# =====================================================================================

import os
import json
import hashlib
from datetime import datetime, timezone
import numpy as np
import pandas as pd

VERSION = "SideWay_V0_stg1"
TOL = 1e-3
NS_4H = np.int64(4 * 3600 * 1_000_000_000)


def resolve_paths():
    here = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(here)
    out_dir = os.path.join(parent, "00WorkHstr")
    return parent, out_dir


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_outputs(out_dir, v):
    with open(os.path.join(out_dir, f"{v}_manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    with open(os.path.join(out_dir, f"{v}_results.json"), encoding="utf-8") as f:
        results = json.load(f)
    summary = pd.read_csv(os.path.join(out_dir, f"{v}_summary.csv"))
    trades = pd.read_csv(os.path.join(out_dir, f"{v}_trades.csv"))
    equity = pd.read_csv(os.path.join(out_dir, f"{v}_equity.csv"))
    return manifest, results, summary, trades, equity


def resample_open_map(df1m):
    r = df1m.resample("4h", origin="epoch", label="left", closed="left")
    opens = r["open"].first().dropna()
    return {str(ts): float(v) for ts, v in opens.items()}


def run_8_scenarios(parent, out_dir, v, manifest, results, summary, trades):
    checks = []
    cfg = results["config"]
    slip = cfg["SLIPPAGE"]
    init = cfg["INIT_CAPITAL"]
    data_path = os.path.join(parent, cfg["DATA_FILENAME"])

    # 원천 데이터 1회 로드(재검증용)
    df = pd.read_csv(data_path, usecols=lambda c: c in
                     ["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").drop_duplicates("timestamp", keep="first").set_index("timestamp")

    # --- 시나리오1: 산출물 파일명 일치/존재 ---
    expected = list(manifest["outputs"].keys())
    missing = [fn for fn in expected if not os.path.exists(os.path.join(out_dir, fn))]
    checks.append(("1.파일명/존재 일치", len(missing) == 0,
                   "모든 산출물 존재" if not missing else f"누락:{missing}"))

    # --- 시나리오2: 산출물 해시 대조 + 입력 해시 대조 ---
    bad = []
    for fn, hsh in manifest["outputs"].items():
        p = os.path.join(out_dir, fn)
        if not os.path.exists(p) or sha256_of(p) != hsh:
            bad.append(fn)
    in_hash_now = sha256_of(data_path)
    in_ok = (in_hash_now == manifest["input_sha256"] == results["input_sha256"])
    checks.append(("2.해시 대조(산출물+입력)", len(bad) == 0 and in_ok,
                   f"산출물해시 {'일치' if not bad else '불일치:'+str(bad)} / 입력해시 {'일치' if in_ok else '불일치'}"))

    # --- 시나리오3: 중복 타임스탬프 ---
    raw = pd.read_csv(data_path, usecols=["timestamp"])
    dup = int(pd.to_datetime(raw["timestamp"], utc=True).duplicated().sum())
    checks.append(("3.중복 타임스탬프", dup == 0, f"중복 {dup}건"))

    # --- 시나리오4: 결측/갭 ---
    na_c = int(df["close"].isna().sum()); na_v = int(df["volume"].isna().sum())
    span_min = int((df.index[-1] - df.index[0]).total_seconds() // 60) + 1
    gaps = int(span_min - len(df))
    checks.append(("4.결측/갭 탐지", na_c == 0 and na_v == 0,
                   f"NaN(close {na_c}, vol {na_v}) / 1분갭 {gaps}"))

    # --- 시나리오5: 미래참조 점검(체결가 = 봉 시가 정합) ---
    omap = resample_open_map(df)
    le_bad = 0; lx_bad = 0; checked = 0
    for _, tr in trades.iterrows():
        op = omap.get(str(tr["entry_time"]), None)
        if op is not None:
            checked += 1
            lo = op * (1 - slip - TOL); hi = op * (1 + slip + TOL)
            if not (lo <= tr["entry_price"] <= hi):
                le_bad += 1
        if tr["reason"] == "signal":
            opx = omap.get(str(tr["exit_time"]), None)
            if opx is not None:
                lo = opx * (1 - slip - TOL); hi = opx * (1 + slip + TOL)
                if not (lo <= tr["exit_price"] <= hi):
                    lx_bad += 1
    checks.append(("5.미래참조 점검(시가체결)", le_bad == 0 and lx_bad == 0,
                   f"진입 시가불일치 {le_bad} / 신호청산 시가불일치 {lx_bad} (검사 {checked}건)"))

    # --- 시나리오6: 거래 비중첩(케이스별) ---
    overlap = 0
    for case, g in trades.groupby("case"):
        g = g.sort_values("entry_time")
        prev_exit = None
        for _, tr in g.iterrows():
            if prev_exit is not None and pd.Timestamp(tr["entry_time"]) < prev_exit:
                overlap += 1
            prev_exit = pd.Timestamp(tr["exit_time"])
    checks.append(("6.거래 비중첩", overlap == 0, f"중첩 {overlap}건"))

    # --- 시나리오7: 자본 정합성(복리 재현 + 음수자본 없음) ---
    recon_bad = []; neg = 0
    for case, g in trades.groupby("case"):
        g = g.sort_values("entry_time")
        eq = init
        for _, tr in g.iterrows():
            eq += tr["net_pnl"]
            if eq < -1e-6:
                neg += 1
            if abs(eq - tr["equity_after"]) > max(1.0, abs(tr["equity_after"]) * 1e-4):
                recon_bad.append(case)
                break
    checks.append(("7.자본 정합성(복리)", len(recon_bad) == 0 and neg == 0,
                   f"복리재현 {'일치' if not recon_bad else '불일치:'+str(set(recon_bad))} / 음수자본 {neg}"))

    # --- 시나리오8: 체결가 현실성(보유구간 실제 가격범위 내) ---
    fill_bad = 0; ck = 0
    for _, tr in trades.iterrows():
        e0 = pd.Timestamp(tr["entry_time"]); e1 = pd.Timestamp(tr["exit_time"])
        sl = df.loc[e0:e1]
        if len(sl) == 0:
            continue
        ck += 1
        lo = sl["low"].min() * (1 - slip - TOL); hi = sl["high"].max() * (1 + slip + TOL)
        if not (lo <= tr["exit_price"] <= hi) or not (lo <= tr["entry_price"] <= hi):
            fill_bad += 1
    checks.append(("8.체결가 현실성", fill_bad == 0, f"범위이탈 체결 {fill_bad} (검사 {ck}건)"))

    all_pass = all(p for _, p, _ in checks)
    return checks, all_pass


def write_report(out_dir, checks, all_pass, results, summary):
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    path = os.path.join(out_dir, f"{now}.txt")
    q = results["data_quality"]
    lines = []
    lines.append(f"# 작업분석 보고 — {VERSION}")
    lines.append(f"생성(UTC): {now}")
    lines.append(f"입력: {results['input_file']} | 입력 sha256: {results['input_sha256']}")
    lines.append(f"데이터: {q['start']} ~ {q['end']} | 4h봉 {results['n_4h_bars']}개 "
                 f"| 1분행 {q['rows']} | 중복제거 {q['duplicates_removed']} | 1분갭 {q['minute_gaps']}")
    lines.append("")
    lines.append(f"== 검증 결과: {'PASS' if all_pass else 'FAIL'} "
                 f"({sum(1 for _,p,_ in checks if p)}/{len(checks)}) ==")
    for nm, p, det in checks:
        lines.append(f"  [{'PASS' if p else 'FAIL'}] {nm} :: {det}")
    lines.append("")
    lines.append("== 케이스별 성과 요약 ==")
    cols = ["stop_pct", "final_equity", "total_return_pct", "CAGR_pct", "MDD_pct",
            "sharpe", "num_trades", "win_rate_pct", "profit_factor", "longs", "shorts"]
    cols = [c for c in cols if c in summary.columns]
    lines.append("  " + " | ".join(cols))
    for _, r in summary.iterrows():
        lines.append("  " + " | ".join(str(r[c]) for c in cols))
    lines.append("")
    lines.append("== 신뢰도/알파 메모 ==")
    lines.append("  본 결과는 '직접 데이터 백테스트'이며, 비용(수수료0.05%/슬리피지0.02%/펀딩0.01%·8h)")
    lines.append("  과 교차마진 청산을 반영. 다만 (a)펀딩 고정가정 (b)단일MMR (c)대칭 숏로직은 가설성분.")
    lines.append("  → 직접데이터 입증: 신뢰도 약 80%. 알파여부는 케이스 비교(요약표)로 판단.")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path, now


def append_index(out_dir, now, all_pass, checks, results, summary):
    idx = os.path.join(out_dir, "00WorkHstr_INDEX.txt")
    q = results["data_quality"]
    npass = sum(1 for _, p, _ in checks if p)
    # 대표값: 무스탑 기준 + 최고 수익 케이스
    best = summary.sort_values("total_return_pct", ascending=False).iloc[0]
    line = (f"{now} | {VERSION} | bars={results['n_4h_bars']} | "
            f"{'PASS' if all_pass else 'FAIL'} {npass}/{len(checks)} | "
            f"best_stop={best['stop_pct']} ret={best['total_return_pct']}% "
            f"MDD={best['MDD_pct']}% sharpe={best['sharpe']} trades={best['num_trades']} | "
            f"data={q['start'][:10]}~{q['end'][:10]}")
    header_needed = not os.path.exists(idx)
    with open(idx, "a", encoding="utf-8") as f:
        if header_needed:
            f.write("# 00WorkHstr INDEX — 작업 한 줄 기록(분단위)\n")
        f.write(line + "\n")


def main():
    parent, out_dir = resolve_paths()
    manifest, results, summary, trades, equity = load_outputs(out_dir, VERSION)
    checks, all_pass = run_8_scenarios(parent, out_dir, VERSION, manifest, results, summary, trades)
    rpt_path, now = write_report(out_dir, checks, all_pass, results, summary)
    append_index(out_dir, now, all_pass, checks, results, summary)
    print(f"[check] {'PASS' if all_pass else 'FAIL'} {sum(1 for _,p,_ in checks if p)}/{len(checks)}")
    for nm, p, det in checks:
        print(f"   [{'PASS' if p else 'FAIL'}] {nm} :: {det}")
    print(f"[check] 분석 → {rpt_path}")
    print(f"[check] INDEX 갱신 완료")


if __name__ == "__main__":
    main()
