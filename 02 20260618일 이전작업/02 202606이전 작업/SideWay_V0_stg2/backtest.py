# [backtest.py]
# 코드길이: 438줄 | 내부버전명: SideWay_V0_stg2
# 로직 축약/생략 없이 전체 출력. 아래 In/Out 태그 후 코드 시작.
# =====================================================================================
# 목적(stg2): stg1(평균회귀 롱+숏, 4h, 교차마진, 1분 정밀스탑)에 '레짐/추세 필터'
#       한 로직을 추가한다. 평균회귀는 횡보장에서만 유효하고 추세장에선 깨진다는
#       원리(ADX/200MA 필터)를 4시간봉에서 직접 계산해 진입 게이트로 씌운다.
#       - 추가지표: ADX(14, Wilder), EMA200 (둘 다 닫힌봉 기준 → 미래참조 없음)
#       - 5개 모드 × 스탑 12종(2~15% + 무스탑) 전수 그리드로 'fade(역추세) 숏을
#         하락레짐에서만 켜면 사는가 / 끄는 게 나은가'를 데이터로 판정.
#       - stg1 대비 변경: 결과파일/분석txt는 '실행 하위폴더'에 저장(사용자 지시),
#         INDEX(사이클 누적기록)만 ../00WorkHstr 에 유지.
#
# === 사용 파일(File In/Out) ===
#  In : ../merged_data.csv   (상위폴더, 1분봉 OHLCV. 추가 컬럼 무시)
#  Out: ./SideWay_V0_stg2_summary.csv   (60셀=5모드x12스탑 핵심지표)
#  Out: ./SideWay_V0_stg2_trades.csv    (전체 거래)
#  Out: ./SideWay_V0_stg2_equity.csv    (셀별 4h MTM 자본곡선)
#  Out: ./SideWay_V0_stg2_results.json  (설정+요약+입력해시)
#  Out: ./SideWay_V0_stg2_manifest.json (산출물 해시, check.py 검증용)
#       ※ 위 5개는 '실행 하위폴더'(이 스크립트 폴더)에 저장된다.
#
# === 함수(Function In/Out) ===
#  resolve_paths()              In:없음   Out:(data_path, out_dir(=스크립트폴더), index_dir(=../00WorkHstr))
#  load_minute_data(path)       In:csv    Out:(1분 DF, 품질 dict)
#  resample_4h(df1m)            In:1분DF  Out:4h DF(OHLCV)
#  compute_signals(bars)        In:4h DF  Out:4h DF + raw 신호열(long_entry/short_entry/long_exit/short_exit)
#  compute_adx(bars, period)    In:4h DF,기간  Out:adx np배열(Wilder)
#  compute_ema(close, period)   In:종가,기간   Out:ema np배열
#  gate_signals(bars,mode,cfg)  In:4h DF(신호+adx+ema),모드,설정  Out:(le_arr, se_arr) 게이트 적용된 진입 bool배열
#  build_minute_index(df1m,bars)In:1분DF,4h DF  Out:(m_open,m_high,m_low,m_index,s_idx,e_idx)
#  liq_price(side,entry,frac,mmr)  In:방향,진입가,명목비율,MMR  Out:청산가
#  scan_minute_stop(...)        In:분슬라이스,방향,스탑가,청산가,슬립  Out:(j,exec,reason)|None
#  simulate(bars,le,se,lx,sx,stop,cfg,mIdx)  In:4h DF,게이트진입,원시청산,스탑,설정,분인덱스  Out:(trades, mtm, metrics)
#  compute_metrics(...)         In:거래,자본곡선,기간,라벨  Out:지표 dict
#  sha256_of(path)              In:경로   Out:해시
#  main()                       In:없음   Out:없음(파일기록+콘솔요약)
#
# === 핵심 변수 ===
#  CFG          : 설정 일체(+ADX_PERIOD/ADX_MAX/TREND_EMA/MODES/STOP_CASES 확장)
#  adx, ema200  : 4h 닫힌봉 기준 필터값(진입 i 결정 → i+1 시가 체결, 미래참조 없음)
#  le_arr/se_arr: 모드별 게이트가 적용된 '롱/숏 진입허가' bool 배열
#  equity       : 실현 잔고(복리). notional=NOTIONAL_FRAC*equity, qty=notional/진입가
# =====================================================================================

