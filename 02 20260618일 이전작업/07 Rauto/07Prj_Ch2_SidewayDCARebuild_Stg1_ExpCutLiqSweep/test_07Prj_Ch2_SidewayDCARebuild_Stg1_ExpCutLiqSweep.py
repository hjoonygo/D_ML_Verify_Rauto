# -*- coding: utf-8 -*-
# [test_07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep.py]
# 코드길이: 241줄 | 내부버전: SDCA_ExpCutLiqSweep_v1 (박제엔진 dfdfac43 import) | 로직 축약/생략 없이 전체 출력
# =============================================================================
# [목적] 박제 엔진을 import만(무수정) → TAKER 기준선 거래 생성 → 거래별 MAE/max_gap/fund 1회 계산(1분봉) →
#        그 위에서 노출(EXP)×레버(lev)×손실허용컷(L, 15개) 3층 방어 스윕을 $10,000 복리로 수행.
#        recover/direct 분해(컷이 평균회귀 알파를 죽이나) + 후보군 CPCV-p25(견고성) 산출.
#        ★엔진 1회 + 사후 재사용(TIL 4-5)로 최적화 — 무거운 1분봉 계산은 단 1회.
#
# [경로 — 중요]
#   - 이 파일은 하위폴더(D:\ML\verify\<NAME>) 안에서 실행. 데이터는 한 단계 상위 D:\ML\verify 에 있음.
#   - 데이터 탐색은 박제 엔진 find_data()에 위임(엔진이 D:\ML\verify 절대경로를 탐색목록에 포함).
#   - 결과 CSV는 이 하위폴더(HERE)에 출력 → check.py가 검사 후 분석txt/INDEX를 00WorkHstr로 보냄.
#
# [사용 파일 — In/Out]
#   In : bots/SidewayDCA_Stg7_engine.py (박제, import) / Merged_Data_with_Regime_Features.csv(1분봉) /
#        BTCUSDT_funding_history_8h.csv(실펀딩)
#   Out: <NAME>_ledger.csv (enriched 원장) / <NAME>_sweep.csv (전 조합) / <NAME>_best.csv (후보+CPCV)
#
# [핵심 상수 — In/Out]
#   START=10000  MMR_T1=0.4% MMR_T2=0.5%(명목>$50k) SLIP_BP=5bp COST_RT=14bp(왕복)
#   EXP_GRID 실효노출 / LEV_GRID 레버(청산거리) / CUT_GRID 손실허용한도 -7~-14% 15개(+None=컷없음 기준선)
#   PROD_OI_Z_HI=1.0 (★Guide 강건. 엔진 CFG 0.0 아님)
#
# [함수 — In/Out]
#   compute_mae_gap_fund(trades, df1m, ft, fr, tf_min) -> trades, stats
#       거래별 mae(청산봉 보정·min(구간최악,최종손익))·max_gap(최악 단일봉)·fund(거래별) 부착.
#   sim_one(R,MAE,GAP,FUND,RPOS, EXP, lev, cut_L, idx=None) -> dict
#       한 조합 3층 판정 복리. idx=거래부분집합(CPCV용). Out: cap/ret/mdd/worst/n_cut/recover·direct/n_liq.
#   cpcv_p25(arrays, EXP, lev, cut_L, n_groups=6) -> float
#       6그룹 중 2개 leave-out 15경로의 수익률 p25(견고성 바닥).
#   main() -> 결과 CSV 3종
# =============================================================================

import os, sys
from itertools import combinations
import numpy as np
import pandas as pd

NAME = "07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep"
HERE = os.path.dirname(os.path.abspath(__file__))

# ── 박제 엔진 import (bots/ 하위, 무수정) ──
_ENGDIR = os.path.join(HERE, "bots")
if _ENGDIR not in sys.path:
    sys.path.insert(0, _ENGDIR)
import SidewayDCA_Stg7_engine as eng   # noqa: E402

# ── 상수 (Ch1 sim_levsweep 계승 + 격리 정정) ──
START         = 10000.0
MMR_T1        = 0.004
MMR_T2        = 0.005
MMR_TIER_USDT = 50000.0
SLIP_BP       = 0.0005                 # 하드스탑 청산-5bp
COST_RT       = eng.COST_SIDE * 2      # 왕복 14bp

EXP_GRID = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
LEV_GRID = [5, 10, 15, 20, 25, 30, 40, 50]
CUT_GRID = [None] + [-(0.07 + 0.005 * k) for k in range(15)]   # None=컷없음 기준선 + -7%~-14% 15개
MDD_LINE = -0.15                        # 절대선

