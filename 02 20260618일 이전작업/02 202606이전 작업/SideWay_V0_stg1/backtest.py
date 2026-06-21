# [backtest.py]
# 코드길이: 452줄 | 내부버전명: SideWay_V0_stg1
# 로직 축약/생략 없이 전체 출력. 아래 In/Out 태그 후 코드 시작.
# =====================================================================================
# 목적: krishna/kris 계열 "평균회귀(Mean Reversion)" 전략(KrisWaters ROC 방식)을
#       바이낸스 USDT-M 선물 환경으로 백테스트한다.
#       - 1분봉 원천데이터를 4시간봉으로 리샘플 후 신호 계산
#       - 롱 + 숏(원본은 롱전용 → 대칭 거울로직으로 숏 추가)
#       - 시장가(테이커) 체결, 수수료/슬리피지/펀딩 현실화, 교차마진 강제청산 백스톱
#       - 레버리지 5배, 명목 = 자본의 50%(=증거금 10% x 5배), 복리
#       - 스탑로스 5케이스(2%/3%/4%/5%/무스탑)를 각각 실행하여 비교
#       - 미래참조(Lookahead) 차단: 결정은 '닫힌 4h봉'에서만, 체결은 '다음 4h봉 시가'
#       - 스탑/청산은 4h봉 내부의 '1분봉 경로'로 정확 체결(장중 정밀)
#
# === 사용 파일(File In/Out) ===
#  In : ../merged_data.csv        (한 단계 상위 폴더, 1분봉 OHLCV. 추가 컬럼은 무시)
#  Out: ../00WorkHstr/SideWay_V0_stg1_summary.csv   (케이스별 핵심지표)
#  Out: ../00WorkHstr/SideWay_V0_stg1_trades.csv    (전체 거래 내역)
#  Out: ../00WorkHstr/SideWay_V0_stg1_equity.csv    (케이스별 4h MTM 자본곡선)
#  Out: ../00WorkHstr/SideWay_V0_stg1_results.json  (설정+요약, 기계판독용)
#  Out: ../00WorkHstr/SideWay_V0_stg1_manifest.json (산출물 파일명+sha256, check.py 검증용)
#
# === 함수(Function In/Out) ===
#  resolve_paths()              In: 없음            Out: (data_path, out_dir) 절대경로
#  load_minute_data(path)       In: csv경로         Out: DataFrame(1분 OHLCV, tz=UTC, 중복제거, 정렬), dict(품질정보)
#  resample_4h(df1m)            In: 1분 DF          Out: 4h DF(open/high/low/close/volume)
#  compute_signals(bars)        In: 4h DF           Out: 4h DF + 신호열(long_entry/short_entry/long_exit/short_exit)
#  build_minute_index(df1m,bars)In: 1분 DF, 4h DF   Out: (m_open,m_high,m_low,m_time[ns]) np배열, (start_idx,end_idx) 슬라이스배열
#  liq_price(side,entry,frac,mmr) In: 방향,진입가,명목비율,유지증거금률 Out: 강제청산가(float)
#  scan_minute_stop(...)        In: 분슬라이스,방향,스탑가,청산가,슬리피지 Out: (exit_time,exit_exec,reason) 또는 None
#  simulate(bars,signals,mIdx,stop_pct,cfg) In: 4h DF,신호,분인덱스,스탑%,설정 Out: (trades list, mtm_equity np, metrics dict)
#  compute_metrics(...)         In: 거래리스트,자본곡선,기간 Out: 지표 dict
#  sha256_of(path)              In: 파일경로        Out: 해시 문자열
#  main()                       In: 없음            Out: 없음(파일 기록 + 콘솔 요약)
#
# === 핵심 변수(Variable In/Out 개념) ===
#  CFG                : 모든 설정(수수료/슬리피지/펀딩/레버리지/명목비율/유지증거금률/초기자본/MA기간/dropRate/스탑케이스)
#  equity(=wallet)    : 실현 잔고(원금). 거래 종료 시마다 갱신 → 복리의 핵심
#  notional           : 진입 명목가치 = NOTIONAL_FRAC * equity (진입시점 자본 기준)
#  qty                : 코인 수량 = notional / 진입체결가
#  stop_price         : 스탑가(롱=진입가*(1-s), 숏=진입가*(1+s))
#  mtm_equity[i]      : 4h봉 i 시점 평가자본(=wallet + 미실현손익) → MDD/샤프 계산용
# =====================================================================================

