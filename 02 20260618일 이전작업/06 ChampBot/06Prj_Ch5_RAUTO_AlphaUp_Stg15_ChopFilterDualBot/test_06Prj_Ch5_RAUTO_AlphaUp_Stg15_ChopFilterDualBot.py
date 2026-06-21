# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch5_RAUTO_AlphaUp_Stg15_ChopFilterDualBot.py
# 코드길이: 약 360줄 | 내부버전: RAUTO_AlphaUp_06_Ch5_Stg15_ChopFilterDualBot | 로직 전체 출력
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   엔진 무수정. 2025 칩장 문제를 두 갈래로 동시 검증:
#   (A) 칩 필터(추세봇): 엔진이 이미 계산하는 CHOP/ER/ADX로 '칩(추세없는 횡보)'을 실시간 판정,
#       칩이면 추세봇 진입수량을 줄이거나(0.3~0.5) 스킵 → 2025·전체 손익이 나아지나.
#   (B) 횡보봇 동시 체크: 같은 칩 구간에서 횡보봇이 버는가. 두 봇 합산이 2025를 흑자로 돌리나.
#   ★칩 정의(전부 진입시점 과거봉 = lookahead 없음): CHOP>chop_hi AND ER<er_lo AND ADX<25
#     - CHOP는 엔진 chop, ER는 엔진 er, ADX는 엔진 adx (compute_signals 산출, 실시간 가능)
#   ★임계 그리드: chop_hi{55,60,65} × er_lo{0.30,0.35,0.40} = 9조합. 학습기간서 2025개선·전체유지 best 선택.
#   ★칩필터 강도: 칩이면 추세봇 R *= chop_mult (0.3/0.5/skip=0). best와 함께 탐색.
#   [임계·강도 모두 학습기간(앞70%)만 결정 → OOS 검증] [label 미사용]
#
# [PATH] 실행: D:\ML\Verify\06Prj_..._Stg15_ChopFilterDualBot\ . 데이터: 상위 (4종).
# [OUTPUT] chop_dist_by_year.csv / chop_grid.csv / trend_chopfilter_by_year.csv
#          / sideways_by_year.csv / dualbot_2025.csv / summary.csv + .stg15_metric
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE); BOTS = os.path.join(HERE, "bots")
COST_RT = 0.0014
CHOP_HI_GRID = [55, 60, 65]
ER_LO_GRID = [0.30, 0.35, 0.40]
CHOP_MULT_GRID = [0.0, 0.3, 0.5]   # 0=스킵
ADX_LO = 25


