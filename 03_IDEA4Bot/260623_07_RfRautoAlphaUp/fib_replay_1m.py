# -*- coding: utf-8 -*-
# [fib_replay_1m.py] (A) 청산버그 정정 — 진입결정(피보 되돌림 지정가)+피보 스텝업 청산+순차(청산후 진입)+1m 실체결.
#   캡틴 지시(2026-06-23): ①이전 진입 있으면 '청산 이후에만' 진입로직 발동(순차) ②진입결정·청산결정 둘 다
#     실시간=백테선 1분봉으로 봉단위 판정 ③알파/수익률 확인은 반드시 1m로 가격이 캔들 통과하는지 검증(환각방지).
#   §15.1 정직성: 엔진(§8 해시락) 재구현 안 함. compute_signals(피봇)·compute_split_entry(진입결정)·run_strategy를 '호출'.
#     공용 fib 루프는 run_strategy 청산부(L304-371)를 1:1 미러 → TS·7h체결로 돌리면 run_strategy와 거래·R '동치'임을
#     자체앵커(§15.2)로 증명한 뒤에만 1m체결/REV로 확장.
#   ★1m이 바꾸는 건 '청산 스톱 체결가'뿐(진입=지정가→target 그대로, 터치되는 봉=7h와 동일→순차 불변). 갭이면 open(더 나쁨).
import sys, os, itertools
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd
import trendstack_signal_engine as TS
import vol_sizing_compare as V

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv"
COST = 0.0008; FUND_8H = TS.FUND_8H; SL_PCT = TS.SL_PCT  # 엔진 상수 재사용(1.0%=초기손절)
FIB = (0.3, 0.5, 0.6)


def _p(*a): print(*a, flush=True)