import os
import json
import hashlib
import numpy as np
import pandas as pd

# ------------------------------------------------------------------ 설정(CFG)
CFG = {
    "VERSION":        "SideWay_V0_stg1",
    "DATA_FILENAME":  "merged_data.csv",   # A:OK — 상위폴더의 실제 입력파일명
    "OUT_DIRNAME":    "00WorkHstr",
    "TF":             "4h",
    "MA_PERIOD":      6,        # KrisWaters 원본 SMA 기간(4h 기본값 유지)
    "DROP_RATE":      1.0,      # KrisWaters 원본 임계치(+/-1)
    "INIT_CAPITAL":   10000.0,  # C4: 초기 선물 자본 $10,000
    "LEVERAGE":       5.0,      # 레버리지 5배
    "NOTIONAL_FRAC":  0.50,     # C1: 명목 = 자본의 50% (=증거금 10% x 5배)
    "MMR":            0.004,    # 유지증거금률 0.4%(BTC 최저티어 가정) — C3 청산 백스톱
    "FEE_RATE":       0.0005,   # D2: 테이커 수수료 0.05%/편 (검색 확인)
    "SLIPPAGE":       0.0002,   # D2: 슬리피지 0.02%/편 (BTC 시장가 현실화)
    "FUNDING_RATE":   0.0001,   # D3(b): 8시간마다 고정 0.01% (보수적으로 항상 '비용'으로 차감)
    "FUNDING_HOURS":  (0, 8, 16),
    "STOP_CASES":     (0.02, 0.03, 0.04, 0.05, None),  # E1: 4개 폭 + 무스탑 기준선
    "PERIODS_PER_YR": 365.25 * 24 / 4.0,  # 4h봉 연간 개수(샤프 연율화용)
}

NS_4H = np.int64(4 * 3600 * 1_000_000_000)  # 4시간(ns)


# ------------------------------------------------------------------ 경로 해석
def resolve_paths():
    here = os.path.dirname(os.path.abspath(__file__))      # ...\SideWay_V0_stg1
    parent = os.path.dirname(here)                          # ...\verify
    data_path = os.path.join(parent, CFG["DATA_FILENAME"])  # ..\merged_data.csv
    out_dir = os.path.join(parent, CFG["OUT_DIRNAME"])      # ..\00WorkHstr
    os.makedirs(out_dir, exist_ok=True)
    return data_path, out_dir