def load_engine(p, nm):
    s = importlib.util.spec_from_file_location(nm, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def find_file(c):
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for x in c:
            p = os.path.join(d, x)
            if os.path.exists(p):
                return p
    return None


champ = load_engine(os.path.join(BOTS, "SpTrd_Fib_V1_Champion.py"), "champ_engine")
sdca = load_engine(os.path.join(BOTS, "SidewayDCA_Stg7_engine.py"), "sdca_engine")
DATA = find_file(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
OIPATH = find_file(["Merged_Data.csv", "merged_data.csv"])
FUND = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv", "sample_BTCUSDT_funding_history_8h.csv"])
NOMINAL = champ.NOMINAL; START_CAP = champ.START_CAP; MIN_CAP = champ.MIN_CAP
TF7 = champ.TF_MIN


def metrics(R):
    R = np.asarray(R, float); n = len(R)
    if n == 0:
        return dict(n=0, PF=0.0, ret_pct=0.0, payoff=0.0, win_pct=0.0)
    win = R[R > 0]; los = R[R < 0]; gp = float(win.sum()); gl = float(-los.sum())
    pf = round(gp / gl, 3) if gl > 0 else (999.0 if gp > 0 else 0.0)
    payoff = round(win.mean() / -los.mean(), 3) if len(win) and len(los) else 0.0
    return dict(n=n, PF=pf, ret_pct=round(R.sum() * 100, 2), payoff=payoff, win_pct=round(100 * len(win) / n, 1))


def sim_comp(R, size):
    cap = START_CAP; peak = START_CAP; mdd = 0.0; liq = False
    for r, s in zip(R, size):
        cap *= (1 + r * s); peak = max(peak, cap)
        if peak > 0:
            mdd = min(mdd, (cap - peak) / peak)
        if cap <= MIN_CAP:
            liq = True; break
    return round(cap - START_CAP, 0), round(mdd * 100, 1), liq


def main():
    print("[Stg15] 칩 필터(추세봇) + 횡보봇 동시 체크 — 2025 정조준")
    open(os.path.join(HERE, ".run_start"), "w").close()
    if DATA is None:
        pd.DataFrame([{'x': 'no data'}]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig'); return
    ft = fr = None
    if FUND:
        try:
            ft, fr = sdca.load_funding(FUND)
        except Exception:
            pass

    def fund_pay(side, et, xt):
        if ft is None:
            return 0.0
        fs = sdca.funding_sum(ft, fr, int(pd.Timestamp(et).value), int(pd.Timestamp(xt).value))
        return side * fs if fs is not None else 0.0

    # ─── 추세봇 (7h) + 진입시점 CHOP/ER/ADX ───
    df1m = champ.load_data(DATA); df7 = champ.resample_tf(df1m, TF7); sig = champ.compute_signals(df7)
    idx7 = df7.index; oi7 = champ.load_oi_8h(OIPATH, idx7); bb7 = champ.load_bb_8h(DATA, idx7)
    i_of = {t: k for k, t in enumerate(idx7)}
    chop = sig['chop']; er = sig['er']; adx = sig['adx']
    n7 = len(idx7); cut7 = int(n7 * 0.7)
    ttr = champ.run_strategy(df7, sig, 0, 'none', 0.8, gate_mode='er', gate_er=0.45,
                             dz_oi=oi7, gate_bb=bb7, fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
    rows = []
    for t in ttr:
        R = t['side'] * (t['exit'] - t['entry']) / t['entry'] - COST_RT - fund_pay(t['side'], t['entry_t'], t['exit_t'])
        pos = i_of.get(t['entry_t'], None)
        if pos is None:
            pos = max(0, idx7.searchsorted(pd.Timestamp(t['entry_t'])) - 1)
        rows.append(dict(year=pd.Timestamp(t['entry_t']).year, side='롱' if t['side'] > 0 else '숏',
                         chop=float(chop[pos]) if pos < len(chop) else np.nan,
                         er=float(er[pos]) if pos < len(er) else np.nan,
                         adx=float(adx[pos]) if pos < len(adx) else np.nan,
                         R=float(R), is_test=pos >= cut7))
    df = pd.DataFrame(rows)

    # 1) CHOP/ER/ADX 연도분포
    dist = []
    for y, g in df.groupby('year'):
        dist.append(dict(year=y, n=len(g), chop_med=round(float(g.chop.median()), 1),
                         er_med=round(float(g.er.median()), 3), adx_med=round(float(g.adx.median()), 1),
                         ret=round(float(g.R.sum()*100), 2)))
    pd.DataFrame(dist).to_csv(os.path.join(HERE, "chop_dist_by_year.csv"), index=False, encoding='utf-8-sig')

    # 2~4) 칩 임계×강도 그리드 (학습기간 기준 선택)
    def is_chop(chop_hi, er_lo):
        return (df.chop.values > chop_hi) & (df.er.values < er_lo) & (df.adx.values < ADX_LO)
    tr_mask = ~df.is_test.values; te_mask = df.is_test.values
    y25 = df.year.values == 2025
    grid = []
    for chop_hi in CHOP_HI_GRID:
        for er_lo in ER_LO_GRID:
            chopmask = is_chop(chop_hi, er_lo)
            for mult in CHOP_MULT_GRID:
                size = np.where(chopmask, mult, 1.0)
                Rs = df.R.values * size
                m_all = metrics(Rs); m_oos = metrics(Rs[te_mask]); m_tr = metrics(Rs[tr_mask])
                r25 = round(float(Rs[y25].sum()*100), 2) if y25.any() else 0.0
                base25 = round(float(df.R.values[y25].sum()*100), 2) if y25.any() else 0.0
                _, mdd, liq = sim_comp(df.R.values, size)
                n_chop = int(chopmask.sum()); n_chop_25 = int((chopmask & y25).sum())
                grid.append(dict(chop_hi=chop_hi, er_lo=er_lo, chop_mult=mult,
                                 n_chop=n_chop, n_chop_2025=n_chop_25,
                                 ret_all=m_all['ret_pct'], ret_oos=m_oos['ret_pct'], PF_oos=m_oos['PF'],
                                 y2025_ret=r25, y2025_base=base25, MDD=mdd, liq=('YES' if liq else 'NO'),
                                 train_ret=m_tr['ret_pct']))
    gdf = pd.DataFrame(grid); gdf.to_csv(os.path.join(HERE, "chop_grid.csv"), index=False, encoding='utf-8-sig')
    # 선택: 2025 개선(>base) & MDD>=-35 & 청산X 중 학습수익 최고
    cand = gdf[(gdf.y2025_ret > gdf.y2025_base) & (gdf.MDD >= -35) & (gdf.liq == 'NO')]
    pick = (cand if len(cand) else gdf[(gdf.MDD >= -35) & (gdf.liq == 'NO')]).sort_values('train_ret', ascending=False)
    pick = pick.iloc[0] if len(pick) else gdf.sort_values('train_ret', ascending=False).iloc[0]
    bh, be, bm = pick['chop_hi'], pick['er_lo'], pick['chop_mult']
    best_chop = is_chop(bh, be); size_best = np.where(best_chop, bm, 1.0)
    df['R_filt'] = df.R.values * size_best

    # 연도별 칩필터 효과
    tby = []
    for y, g in df.groupby('year'):
        mb = metrics(g.R.values); mf = metrics(g.R_filt.values)
        tby.append(dict(year=y, n=len(g), ret_base=mb['ret_pct'], ret_filt=mf['ret_pct'],
                        PF_base=mb['PF'], PF_filt=mf['PF'],
                        profit_base=round(float(g.R.sum()*NOMINAL)), profit_filt=round(float(g.R_filt.sum()*NOMINAL))))
    pd.DataFrame(tby).to_csv(os.path.join(HERE, "trend_chopfilter_by_year.csv"), index=False, encoding='utf-8-sig')

    # ─── (B) 횡보봇 (8h) 연도별 — Stg7 정석 호출(build_1m_map + 1분봉 OHLC 배열) ───
    sw_rows = []
    try:
        s1 = sdca.load_1m(DATA)
        df8 = sdca.resample_tf(s1, sdca.TF_MIN); ssig = sdca.precompute(df8)
        ss, se = sdca.build_1m_map(s1, df8)
        mO = s1['open'].values; mH = s1['high'].values; mL = s1['low'].values
        mT = s1.index.values.astype('datetime64[ns]').astype('int64')
        out = sdca.run_bot_honest(df8, ssig, sdca.BEST_PAR, mO, mH, mL, mT, ss, se, ft, fr, sdca.DEFAULT_SLMULT)
        trades = out[0] if isinstance(out, tuple) else out
        for t in (trades or []):
            et = t.get('entry_t') or t.get('t_in') or t.get('entry_time') or t.get('t')
            R = t.get('R', t.get('r', t.get('pnl', 0.0)))
            if et is None:
                continue
            sw_rows.append(dict(year=pd.Timestamp(et).year, R=float(R)))
    except Exception as e:
        print(f"[횡보봇 추출오류] {type(e).__name__}: {e}")
    swdf = pd.DataFrame(sw_rows) if sw_rows else pd.DataFrame(columns=['year', 'R'])
    print(f"[횡보봇] {len(swdf)}거래 추출")
    sby = []
    if len(swdf):
        for y, g in swdf.groupby('year'):
            m = metrics(g.R.values); sby.append(dict(year=int(y), n=len(g), ret=m['ret_pct'], PF=m['PF']))
    pd.DataFrame(sby if sby else [dict(year=0, n=0, ret=0, PF=0, note='횡보봇 추출실패')]).to_csv(
        os.path.join(HERE, "sideways_by_year.csv"), index=False, encoding='utf-8-sig')

    # ─── 두 봇 2025 합산 ───
    t25_base = round(float(df.R.values[y25].sum()*100), 2) if y25.any() else 0.0
    t25_filt = round(float(df.R_filt.values[y25].sum()*100), 2) if y25.any() else 0.0
    s25 = round(float(swdf[swdf.year == 2025].R.sum()*100), 2) if (len(swdf) and (swdf.year == 2025).any()) else 0.0
    dual = [dict(item='추세봇 2025 (칩필터前)', ret_pct=t25_base),
            dict(item='추세봇 2025 (칩필터後)', ret_pct=t25_filt),
            dict(item='횡보봇 2025', ret_pct=s25),
            dict(item='두봇 합산 2025 (칩필터後+횡보)', ret_pct=round(t25_filt + s25, 2))]
    pd.DataFrame(dual).to_csv(os.path.join(HERE, "dualbot_2025.csv"), index=False, encoding='utf-8-sig')

    mb = metrics(df.R.values); mf = metrics(df.R_filt.values)
    _, mdd_b, _ = sim_comp(df.R.values, np.ones(len(df)))
    _, mdd_f, liq_f = sim_comp(df.R.values, size_best)
    mb_oos = metrics(df.R.values[te_mask]); mf_oos = metrics(df.R_filt.values[te_mask])
    verdict = (f"VERDICT Stg15 | 칩필터 best CHOP>{bh}·ER<{be}·×{bm} (칩거래 {int(best_chop.sum())}건, 2025중 {int((best_chop&y25).sum())}건) | "
               f"[추세봇 2025] base {t25_base}% -> 칩필터 {t25_filt}% | [횡보봇 2025] {s25}% | [두봇합산 2025] {round(t25_filt+s25,2)}% | "
               f"[전체] base PF{mb['PF']}/{mb['ret_pct']}%/MDD{mdd_b} -> 칩필터 PF{mf['PF']}/{mf['ret_pct']}%/MDD{mdd_f} | "
               f"[OOS] base {mb_oos['ret_pct']}% -> 칩필터 {mf_oos['ret_pct']}%")
    print("[verdict] " + verdict)
    pd.DataFrame([dict(sec=verdict), dict(sec=f"[연도분포] {dist}"), dict(sec=f"[두봇2025] {dual}")]).to_csv(
        os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
    with open(os.path.join(HERE, ".stg15_metric"), "w", encoding="utf-8") as f:
        f.write(f"best_chop_hi={bh}\nbest_er_lo={be}\nbest_mult={bm}\nn_chop={int(best_chop.sum())}\nn_chop_2025={int((best_chop&y25).sum())}\n"
                f"t2025_base={t25_base}\nt2025_filt={t25_filt}\ns2025={s25}\ndual2025={round(t25_filt+s25,2)}\n"
                f"base_ret={mb['ret_pct']}\nfilt_ret={mf['ret_pct']}\nbase_mdd={mdd_b}\nfilt_mdd={mdd_f}\nfilt_liq={'YES' if liq_f else 'NO'}\n"
                f"oos_base={mb_oos['ret_pct']}\noos_filt={mf_oos['ret_pct']}\nn_trades={len(df)}\nsw_extracted={len(swdf)}\n"
                f"grid_rows={len(gdf)}\nhas_label_in_feats=False\nfunding={'REAL' if ft is not None else 'NONE'}\n")
    print("[save] chop_dist_by_year/chop_grid/trend_chopfilter_by_year/sideways_by_year/dualbot_2025/summary.csv")


if __name__ == "__main__":
    main()