def load_1m():
    d = pd.read_csv(DATA, usecols=["timestamp", "open", "high", "low", "close", "oi_zscore_24h"])
    d["t"] = pd.to_datetime(d["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
    d = d.dropna(subset=["open", "high", "low", "close"]).set_index("t").sort_index()
    return d


FUND_FILE = r"D:\ML\RfRauto\08_BTC_Data\raw_irreplaceable\BTCUSDT_funding_history_8h.csv"


def load_funding():
    """실펀딩 8h(BTCUSDT_funding_history_8h.csv) → (times[datetime64], prefix_sum[len+1]). 룩어헤드0(과거 확정값)."""
    f = pd.read_csv(FUND_FILE, usecols=["fundingTime", "fundingRate"])
    f["t"] = pd.to_datetime(f["fundingTime"], utc=True, format="ISO8601").dt.tz_localize(None)
    f = f.dropna(subset=["fundingRate"]).sort_values("t")
    times = f["t"].values.astype("datetime64[ns]")
    pref = np.concatenate([[0.0], np.cumsum(f["fundingRate"].values.astype(float))])
    return times, pref


def correct_exit_1m(side, entry, sl_level, exit_t, reason, d1m, tf_min):
    """청산 스톱 체결을 1m로 보정. 진입가·sl레벨·exit봉(7h/8h)은 엔진/루프 산출 그대로.
       reason이 스톱류면 exit_t봉 1m에서 첫 터치 찾아 갭이면 open(더 나쁨). trend_flip/maxhold=종가체결 불변."""
    if reason not in ("sl", "trail", "fibstop"):
        return sl_level, False
    win = d1m.loc[exit_t: exit_t + pd.Timedelta(minutes=tf_min) - pd.Timedelta(minutes=1)]
    if len(win) == 0:
        return sl_level, False
    O = win["open"].values; H = win["high"].values; L = win["low"].values
    for k in range(len(win)):
        if side == 1 and L[k] <= sl_level:
            fill = min(O[k], sl_level); return fill, (O[k] < sl_level)   # 갭=open<sl
        if side == -1 and H[k] >= sl_level:
            fill = max(O[k], sl_level); return fill, (O[k] > sl_level)
    return sl_level, False   # 1m서 미터치(드묾)=레벨 유지(보수)


def fib_loop(df_tf, sig, d1m, *, ext_side=None, use_trend_flip=True, fill_1m=True,
             lev=1.0, cost=COST, er=None, er_gate=None, tf_min=420, fib=FIB, oi_arr=None,
             init_sl_pct=SL_PCT, init_atr_mult=None, fund_pref=None, align_pivot=False, arm_bars=6):
    """run_strategy(L299-371) 1:1 미러 + 1m 청산보정. ext_side=None이면 TS 엔진조건, 아니면 외부신호(REV).
       반환: 거래 DataFrame(et,xt,side,entry,exit,R,reason,year,atr_pct,oi_z)."""
    high = df_tf['high'].values; low = df_tf['low'].values
    close = df_tf['close'].values; open_ = df_tf['open'].values
    atr_a = sig['atr']
    idx = df_tf.index; n = len(close)
    Trend = sig['Trend']; ph_conf = sig['ph_conf']; pl_conf = sig['pl_conf']
    eh = ((idx - pd.Timestamp('1970-01-01')) / pd.Timedelta(hours=1)).values.astype('float64')
    def n_fund(a, b): return int(np.floor(eh[b] / 8.0) - np.floor(eh[a] / 8.0))
    ftimes, fpref = (fund_pref if fund_pref is not None else (None, None))
    def fund_of(a, b, side):
        """실펀딩 있으면 (et,xt] 구간 펀딩합×side(롱=양rate 지불). 없으면 엔진 FUND_8H×기간(앵커용)."""
        if ftimes is None:
            return FUND_8H * n_fund(a, b)
        lo = int(np.searchsorted(ftimes, np.datetime64(idx[a]), 'right'))
        hi = int(np.searchsorted(ftimes, np.datetime64(idx[b]), 'right'))
        return side * (fpref[hi] - fpref[lo])
    lastPH = np.nan; lastPL = np.nan
    pos = 0; entry_price = np.nan; entry_i = -1; sl = np.nan; pb = 0
    e_ap = 0.02; e_oi = 0.0; armed_dir = 0; armed_left = 0
    trades = []
    for i in range(n):
        new_ph = i in ph_conf; new_pl = i in pl_conf
        if new_ph: lastPH = ph_conf[i][1]
        if new_pl: lastPL = pl_conf[i][1]
        if ext_side is not None and align_pivot:   # combo 방향 arming(신호 뜨면 arm_bars봉 유효)
            if ext_side[i] != 0: armed_dir = int(ext_side[i]); armed_left = arm_bars
            else: armed_left = max(0, armed_left - 1)
        if pos != 0:
            # ① 추세전환 청산(종가) — REV는 off
            if use_trend_flip and ((pos == 1 and Trend[i] == -1) or (pos == -1 and Trend[i] == 1)):
                px = close[i]; reason = "trend_flip"
                R = pos * (px - entry_price) / entry_price * lev
                fp = fund_of(entry_i, i, pos); R = R - cost - fp
                trades.append(dict(et=idx[entry_i], xt=idx[i], side=pos, entry=entry_price, exit=px,
                                   R=R, reason=reason, year=idx[i].year, atr_pct=e_ap, oi_z=e_oi)); pos = 0; sl = np.nan; pb = 0; continue
            # ② 스톱 터치 (현 sl로 체크 — 엔진순서: 업데이트 前)
            if i > entry_i and not np.isnan(sl):
                fill = None
                if fill_1m:
                    f, _gap = correct_exit_1m(pos, entry_price, sl, idx[i], "fibstop", d1m, tf_min)
                    # 1m서 실제 터치했는지: 7h봉 범위로 1차판정(엔진과 동일 터치봉), 체결가만 1m
                    o_, h_, l_, c_ = open_[i], high[i], low[i], close[i]
                    touched = (pos == 1 and l_ <= sl) or (pos == -1 and h_ >= sl)
                    if touched: fill = f
                else:
                    o_, h_, l_, c_ = open_[i], high[i], low[i], close[i]
                    ticks = (o_, h_, l_, c_) if c_ < o_ else (o_, l_, h_, c_)
                    for px in ticks:
                        if pos == 1 and px <= sl: fill = sl; break
                        if pos == -1 and px >= sl: fill = sl; break
                if fill is not None:
                    R = pos * (fill - entry_price) / entry_price * lev
                    fp = fund_of(entry_i, i, pos); R = R - cost - fp
                    trades.append(dict(et=idx[entry_i], xt=idx[i], side=pos, entry=entry_price, exit=fill,
                                       R=R, reason="fibstop", year=idx[i].year, atr_pct=e_ap, oi_z=e_oi)); pos = 0; sl = np.nan; pb = 0; continue
        # ③ 피보 스텝업 sl 업데이트 (엔진 L327-336)
        if pos == 1 and new_pl:
            pb += 1; ratio = fib[0] if pb == 1 else fib[1] if pb == 2 else fib[2]
            if not np.isnan(lastPH):
                cand = lastPH - ratio * (lastPH - pl_conf[i][1]); sl = cand if np.isnan(sl) else max(sl, cand)
        if pos == -1 and new_ph:
            pb += 1; ratio = fib[0] if pb == 1 else fib[1] if pb == 2 else fib[2]
            if not np.isnan(lastPL):
                cand = lastPL + ratio * (ph_conf[i][1] - lastPL); sl = cand if np.isnan(sl) else min(sl, cand)
        # ④ 진입 (flat일 때만 = '청산 이후에만')
        if pos == 0:
            if ext_side is None:
                le = Trend[i] == 1 and new_pl and not np.isnan(lastPH)
                se = Trend[i] == -1 and new_ph and not np.isnan(lastPL)
            elif align_pivot:
                # ★진입정렬: combo가 방향만 켜고(arming), '눌림목(피봇) 확정' 봉에서 진입 → SL이 눌림목 구조에 붙음(TS와 동일)
                le = (armed_dir == 1 and armed_left > 0) and new_pl and not np.isnan(lastPH)
                se = (armed_dir == -1 and armed_left > 0) and new_ph and not np.isnan(lastPL)
            else:
                s = ext_side[i]; le = (s == 1); se = (s == -1)
            if er is not None and er_gate is not None and (le or se) and er[i] < er_gate:
                le = se = False
            if le or se:
                d = 1 if le else -1
                ep = TS.compute_split_entry(d, i, close, high, low, open_, n, pl_conf, ph_conf,
                                            lastPH, lastPL, 'A', 3)   # 엔진 진입결정 호출
                pos = d; entry_price = ep; entry_i = i; pb = 0
                if init_atr_mult is not None and atr_a[i] > 0:
                    risk = float(np.clip(atr_a[i] / ep * init_atr_mult, 0.005, 0.08))
                    sl = ep * (1 - d * risk)
                else:
                    sl = ep * (1 - d * init_sl_pct / 100)
                e_ap = float(atr_a[i] / close[i]) if (atr_a[i] > 0 and close[i] > 0) else 0.02
                e_oi = float(oi_arr[i]) if (oi_arr is not None and not np.isnan(oi_arr[i])) else 0.0
    return pd.DataFrame(trades)


def anchor_check(df7h, sig, d1m):
    """§15.2 동치앵커: fib_loop(TS·7h체결·trend_flip) ≡ run_strategy. 거래수·총R 대조."""
    eng = TS.run_strategy(df7h, sig, 0, "none", 0.8, gate_mode="er", gate_er=0.45,
                          split_mode="A", split_n=3, fib=FIB)
    ER = pd.DataFrame(eng)
    mine = fib_loop(df7h, sig, d1m, ext_side=None, use_trend_flip=True, fill_1m=False,
                    lev=TS.LEVERAGE, cost=TS.COST, tf_min=420)
    _p(f"[앵커] run_strategy 거래 {len(ER)} / fib_loop(7h) 거래 {len(mine)}  "
       f"| 총R 엔진 {ER['R'].sum():+.4f} vs 루프 {mine['R'].sum():+.4f}  "
       f"| 일치={'O' if (len(ER)==len(mine) and abs(ER['R'].sum()-mine['R'].sum())<1e-6) else 'X'}")
    return len(ER) == len(mine) and abs(ER['R'].sum() - mine['R'].sum()) < 1e-6


def sized(T):
    """사이징 sat×soi(스펙 §2) 적용한 거래수익 + 월복리 시리즈 반환."""
    if len(T) == 0: return T.assign(rs=[]), pd.Series(dtype=float)
    med = T.atr_pct.median()
    sat = np.clip(med / T.atr_pct.replace(0, med), 0.25, 1.0)
    soi = np.clip(1 - 0.3 * np.maximum(0, T.oi_z - 1.5), 0.25, 1.0)
    T = T.copy(); T["rs"] = T.R * sat * soi
    T["m"] = pd.to_datetime(T.et).dt.to_period("M")
    return T, T.groupby("m").rs.apply(lambda x: (1 + x).prod() - 1)


def mstat(m):
    if len(m) == 0: return 0.0, 0.0, 0.0
    eq = np.cumprod(1 + m); tot = (eq[-1] - 1) * 100
    mdd = ((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq)).min() * 100
    cagr = ((1 + tot / 100) ** (12 / len(m)) - 1) * 100
    return tot, mdd, cagr


def cpcv_p25(port_m):
    g6 = np.array_split(np.arange(len(port_m)), 6); cg = []
    for c in itertools.combinations(range(6), 2):
        te = np.sort(np.concatenate([g6[k] for k in c])); _, _, cc = mstat(port_m[te]); cg.append(cc)
    cg = np.array(cg); return np.percentile(cg, 25), cg.min(), 100 * (cg < 0).mean()


def main():
    d1m = load_1m()
    doi = pd.to_numeric(d1m["oi_zscore_24h"], errors="coerce")
    fund_pref = load_funding()
    df7h = TS.resample_tf(d1m[["open", "high", "low", "close"]], 420); sig7 = TS.compute_signals(df7h)
    _p(f"[데이터] 1m {len(d1m)} | 7h봉 {len(df7h)} | 실펀딩 {len(fund_pref[0])}건")
    if not anchor_check(df7h, sig7, d1m):
        _p("[중단] 동치앵커 실패 — 루프가 엔진과 불일치. 정지(§15.2)."); return

    # ── TS 스트림: 엔진조건 + 피보스텝업 + 1m 청산체결 + er≥0.40 필터 + 실펀딩 ──
    oi7 = doi.reindex(df7h.index, method="ffill").values
    TSr = fib_loop(df7h, sig7, d1m, ext_side=None, use_trend_flip=True, fill_1m=True,
                   lev=1.0, cost=COST, er=sig7["er"], er_gate=0.40, tf_min=420, oi_arr=oi7, fund_pref=fund_pref)
    # ── REV 스트림: combo 방향 + ★진입정렬(눌림목 확정 후 진입) + 피보스텝업 + 1m 체결 + 실펀딩 ──
    df8h = TS.resample_tf(d1m[["open", "high", "low", "close"]], 480); sig8 = TS.compute_signals(df8h)
    _, S, _ = V.build(V.find_data())
    sidx = S.index.tz_localize(None)
    side8 = pd.Series(S["side"].values, index=sidx).reindex(df8h.index, fill_value=0).values.astype(int)
    oi8 = pd.Series(S["oi_z"].values, index=sidx).reindex(df8h.index).values
    REVr = fib_loop(df8h, sig8, d1m, ext_side=side8, use_trend_flip=False, fill_1m=True,
                    lev=1.0, cost=COST, tf_min=480, oi_arr=oi8, fund_pref=fund_pref,
                    align_pivot=True, arm_bars=6)

    TSr.to_csv(os.path.join(HERE, "ledger_ts_1m.csv"), index=False, encoding="utf-8-sig")
    REVr.to_csv(os.path.join(HERE, "ledger_rev_1m.csv"), index=False, encoding="utf-8-sig")

    TSs, tsm = sized(TSr); REVs, revm = sized(REVr)
    _p(f"\n[스트림 — 피보스텝업·1m 실체결·사이징]")
    for nm, T, mser in [("TS(7h)", TSs, tsm), ("REV(8h)", REVs, revm)]:
        tot, mdd, _ = mstat(mser.values)
        rc = T.reason.value_counts().to_dict() if len(T) else {}
        _p(f"  {nm:<8} 거래 {len(T):<4} 승률 {100*(T.R>0).mean() if len(T) else 0:4.0f}% "
           f"거래평균 {T.R.mean()*100 if len(T) else 0:+.3f}% | 월복리 {tot:+.0f}% MDD {mdd:.1f}% | 청산 {rc}")

    # ── 블렌드 20/80 월복리 + 노출 ──
    allm = sorted(set(tsm.index) | set(revm.index))
    ts_s = tsm.reindex(allm, fill_value=0.0).values; rev_s = revm.reindex(allm, fill_value=0.0).values
    corr = np.corrcoef(ts_s, rev_s)[0, 1]
    port = 0.2 * ts_s + 0.8 * rev_s
    _p(f"\n[블렌드 TS20/REV80 월복리] 월상관 {corr:+.2f} | 개월 {len(allm)}")
    _p(f"{'노출':>5}{'복리%':>9}{'MDD%':>8}{'CAGR%':>8}{'CPCVp25':>9}{'최악':>8}{'음수%':>6}{'-20내':>6}")
    for e in [0.5, 1.0, 1.2, 1.5, 2.0]:
        tot, mdd, cagr = mstat(port * e); p25, worst, neg = cpcv_p25(port * e)
        ok = "O" if (tot > 0 and p25 > 0 and mdd > -20) else "X"
        _p(f"{e:>5.1f}{tot:>+9.0f}{mdd:>+8.1f}{cagr:>+8.1f}{p25:>+9.1f}{worst:>+8.1f}{neg:>5.0f}%{ok:>6}")
    yrs = np.array([int(str(x)[:4]) for x in allm])
    _p("\n[연도별 블렌드@1.2 수익%] " + "  ".join(
        f"{y}:{((1+(port*1.2)[yrs==y]).prod()-1)*100:+.0f}%" for y in sorted(set(yrs))))
    _p("\n[대조] 옛 가짜청산(3% 트레일·시장진입): TS20/REV80@1.2 = +137%/MDD-20.0%/CAGR33.4% (port_lev).")
    _p("[정직] 위는 피보스텝업·진입결정·순차·1m 실체결 정정본. 노출은 OOS칼날이므로 1.2 천장 유지하에 해석.")


if __name__ == "__main__":
    main()
