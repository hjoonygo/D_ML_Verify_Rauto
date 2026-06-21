# -*- coding: utf-8 -*-
# [파일명] test_07Prj_Ch4_RunAWS_Stg8_CausalRecert.py
# 코드길이: 약 230줄 | 내부버전: ch4_stg8_causal_recert_v1
# ─────────────────────────────────────────────────────────────────────────────
# [목적 — 고딩 설명]
#   Stg7 인과(causal) 신호봇이 만든 거래(84건)가 박제 원장(86건, 인트라바 선지식 포함)의
#   알파를 유지하는지 '같은 잣대'로 재인증한다. 잣대는 전부 박제 import(무수정):
#     ① 3층 방어 시뮬 = Ch2 Stg1 test의 sim_one/cpcv_p25/compute_mae_gap_fund (bots/ 동봉 사본,
#        check가 원본과 해시 대조). EXP4×lev15·컷없음·왕복14bp+슬립5bp·MMR티어.
#     ② 듀얼합성 = Ch4 Stg3 NMult test의 load/p_of/comp (devledger 264거래, p=R×EXP×OPVnN×컷,
#        NMULT 0.6 확정). 합성 = 두 봇 거래를 entry_t 시간순 병합 후 $10k 단일계좌 복리,
#        k(노출배분)를 양봇 p에 공통 곱. ※근간 devledger에 exit_t 없음 → 동시보유 일수 계산불가(명시).
#   재현 대조(§2): 박제 원장 86건을 같은 sim_one에 넣어 +148.8%/-13.6%/CPCVp25 0.7093 재현 확인.
#   판정 가이드(캡틴 확정): MDD>-20% 필수 + CPCV-p25>0 필수. 채택/기각은 캡틴 결정.
# [In] Merged_Data_with_Regime_Features.csv / BTCUSDT_funding_history_8h.csv (상위, 엔진 위임)
#      bots/devledger(264) / 박제 ledger(86)
# [Out] (HERE) causal_ledger.csv(84건 동봉용) / recert_summary.csv / dual_k_sweep.csv /
#       recert_compare.png / recert_result.txt
# ==============================================================================
import os, sys, time
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
BOTS = os.path.join(HERE, "bots")
for _p in (HERE, BOTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import SidewayDCA_Stg7_engine as ENG                                        # noqa: E402
import test_07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep as SIM          # noqa: E402  3층시뮬(박제)
import test_07Prj_Ch4_RunAWS_Stg3_NMultSweep as TS                          # noqa: E402  devledger복리(박제)
from rauto_contract import MarketBar                                        # noqa: E402
from bot_sidewaydca_signal import SidewayDCASignalBot                       # noqa: E402

PASTE_LEDGER = os.path.join(HERE, "07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep_ledger.csv")
OUT_LEDGER = os.path.join(HERE, "causal_ledger.csv")
OUT_SUM = os.path.join(HERE, "recert_summary.csv")
OUT_K = os.path.join(HERE, "dual_k_sweep.csv")
OUT_PNG = os.path.join(HERE, "recert_compare.png")
OUT_TXT = os.path.join(HERE, "recert_result.txt")
BASE = {'ret': 1.4880, 'mdd': -0.1361, 'pf': 2.653, 'cpcv': 0.7093}        # 박제 기준치(§9)
EXP_S, LEV_S = 4, 15
K_GRID = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
SDCA_EXP = 4.0


def replay_causal():
    df = ENG.load_1m(ENG.find_data())
    ts = df.index.values.astype('datetime64[ns]').astype('int64')
    o = df['open'].values; h = df['high'].values; l = df['low'].values; c = df['close'].values
    v = df['volume'].values if 'volume' in df.columns else np.ones(len(df))
    ar = df['atr_ratio'].values if 'atr_ratio' in df.columns else np.full(len(df), np.nan)
    oz = df['oi_zscore_24h'].values if 'oi_zscore_24h' in df.columns else np.full(len(df), np.nan)
    bot = SidewayDCASignalBot(); bot.on_init({})
    t0 = time.time()
    for i in range(len(ts)):
        bot.on_bar(MarketBar(ts=int(ts[i]), o=float(o[i]), h=float(h[i]), l=float(l[i]),
                             c=float(c[i]), v=float(v[i]),
                             aux={'atr_ratio': float(ar[i]), 'oi_zscore_24h': float(oz[i])}))
    bot.flush_partial()
    print(f"[replay] 인과봇 {len(bot.trades)}건 ({time.time()-t0:.0f}s)")
    return df, bot.trades


def enrich(trades, df1m, ft, fr):
    # R = 엔진 공식(Ch2 Stg1 89줄과 동일식): pos×가격수익 − 왕복비용×pos − 펀딩×pos
    out = []
    for t in trades:
        sd = int(t['side'])
        pos = 1.0 if sd == 1 else ENG.SHORT_SIZE
        e_ns = int(pd.Timestamp(t['entry_t']).value); x_ns = int(pd.Timestamp(t['exit_t']).value)
        fsum = ENG.funding_sum(ft, fr, e_ns, x_ns) if ft is not None else None
        fund = (ENG.FUND_8H * int(np.floor(x_ns / 3.6e12 / 8.0) - np.floor(e_ns / 3.6e12 / 8.0))
                if fsum is None else sd * float(fsum))
        R = pos * (sd * (t['exit'] - t['entry']) / t['entry']) - ENG.COST_SIDE * 2 * pos - fund * pos
        out.append({'entry_t': pd.Timestamp(t['entry_t']), 'exit_t': pd.Timestamp(t['exit_t']),
                    'side': sd, 'entry': float(t['entry']), 'exit': float(t['exit']), 'R': R,
                    'reason': t['reason'], 'bars': t['bars'], 'scen': t['scen'],
                    'year': pd.Timestamp(t['exit_t']).year, 'nfilled': t['nfilled']})
    return out


def arrays_from(trades):
    R = np.array([t['R'] for t in trades], float)
    MAE = np.array([t['mae'] for t in trades], float)
    GAP = np.array([t['max_gap'] for t in trades], float)
    FUND = np.array([t['fund'] for t in trades], float)
    POS = np.array([t['pos'] for t in trades], float)
    return R, MAE, GAP, FUND, R > 0, POS


def arrays_from_csv(path):
    d = pd.read_csv(path)
    return (d['R'].values.astype(float), d['mae'].values.astype(float),
            d['max_gap'].values.astype(float), d['fund'].values.astype(float),
            d['R'].values.astype(float) > 0, d['pos'].values.astype(float)), d


def fmt(r, cpcv):
    return {'ret_pct': round(r['ret'] * 100, 1), 'mdd_pct': round(r['mdd'] * 100, 1),
            'PF': r['PF'], 'worst_pct': round(r['worst'] * 100, 1),
            'n_cut': r['n_cut'], 'n_liq': r['n_liq'], 'cpcv_p25_pct': round(cpcv * 100, 1) if cpcv is not None else None}


def main():
    print("[Stg8] 인과 알파 재인증 — 박제 3층시뮬 무수정 적용 + 듀얼합성 k스윕")
    df1m, raw = replay_causal()
    ft = fr = None
    fp = ENG.find_funding()
    if fp is not None:
        ft, fr = ENG.load_funding(fp); print(f"[funding] REAL({len(ft)}건)")
    trades = enrich(raw, df1m, ft, fr)
    trades, st = SIM.compute_mae_gap_fund(trades, df1m, ft, fr, ENG.TF_MIN)   # 박제 — R재구성 교차검증 포함
    print(f"[교차검증] R재구성 불일치 {st['pos_mismatch']}건(★0이어야) | MAE물리위반 {st['violate']}건(★0)")

    # 인과 원장 저장(동봉 산출물)
    pd.DataFrame([{'entry_t': t['entry_t'].strftime('%Y-%m-%d %H:%M'),
                   'exit_t': t['exit_t'].strftime('%Y-%m-%d %H:%M'), 'side': t['side'],
                   'pos': round(t['pos'], 4), 'year': t['year'], 'scen': t['scen'],
                   'reason': t['reason'], 'entry_price': round(t['entry'], 2),
                   'exit_price': round(t['exit'], 2), 'R': round(t['R'], 6),
                   'fund': round(t['fund'], 6), 'mae': round(t['mae'], 6),
                   'max_gap': round(t['max_gap'], 6), 'bars': t['bars'],
                   'nfilled': t['nfilled']} for t in trades]).to_csv(OUT_LEDGER, index=False, encoding='utf-8-sig')

    # ① 재현 대조: 박제 원장 86건 → 기준치 재현(§2 결과재현)
    (Rp, MAEp, GAPp, FUNDp, RPOSp, POSp), led = arrays_from_csv(PASTE_LEDGER)
    rp = SIM.sim_one(Rp, MAEp, GAPp, FUNDp, RPOSp, POSp, EXP_S, LEV_S, None)
    cp = SIM.cpcv_p25(Rp, MAEp, GAPp, FUNDp, RPOSp, POSp, EXP_S, LEV_S, None)
    rep = fmt(rp, cp)
    rep_ok = (abs(rp['ret'] - BASE['ret']) < 0.02 and abs(rp['mdd'] - BASE['mdd']) < 0.01
              and abs((cp or 0) - BASE['cpcv']) < 0.02)
    print(f"[재현] 박제 86건: ret {rep['ret_pct']}% / MDD {rep['mdd_pct']}% / PF {rep['PF']} / "
          f"CPCVp25 {rep['cpcv_p25_pct']}% → 기준치 일치 {'OK' if rep_ok else '★불일치'}")

    # ② 인과 84건 → 동일 시뮬
    Rc, MAEc, GAPc, FUNDc, RPOSc, POSc = arrays_from(trades)
    rc = SIM.sim_one(Rc, MAEc, GAPc, FUNDc, RPOSc, POSc, EXP_S, LEV_S, None)
    cc = SIM.cpcv_p25(Rc, MAEc, GAPc, FUNDc, RPOSc, POSc, EXP_S, LEV_S, None)
    cau = fmt(rc, cc)
    # 참고: 거래단위 -10% 손실허용컷(스톱아웃-10%의 시뮬 내 최근접 아날로그 — 피크대비 플로팅 스톱아웃은 박제시뮬에 없음)
    rc10 = SIM.sim_one(Rc, MAEc, GAPc, FUNDc, RPOSc, POSc, EXP_S, LEV_S, -0.10)
    gate_mdd = rc['mdd'] > -0.20
    gate_cpcv = (cc or -1) > 0
    print(f"[인과] {len(trades)}건: ret {cau['ret_pct']}% / MDD {cau['mdd_pct']}% / PF {cau['PF']} / "
          f"CPCVp25 {cau['cpcv_p25_pct']}% | 게이트: MDD>-20% {'PASS' if gate_mdd else 'FAIL'} · "
          f"CPCVp25>0 {'PASS' if gate_cpcv else 'FAIL'}")

    rows = [dict(cell='PASTE_repro(86)', **rep), dict(cell='CAUSAL(84)', **cau),
            dict(cell='CAUSAL_cut-10(참고)', **fmt(rc10, None)),
            dict(cell='BASELINE(§9)', ret_pct=148.8, mdd_pct=-13.61, PF=2.653, worst_pct=None,
                 n_cut=None, n_liq=None, cpcv_p25_pct=70.9)]
    pd.DataFrame(rows).to_csv(OUT_SUM, index=False, encoding='utf-8-sig')

    # ③ 듀얼합성 k스윕 — TrendStack devledger(박제 p_of, NMULT0.6) + SDCA(박제86/인과84) 비교
    d_ts = TS.load()
    p_ts = TS.p_of(d_ts, 0.6)
    t_ts = d_ts['entry_t'].values
    def dual(p_sdca, t_sdca, k):
        p_all = np.concatenate([p_ts * k, p_sdca * k])
        t_all = np.concatenate([t_ts.astype('datetime64[ns]'), t_sdca.astype('datetime64[ns]')])
        order = np.argsort(t_all, kind='stable')
        ret, mdd, bal = TS.comp(p_all[order])          # 박제 comp($10k 복리)
        return ret, mdd
    t_cau = np.array([t['entry_t'].to_datetime64() for t in trades])
    p_cau = Rc * SDCA_EXP
    t_pas = pd.to_datetime(led['entry_t']).values
    p_pas = Rp * SDCA_EXP
    krows = []
    for k in K_GRID:
        r1, m1 = dual(p_pas, t_pas, k)
        r2, m2 = dual(p_cau, t_cau, k)
        krows.append(dict(k=k, paste_ret=round(r1, 1), paste_mdd=round(m1, 1),
                          causal_ret=round(r2, 1), causal_mdd=round(m2, 1)))
        print(f"[dual k={k}] 박제 {r1:8.1f}%/{m1:6.1f}%  |  인과 {r2:8.1f}%/{m2:6.1f}%")
    pd.DataFrame(krows).to_csv(OUT_K, index=False, encoding='utf-8-sig')

    # 그래프(영문 라벨): 좌=박제vs인과 에쿼티, 우=k스윕
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(13, 4.6))
        for lbl, RR, col in [('paste 86 (intrabar-foreknowledge)', Rp, '#888888'),
                             ('causal 84 (live-true)', Rc, '#0F6E56')]:
            bal = 10000.0 * np.cumprod(1 + RR * SDCA_EXP)
            ax[0].plot(np.arange(1, len(RR) + 1), bal, label=lbl, color=col)
        ax[0].set_title('SidewayDCA Equity by Trade # (EXP4xLev15, $10k)')
        ax[0].set_xlabel('Trade #'); ax[0].set_ylabel('Balance $'); ax[0].legend(); ax[0].grid(alpha=.3)
        ks = [r['k'] for r in krows]
        ax[1].plot(ks, [r['paste_ret'] for r in krows], 'o--', color='#888888', label='dual ret% (paste)')
        ax[1].plot(ks, [r['causal_ret'] for r in krows], 'o-', color='#0F6E56', label='dual ret% (causal)')
        ax2 = ax[1].twinx()
        ax2.plot(ks, [r['paste_mdd'] for r in krows], 's--', color='#C99', label='MDD% (paste)')
        ax2.plot(ks, [r['causal_mdd'] for r in krows], 's-', color='#C0392B', label='MDD% (causal)')
        ax2.axhline(-20, ls=':', color='red')
        ax[1].set_title('Dual Synthesis k-Sweep (TrendStack 264 + SidewayDCA)')
        ax[1].set_xlabel('k (exposure allocation)'); ax[1].legend(loc='upper left'); ax2.legend(loc='lower right')
        plt.tight_layout(); plt.savefig(OUT_PNG, dpi=110)
        print(f"[그래프] {os.path.basename(OUT_PNG)}")
    except Exception as e:
        print(f"[그래프] 생략: {e}")

    n_pass = int(rep_ok) + int(st['pos_mismatch'] == 0) + int(st['violate'] == 0) + int(gate_mdd) + int(gate_cpcv)
    verdict = (f"VERDICT {n_pass}/5 | 재현{'OK' if rep_ok else 'X'} R교차{st['pos_mismatch']} MAE위반{st['violate']} | "
               f"인과(84) ret {cau['ret_pct']}% MDD {cau['mdd_pct']}% PF {cau['PF']} CPCVp25 {cau['cpcv_p25_pct']}% "
               f"(기준 148.8/-13.61/2.653/70.9) | 게이트 MDD{'PASS' if gate_mdd else 'FAIL'}·CPCV{'PASS' if gate_cpcv else 'FAIL'} | "
               f"동시보유: devledger에 exit_t 없어 계산불가(Stg6 zip 필요)")
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write(verdict + "\n\n[k스윕]\n" + pd.DataFrame(krows).to_string(index=False) + "\n")
    print(verdict)


if __name__ == "__main__":
    main()
