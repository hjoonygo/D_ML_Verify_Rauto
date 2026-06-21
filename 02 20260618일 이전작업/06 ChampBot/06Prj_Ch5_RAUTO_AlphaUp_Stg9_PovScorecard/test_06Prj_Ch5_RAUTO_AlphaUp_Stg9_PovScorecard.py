# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch5_RAUTO_AlphaUp_Stg9_PovScorecard.py
# 코드길이: 약 280줄 | 내부버전: RAUTO_AlphaUp_06_Ch5_Stg9_PovScorecard | 로직 전체 출력
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   엔진 무수정. 추세봇에 POV 사이징(일치×2, 불일치×0.25)을 적용한 뒤
#   Stg7처럼 세 축(장세/연도/롱숏)으로 5지표(PF·수익률·손익비·거래수·수익금) 성적표를 만든다.
#   ★사이징 정의(Stg8 확정): 추세봇 진입시점의 횡보봇 POV(dev=POC편차)로
#     - 방향일치(롱&dev<0 또는 숏&dev>0): R *= 2.0
#     - 방향반대(롱&dev>0 또는 숏&dev<0): R *= 0.25
#     - dev=NaN(POV판단불가): R *= 1.0(중립)
#   진입 자체는 안 막음(잭팟 보존). dev는 진입시점 과거기반 → 미래참조 없음.
#   [비교] 같은 거래의 사이징 전(base)과 후(POV)를 나란히 집계해 효과를 본다.
#   [수익금] 추세봇 명목 $50,000 고정단리: profit = Σ(R*size) * NOMINAL (Stg7과 동일 노출규칙).
#     ※size 평균이 1이 아니므로(일치×2 다수) 절대수익금은 노출확대 포함 — base와 체질비교용.
#   [TF] 추세봇 기본 7h(=420). label_smc_8로 장세 사후 매칭(매매 미사용).
#
# [PATH] 실행: D:\ML\Verify\06Prj_..._Stg9_PovScorecard\ . 데이터: 상위 D:\ML\Verify\ (4종).
# [OUTPUT] pov_by_regime.csv / pov_by_year.csv / pov_by_side.csv / pov_all_trades.csv / summary.csv + .stg9_metric
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE); BOTS = os.path.join(HERE, "bots")
COST_RT = 0.0014
M_AGREE = 2.0; M_OPPO = 0.25
REGIME_MAP = {'uptrend': 0, 'downtrend': 1, 'volatile_range': 2, 'dead_range': 3}
REGIME_NAME = {0: 'uptrend', 1: 'downtrend', 2: 'volatile_range', 3: 'dead_range', -1: 'unknown'}


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
NOMINAL = champ.NOMINAL


def metrics(R):
    R = np.asarray(R, float); n = len(R)
    if n == 0:
        return dict(n=0, PF=0.0, ret_pct=0.0, payoff=0.0, win_pct=0.0)
    win = R[R > 0]; los = R[R < 0]; gp = float(win.sum()); gl = float(-los.sum())
    pf = round(gp / gl, 3) if gl > 0 else (999.0 if gp > 0 else 0.0)
    payoff = round(win.mean() / -los.mean(), 3) if len(win) and len(los) else 0.0
    return dict(n=n, PF=pf, ret_pct=round(R.sum() * 100, 2), payoff=payoff, win_pct=round(100 * len(win) / n, 1))


