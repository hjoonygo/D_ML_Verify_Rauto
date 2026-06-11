# [backtest.py]
# 코드길이: 307줄 | 내부버전명: SideWay_V0_stg3
# 로직 축약/생략 없이 전체 출력. 아래 In/Out 태그 후 코드 시작.
# =====================================================================================
# 목적(stg3): stg2 분석으로 확정한 'long_only(숏 제거, ADX 제거), 스탑 6%'를 베이스로
#       고정하고, 단 하나의 변수 '명목 배율(NOTIONAL_FRAC)'만 0.5~2.5로 훑어
#       '수익↑이 사이즈 덕인지 / 안전 한계가 어디인지'를 가린다.(3-B)
#       동시에 각 거래를 진입 시점의 추세 레짐(가격 vs 4h EMA200)으로 태그해
#       '상승레짐 vs 하락레짐'별 롱 손익을 산출한다.(3-A: 상승장 의존성 검증)
#       배율별 강제청산 도달거리(%)도 결과에 박아 안전성을 눈으로 확인하게 한다.
#       ※ EMA200은 '게이트가 아니라 레짐 분류 라벨'로만 쓴다(진입을 막지 않음).
#       ※ 출력: 결과파일/분석txt는 실행 하위폴더, INDEX만 ../00WorkHstr.
#
# === 파일 In/Out ===
#  In : ../merged_data.csv (1분봉 OHLCV)
#  Out: ./SideWay_V0_stg3_summary.csv / _trades.csv / _equity.csv / _results.json / _manifest.json
#       (모두 실행 하위폴더)
#
# === 함수 In/Out ===
#  resolve_paths()  Out:(data_path, out_dir(=스크립트폴더), index_dir(=../00WorkHstr))
#  load_minute_data(path)  Out:(1분DF, 품질dict)
#  resample_4h(df1m)       Out:4h DF
#  compute_signals(bars)   Out:4h DF + 롱 진입/청산 신호(숏 미사용)
#  compute_ema(close,p)    Out:ema np배열(레짐 라벨용)
#  build_minute_index(...) Out:(m_open,m_high,m_low,m_index,s_idx,e_idx)
#  liq_price(side,entry,frac,mmr)  Out:청산가
#  liq_dist_pct(frac,mmr)  Out:롱 청산까지 가격 하락 % (안전성 표기)
#  scan_minute_stop(...)   Out:(j,exec,reason)|None
#  count_funding_crossings(...)  Out:펀딩 횟수
#  simulate(bars,le,lx,frac,stop,cfg,mIdx,ema)  In:신호,명목배율,스탑,설정,분인덱스,ema  Out:(trades,mtm)
#  compute_metrics(...)    Out:지표 dict(+상승/하락 레짐별 손익, 청산거리)
#  sha256_of / main
#
# === 핵심 변수 ===
#  NOTIONAL_FRAC_SWEEP : 0.5/1.0/1.5/2.0/2.5 (명목=배율*자본; 0.5=자본의 50%)
#  regime              : 진입 결정봉(i-1) close>ema200 → 'up', 아니면 'down'
#  equity              : 실현 잔고(복리). 거래 %충격 = frac * 가격수익(롱)
# =====================================================================================

import os
import json
import hashlib
import numpy as np
import pandas as pd

CFG = {
    "VERSION":        "SideWay_V0_stg3",
    "DATA_FILENAME":  "merged_data.csv",
    "INDEX_DIRNAME":  "00WorkHstr",
    "TF":             "4h",
    "MA_PERIOD":      6,
    "DROP_RATE":      1.0,
    "INIT_CAPITAL":   10000.0,
    "LEVERAGE":       5.0,
    "MMR":            0.004,
    "FEE_RATE":       0.0005,
    "SLIPPAGE":       0.0002,
    "FUNDING_RATE":   0.0001,
    "FUNDING_HOURS":  (0, 8, 16),
    "TREND_EMA":      200,        # 레짐 분류 전용(게이트 아님)
    "STOP_PCT":       0.06,       # 고정 6% 재해 백스톱(4%+는 동일·미발동)
    "NOTIONAL_FRAC_SWEEP": (0.5, 1.0, 1.5, 2.0, 2.5),  # 3-B 사이즈 스윕
    "PERIODS_PER_YR": 365.25 * 24 / 4.0,
}

NS_4H = np.int64(4 * 3600 * 1_000_000_000)


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
    quality = {"rows": int(len(df)), "duplicates_removed": dup,
               "minute_gaps": int(span_min - len(df)),
               "nan_close": int(df["close"].isna().sum()), "nan_volume": int(df["volume"].isna().sum()),
               "start": str(df.index[0]), "end": str(df.index[-1])}
    return df, quality


