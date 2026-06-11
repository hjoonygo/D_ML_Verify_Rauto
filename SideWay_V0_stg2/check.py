# [check.py]
# 코드길이: 215줄 | 내부버전명: SideWay_V0_stg2
# 로직 축약/생략 없이 전체 출력. 아래 In/Out 태그 후 코드 시작.
# =====================================================================================
# 목적(stg2): backtest.py 산출물을 8개 시나리오로 검증하고 전량 파일로만 기록.
#       변경점: 결과파일/분석txt는 '실행 하위폴더'에서 읽고/쓰며, INDEX(누적기록)만
#       ../00WorkHstr 에 추가한다. 시나리오8은 1분배열 searchsorted로 가속(60셀 대응).
#
# === 파일 In/Out ===
#  In : ./SideWay_V0_stg2_manifest.json / _results.json / _summary.csv / _trades.csv
#  In : ../merged_data.csv
#  Out: ./<YYYYMMDD_HHMM>.txt              (분석, 실행 하위폴더)
#  Out: ../00WorkHstr/00WorkHstr_INDEX.txt (한 줄 누적)
#
# === 함수 In/Out ===
#  resolve_paths()  In:없음 Out:(parent, out_dir(=스크립트폴더), index_dir(=../00WorkHstr))
#  sha256_of(path)  In:경로 Out:해시
#  load_outputs(out_dir,v)  In:폴더,버전 Out:(manifest,results,summary_df,trades_df)
#  resample_open_map(df1m)  In:1분DF Out:{시각문자열: open가}
#  run_8_scenarios(...)     In:산출물+원천 Out:(checks,all_pass)
#  write_report / append_index / main
# === 핵심 변수 ===
#  TOL : 가격정합 허용오차(슬리피지 위 추가여유)
#  checks : [(시나리오명, PASS/FAIL, 상세)] 8개
# =====================================================================================

import os
import json
import hashlib
from datetime import datetime, timezone
import numpy as np
import pandas as pd

VERSION = "SideWay_V0_stg2"
TOL = 1e-3


def resolve_paths():
    here = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(here)
    index_dir = os.path.join(parent, "00WorkHstr")
    os.makedirs(index_dir, exist_ok=True)
    return parent, here, index_dir


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
    return manifest, results, summary, trades


def resample_open_map(df1m):
    opens = df1m.resample("4h", origin="epoch", label="left", closed="left")["open"].first().dropna()
    return {str(ts): float(v) for ts, v in opens.items()}