import os
import json
import hashlib
import numpy as np
import pandas as pd

CFG = {
    "VERSION":        "SideWay_V0_stg2",
    "DATA_FILENAME":  "merged_data.csv",
    "INDEX_DIRNAME":  "00WorkHstr",       # INDEX만 여기(상위/00WorkHstr)에 기록
    "TF":             "4h",
    "MA_PERIOD":      6,
    "DROP_RATE":      1.0,
    "INIT_CAPITAL":   10000.0,
    "LEVERAGE":       5.0,
    "NOTIONAL_FRAC":  0.50,
    "MMR":            0.004,
    "FEE_RATE":       0.0005,
    "SLIPPAGE":       0.0002,
    "FUNDING_RATE":   0.0001,
    "FUNDING_HOURS":  (0, 8, 16),
    # --- stg2 신규: 레짐/추세 필터 ---
    "ADX_PERIOD":     14,
    "ADX_MAX":        25.0,    # ADX<25(횡보)에서만 진입 허가 (자료의 25~30 위험구간 하단)
    "TREND_EMA":      200,     # 방향 판정용 4h EMA
    "MODES":          ("both_raw", "long_only", "both_adx", "both_adx_dir", "long_only_adx"),
    "STOP_CASES":     (0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12, 0.15, None),
    "PERIODS_PER_YR": 365.25 * 24 / 4.0,
}

NS_4H = np.int64(4 * 3600 * 1_000_000_000)


# ------------------------------------------------------------------ 경로
def resolve_paths():
    here = os.path.dirname(os.path.abspath(__file__))     # 실행 하위폴더(=결과 저장처)
    parent = os.path.dirname(here)                         # ...\verify
    data_path = os.path.join(parent, CFG["DATA_FILENAME"])
    index_dir = os.path.join(parent, CFG["INDEX_DIRNAME"])
    os.makedirs(index_dir, exist_ok=True)
    return data_path, here, index_dir


# ------------------------------------------------------------------ 데이터 로드
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
               "nan_close": int(df["close"].isna().sum()),
               "nan_volume": int(df["volume"].isna().sum()),
               "start": str(df.index[0]), "end": str(df.index[-1])}
    return df, quality


# ------------------------------------------------------------------ 4h 리샘플
def resample_4h(df1m):
    r = df1m.resample("4h", origin="epoch", label="left", closed="left")
    bars = pd.DataFrame({
        "open":   r["open"].first(),
        "high":   r["high"].max(),
        "low":    r["low"].min(),
        "close":  r["close"].last(),
        "volume": r["volume"].sum(min_count=1),
    }).dropna(subset=["close"]).copy()
    return bars


# ------------------------------------------------------------------ 평균회귀 raw 신호(stg1 동일)
def compute_signals(bars):
    close = bars["close"].to_numpy("float64")
    vol = bars["volume"].to_numpy("float64")
    roc = np.empty(len(close)); roc[:] = np.nan
    roc[1:] = (close[1:] - close[:-1]) / close[1:] * 100.0
    cma = pd.Series(roc).rolling(CFG["MA_PERIOD"]).mean().to_numpy()
    dr = CFG["DROP_RATE"]
    cma_prev = np.roll(cma, 1); cma_prev[0] = np.nan
    vol_prev = np.roll(vol, 1); vol_prev[0] = np.nan
    long_entry = (cma > cma_prev) & (cma_prev < -dr) & (vol_prev < vol)
    short_entry = (cma < cma_prev) & (cma_prev > dr) & (vol_prev < vol)
    long_exit = (cma > 0) & (vol_prev > vol)
    short_exit = (cma < 0) & (vol_prev > vol)
    for nm, arr in [("long_entry", long_entry), ("short_entry", short_entry),
                    ("long_exit", long_exit), ("short_exit", short_exit)]:
        bars[nm] = np.where(np.isnan(cma), False, arr)
    bars["cma"] = cma
    return bars


