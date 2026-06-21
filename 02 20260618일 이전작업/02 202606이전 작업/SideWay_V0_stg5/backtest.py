# [backtest.py]
# 코드길이: 303줄 | 내부버전명: SideWay_V0_stg5
# 로직 축약/생략 없이 전체 출력. 아래 In/Out 태그 후 코드 시작.
# =====================================================================================
# 목적(stg5): 빈도의 진짜 손잡이를 찾는다. 베이스(롱전용·스탑6%·ADX없음) 위에서
#       격자 스윕: 타임프레임 TF(4~12h) × 진입임계 dropRate(1.0~0.5) × 사이즈(1.0,2.5).
#       - dropRate를 낮추면 더 얕은 눌림에도 진입 → 거래수↑ (단 신호 질 저하 위험).
#       - TF는 4h가 stg4 최적이었으나 더 긴 봉(6/8/12h 등)에서 빈도·엣지가 더 좋은지 확인.
#       - 사이즈 1.0배(순효과)와 확정 2.5배를 함께 보여 최종 후보 산출.
#       - 각 셀: 거래수·CAGR·MDD·샤프·승률·PF·비용드래그·상승/하락 레짐손익.
#       - 결정=닫힌 TF봉, 체결=다음 TF봉 시가, 스탑/청산=봉 내부 1분봉 정밀(미래참조 차단).
#       ※ 주의: 5/7/9/10/11h는 바이낸스 native 캔들 아님(연구용). 실거래는 4/6/8/12h 권장.
#       ※ 출력: 결과/분석txt는 실행 하위폴더, INDEX만 ../00WorkHstr.
#       ※ equity.csv는 파일 비대화 방지 위해 사이즈 1.0배 곡선만 저장(2.5배는 동형·스케일).
#
# === 파일 In/Out ===
#  In : ../merged_data.csv
#  Out: ./SideWay_V0_stg5_summary.csv(108행) / _trades.csv / _equity.csv(1.0배만) / _results.json / _manifest.json
#
# === 함수 In/Out ===
#  resolve_paths / load_minute_data / sha256_of
#  resample_tf(df1m, tf_str)            Out:TF봉 DF
#  compute_signals(bars, drop_rate)     In:TF봉, 임계  Out:(le, lx) 롱 진입/청산 bool배열
#  compute_ema(close, period)           Out:ema(레짐 라벨)
#  build_minute_index(df1m,bars,ns_tf)  Out:(m_open,m_high,m_low,m_index,s_idx,e_idx)
#  liq_price / liq_dist_pct / scan_minute_stop / count_funding_crossings
#  simulate(bars,le,lx,frac,stop,cfg,mIdx,ema)  Out:(trades,mtm)
#  compute_metrics(trades,mtm,bars,cfg,tf_h,drop,frac,ppy)  Out:지표 dict
#  main
#
# === 핵심 변수 ===
#  TF_HOURS_LIST=(4..12) / DROPRATES=(1.0..0.5) / SIZES=(1.0,2.5)
#  case 라벨 = tf{h}h_dr{dr}_x{frac}
# =====================================================================================

import os
import json
import hashlib
import numpy as np
import pandas as pd

CFG = {
    "VERSION":        "SideWay_V0_stg5",
    "DATA_FILENAME":  "merged_data.csv",
    "INDEX_DIRNAME":  "00WorkHstr",
    "MA_PERIOD":      6,
    "INIT_CAPITAL":   10000.0,
    "MMR":            0.004,
    "FEE_RATE":       0.0005,
    "SLIPPAGE":       0.0002,
    "FUNDING_RATE":   0.0001,
    "FUNDING_HOURS":  (0, 8, 16),
    "STOP_PCT":       0.06,
    "TREND_EMA_HOURS": 800,                                   # 레짐 EMA 실시간 기준(TF별 봉수 환산)
    "TF_HOURS_LIST":  (4, 5, 6, 7, 8, 9, 10, 11, 12),         # 4h~12h
    "DROPRATES":      (1.0, 0.9, 0.8, 0.7, 0.6, 0.5),
    "SIZES":          (1.0, 2.5),
    "NATIVE_TFS":     (4, 6, 8, 12),                          # 바이낸스 native(실거래 권장)
}


def resolve_paths():
    here = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(here)
    data_path = os.path.join(parent, CFG["DATA_FILENAME"])
    index_dir = os.path.join(parent, CFG["INDEX_DIRNAME"])
    os.makedirs(index_dir, exist_ok=True)
    return data_path, here, index_dir