def run_8_scenarios(parent, out_dir, v, manifest, results, summary, trades):
    checks = []
    cfg = results["config"]; slip = cfg["SLIPPAGE"]; init = cfg["INIT_CAPITAL"]
    data_path = os.path.join(parent, cfg["DATA_FILENAME"])
    df = pd.read_csv(data_path, usecols=lambda c: c in ["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").drop_duplicates("timestamp", keep="first").set_index("timestamp")
    m_time_ns = df.index.values.astype("datetime64[ns]").astype("int64")
    m_low = df["low"].to_numpy("float64"); m_high = df["high"].to_numpy("float64")

    # 1: 파일명/존재
    expected = list(manifest["outputs"].keys())
    missing = [fn for fn in expected if not os.path.exists(os.path.join(out_dir, fn))]
    checks.append(("1.파일명/존재 일치", len(missing) == 0, "모든 산출물 존재" if not missing else f"누락:{missing}"))

    # 2: 해시 대조(산출물+입력)
    bad = [fn for fn, hsh in manifest["outputs"].items()
           if (not os.path.exists(os.path.join(out_dir, fn))) or sha256_of(os.path.join(out_dir, fn)) != hsh]
    in_ok = (sha256_of(data_path) == manifest["input_sha256"] == results["input_sha256"])
    checks.append(("2.해시 대조(산출물+입력)", len(bad) == 0 and in_ok,
                   f"산출물 {'일치' if not bad else '불일치:'+str(bad)} / 입력 {'일치' if in_ok else '불일치'}"))

    # 3: 중복 타임스탬프
    raw = pd.read_csv(data_path, usecols=["timestamp"])
    dup = int(pd.to_datetime(raw["timestamp"], utc=True).duplicated().sum())
    checks.append(("3.중복 타임스탬프", dup == 0, f"중복 {dup}건"))

    # 4: 결측/갭
    na_c = int(df["close"].isna().sum()); na_v = int(df["volume"].isna().sum())
    span_min = int((df.index[-1] - df.index[0]).total_seconds() // 60) + 1
    gaps = int(span_min - len(df))
    checks.append(("4.결측/갭 탐지", na_c == 0 and na_v == 0, f"NaN(close {na_c}, vol {na_v}) / 1분갭 {gaps}"))

    # 5: 미래참조 점검(체결가=봉 시가 정합)
    omap = resample_open_map(df)
    e_bad = x_bad = checked = 0
    for _, tr in trades.iterrows():
        op = omap.get(str(tr["entry_time"]))
        if op is not None:
            checked += 1
            if not (op * (1 - slip - TOL) <= tr["entry_price"] <= op * (1 + slip + TOL)):
                e_bad += 1
        if tr["reason"] == "signal":
            ox = omap.get(str(tr["exit_time"]))
            if ox is not None and not (ox * (1 - slip - TOL) <= tr["exit_price"] <= ox * (1 + slip + TOL)):
                x_bad += 1
    checks.append(("5.미래참조 점검(시가체결)", e_bad == 0 and x_bad == 0,
                   f"진입 불일치 {e_bad} / 신호청산 불일치 {x_bad} (검사 {checked}건)"))

    # 6: 거래 비중첩(셀별)
    overlap = 0
    for case, g in trades.groupby("case"):
        g = g.sort_values("entry_time"); prev = None
        for _, tr in g.iterrows():
            if prev is not None and pd.Timestamp(tr["entry_time"]) < prev:
                overlap += 1
            prev = pd.Timestamp(tr["exit_time"])
    checks.append(("6.거래 비중첩", overlap == 0, f"중첩 {overlap}건"))

    # 7: 자본 정합성(복리 재현 + 음수자본)
    recon_bad = set(); neg = 0
    for case, g in trades.groupby("case"):
        g = g.sort_values("entry_time"); eq = init
        for _, tr in g.iterrows():
            eq += tr["net_pnl"]
            if eq < -1e-6:
                neg += 1
            if abs(eq - tr["equity_after"]) > max(1.0, abs(tr["equity_after"]) * 1e-4):
                recon_bad.add(case); break
    checks.append(("7.자본 정합성(복리)", len(recon_bad) == 0 and neg == 0,
                   f"복리재현 {'일치' if not recon_bad else '불일치:'+str(recon_bad)} / 음수자본 {neg}"))

    # 8: 체결가 현실성(보유구간 실제 범위 내) — searchsorted 가속
    fill_bad = ck = 0
    for _, tr in trades.iterrows():
        e0 = int(pd.Timestamp(tr["entry_time"]).value); e1 = int(pd.Timestamp(tr["exit_time"]).value)
        s = np.searchsorted(m_time_ns, e0, "left"); e = np.searchsorted(m_time_ns, e1, "right")
        if e <= s:
            continue
        ck += 1
        lo = m_low[s:e].min() * (1 - slip - TOL); hi = m_high[s:e].max() * (1 + slip + TOL)
        if not (lo <= tr["exit_price"] <= hi) or not (lo <= tr["entry_price"] <= hi):
            fill_bad += 1
    checks.append(("8.체결가 현실성", fill_bad == 0, f"범위이탈 체결 {fill_bad} (검사 {ck}건)"))

    return checks, all(p for _, p, _ in checks)


def write_report(out_dir, checks, all_pass, results, summary):
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    q = results["data_quality"]
    lines = [f"# 작업분석 보고 — {VERSION}", f"생성(UTC): {now}",
             f"입력: {results['input_file']} | sha256: {results['input_sha256']}",
             f"데이터: {q['start']} ~ {q['end']} | 4h봉 {results['n_4h_bars']} | 1분행 {q['rows']}",
             "",
             f"== 검증: {'PASS' if all_pass else 'FAIL'} ({sum(1 for _,p,_ in checks if p)}/{len(checks)}) =="]
    for nm, p, det in checks:
        lines.append(f"  [{'PASS' if p else 'FAIL'}] {nm} :: {det}")
    lines.append("")
    lines.append("== 셀별 성과(수익률 내림차순 상위 15) ==")
    cols = ["mode", "stop_pct", "total_return_pct", "CAGR_pct", "MDD_pct", "sharpe",
            "num_trades", "win_rate_pct", "long_pnl", "short_pnl"]
    cols = [c for c in cols if c in summary.columns]
    top = summary.sort_values("total_return_pct", ascending=False).head(15)
    lines.append("  " + " | ".join(cols))
    for _, r in top.iterrows():
        lines.append("  " + " | ".join(str(r[c]) for c in cols))
    lines.append("")
    lines.append("== 신뢰도/알파 메모 ==")
    lines.append("  직접데이터 백테스트(비용·교차마진 반영). 레짐필터(ADX<25,EMA200)는 4h 자체계산.")
    lines.append("  롱/숏 분리손익으로 'fade 숏을 하락레짐에서만 켜면 사는가'를 판정. 신뢰도 ~80%.")
    path = os.path.join(out_dir, f"{now}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path, now


def append_index(index_dir, now, all_pass, checks, results, summary):
    idx = os.path.join(index_dir, "00WorkHstr_INDEX.txt")
    q = results["data_quality"]; npass = sum(1 for _, p, _ in checks if p)
    best = summary.sort_values("total_return_pct", ascending=False).iloc[0]
    line = (f"{now} | {VERSION} | bars={results['n_4h_bars']} | {'PASS' if all_pass else 'FAIL'} {npass}/{len(checks)} | "
            f"best={best['mode']}/{best['stop_pct']} ret={best['total_return_pct']}% MDD={best['MDD_pct']}% "
            f"sharpe={best['sharpe']} trades={best['num_trades']} L/S={best['long_pnl']}/{best['short_pnl']} | "
            f"data={q['start'][:10]}~{q['end'][:10]}")
    new = not os.path.exists(idx)
    with open(idx, "a", encoding="utf-8") as f:
        if new:
            f.write("# 00WorkHstr INDEX — 작업 한 줄 기록(분단위)\n")
        f.write(line + "\n")


def main():
    parent, out_dir, index_dir = resolve_paths()
    manifest, results, summary, trades = load_outputs(out_dir, VERSION)
    checks, all_pass = run_8_scenarios(parent, out_dir, VERSION, manifest, results, summary, trades)
    rpt, now = write_report(out_dir, checks, all_pass, results, summary)
    append_index(index_dir, now, all_pass, checks, results, summary)
    print(f"[check] {'PASS' if all_pass else 'FAIL'} {sum(1 for _,p,_ in checks if p)}/{len(checks)}")
    for nm, p, det in checks:
        print(f"   [{'PASS' if p else 'FAIL'}] {nm} :: {det}")
    print(f"[check] 분석 → {rpt}")
    print(f"[check] INDEX → {os.path.join(index_dir, '00WorkHstr_INDEX.txt')}")


if __name__ == "__main__":
    main()