# ------------------------------------------------------------------ ADX(14, Wilder)
def compute_adx(bars, period):
    high = bars["high"].to_numpy("float64")
    low = bars["low"].to_numpy("float64")
    close = bars["close"].to_numpy("float64")
    n = len(bars)
    tr = np.zeros(n); plus_dm = np.zeros(n); minus_dm = np.zeros(n)
    for i in range(1, n):
        up = high[i] - high[i-1]
        dn = low[i-1] - low[i]
        plus_dm[i] = up if (up > dn and up > 0) else 0.0
        minus_dm[i] = dn if (dn > up and dn > 0) else 0.0
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
    # Wilder 스무딩 = ewm(alpha=1/period, adjust=False)
    a = 1.0 / period
    atr = pd.Series(tr).ewm(alpha=a, adjust=False).mean().to_numpy()
    pdi = 100.0 * pd.Series(plus_dm).ewm(alpha=a, adjust=False).mean().to_numpy() / np.where(atr == 0, np.nan, atr)
    mdi = 100.0 * pd.Series(minus_dm).ewm(alpha=a, adjust=False).mean().to_numpy() / np.where(atr == 0, np.nan, atr)
    dx = 100.0 * np.abs(pdi - mdi) / np.where((pdi + mdi) == 0, np.nan, (pdi + mdi))
    adx = pd.Series(dx).ewm(alpha=a, adjust=False).mean().to_numpy().copy()
    # 워밍업 구간(초기 2*period)은 신뢰 불가 → NaN 처리
    adx[: 2 * period] = np.nan
    return adx


def compute_ema(close, period):
    return pd.Series(close).ewm(span=period, adjust=False).mean().to_numpy()


# ------------------------------------------------------------------ 모드별 진입 게이트
def gate_signals(bars, mode, cfg):
    le = bars["long_entry"].to_numpy().copy()
    se = bars["short_entry"].to_numpy().copy()
    adx = bars["adx"].to_numpy("float64")
    ema = bars["ema_trend"].to_numpy("float64")
    close = bars["close"].to_numpy("float64")
    adx_ok = adx < cfg["ADX_MAX"]            # NaN<25 → False (워밍업/불명 시 진입 차단=보수)
    ema_nan = np.isnan(ema)
    long_dir_ok = ema_nan | (close > ema)    # 워밍업엔 롱 허용
    short_dir_ok = (~ema_nan) & (close < ema)  # 워밍업엔 숏 차단

    if mode == "both_raw":
        pass
    elif mode == "long_only":
        se = np.zeros_like(se, dtype=bool)
    elif mode == "both_adx":
        le = le & adx_ok; se = se & adx_ok
    elif mode == "both_adx_dir":
        le = le & adx_ok & long_dir_ok
        se = se & adx_ok & short_dir_ok
    elif mode == "long_only_adx":
        le = le & adx_ok
        se = np.zeros_like(se, dtype=bool)
    else:
        raise ValueError(f"알 수 없는 모드: {mode}")
    return le, se


# ------------------------------------------------------------------ 1분 인덱스(나노초 강제)
def build_minute_index(df1m, bars):
    m_time_ns = df1m.index.values.astype("datetime64[ns]").astype("int64")
    m_open = df1m["open"].to_numpy("float64")
    m_high = df1m["high"].to_numpy("float64")
    m_low = df1m["low"].to_numpy("float64")
    m_index = df1m.index
    bar_start_ns = bars.index.values.astype("datetime64[ns]").astype("int64")
    s_idx = np.searchsorted(m_time_ns, bar_start_ns, side="left")
    e_idx = np.searchsorted(m_time_ns, bar_start_ns + int(NS_4H), side="left")
    return m_open, m_high, m_low, m_index, s_idx, e_idx


# ------------------------------------------------------------------ 청산가(교차마진 단일포지션)
def liq_price(side, entry, frac, mmr):
    EoverN = 1.0 / frac
    if side == "long":
        return entry * (1.0 + mmr - EoverN)
    else:
        return entry * (1.0 - mmr + EoverN)