def resample_4h(df1m):
    r = df1m.resample("4h", origin="epoch", label="left", closed="left")
    return pd.DataFrame({"open": r["open"].first(), "high": r["high"].max(), "low": r["low"].min(),
                         "close": r["close"].last(), "volume": r["volume"].sum(min_count=1)}
                        ).dropna(subset=["close"]).copy()


def compute_signals(bars):
    close = bars["close"].to_numpy("float64"); vol = bars["volume"].to_numpy("float64")
    roc = np.empty(len(close)); roc[:] = np.nan
    roc[1:] = (close[1:] - close[:-1]) / close[1:] * 100.0
    cma = pd.Series(roc).rolling(CFG["MA_PERIOD"]).mean().to_numpy()
    dr = CFG["DROP_RATE"]
    cma_prev = np.roll(cma, 1); cma_prev[0] = np.nan
    vol_prev = np.roll(vol, 1); vol_prev[0] = np.nan
    long_entry = (cma > cma_prev) & (cma_prev < -dr) & (vol_prev < vol)   # 롱: 급락 후 반등 초입
    long_exit = (cma > 0) & (vol_prev > vol)
    bars["long_entry"] = np.where(np.isnan(cma), False, long_entry)
    bars["long_exit"] = np.where(np.isnan(cma), False, long_exit)
    return bars


def compute_ema(close, period):
    return pd.Series(close).ewm(span=period, adjust=False).mean().to_numpy()


def build_minute_index(df1m, bars):
    m_time_ns = df1m.index.values.astype("datetime64[ns]").astype("int64")
    m_open = df1m["open"].to_numpy("float64"); m_high = df1m["high"].to_numpy("float64")
    m_low = df1m["low"].to_numpy("float64"); m_index = df1m.index
    bar_start_ns = bars.index.values.astype("datetime64[ns]").astype("int64")
    s_idx = np.searchsorted(m_time_ns, bar_start_ns, side="left")
    e_idx = np.searchsorted(m_time_ns, bar_start_ns + int(NS_4H), side="left")
    return m_open, m_high, m_low, m_index, s_idx, e_idx


def liq_price(side, entry, frac, mmr):
    EoverN = 1.0 / frac
    return entry * (1.0 + mmr - EoverN) if side == "long" else entry * (1.0 - mmr + EoverN)


def liq_dist_pct(frac, mmr):
    # 롱 청산까지 가격 하락 폭(%). 1/frac - mmr. 100% 이상이면 사실상 도달 불가.
    return (1.0 / frac - mmr) * 100.0


def scan_minute_stop(m_open, m_high, m_low, s, e, side, stop_price, liq_p, slip):
    # 롱 전용(숏 미사용)이지만 일반형 유지
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
        ex = ref_open * (1.0 + slip)
        notional = frac * equity; qty = notional / ex
        entry_fee = notional * fee; equity -= entry_fee
        stop_price = ex * (1.0 - stop_pct)
        liq_p = liq_price("long", ex, frac, mmr)
        if liq_p <= 0:
            liq_p = None
        pos = "long"; entry_exec = ex; entry_t = t[bar_i]; entry_regime = regime
        return entry_fee

    def close_trade(exit_exec, exit_ts, reason, entry_fee):
        nonlocal equity, pos
        gross = qty * (exit_exec - entry_exec)
        exit_fee = qty * exit_exec * fee
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
            need = (stop_price is not None and lo_arr[i] <= stop_price) or (liq_p is not None and lo_arr[i] <= liq_p)
            if need:
                hit = scan_minute_stop(m_open, m_high, m_low, s_idx[i], e_idx[i], "long", stop_price, liq_p, slip)
                if hit is not None:
                    j, exec_px, reason = hit
                    close_trade(exec_px, m_index[j], reason, pending_fee)
        mtm[i] = equity if pos is None else equity + qty * (c[i] - entry_exec)
    return trades, mtm