# ── PROD 필터 구성 (★Guide 강건 OI z=1.0) ──
PROD_FILTER_MODE = 'precise'; PROD_ATR_LO = 0.9; PROD_ATR_HI = 1.3
PROD_OI_FILTER   = True;      PROD_OI_Z_HI = 1.0

LEDGER_CSV = os.path.join(HERE, f"{NAME}_ledger.csv")
SWEEP_CSV  = os.path.join(HERE, f"{NAME}_sweep.csv")
BEST_CSV   = os.path.join(HERE, f"{NAME}_best.csv")


def compute_mae_gap_fund(trades, df1m, ft, fr, tf_min):
    ts = df1m.index.values.astype('datetime64[ns]').astype('int64')
    low = df1m['low'].values.astype('float64'); high = df1m['high'].values.astype('float64')
    tf_ns = np.int64(int(tf_min) * 60 * 1_000_000_000)
    COST_RT_ = eng.COST_SIDE * 2
    stats = {'n': 0, 'corrected': 0, 'violate': 0, 'pos_mismatch': 0, 'pos_maxerr': 0.0}
    for t in trades:
        stats['n'] += 1
        e = np.int64(pd.Timestamp(t['entry_t']).value); xt = np.int64(pd.Timestamp(t['exit_t']).value)
        i0 = int(np.searchsorted(ts, e, side='left')); i1 = int(np.searchsorted(ts, xt + tf_ns, side='right'))
        ep = float(t['entry']); sd = int(t['side'])
        fsum = eng.funding_sum(ft, fr, e, xt) if ft is not None else None
        if fsum is None:
            t['fund'] = eng.FUND_8H * int(np.floor(xt / 3.6e12 / 8.0) - np.floor(e / 3.6e12 / 8.0))  # 폴백(부호無)
        else:
            t['fund'] = sd * float(fsum)                                                              # 실펀딩(부호有)
        # pos 도출(실증완료: nDCA=1→롱1.0/숏SHORT_SIZE) + 엔진 R 재구성 검증(추정금지)
        t['pos'] = 1.0 if sd == 1 else eng.SHORT_SIZE
        R_re = t['pos'] * (sd * (float(t['exit']) - ep) / ep) - COST_RT_ * t['pos'] - t['fund'] * t['pos']
        err = abs(R_re - float(t['R']))
        if err > 1e-9: stats['pos_mismatch'] += 1
        if err > stats['pos_maxerr']: stats['pos_maxerr'] = err
        final_px = sd * (float(t['exit']) - ep) / ep
        if i1 <= i0 or ep <= 0:
            t['mae'] = min(0.0, final_px); t['max_gap'] = 0.0; continue
        if sd == 1:
            seg = low[i0:i1]; interval = float((seg.min() - ep) / ep)
            step = (seg[:-1] - seg[1:]) / ep if seg.size >= 2 else np.array([0.0])
        else:
            seg = high[i0:i1]; interval = float((ep - seg.max()) / ep)
            step = (seg[1:] - seg[:-1]) / ep if seg.size >= 2 else np.array([0.0])
        if interval > final_px and final_px < 0:
            stats['corrected'] += 1
        t['mae'] = min(interval, final_px)
        t['max_gap'] = -float(max(0.0, step.max()))
        if t['mae'] > final_px + 1e-9 and final_px < 0:
            stats['violate'] += 1
    return trades, stats