# ------------------------------------------------------------------ 분 스탑/청산 스캔
def scan_minute_stop(m_open, m_high, m_low, s, e, side, stop_price, liq_p, slip):
    if side == "long":
        for j in range(s, e):
            lo = m_low[j]
            if liq_p is not None and lo <= liq_p:
                ref = min(liq_p, m_open[j]); return j, ref * (1.0 - slip), "liquidation"
            if stop_price is not None and lo <= stop_price:
                ref = min(stop_price, m_open[j]); return j, ref * (1.0 - slip), "stop"
        return None
    else:
        for j in range(s, e):
            hi = m_high[j]
            if liq_p is not None and hi >= liq_p:
                ref = max(liq_p, m_open[j]); return j, ref * (1.0 + slip), "liquidation"
            if stop_price is not None and hi >= stop_price:
                ref = max(stop_price, m_open[j]); return j, ref * (1.0 + slip), "stop"
        return None


# ------------------------------------------------------------------ 펀딩 크로싱
def count_funding_crossings(start, end, funding_hours):
    if end <= start:
        return 0
    cnt = 0
    day = start.normalize(); last = end.normalize() + pd.Timedelta(days=1)
    while day <= last:
        for h in funding_hours:
            ft = day + pd.Timedelta(hours=int(h))
            if start < ft <= end:
                cnt += 1
        day += pd.Timedelta(days=1)
    return cnt


# ------------------------------------------------------------------ 시뮬레이션(한 셀=모드+스탑)
def simulate(bars, le, se, lx, sx, stop_pct, cfg, mIdx):
    m_open, m_high, m_low, m_index, s_idx, e_idx = mIdx
    o = bars["open"].to_numpy("float64"); c = bars["close"].to_numpy("float64")
    t = bars.index
    lo_arr = bars["low"].to_numpy("float64"); hi_arr = bars["high"].to_numpy("float64")
    n = len(bars)
    fee = cfg["FEE_RATE"]; slip = cfg["SLIPPAGE"]; frac = cfg["NOTIONAL_FRAC"]
    mmr = cfg["MMR"]; fr = cfg["FUNDING_RATE"]; fh = cfg["FUNDING_HOURS"]

    equity = cfg["INIT_CAPITAL"]; pos = None
    entry_exec = qty = notional = stop_price = 0.0; liq_p = None; entry_t = None
    trades = []; mtm = np.empty(n, dtype="float64")

    def open_trade(side, ref_open, bar_i):
        nonlocal equity, pos, entry_exec, entry_t, qty, notional, stop_price, liq_p
        ex = ref_open * (1.0 + slip) if side == "long" else ref_open * (1.0 - slip)
        notional = frac * equity; qty = notional / ex
        entry_fee = notional * fee; equity -= entry_fee
        stop_price = None if stop_pct is None else (ex * (1.0 - stop_pct) if side == "long" else ex * (1.0 + stop_pct))
        liq_p = liq_price(side, ex, frac, mmr)
        if side == "long" and liq_p <= 0:
            liq_p = None
        pos = side; entry_exec = ex; entry_t = t[bar_i]
        return entry_fee

    def close_trade(side, exit_exec, exit_ts, reason, entry_fee):
        nonlocal equity, pos
        gross = qty * (exit_exec - entry_exec) if side == "long" else qty * (entry_exec - exit_exec)
        exit_fee = qty * exit_exec * fee
        funding_cost = count_funding_crossings(entry_t, exit_ts, fh) * (notional * fr)
        equity += gross - exit_fee - funding_cost
        if equity < 0:
            equity = 0.0
        trades.append({
            "side": side, "reason": reason, "entry_time": str(entry_t), "exit_time": str(exit_ts),
            "entry_price": round(entry_exec, 4), "exit_price": round(exit_exec, 4),
            "qty": round(qty, 8), "notional": round(notional, 2), "gross_pnl": round(gross, 4),
            "entry_fee": round(entry_fee, 4), "exit_fee": round(exit_fee, 4), "funding": round(funding_cost, 4),
            "net_pnl": round(gross - exit_fee - funding_cost - entry_fee, 4), "equity_after": round(equity, 4),
        })
        pos = None

    pending_entry_fee = 0.0
    for i in range(n):
        if pos is not None and i >= 1:
            if (pos == "long" and lx[i-1]) or (pos == "short" and sx[i-1]):
                ex = o[i] * (1.0 - slip) if pos == "long" else o[i] * (1.0 + slip)
                close_trade(pos, ex, t[i], "signal", pending_entry_fee)
        if pos is None and i >= 1:
            if le[i-1]:
                pending_entry_fee = open_trade("long", o[i], i)
            elif se[i-1]:
                pending_entry_fee = open_trade("short", o[i], i)
        if pos is not None:
            need = False
            if pos == "long":
                if (stop_price is not None and lo_arr[i] <= stop_price) or (liq_p is not None and lo_arr[i] <= liq_p):
                    need = True
            else:
                if (stop_price is not None and hi_arr[i] >= stop_price) or (liq_p is not None and hi_arr[i] >= liq_p):
                    need = True
            if need:
                hit = scan_minute_stop(m_open, m_high, m_low, s_idx[i], e_idx[i], pos, stop_price, liq_p, slip)
                if hit is not None:
                    j, exec_px, reason = hit
                    close_trade(pos, exec_px, m_index[j], reason, pending_entry_fee)
        if pos is None:
            mtm[i] = equity
        else:
            mtm[i] = equity + (qty * (c[i] - entry_exec) if pos == "long" else qty * (entry_exec - c[i]))
    return trades, mtm