def load_minute_data(path):
    cols = ["timestamp", "open", "high", "low", "close", "volume"]
    df = pd.read_csv(path, usecols=lambda c: c in cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp")
    dup = int(df["timestamp"].duplicated().sum())
    df = df.drop_duplicates(subset="timestamp", keep="first").set_index("timestamp")
    span_min = int((df.index[-1] - df.index[0]).total_seconds() // 60) + 1
    quality = {"rows": int(len(df)), "duplicates_removed": dup, "minute_gaps": int(span_min - len(df)),
               "nan_close": int(df["close"].isna().sum()), "nan_volume": int(df["volume"].isna().sum()),
               "start": str(df.index[0]), "end": str(df.index[-1])}
    return df, quality


def resample_tf(df1m, tf):
    r = df1m.resample(tf, origin="epoch", label="left", closed="left")
    return pd.DataFrame({"open": r["open"].first(), "high": r["high"].max(), "low": r["low"].min(),
                         "close": r["close"].last(), "volume": r["volume"].sum(min_count=1)}
                        ).dropna(subset=["close"]).copy()


def compute_signals(bars, drop_rate):
    close = bars["close"].to_numpy("float64"); vol = bars["volume"].to_numpy("float64")
    roc = np.empty(len(close)); roc[:] = np.nan
    roc[1:] = (close[1:] - close[:-1]) / close[1:] * 100.0
    cma = pd.Series(roc).rolling(CFG["MA_PERIOD"]).mean().to_numpy()
    cma_prev = np.roll(cma, 1); cma_prev[0] = np.nan
    vol_prev = np.roll(vol, 1); vol_prev[0] = np.nan
    long_entry = (cma > cma_prev) & (cma_prev < -drop_rate) & (vol_prev < vol)
    long_exit = (cma > 0) & (vol_prev > vol)
    le = np.where(np.isnan(cma), False, long_entry)
    lx = np.where(np.isnan(cma), False, long_exit)
    return le, lx


def compute_ema(close, period):
    return pd.Series(close).ewm(span=period, adjust=False).mean().to_numpy()


def build_minute_index(df1m, bars, ns_tf):
    m_time_ns = df1m.index.values.astype("datetime64[ns]").astype("int64")
    m_open = df1m["open"].to_numpy("float64"); m_high = df1m["high"].to_numpy("float64")
    m_low = df1m["low"].to_numpy("float64"); m_index = df1m.index
    bar_start_ns = bars.index.values.astype("datetime64[ns]").astype("int64")
    s_idx = np.searchsorted(m_time_ns, bar_start_ns, side="left")
    e_idx = np.searchsorted(m_time_ns, bar_start_ns + int(ns_tf), side="left")
    return m_open, m_high, m_low, m_index, s_idx, e_idx


def liq_price(side, entry, frac, mmr):
    EoverN = 1.0 / frac
    return entry * (1.0 + mmr - EoverN) if side == "long" else entry * (1.0 - mmr + EoverN)


def liq_dist_pct(frac, mmr):
    return (1.0 / frac - mmr) * 100.0


def scan_minute_stop(m_open, m_high, m_low, s, e, side, stop_price, liq_p, slip):
    if side == "long":
        for j in range(s, e):
            lo = m_low[j]
            if liq_p is not None and lo <= liq_p:
                ref = min(liq_p, m_open[j]); return j, ref * (1.0 - slip), "liquidation"
            if stop_price is not None and lo <= stop_price:
                ref = min(stop_price, m_open[j]); return j, ref * (1.0 - slip), "stop"
    return None


def count_funding_crossings(start, end, funding_hours):
    if end <= start:
        return 0
    cnt = 0; day = start.normalize(); last = end.normalize() + pd.Timedelta(days=1)
    while day <= last:
        for h in funding_hours:
            ft = day + pd.Timedelta(hours=int(h))
            if start < ft <= end:
                cnt += 1
        day += pd.Timedelta(days=1)
    return cnt


def simulate(bars, le, lx, frac, stop_pct, cfg, mIdx, ema):
    m_open, m_high, m_low, m_index, s_idx, e_idx = mIdx
    o = bars["open"].to_numpy("float64"); c = bars["close"].to_numpy("float64")
    t = bars.index; lo_arr = bars["low"].to_numpy("float64"); n = len(bars)
    fee = cfg["FEE_RATE"]; slip = cfg["SLIPPAGE"]; mmr = cfg["MMR"]
    fr = cfg["FUNDING_RATE"]; fh = cfg["FUNDING_HOURS"]

    equity = cfg["INIT_CAPITAL"]; pos = None
    entry_exec = qty = notional = stop_price = 0.0; liq_p = None; entry_t = None; entry_regime = "up"
    trades = []; mtm = np.empty(n, dtype="float64")

    def open_trade(ref_open, bar_i, regime):
        nonlocal equity, pos, entry_exec, entry_t, qty, notional, stop_price, liq_p, entry_regime
        ex = ref_open * (1.0 + slip); notional = frac * equity; qty = notional / ex
        entry_fee = notional * fee; equity -= entry_fee
        stop_price = ex * (1.0 - stop_pct); liq_p = liq_price("long", ex, frac, mmr)
        if liq_p <= 0:
            liq_p = None
        pos = "long"; entry_exec = ex; entry_t = t[bar_i]; entry_regime = regime
        return entry_fee

    def close_trade(exit_exec, exit_ts, reason, entry_fee):
        nonlocal equity, pos
        gross = qty * (exit_exec - entry_exec); exit_fee = qty * exit_exec * fee
        funding_cost = count_funding_crossings(entry_t, exit_ts, fh) * (notional * fr)
        equity += gross - exit_fee - funding_cost
        if equity < 0:
            equity = 0.0
        trades.append({"side": "long", "reason": reason, "regime": entry_regime,
                       "entry_time": str(entry_t), "exit_time": str(exit_ts),
                       "entry_price": round(entry_exec, 4), "exit_price": round(exit_exec, 4),
                       "qty": round(qty, 8), "notional": round(notional, 2), "gross_pnl": round(gross, 4),
                       "entry_fee": round(entry_fee, 4), "exit_fee": round(exit_fee, 4),
                       "funding": round(funding_cost, 4),
                       "net_pnl": round(gross - exit_fee - funding_cost - entry_fee, 4),
                       "equity_after": round(equity, 4)})
        pos = None

    pending_fee = 0.0
    for i in range(n):
        if pos is not None and i >= 1 and lx[i-1]:
            close_trade(o[i] * (1.0 - slip), t[i], "signal", pending_fee)
        if pos is None and i >= 1 and le[i-1]:
            regime = "up" if (not np.isnan(ema[i-1]) and c[i-1] > ema[i-1]) else "down"
            pending_fee = open_trade(o[i], i, regime)
        if pos is not None:
            if (stop_price is not None and lo_arr[i] <= stop_price) or (liq_p is not None and lo_arr[i] <= liq_p):
                hit = scan_minute_stop(m_open, m_high, m_low, s_idx[i], e_idx[i], "long", stop_price, liq_p, slip)
                if hit is not None:
                    j, exec_px, reason = hit
                    close_trade(exec_px, m_index[j], reason, pending_fee)
        mtm[i] = equity if pos is None else equity + qty * (c[i] - entry_exec)
    return trades, mtm


def compute_metrics(trades, mtm, bars, cfg, tf_h, drop, frac, ppy):
    init = cfg["INIT_CAPITAL"]; final = float(mtm[-1]) if len(mtm) else init
    span_days = (bars.index[-1] - bars.index[0]).total_seconds() / 86400.0
    yrs = span_days / 365.25 if span_days > 0 else np.nan
    cagr = (final / init) ** (1.0 / yrs) - 1.0 if (yrs and yrs > 0 and final > 0) else np.nan
    peak = np.maximum.accumulate(mtm); dd = (mtm - peak) / peak
    mdd = float(dd.min()) if len(dd) else 0.0
    rets = np.diff(mtm) / mtm[:-1] if len(mtm) > 1 else np.array([0.0])
    rets = rets[np.isfinite(rets)]
    sharpe = (rets.mean() / rets.std() * np.sqrt(ppy)) if rets.std() > 0 else 0.0
    nt = len(trades); wins = [x for x in trades if x["net_pnl"] > 0]
    gw = sum(x["net_pnl"] for x in wins); gl = -sum(x["net_pnl"] for x in trades if x["net_pnl"] <= 0)
    total_cost = sum(x["entry_fee"] + x["exit_fee"] + x["funding"] for x in trades)
    total_gross = sum(x["gross_pnl"] for x in trades)
    dn = [x for x in trades if x["regime"] == "down"]; up = [x for x in trades if x["regime"] == "up"]
    return {
        "tf_h": tf_h, "drop_rate": drop, "frac": frac, "native": (tf_h in cfg["NATIVE_TFS"]),
        "final_equity": round(final, 2), "total_return_pct": round((final / init - 1) * 100, 2),
        "CAGR_pct": (None if np.isnan(cagr) else round(cagr * 100, 2)), "MDD_pct": round(mdd * 100, 2),
        "sharpe": round(float(sharpe), 3), "num_trades": nt,
        "win_rate_pct": (round(len(wins) / nt * 100, 2) if nt else 0.0),
        "profit_factor": (round(gw / gl, 3) if gl > 0 else None),
        "cost_drag_pct": (round(total_cost / total_gross * 100, 1) if total_gross > 0 else None),
        "liq_dist_pct": round(liq_dist_pct(frac, cfg["MMR"]), 1),
        "regime_up_pnl": round(sum(x["net_pnl"] for x in up), 2),
        "regime_down_pnl": round(sum(x["net_pnl"] for x in dn), 2),
    }


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    data_path, out_dir, index_dir = resolve_paths()
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"입력파일 없음: {data_path}")
    df1m, quality = load_minute_data(data_path)
    input_hash = sha256_of(data_path)

    all_trades = []; summaries = []; eq_rows = []; nbars = {}
    for hrs in CFG["TF_HOURS_LIST"]:
        tf = f"{hrs}h"
        bars = resample_tf(df1m, tf); nbars[tf] = int(len(bars))
        ema = compute_ema(bars["close"].to_numpy("float64"), int(round(CFG["TREND_EMA_HOURS"] / hrs)))
        ns_tf = np.int64(hrs * 3600 * 1_000_000_000)
        mIdx = build_minute_index(df1m, bars, ns_tf)
        ppy = 365.25 * 24 / hrs
        bar_times = [str(x) for x in bars.index]
        for dr in CFG["DROPRATES"]:
            le, lx = compute_signals(bars, dr)
            for frac in CFG["SIZES"]:
                trades, mtm = simulate(bars, le, lx, frac, CFG["STOP_PCT"], CFG, mIdx, ema)
                metrics = compute_metrics(trades, mtm, bars, CFG, hrs, dr, frac, ppy)
                case = f"tf{hrs}h_dr{dr}_x{frac}"
                for tr in trades:
                    tr2 = dict(tr); tr2["case"] = case; tr2["tf_h"] = hrs; all_trades.append(tr2)
                summaries.append(metrics)
                if frac == 1.0:  # equity는 1.0배 곡선만 저장(2.5배는 동형·스케일)
                    for ts, val in zip(bar_times, mtm):
                        eq_rows.append({"case": case, "time": ts, "equity": round(float(val), 4)})

    v = CFG["VERSION"]
    pd.DataFrame(summaries).to_csv(os.path.join(out_dir, f"{v}_summary.csv"), index=False, encoding="utf-8-sig")
    tr_cols = ["case", "tf_h", "side", "reason", "regime", "entry_time", "exit_time", "entry_price", "exit_price",
               "qty", "notional", "gross_pnl", "entry_fee", "exit_fee", "funding", "net_pnl", "equity_after"]
    pd.DataFrame(all_trades, columns=tr_cols).to_csv(os.path.join(out_dir, f"{v}_trades.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame(eq_rows).to_csv(os.path.join(out_dir, f"{v}_equity.csv"), index=False, encoding="utf-8-sig")
    results = {"version": v, "config": CFG, "data_quality": quality, "input_file": CFG["DATA_FILENAME"],
               "input_sha256": input_hash, "n_bars_by_tf": nbars, "summaries": summaries}
    with open(os.path.join(out_dir, f"{v}_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    out_files = [f"{v}_summary.csv", f"{v}_trades.csv", f"{v}_equity.csv", f"{v}_results.json"]
    manifest = {"version": v, "input_file": CFG["DATA_FILENAME"], "input_sha256": input_hash,
                "outputs": {fn: sha256_of(os.path.join(out_dir, fn)) for fn in out_files},
                "data_quality": quality, "out_dir": out_dir, "index_dir": index_dir}
    with open(os.path.join(out_dir, f"{v}_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, default=str)

    print(f"[{v}] {quality['start']} ~ {quality['end']} | 롱전용·스탑6% | {len(summaries)}셀 (TF{len(CFG['TF_HOURS_LIST'])}×dr{len(CFG['DROPRATES'])}×size{len(CFG['SIZES'])})")
    # 사이즈 1.0배 기준, 수익 상위 8셀
    top = sorted([m for m in summaries if m["frac"] == 1.0], key=lambda m: m["total_return_pct"], reverse=True)[:8]
    print("  [상위 8셀 @사이즈1.0배]")
    for m in top:
        nat = "native" if m["native"] else "합성"
        print(f"   TF{m['tf_h']:>2}h dr{m['drop_rate']} ({nat}) | 거래 {m['num_trades']:>3} | 수익 {m['total_return_pct']:>7}% "
              f"| CAGR {m['CAGR_pct']}% | MDD {m['MDD_pct']:>6}% | 샤프 {m['sharpe']:>5} | 승률 {m['win_rate_pct']}% | 비용드래그 {m['cost_drag_pct']}%")
    print(f"  결과파일 → {out_dir}")


if __name__ == "__main__":
    main()