def sim_one(R, MAE, GAP, FUND, RPOS, POS, EXP, lev, cut_L, idx=None):
    # 한 조합 3층 복리. cut_L=None이면 손실허용컷 없음(하드스탑만). POS=거래별 포지션크기(롱1.0/숏0.5).
    #   격리증거금/컷거리/컷손익은 전부 pos 비례. o=R*EXP은 R에 이미 pos 반영(엔진).
    if idx is None:
        idx = np.arange(len(R))
    cap = START; peak = START; mdd = 0.0; worst = 0.0
    n_cut = n_rec = n_dir = n_liq = 0; rec_loss = 0.0; dir_gain = 0.0
    gp = 0.0; gl = 0.0
    for i in idx:
        pos = POS[i]
        notional = cap * pos * EXP
        mmr = MMR_T1 if notional <= MMR_TIER_USDT else MMR_T2
        liq = 1.0 / lev - mmr                                   # 가격거리(pos無)
        hsd = liq - SLIP_BP                                     # 가격거리
        cutd = (1e9 if cut_L is None else (-cut_L) / (pos * EXP))   # 계좌 -L% 되는 가격거리(pos↓→거리↑)
        inner = min(cutd, hsd)
        o = R[i] * EXP                                          # 무컷 손익(R에 pos 내재)
        if (-MAE[i] >= liq) and (-GAP[i] >= (liq - inner)):     # ③ 갭 강제청산
            pnl = -pos * EXP / lev; n_liq += 1                  # 격리증거금 전액(pos 비례)
        elif MAE[i] <= -inner:                                  # ①/② 시장가 컷
            pnl = -EXP * pos * (inner + COST_RT + FUND[i]); n_cut += 1
            if RPOS[i]: n_rec += 1; rec_loss += (o - pnl)
            else:       n_dir += 1; dir_gain += (pnl - o)
        else:
            pnl = o
        if pnl > 0: gp += pnl
        else:       gl += -pnl
        cap *= (1.0 + pnl)
        if pnl < worst: worst = pnl
        if cap > peak: peak = cap
        dd = (cap - peak) / peak
        if dd < mdd: mdd = dd
    pf = (gp / gl) if gl > 0 else 999.0
    return dict(EXP=EXP, lev=lev, entry_pct=round(EXP / lev, 4),     # entry_pct=롱기준 최대 격리증거금
                cut_L=('none' if cut_L is None else round(cut_L, 4)),
                cap=round(cap, 0), ret=round(cap / START - 1.0, 4), mdd=round(mdd, 4),
                worst=round(worst, 4), n_cut=n_cut, n_rec=n_rec, rec_loss=round(rec_loss, 4),
                n_dir=n_dir, dir_gain=round(dir_gain, 4), n_liq=n_liq, PF=round(pf, 3))


def cpcv_p25(R, MAE, GAP, FUND, RPOS, POS, EXP, lev, cut_L, n_groups=6):
    n = len(R)
    if n < n_groups: return None
    groups = np.array_split(np.arange(n), n_groups)
    rets = []
    for leave in combinations(range(n_groups), 2):       # 2개 빼기 → 15경로
        idx = np.concatenate([g for j, g in enumerate(groups) if j not in leave])
        rets.append(sim_one(R, MAE, GAP, FUND, RPOS, POS, EXP, lev, cut_L, idx=idx)['ret'])
    return round(float(np.percentile(rets, 25)), 4)