def compute_metrics(trades, mtm, bars, cfg, frac):
    init = cfg["INIT_CAPITAL"]; final = float(mtm[-1]) if len(mtm) else init
    span_days = (bars.index[-1] - bars.index[0]).total_seconds() / 86400.0
    yrs = span_days / 365.25 if span_days > 0 else np.nan
    cagr = (final / init) ** (1.0 / yrs) - 1.0 if (yrs and yrs > 0 and final > 0) else np.nan
    peak = np.maximum.accumulate(mtm); dd = (mtm - peak) / peak
    mdd = float(dd.min()) if len(dd) else 0.0
    rets = np.diff(mtm) / mtm[:-1] if len(mtm) > 1 else np.array([0.0])
    rets = rets[np.isfinite(rets)]
    sharpe = (rets.mean() / rets.std() * np.sqrt(cfg["PERIODS_PER_YR"])) if rets.std() > 0 else 0.0
    nt = len(trades); wins = [x for x in trades if x["net_pnl"] > 0]
    gw = sum(x["net_pnl"] for x in wins); gl = -sum(x["net_pnl"] for x in trades if x["net_pnl"] <= 0)
    up = [x for x in trades if x["regime"] == "up"]; dn = [x for x in trades if x["regime"] == "down"]
    return {
        "frac": frac, "leverage_used": round(frac * 1.0, 2),  # 명목배율(=자본 대비 명목)
        "final_equity": round(final, 2), "total_return_pct": round((final / init - 1) * 100, 2),
        "CAGR_pct": (None if np.isnan(cagr) else round(cagr * 100, 2)),
        "MDD_pct": round(mdd * 100, 2), "sharpe": round(float(sharpe), 3),
        "num_trades": nt, "win_rate_pct": (round(len(wins) / nt * 100, 2) if nt else 0.0),
        "profit_factor": (round(gw / gl, 3) if gl > 0 else None),
        "liq_dist_pct": round(liq_dist_pct(frac, cfg["MMR"]), 1),
        "regime_up_n": len(up), "regime_up_pnl": round(sum(x["net_pnl"] for x in up), 2),
        "regime_down_n": len(dn), "regime_down_pnl": round(sum(x["net_pnl"] for x in dn), 2),
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
    bars = resample_4h(df1m)
    bars = compute_signals(bars)
    ema = compute_ema(bars["close"].to_numpy("float64"), CFG["TREND_EMA"])
    mIdx = build_minute_index(df1m, bars)
    le = bars["long_entry"].to_numpy(); lx = bars["long_exit"].to_numpy()

    all_trades = []; summaries = []; equity_curves = {}
    for frac in CFG["NOTIONAL_FRAC_SWEEP"]:
        trades, mtm = simulate(bars, le, lx, frac, CFG["STOP_PCT"], CFG, mIdx, ema)
        metrics = compute_metrics(trades, mtm, bars, CFG, frac)
        case = f"frac{frac:.1f}"
        for tr in trades:
            tr2 = dict(tr); tr2["case"] = case; all_trades.append(tr2)
        summaries.append(metrics); equity_curves[case] = mtm

    v = CFG["VERSION"]
    pd.DataFrame(summaries).to_csv(os.path.join(out_dir, f"{v}_summary.csv"), index=False, encoding="utf-8-sig")
    tr_cols = ["case", "side", "reason", "regime", "entry_time", "exit_time", "entry_price", "exit_price",
               "qty", "notional", "gross_pnl", "entry_fee", "exit_fee", "funding", "net_pnl", "equity_after"]
    pd.DataFrame(all_trades, columns=tr_cols).to_csv(os.path.join(out_dir, f"{v}_trades.csv"), index=False, encoding="utf-8-sig")
    eq_df = pd.DataFrame({"time": [str(x) for x in bars.index]})
    for case, mtm in equity_curves.items():
        eq_df[case] = np.round(mtm, 4)
    eq_df.to_csv(os.path.join(out_dir, f"{v}_equity.csv"), index=False, encoding="utf-8-sig")
    results = {"version": v, "config": CFG, "data_quality": quality, "input_file": CFG["DATA_FILENAME"],
               "input_sha256": input_hash, "n_4h_bars": int(len(bars)), "summaries": summaries}
    with open(os.path.join(out_dir, f"{v}_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    out_files = [f"{v}_summary.csv", f"{v}_trades.csv", f"{v}_equity.csv", f"{v}_results.json"]
    manifest = {"version": v, "input_file": CFG["DATA_FILENAME"], "input_sha256": input_hash,
                "outputs": {fn: sha256_of(os.path.join(out_dir, fn)) for fn in out_files},
                "n_4h_bars": int(len(bars)), "data_quality": quality, "out_dir": out_dir, "index_dir": index_dir}
    with open(os.path.join(out_dir, f"{v}_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, default=str)

    print(f"[{v}] 4h봉 {len(bars)} | {quality['start']} ~ {quality['end']} | 롱전용 스탑6% | 사이즈 {len(summaries)}종")
    for m in summaries:
        print(f"  명목 {m['frac']:>3}배 | 최종 ${m['final_equity']:>10} | 수익 {m['total_return_pct']:>7}% | CAGR {m['CAGR_pct']}% "
              f"| MDD {m['MDD_pct']:>6}% | 샤프 {m['sharpe']:>5} | 청산거리 {m['liq_dist_pct']}% "
              f"| 레짐 상승 {m['regime_up_n']}건 ${m['regime_up_pnl']} / 하락 {m['regime_down_n']}건 ${m['regime_down_pnl']}")
    print(f"  결과파일 → {out_dir}")


if __name__ == "__main__":
    main()