# ------------------------------------------------------------------ 지표
def compute_metrics(trades, mtm, bars, cfg, mode, stop_pct):
    init = cfg["INIT_CAPITAL"]; final = float(mtm[-1]) if len(mtm) else init
    span_days = (bars.index[-1] - bars.index[0]).total_seconds() / 86400.0
    yrs = span_days / 365.25 if span_days > 0 else np.nan
    total_ret = final / init - 1.0
    cagr = (final / init) ** (1.0 / yrs) - 1.0 if (yrs and yrs > 0 and final > 0) else np.nan
    peak = np.maximum.accumulate(mtm); dd = (mtm - peak) / peak
    mdd = float(dd.min()) if len(dd) else 0.0
    rets = np.diff(mtm) / mtm[:-1] if len(mtm) > 1 else np.array([0.0])
    rets = rets[np.isfinite(rets)]
    sharpe = (rets.mean() / rets.std() * np.sqrt(cfg["PERIODS_PER_YR"])) if rets.std() > 0 else 0.0
    nt = len(trades)
    wins = [tr for tr in trades if tr["net_pnl"] > 0]; losses = [tr for tr in trades if tr["net_pnl"] <= 0]
    gw = sum(tr["net_pnl"] for tr in wins); gl = -sum(tr["net_pnl"] for tr in losses)
    longs = sum(1 for tr in trades if tr["side"] == "long")
    long_pnl = round(sum(tr["net_pnl"] for tr in trades if tr["side"] == "long"), 2)
    short_pnl = round(sum(tr["net_pnl"] for tr in trades if tr["side"] == "short"), 2)
    by_reason = {}
    for tr in trades:
        by_reason[tr["reason"]] = by_reason.get(tr["reason"], 0) + 1
    return {
        "mode": mode, "stop_pct": ("none" if stop_pct is None else stop_pct),
        "final_equity": round(final, 2), "total_return_pct": round(total_ret * 100, 2),
        "CAGR_pct": (None if np.isnan(cagr) else round(cagr * 100, 2)),
        "MDD_pct": round(mdd * 100, 2), "sharpe": round(float(sharpe), 3),
        "num_trades": nt, "win_rate_pct": (round(len(wins) / nt * 100, 2) if nt else 0.0),
        "profit_factor": (round(gw / gl, 3) if gl > 0 else None),
        "longs": longs, "shorts": nt - longs,
        "long_pnl": long_pnl, "short_pnl": short_pnl, "exit_by_reason": by_reason,
    }


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ main
def main():
    data_path, out_dir, index_dir = resolve_paths()
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"입력파일 없음: {data_path}")
    df1m, quality = load_minute_data(data_path)
    input_hash = sha256_of(data_path)
    bars = resample_4h(df1m)
    bars = compute_signals(bars)
    bars["adx"] = compute_adx(bars, CFG["ADX_PERIOD"])
    bars["ema_trend"] = compute_ema(bars["close"].to_numpy("float64"), CFG["TREND_EMA"])
    mIdx = build_minute_index(df1m, bars)
    lx = bars["long_exit"].to_numpy(); sx = bars["short_exit"].to_numpy()

    all_trades = []; summaries = []; equity_curves = {}
    for mode in CFG["MODES"]:
        le, se = gate_signals(bars, mode, CFG)
        for stop_pct in CFG["STOP_CASES"]:
            trades, mtm = simulate(bars, le, se, lx, sx, stop_pct, CFG, mIdx)
            metrics = compute_metrics(trades, mtm, bars, CFG, mode, stop_pct)
            slabel = ("none" if stop_pct is None else f"{int(round(stop_pct*100))}pct")
            case = f"{mode}__{slabel}"
            for tr in trades:
                tr2 = dict(tr); tr2["case"] = case; all_trades.append(tr2)
            summaries.append(metrics); equity_curves[case] = mtm

    v = CFG["VERSION"]
    sum_path = os.path.join(out_dir, f"{v}_summary.csv")
    pd.DataFrame(summaries).to_csv(sum_path, index=False, encoding="utf-8-sig")
    tr_cols = ["case", "side", "reason", "entry_time", "exit_time", "entry_price", "exit_price",
               "qty", "notional", "gross_pnl", "entry_fee", "exit_fee", "funding", "net_pnl", "equity_after"]
    tr_path = os.path.join(out_dir, f"{v}_trades.csv")
    pd.DataFrame(all_trades, columns=tr_cols).to_csv(tr_path, index=False, encoding="utf-8-sig")
    eq_path = os.path.join(out_dir, f"{v}_equity.csv")
    eq_df = pd.DataFrame({"time": [str(x) for x in bars.index]})
    for case, mtm in equity_curves.items():
        eq_df[case] = np.round(mtm, 4)
    eq_df.to_csv(eq_path, index=False, encoding="utf-8-sig")
    res_path = os.path.join(out_dir, f"{v}_results.json")
    results = {"version": v, "config": CFG, "data_quality": quality,
               "input_file": CFG["DATA_FILENAME"], "input_sha256": input_hash,
               "n_4h_bars": int(len(bars)), "summaries": summaries}
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    out_files = [f"{v}_summary.csv", f"{v}_trades.csv", f"{v}_equity.csv", f"{v}_results.json"]
    manifest = {"version": v, "input_file": CFG["DATA_FILENAME"], "input_sha256": input_hash,
                "outputs": {fn: sha256_of(os.path.join(out_dir, fn)) for fn in out_files},
                "n_4h_bars": int(len(bars)), "data_quality": quality, "out_dir": out_dir, "index_dir": index_dir}
    with open(os.path.join(out_dir, f"{v}_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, default=str)

    print(f"[{v}] 4h봉 {len(bars)} | {quality['start']} ~ {quality['end']} | 모드 {len(CFG['MODES'])} x 스탑 {len(CFG['STOP_CASES'])} = {len(summaries)}셀")
    # 모드별 최고 스탑만 콘솔 요약
    import collections
    best = {}
    for m in summaries:
        md = m["mode"]
        if md not in best or m["total_return_pct"] > best[md]["total_return_pct"]:
            best[md] = m
    for md in CFG["MODES"]:
        m = best[md]
        print(f"  {md:>14} 최고: 스탑={m['stop_pct']:>4} 수익 {m['total_return_pct']:>7}% CAGR {m['CAGR_pct']}% "
              f"MDD {m['MDD_pct']}% 샤프 {m['sharpe']} 거래 {m['num_trades']} 승률 {m['win_rate_pct']}% "
              f"롱/숏손익 {m['long_pnl']}/{m['short_pnl']}")
    print(f"  결과파일 → {out_dir}")


if __name__ == "__main__":
    main()