def main():
    print(f"[Stg9] 추세봇 POV사이징(일치×{M_AGREE}, 불일치×{M_OPPO}) 성적표")
    open(os.path.join(HERE, ".run_start"), "w").close()
    if DATA is None:
        pd.DataFrame([{'x': '데이터없음'}]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig'); return
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

    # 장세 라벨
    head = list(pd.read_csv(DATA, nrows=1).columns)
    lbl = next((c for c in head if c.startswith('label_smc_8')), None) or next((c for c in head if c.startswith('label_smc')), None)
    lab = pd.read_csv(DATA, usecols=['timestamp', lbl], index_col='timestamp', parse_dates=True)
    if getattr(lab.index, 'tz', None) is not None:
        lab.index = lab.index.tz_localize(None)
    lab = lab.sort_index()

    # 추세봇 거래 (7h)
    TF = champ.TF_MIN
    df1m = champ.load_data(DATA); df7 = champ.resample_tf(df1m, TF); sig = champ.compute_signals(df7)
    idx7 = df7.index; oi7 = champ.load_oi_8h(OIPATH, idx7); bb7 = champ.load_bb_8h(DATA, idx7)
    reg7 = lab[lbl].resample(f"{TF}min", label='left', closed='left').last().reindex(idx7).map(REGIME_MAP).values.astype('float64')
    ttr = champ.run_strategy(df7, sig, 0, 'none', 0.8, gate_mode='er', gate_er=0.45,
                             dz_oi=oi7, gate_bb=bb7, fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)

    # POV(dev) 배열 — 같은 7h
    s1 = sdca.load_1m(DATA); s8 = sdca.resample_tf(s1, TF); ssig = sdca.precompute(s8)
    poc = ssig['poc']; atr = ssig['atr']; close8 = s8['close'].values; sidx = s8.index
    dev_arr = np.full(len(sidx), np.nan)
    for k in range(len(sidx)):
        if not np.isnan(poc[k]) and not np.isnan(atr[k]) and atr[k] > 0:
            dev_arr[k] = (close8[k] - poc[k]) / atr[k]

    rows = []
    for t in ttr:
        R = t['side'] * (t['exit'] - t['entry']) / t['entry'] - COST_RT - fund_pay(t['side'], t['entry_t'], t['exit_t'])
        pos = sidx.searchsorted(pd.Timestamp(t['entry_t'])) - 1
        dv = dev_arr[pos] if 0 <= pos < len(dev_arr) else np.nan
        side = t['side']
        if np.isnan(dv):
            pov = '중립'; size = 1.0
        elif (side > 0 and dv < 0) or (side < 0 and dv > 0):
            pov = '일치'; size = M_AGREE
        else:
            pov = '반대'; size = M_OPPO
        ipos = lab.index.searchsorted(pd.Timestamp(t['entry_t'])) - 1
        rg = REGIME_NAME[int(reg7[lab.index.searchsorted(pd.Timestamp(t['entry_t']))-1])] if False else REGIME_NAME[int(reg7[pos])] if (0 <= pos < len(reg7) and not np.isnan(reg7[pos])) else 'unknown'
        rows.append(dict(side='롱' if side > 0 else '숏', year=pd.Timestamp(t['entry_t']).year,
                         regime=rg, pov=pov, size=size,
                         R_base=float(R), R_pov=float(R * size), entry_t=str(t['entry_t'])))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "pov_all_trades.csv"), index=False, encoding='utf-8-sig')
    print(f"[추세봇] {len(df)}건 | POV분포 {dict(df.pov.value_counts())}")

    def agg(key, fname):
        out = []
        for grp, g in df.groupby(key):
            mb = metrics(g.R_base.values); mp = metrics(g.R_pov.values)
            row = {key: grp, 'n': mb['n'],
                   'PF_base': mb['PF'], 'PF_pov': mp['PF'],
                   'ret_base': mb['ret_pct'], 'ret_pov': mp['ret_pct'],
                   'payoff_base': mb['payoff'], 'payoff_pov': mp['payoff'],
                   'win_pct': mb['win_pct'],
                   'profit_base': round(float(g.R_base.sum() * NOMINAL), 0),
                   'profit_pov': round(float(g.R_pov.sum() * NOMINAL), 0)}
            out.append(row)
        d = pd.DataFrame(out); d.to_csv(os.path.join(HERE, fname), index=False, encoding='utf-8-sig'); return d

    by_reg = agg('regime', "pov_by_regime.csv")
    by_year = agg('year', "pov_by_year.csv")
    by_side = agg('side', "pov_by_side.csv")

    mb = metrics(df.R_base.values); mp = metrics(df.R_pov.values)
    prof_b = round(float(df.R_base.sum() * NOMINAL), 0); prof_p = round(float(df.R_pov.sum() * NOMINAL), 0)
    n_ag = int((df.pov == '일치').sum()); n_op = int((df.pov == '반대').sum()); n_nu = int((df.pov == '중립').sum())
    verdict = (f"VERDICT Stg9 | 추세봇 POV사이징(일치×{M_AGREE} 반대×{M_OPPO}) | 거래{len(df)}(일치{n_ag}/반대{n_op}/중립{n_nu}) | "
               f"[전체] base: PF{mb['PF']} 승률{mb['win_pct']}% 손익비{mb['payoff']} 수익률{mb['ret_pct']}% ${prof_b} "
               f"-> POV: PF{mp['PF']} 승률{mp['win_pct']}% 손익비{mp['payoff']} 수익률{mp['ret_pct']}% ${prof_p}")
    print("[verdict] " + verdict)

    pd.DataFrame([dict(sec=verdict),
                  dict(sec=f"[장세별] {by_reg.to_dict('records')}"),
                  dict(sec=f"[연도별] {by_year.to_dict('records')}"),
                  dict(sec=f"[롱숏별] {by_side.to_dict('records')}")
                  ]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
    with open(os.path.join(HERE, ".stg9_metric"), "w", encoding="utf-8") as f:
        f.write(f"n_all={len(df)}\nn_agree={n_ag}\nn_oppo={n_op}\nn_neutral={n_nu}\n"
                f"base_PF={mb['PF']}\nbase_win={mb['win_pct']}\nbase_payoff={mb['payoff']}\nbase_ret={mb['ret_pct']}\nbase_profit={prof_b}\n"
                f"pov_PF={mp['PF']}\npov_win={mp['win_pct']}\npov_payoff={mp['payoff']}\npov_ret={mp['ret_pct']}\npov_profit={prof_p}\n"
                f"m_agree={M_AGREE}\nm_oppo={M_OPPO}\nlabel={lbl}\nhas_label_in_feats=False\nfunding={'REAL' if ft is not None else 'NONE'}\n")
    print("[save] pov_by_regime / pov_by_year / pov_by_side / pov_all_trades / summary.csv")


if __name__ == "__main__":
    main()