# ------------------------------------------------------------------ 데이터 로드
def load_minute_data(path):
    cols = ["timestamp", "open", "high", "low", "close", "volume"]
    df = pd.read_csv(path, usecols=lambda c: c in cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp")
    dup = int(df["timestamp"].duplicated().sum())
    df = df.drop_duplicates(subset="timestamp", keep="first")
    df = df.set_index("timestamp")
    # 1분 갭(누락 분) 수 계산: 실제 분수 vs 기대 분수
    span_min = int((df.index[-1] - df.index[0]).total_seconds() // 60) + 1
    gaps = int(span_min - len(df))
    na_close = int(df["close"].isna().sum())
    na_vol = int(df["volume"].isna().sum())
    quality = {"rows": int(len(df)), "duplicates_removed": dup, "minute_gaps": gaps,
               "nan_close": na_close, "nan_volume": na_vol,
               "start": str(df.index[0]), "end": str(df.index[-1])}
    return df, quality


# ------------------------------------------------------------------ 4h 리샘플
def resample_4h(df1m):
    # origin='epoch' → 00:00 UTC 경계(00,04,08,12,16,20)에 정렬(바이낸스 4h봉과 동일)
    r = df1m.resample("4h", origin="epoch", label="left", closed="left")
    bars = pd.DataFrame({
        "open":   r["open"].first(),
        "high":   r["high"].max(),
        "low":    r["low"].min(),
        "close":  r["close"].last(),
        "volume": r["volume"].sum(min_count=1),
    })
    bars = bars.dropna(subset=["close"]).copy()
    return bars


# ------------------------------------------------------------------ 신호 계산(닫힌 봉 기준)
def compute_signals(bars):
    close = bars["close"].to_numpy(dtype="float64")
    vol = bars["volume"].to_numpy(dtype="float64")
    # KrisWaters 원본: rateOfChange = (change(close)/close)*100  (현재 종가로 나눔)
    roc = np.empty(len(close)); roc[:] = np.nan
    roc[1:] = (close[1:] - close[:-1]) / close[1:] * 100.0
    # changeMovAvg = SMA(roc, MA_PERIOD)
    cma = pd.Series(roc).rolling(CFG["MA_PERIOD"]).mean().to_numpy()
    dr = CFG["DROP_RATE"]

    cma_prev = np.roll(cma, 1); cma_prev[0] = np.nan
    vol_prev = np.roll(vol, 1); vol_prev[0] = np.nan

    # 롱(원본): cma>cma[-1] & cma[-1]<-dr & vol[-1]<vol
    long_entry = (cma > cma_prev) & (cma_prev < -dr) & (vol_prev < vol)
    # 숏(대칭 거울): cma<cma[-1] & cma[-1]>+dr & vol[-1]<vol
    short_entry = (cma < cma_prev) & (cma_prev > dr) & (vol_prev < vol)
    # 롱청산(원본): cma>0 & vol[-1]>vol
    long_exit = (cma > 0) & (vol_prev > vol)
    # 숏청산(거울): cma<0 & vol[-1]>vol
    short_exit = (cma < 0) & (vol_prev > vol)

    for nm, arr in [("long_entry", long_entry), ("short_entry", short_entry),
                    ("long_exit", long_exit), ("short_exit", short_exit)]:
        a = np.where(np.isnan(cma), False, arr)
        bars[nm] = a
    bars["cma"] = cma
    return bars


# ------------------------------------------------------------------ 1분 인덱스 맵(장중 스탑 감시용)
def build_minute_index(df1m, bars):
    # pandas 해상도(us/ns) 무관하게 '나노초 정수'로 강제 통일
    m_time_ns = df1m.index.values.astype("datetime64[ns]").astype("int64")
    m_open = df1m["open"].to_numpy(dtype="float64")
    m_high = df1m["high"].to_numpy(dtype="float64")
    m_low = df1m["low"].to_numpy(dtype="float64")
    m_index = df1m.index                         # 분 Timestamp(체결시각 기록용)
    bar_start_ns = bars.index.values.astype("datetime64[ns]").astype("int64")
    s_idx = np.searchsorted(m_time_ns, bar_start_ns, side="left")
    e_idx = np.searchsorted(m_time_ns, bar_start_ns + int(NS_4H), side="left")
    return m_open, m_high, m_low, m_index, s_idx, e_idx


# ------------------------------------------------------------------ 강제청산가(교차마진 단일포지션)
def liq_price(side, entry, frac, mmr):
    # 파생식 유도는 파일상단 C3 설명 참조. E/N = 1/frac.
    EoverN = 1.0 / frac
    if side == "long":
        return entry * (1.0 + mmr - EoverN)   # 보통 <=0 → 도달 불가
    else:
        return entry * (1.0 - mmr + EoverN)   # 보통 entry*3 수준 → 거의 도달 불가


# ------------------------------------------------------------------ 분단위 스탑/청산 스캔
def scan_minute_stop(m_open, m_high, m_low, s, e, side, stop_price, liq_p, slip):
    # 반환: (분인덱스 j, 체결가 exec, reason) 또는 None
    if side == "long":
        for j in range(s, e):
            lo = m_low[j]
            # 청산 우선 검사(보통 stop_price > liq_p 라 stop이 먼저지만 무스탑 케이스 대비)
            if liq_p is not None and lo <= liq_p:
                ref = min(liq_p, m_open[j])      # 갭 다운이면 더 나쁜 시가로 체결
                return j, ref * (1.0 - slip), "liquidation"
            if stop_price is not None and lo <= stop_price:
                ref = min(stop_price, m_open[j])
                return j, ref * (1.0 - slip), "stop"
        return None
    else:  # short
        for j in range(s, e):
            hi = m_high[j]
            if liq_p is not None and hi >= liq_p:
                ref = max(liq_p, m_open[j])      # 갭 업이면 더 나쁜 시가로 체결
                return j, ref * (1.0 + slip), "liquidation"
            if stop_price is not None and hi >= stop_price:
                ref = max(stop_price, m_open[j])
                return j, ref * (1.0 + slip), "stop"
        return None


# ------------------------------------------------------------------ 펀딩 크로싱 카운트
def count_funding_crossings(start, end, funding_hours):
    # start/end 는 tz-aware Timestamp. 사이를 지난 펀딩시각(00/08/16 UTC) 횟수
    if end <= start:
        return 0
    cnt = 0
    day = start.normalize()
    last = end.normalize() + pd.Timedelta(days=1)
    while day <= last:
        for h in funding_hours:
            ft = day + pd.Timedelta(hours=int(h))
            if start < ft <= end:
                cnt += 1
        day += pd.Timedelta(days=1)
    return cnt


# ------------------------------------------------------------------ 시뮬레이션(한 케이스)
def simulate(bars, stop_pct, cfg, mIdx):
    m_open, m_high, m_low, m_index, s_idx, e_idx = mIdx
    o = bars["open"].to_numpy("float64")
    c = bars["close"].to_numpy("float64")
    t = bars.index   # DatetimeIndex (tz-aware Timestamp) — 시각 직접 사용
    lo_arr = bars["low"].to_numpy("float64")
    hi_arr = bars["high"].to_numpy("float64")
    le = bars["long_entry"].to_numpy(); se = bars["short_entry"].to_numpy()
    lx = bars["long_exit"].to_numpy(); sx = bars["short_exit"].to_numpy()
    n = len(bars)

    fee = cfg["FEE_RATE"]; slip = cfg["SLIPPAGE"]; frac = cfg["NOTIONAL_FRAC"]
    mmr = cfg["MMR"]; lev = cfg["LEVERAGE"]; fr = cfg["FUNDING_RATE"]; fh = cfg["FUNDING_HOURS"]

    equity = cfg["INIT_CAPITAL"]            # 실현 잔고(복리)
    pos = None                              # None / 'long' / 'short'
    entry_exec = entry_t = qty = notional = stop_price = liq_p = 0.0
    trades = []
    mtm = np.empty(n, dtype="float64")

    def open_trade(side, ref_open, bar_i):
        nonlocal equity, pos, entry_exec, entry_t, qty, notional, stop_price, liq_p
        ex = ref_open * (1.0 + slip) if side == "long" else ref_open * (1.0 - slip)
        notional = frac * equity
        qty = notional / ex
        entry_fee = notional * fee
        equity -= entry_fee
        if stop_pct is None:
            stop_price = None
        else:
            stop_price = ex * (1.0 - stop_pct) if side == "long" else ex * (1.0 + stop_pct)
        liq_p = liq_price(side, ex, frac, mmr)
        if side == "long" and liq_p <= 0:
            liq_p = None  # 롱은 도달 불가 → 비활성
        pos = side; entry_exec = ex; entry_t = t[bar_i]
        return entry_fee

    def close_trade(side, exit_ref_exec, exit_ts, bar_i, reason, entry_fee):
        nonlocal equity, pos
        if side == "long":
            gross = qty * (exit_ref_exec - entry_exec)
        else:
            gross = qty * (entry_exec - exit_ref_exec)
        exit_notional = qty * exit_ref_exec
        exit_fee = exit_notional * fee
        fcross = count_funding_crossings(entry_t, exit_ts, fh)
        funding_cost = fcross * (notional * fr)
        equity += gross - exit_fee - funding_cost
        if equity < 0:
            equity = 0.0
        trades.append({
            "side": side, "reason": reason,
            "entry_time": str(entry_t),
            "exit_time": str(exit_ts),
            "entry_price": round(entry_exec, 4), "exit_price": round(exit_ref_exec, 4),
            "qty": round(qty, 8), "notional": round(notional, 2),
            "gross_pnl": round(gross, 4), "entry_fee": round(entry_fee, 4),
            "exit_fee": round(exit_fee, 4), "funding": round(funding_cost, 4),
            "net_pnl": round(gross - exit_fee - funding_cost - entry_fee, 4),
            "equity_after": round(equity, 4),
        })
        pos = None

    pending_entry_fee = 0.0
    for i in range(n):
        # (1) 신호청산: 직전봉(i-1) 청산신호 → 현재봉 시가 체결
        if pos is not None and i >= 1:
            if (pos == "long" and lx[i-1]) or (pos == "short" and sx[i-1]):
                ref = o[i]
                ex = ref * (1.0 - slip) if pos == "long" else ref * (1.0 + slip)
                close_trade(pos, ex, t[i], i, "signal", pending_entry_fee)
        # (2) 신규진입: 무포지션 & 직전봉 진입신호 → 현재봉 시가 체결
        if pos is None and i >= 1:
            if le[i-1]:
                pending_entry_fee = open_trade("long", o[i], i)
            elif se[i-1]:
                pending_entry_fee = open_trade("short", o[i], i)
        # (3) 장중 스탑/청산: 현재봉의 1분 경로 감시(보유중일 때만)
        if pos is not None:
            need_scan = False
            if pos == "long":
                if (stop_price is not None and lo_arr[i] <= stop_price) or \
                   (liq_p is not None and lo_arr[i] <= liq_p):
                    need_scan = True
            else:
                if (stop_price is not None and hi_arr[i] >= stop_price) or \
                   (liq_p is not None and hi_arr[i] >= liq_p):
                    need_scan = True
            if need_scan:
                hit = scan_minute_stop(m_open, m_high, m_low, s_idx[i], e_idx[i],
                                       pos, stop_price, liq_p, slip)
                if hit is not None:
                    j, exec_px, reason = hit
                    close_trade(pos, exec_px, m_index[j], i, reason, pending_entry_fee)
        # (4) MTM 자본 기록(미실현 포함)
        if pos is None:
            mtm[i] = equity
        else:
            if pos == "long":
                unreal = qty * (c[i] - entry_exec)
            else:
                unreal = qty * (entry_exec - c[i])
            mtm[i] = equity + unreal

    metrics = compute_metrics(trades, mtm, bars, cfg, stop_pct)
    return trades, mtm, metrics


# ------------------------------------------------------------------ 지표 계산
def compute_metrics(trades, mtm, bars, cfg, stop_pct):
    init = cfg["INIT_CAPITAL"]
    final = float(mtm[-1]) if len(mtm) else init
    span_days = (bars.index[-1] - bars.index[0]).total_seconds() / 86400.0
    yrs = span_days / 365.25 if span_days > 0 else np.nan
    total_ret = final / init - 1.0
    cagr = (final / init) ** (1.0 / yrs) - 1.0 if (yrs and yrs > 0 and final > 0) else np.nan

    # MDD (MTM 자본곡선)
    peak = np.maximum.accumulate(mtm)
    dd = (mtm - peak) / peak
    mdd = float(dd.min()) if len(dd) else 0.0

    # 샤프 (4h MTM 수익률 연율화, rf=0)
    rets = np.diff(mtm) / mtm[:-1] if len(mtm) > 1 else np.array([0.0])
    rets = rets[np.isfinite(rets)]
    if rets.std() > 0:
        sharpe = rets.mean() / rets.std() * np.sqrt(cfg["PERIODS_PER_YR"])
    else:
        sharpe = 0.0

    nt = len(trades)
    wins = [tr for tr in trades if tr["net_pnl"] > 0]
    losses = [tr for tr in trades if tr["net_pnl"] <= 0]
    gross_win = sum(tr["net_pnl"] for tr in wins)
    gross_loss = -sum(tr["net_pnl"] for tr in losses)
    by_reason = {}
    for tr in trades:
        by_reason[tr["reason"]] = by_reason.get(tr["reason"], 0) + 1
    longs = sum(1 for tr in trades if tr["side"] == "long")
    shorts = nt - longs

    return {
        "stop_pct": ("none" if stop_pct is None else stop_pct),
        "final_equity": round(final, 2),
        "total_return_pct": round(total_ret * 100, 2),
        "CAGR_pct": (None if np.isnan(cagr) else round(cagr * 100, 2)),
        "MDD_pct": round(mdd * 100, 2),
        "sharpe": round(float(sharpe), 3),
        "num_trades": nt,
        "win_rate_pct": (round(len(wins) / nt * 100, 2) if nt else 0.0),
        "profit_factor": (round(gross_win / gross_loss, 3) if gross_loss > 0 else None),
        "avg_win": (round(gross_win / len(wins), 2) if wins else 0.0),
        "avg_loss": (round(-gross_loss / len(losses), 2) if losses else 0.0),
        "longs": longs, "shorts": shorts,
        "exit_by_reason": by_reason,
        "span_days": round(span_days, 1),
    }


# ------------------------------------------------------------------ 해시
def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ main
def main():
    data_path, out_dir = resolve_paths()
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"입력파일 없음: {data_path}")

    df1m, quality = load_minute_data(data_path)
    input_hash = sha256_of(data_path)
    bars = resample_4h(df1m)
    bars = compute_signals(bars)
    mIdx = build_minute_index(df1m, bars)

    all_trades = []
    summaries = []
    equity_curves = {}
    for stop_pct in CFG["STOP_CASES"]:
        trades, mtm, metrics = simulate(bars, stop_pct, CFG, mIdx)
        case = ("none" if stop_pct is None else f"{int(stop_pct*100)}pct")
        for tr in trades:
            tr2 = dict(tr); tr2["case"] = case; all_trades.append(tr2)
        summaries.append(metrics)
        equity_curves[case] = mtm

    v = CFG["VERSION"]
    # 1) summary.csv
    sum_path = os.path.join(out_dir, f"{v}_summary.csv")
    pd.DataFrame(summaries).to_csv(sum_path, index=False, encoding="utf-8-sig")
    # 2) trades.csv (거래 0건에도 헤더 유지)
    tr_cols = ["case", "side", "reason", "entry_time", "exit_time", "entry_price",
               "exit_price", "qty", "notional", "gross_pnl", "entry_fee", "exit_fee",
               "funding", "net_pnl", "equity_after"]
    tr_path = os.path.join(out_dir, f"{v}_trades.csv")
    pd.DataFrame(all_trades, columns=tr_cols).to_csv(tr_path, index=False, encoding="utf-8-sig")
    # 3) equity.csv (4h MTM, 케이스별 열)
    eq_path = os.path.join(out_dir, f"{v}_equity.csv")
    eq_df = pd.DataFrame({"time": [str(x) for x in bars.index]})
    for case, mtm in equity_curves.items():
        eq_df[case] = np.round(mtm, 4)
    eq_df.to_csv(eq_path, index=False, encoding="utf-8-sig")
    # 4) results.json
    res_path = os.path.join(out_dir, f"{v}_results.json")
    results = {"version": v, "config": CFG, "data_quality": quality,
               "input_file": CFG["DATA_FILENAME"], "input_sha256": input_hash,
               "n_4h_bars": int(len(bars)), "summaries": summaries}
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    # 5) manifest.json (check.py 검증용)
    out_files = [f"{v}_summary.csv", f"{v}_trades.csv", f"{v}_equity.csv", f"{v}_results.json"]
    manifest = {"version": v, "input_file": CFG["DATA_FILENAME"], "input_sha256": input_hash,
                "outputs": {fn: sha256_of(os.path.join(out_dir, fn)) for fn in out_files},
                "n_4h_bars": int(len(bars)), "data_quality": quality}
    man_path = os.path.join(out_dir, f"{v}_manifest.json")
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, default=str)

    # 콘솔 요약(간단)
    print(f"[{v}] 4h봉 {len(bars)}개 | 데이터 {quality['start']} ~ {quality['end']}")
    print(f"  중복제거 {quality['duplicates_removed']} / 1분갭 {quality['minute_gaps']} / NaN(close {quality['nan_close']}, vol {quality['nan_volume']})")
    for m in summaries:
        print(f"  스탑={m['stop_pct']:>4} | 최종 ${m['final_equity']:>10} | 수익 {m['total_return_pct']:>8}% "
              f"| CAGR {m['CAGR_pct']}% | MDD {m['MDD_pct']}% | 샤프 {m['sharpe']} "
              f"| 거래 {m['num_trades']} | 승률 {m['win_rate_pct']}% | L/S {m['longs']}/{m['shorts']}")
    print(f"  결과파일 → {out_dir}")


if __name__ == "__main__":
    main()