def main():
    print(f"[{NAME}] 박제엔진 import → TAKER 원장 → MAE/gap/fund → 3층 EXP×lev×cut 스윕 ($10k 복리)")
    print(f"[engine] {eng.__file__}")
    data = eng.find_data(); print(f"[data] {data}")
    df1m = eng.load_1m(data)
    print(f"[load] {len(df1m):,} rows | {df1m.index.min()} ~ {df1m.index.max()}")
    fpath = eng.find_funding(); ft = fr = None
    if fpath is not None:
        ft, fr = eng.load_funding(fpath); print(f"[funding] REAL ({len(ft)}건)")
    else:
        print("[funding] FALLBACK")

    df8 = eng.resample_tf(df1m, eng.TF_MIN); sig = eng.precompute(df8)
    ss, se = eng.build_1m_map(df1m, df8)
    mO = df1m['open'].values; mH = df1m['high'].values; mL = df1m['low'].values
    mT = df1m.index.values.astype('datetime64[ns]').astype('int64')
    has_atrr = df1m.attrs.get('has_atrr', False); has_oi = df1m.attrs.get('has_oi', False)
    fmode = PROD_FILTER_MODE if has_atrr else 'off'; oi_on = PROD_OI_FILTER and has_oi

    # ── 엔진 1회 호출 (TAKER, PROD 필터, 무수정) ──
    trades, ambig_n, held_n, blocked_n = eng.run_bot_honest(
        df8, sig, eng.BEST_PAR, mO, mH, mL, mT, ss, se, ft, fr, eng.DEFAULT_SLMULT,
        filter_mode=fmode, atr_lo=PROD_ATR_LO, atr_hi=PROD_ATR_HI, filter_scens=eng.FILTER_SCENS,
        oi_filter=oi_on, oi_z_hi=PROD_OI_Z_HI, oi_filter_scens=eng.OI_FILTER_SCENS)
    print(f"[engine·TAKER] 거래 {len(trades)}건 | filter={fmode} OI={'z>='+str(PROD_OI_Z_HI) if oi_on else 'OFF'} | 차단{blocked_n}")
    trades, st = compute_mae_gap_fund(trades, df1m, ft, fr, eng.TF_MIN)

    # ── 원장 CSV + numpy 배열 (1회 고정 후 사후 재사용) ──
    led_cols = ['entry_t', 'exit_t', 'side', 'pos', 'year', 'scen', 'reason', 'entry_price', 'exit_price',
                'R', 'fund', 'mae', 'max_gap', 'bars', 'nfilled']
    led_rows = [{'entry_t': pd.Timestamp(t['entry_t']).strftime('%Y-%m-%d %H:%M'),
                 'exit_t': pd.Timestamp(t['exit_t']).strftime('%Y-%m-%d %H:%M'),
                 'side': int(t['side']), 'pos': round(float(t['pos']), 4),
                 'year': int(t['year']), 'scen': t['scen'], 'reason': t['reason'],
                 'entry_price': round(float(t['entry']), 2), 'exit_price': round(float(t['exit']), 2),
                 'R': round(float(t['R']), 6), 'fund': round(float(t['fund']), 6),
                 'mae': round(float(t['mae']), 6), 'max_gap': round(float(t['max_gap']), 6),
                 'bars': int(t['bars']), 'nfilled': int(t['nfilled'])} for t in trades]
    pd.DataFrame(led_rows, columns=led_cols).to_csv(LEDGER_CSV, index=False, encoding='utf-8-sig')

    R = np.array([t['R'] for t in trades], float); MAE = np.array([t['mae'] for t in trades], float)
    GAP = np.array([t['max_gap'] for t in trades], float); FUND = np.array([t['fund'] for t in trades], float)
    POS = np.array([t['pos'] for t in trades], float); RPOS = R > 0

    # ── 3층 스윕 (EXP×lev×cut, lev>=EXP 제약) ──
    rows = []
    for EXP in EXP_GRID:
        for lev in LEV_GRID:
            if lev < EXP: continue                       # entry%=EXP/lev>1 불가
            for cut_L in CUT_GRID:
                rows.append(sim_one(R, MAE, GAP, FUND, RPOS, POS, EXP, lev, cut_L))
    sweep = pd.DataFrame(rows)
    sweep.to_csv(SWEEP_CSV, index=False, encoding='utf-8-sig')

    # ── 후보군: MDD>=-15% & 최악단일손실<=감내(컷한도) → CPCV-p25 부착, 수익순 정렬 ──
    def within_tol(r):
        if r['cut_L'] == 'none': return True             # 기준선은 한도제약 없음(참고)
        return r['worst'] >= float(r['cut_L']) - 1e-6     # 갭청산이 한도 깨면 탈락
    cand = sweep[(sweep['mdd'] >= MDD_LINE)].copy()
    cand = cand[cand.apply(within_tol, axis=1)]
    cand = cand.sort_values('ret', ascending=False).head(30).reset_index(drop=True)
    cpcvs = []
    for _, r in cand.iterrows():
        cl = None if r['cut_L'] == 'none' else float(r['cut_L'])
        cpcvs.append(cpcv_p25(R, MAE, GAP, FUND, RPOS, POS, int(r['EXP']), int(r['lev']), cl))
    cand['cpcv_p25'] = cpcvs
    cand.to_csv(BEST_CSV, index=False, encoding='utf-8-sig')

    print(f"[save] {os.path.basename(LEDGER_CSV)} / {os.path.basename(SWEEP_CSV)} / {os.path.basename(BEST_CSV)}")
    print(f"[자가검사] 거래 {st['n']}건 | 청산봉보정 {st['corrected']}건 | MAE물리위반 {st['violate']}건(★0)")
    print(f"[자가검사] pos(롱1.0/숏{eng.SHORT_SIZE}) R재구성 불일치 {st['pos_mismatch']}건(★0) | 최대오차 {st['pos_maxerr']:.1e}")
    print(f"[스윕] 조합 {len(sweep)} | MDD<=-15%&한도내 후보 {len(cand)}")
    if len(cand):
        top = cand.iloc[0]
        print(f"[best] EXP{top['EXP']}×lev{top['lev']} cut{top['cut_L']} → ret{top['ret']*100:.1f}% "
              f"MDD{top['mdd']*100:.1f}% worst{top['worst']*100:.1f}% CPCVp25 {top['cpcv_p25']}")


if __name__ == "__main__":
    main()
