# -*- coding: utf-8 -*-
# [test_07Prj_Ch2_Stg4_TrendStack_LevExpScan.py]
# 코드길이: 약 235줄 | 내부버전: TS_LevExpScan_v1 (추세봇엔진 7f9192e3 import·무수정) | 로직 축약/생략 없이 전체 출력
# =============================================================================
# [목적] 레버 × EXP 2D 스캔. Ch1 sim_levsweep의 정확한 하드스탑 손익공식을 그대로 통일 적용하여
#   figE/figG/figH의 들쭉날쭉한 복리 숫자를 '하나의 신뢰할 표'로 만든다. 핵심은 회복거래 잘림을
#   정밀 분해하는 것: 발동거래 중 '정상손익 > 하드스탑손익'이면 하드스탑이 손실을 키운 것(회복죽임),
#   반대면 손실을 줄인 것(진짜손실). 레버↑ → 청산거리↓ → 회복죽임↑ → 복리 손해(figH 패턴) 정량화.
#
# [통일 공식 — Ch1 원본 sim_levsweep line226~248과 동일]
#   발동조건: MAE(1분봉) <= -hsd,  hsd = 1/L - MMR(cap별 tier) - SLIP_BP(5bp)
#   하드스탑 손익: -EXP×mult×(hsd + COST_RT + fund)   ← ★figH에서 누락했던 COST_RT·fund 포함
#   정상 손익:     R×EXP×mult   (R은 stg6 원장의 net, 비용·실펀딩 차감됨)
#   회복죽임 판정:  정상손익 o > 하드스탑손익 pnl  →  손해 (o - pnl)
#
# [제약/목표] 단일손실 = EXP×hsd ≤ 7.5%(LOSS_CAP) + MDD ≥ -20%(MDD_LINE). 각 레버에서 두 제약을
#   동시에 만족하는 최대 EXP를 이분탐색(복리는 EXP 단조증가). 목표 지표 = 36개월 복리. PF·회복죽임은
#   '출력만' 하여 사장님이 표를 보고 레버 상한·PF하한·회복죽임 한도를 결정하도록 한다.
#
# [입력 — In/Out]
#   bots/SpTrd_Fib_V1_Champion.py(import resample_tf·compute_atr·TF_MIN·ATR_PERIOD)
#   stg6_levsweep_ledger.csv(R·mae·fund·side·entry_price) / Merged_Data_with_Regime_Features.csv(1분봉)
#   Out: <NAME>_scan.csv(레버별 최적EXP·복리·MDD·PF·회복죽임·진짜손실·회복보존가상복리) / <NAME>_best.csv(CPCV 포함 최적)
#
# [함수 In/Out]
#   find_in_tree(names)->path
#   compute_poc(high,low,mid,vol,lb,bins)->poc
#   mult_array(dev,side,OPV,n,N)->(mult, n_oppo)
#   sim(R,MAE,FUND,mult,entry_pct,lev,hs_on)->dict(cap,mdd,pf,rec_n,rec_loss,dir_n,dir_gain,cap_recsave,nliq)
#   best_exp_for(lev)->(exp,res)             손실한도+MDD 이분탐색 최적 EXP
#   cpcv(R,MAE,FUND,mult,entry_pct,lev,k)->p25   조합형 purged CV 하위25% 복리
#   main()
# =============================================================================
import os, sys, glob, itertools
import numpy as np, pandas as pd

NAME = "07Prj_Ch2_Stg4_TrendStack_LevExpScan"
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "bots"))
import SpTrd_Fib_V1_Champion as st

START = 10000.0
MMR_T1 = 0.004; MMR_T2 = 0.005; MMR_TIER = 50000.0      # Binance BTCUSDT USDⓈ-M tier
SLIP_BP = 0.0005; COST_RT = 0.0014                       # 하드스탑 5bp 버퍼 / 정상 왕복 14bp
LOSS_CAP = 0.075; MDD_LINE = -20.0                       # ★단일손실 한도 7.5% / MDD 절대선
OPV, n_mult, N_mult = 0.25, 0.60, 1.00                   # OPVnN 최적(반대0.6, 동일1.0)
POC_LB = 60; POC_BINS = 50
LEV_GRID = list(range(11, 31))                           # 레버 11~30 스캔
SCAN_CSV = os.path.join(HERE, f"{NAME}_scan.csv")
BEST_CSV = os.path.join(HERE, f"{NAME}_best.csv")


def find_in_tree(names):
    for nm in names:
        p = os.path.join(DATA, nm)
        if os.path.exists(p): return p
    for nm in names:
        h = sorted(glob.glob(os.path.join(DATA, '**', nm), recursive=True))
        if h: return h[0]
    return None


def compute_poc(high, low, mid, vol, lb, bins):
    nn = len(mid); poc = np.full(nn, np.nan)
    for i in range(lb, nn):
        s = i - lb; lo = low[s:i].min(); hi = high[s:i].max()
        if hi <= lo: poc[i] = mid[i - 1]; continue
        edges = np.linspace(lo, hi, bins + 1)
        idxb = np.clip(np.digitize(mid[s:i], edges) - 1, 0, bins - 1)
        hist = np.zeros(bins); np.add.at(hist, idxb, vol[s:i])
        k = int(hist.argmax()); poc[i] = (edges[k] + edges[k + 1]) / 2.0
    return poc


def mult_array(dev, side, OPV, n, N):
    valid = ~np.isnan(dev); adev = np.where(valid, np.abs(dev), 0.0)
    rdir = np.where(valid, -np.sign(dev), 0).astype(int)
    oppo = valid & (side == -rdir) & (adev >= OPV)
    same = valid & (side == rdir) & (adev >= OPV)
    m = np.ones(len(dev)); m[oppo] = n; m[same] = N
    return m, int(oppo.sum())


def sim(R, MAE, FUND, mult, entry_pct, lev, hs_on):
    # Ch1 sim_levsweep 통일 공식 + 거래별 mult + 회복죽임 정밀분해(정상손익>하드스탑손익).
    entry = entry_pct / 100.0; EXP = entry * lev
    cap = START; peak = START; mdd = 0.0
    nliq = 0; rec_n = 0; rec_loss = 0.0; dir_n = 0; dir_gain = 0.0
    gp = 0.0; gl = 0.0
    cap_rs = START                                       # 회복보존 가상(회복거래는 정상손익 유지)
    for i in range(len(R)):
        o = R[i] * EXP * mult[i]                         # 정상 손익
        pnl = o; pnl_rs = o
        if hs_on:
            mmr = MMR_T1 if cap * EXP <= MMR_TIER else MMR_T2
            hsd = 1.0 / lev - mmr - SLIP_BP
            if MAE[i] <= -hsd:                           # 발동
                hp = -EXP * mult[i] * (hsd + COST_RT + FUND[i])   # ★정확한 하드스탑 손익
                pnl = hp; nliq += 1
                if o > hp:                               # 정상이 더 좋음 → 하드스탑이 손실 키움(회복죽임)
                    rec_n += 1; rec_loss += (o - hp); pnl_rs = o   # 가상은 회복거래 살림
                else:                                    # 하드스탑이 손실 줄임(진짜손실)
                    dir_n += 1; dir_gain += (hp - o); pnl_rs = hp
        if pnl > 0: gp += pnl
        else: gl += -pnl
        cap *= (1.0 + pnl); cap_rs *= (1.0 + pnl_rs)
        if cap > peak: peak = cap
        d = (cap - peak) / peak
        if d < mdd: mdd = d
    pf = gp / gl if gl > 0 else 99.0
    return dict(cap=cap, mdd=mdd * 100.0, pf=pf, nliq=nliq,
                rec_n=rec_n, rec_loss=rec_loss * 100.0, dir_n=dir_n, dir_gain=dir_gain * 100.0,
                cap_recsave=cap_rs)


def best_exp_for(R, MAE, FUND, mult, lev):
    # 손실한도(EXP×hsd≤7.5%) + MDD≥-20% 동시 만족 최대 EXP를 이분탐색(복리 단조증가).
    mmr = MMR_T2  # 보수적 tier2로 상한 산정
    hsd0 = 1.0 / lev - mmr - SLIP_BP
    exp_losscap = LOSS_CAP / hsd0
    lo, hi = 0.10, exp_losscap
    for _ in range(40):
        mid = (lo + hi) / 2.0
        r = sim(R, MAE, FUND, mult, mid / lev * 100.0, lev, True)
        if r['mdd'] >= MDD_LINE: lo = mid
        else: hi = mid
    exp = lo
    return exp, sim(R, MAE, FUND, mult, exp / lev * 100.0, lev, True)


def cpcv(R, MAE, FUND, mult, entry_pct, lev, k=6):
    # 조합형 purged CV: k폴드 중 2개씩 빼고 학습구간 복리, 하위25% 분위(견고성).
    n = len(R); fold = np.array_split(np.arange(n), k); outs = []
    for combo in itertools.combinations(range(k), 2):
        mask = np.ones(n, bool)
        for c in combo: mask[fold[c]] = False
        idx = np.where(mask)[0]
        r = sim(R[idx], MAE[idx], FUND[idx], mult[idx], entry_pct, lev, True)
        outs.append(r['cap'] / START - 1.0)
    return float(np.percentile(outs, 25) * 100)


def main():
    print(f"[{NAME}] 레버×EXP 2D 스캔 — Ch1 정확공식 통일 + 회복죽임 정밀분해 (엔진 7f9192e3)")
    lp = find_in_tree(["stg6_levsweep_ledger.csv"])
    mp = find_in_tree(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
    if lp is None or mp is None:
        csvs = [os.path.relpath(x, DATA) for x in glob.glob(os.path.join(DATA, '**', '*.csv'), recursive=True)]
        print(f"[ERROR] 데이터 못찾음 (DATA={DATA}) ledger={lp} 1m={mp}\n 트리 csv: {csvs[:25]}")
        raise SystemExit("→ stg6_levsweep_ledger.csv / Merged_Data_with_Regime_Features.csv 를 D:\\ML\\Verify(또는 하위)에 두세요.")
    print(f"[in] ledger={lp}\n     1m={mp}")
    L = pd.read_csv(lp); L['entry_t'] = pd.to_datetime(L['entry_t']); L = L.sort_values('entry_t').reset_index(drop=True)
    for c in ['R', 'mae', 'side', 'entry_price']:
        if c not in L.columns: raise SystemExit(f"[ERROR] ledger '{c}' 컬럼 필요")
    R = L['R'].values.astype(float); MAE = L['mae'].values.astype(float)
    side = L['side'].values.astype(int); fund = L['fund'].values.astype(float) if 'fund' in L.columns else np.zeros(len(L))
    print(f"[ledger] {len(L)}건 (R·MAE·fund)")

    df1 = pd.read_csv(mp); df1['timestamp'] = pd.to_datetime(df1['timestamp']); df1 = df1.set_index('timestamp')
    df7 = st.resample_tf(df1, st.TF_MIN)
    vol7 = df1['volume'].resample(f"{st.TF_MIN}min", label='left', closed='left').sum().reindex(df7.index).fillna(0.0)
    hi = df7['high'].values; lo = df7['low'].values; cl = df7['close'].values; mid = (hi + lo) / 2.0
    atr = st.compute_atr(hi, lo, cl, st.ATR_PERIOD); poc = compute_poc(hi, lo, mid, vol7.values, POC_LB, POC_BINS)
    t7 = df7.index.values.astype('datetime64[ns]').astype('int64')
    ev = L['entry_t'].values.astype('datetime64[ns]').astype('int64'); ep = L['entry_price'].values.astype(float)
    dev = np.full(len(L), np.nan)
    for i in range(len(L)):
        b = int(np.searchsorted(t7, ev[i], side='right') - 1)
        if 0 <= b < len(poc) and not np.isnan(poc[b]) and atr[b] > 0: dev[i] = (ep[i] - poc[b]) / atr[b]
    mult, n_opp = mult_array(dev, side, OPV, n_mult, N_mult)
    months = (L['entry_t'].max() - L['entry_t'].min()).days / 30.44
    print(f"[mult] 반대(0.6배) {n_opp}건 | 기간 {months:.1f}개월")

    rows = []
    for lev in LEV_GRID:
        exp, r = best_exp_for(R, MAE, fund, mult, lev)
        mmr = MMR_T2; liq = (1.0 / lev - mmr) * 100.0; hsd = (1.0 / lev - mmr - SLIP_BP) * 100.0
        single = exp * hsd / 100.0 * 100.0
        rows.append(dict(lev=lev, entry_pct=round(exp / lev * 100, 2), EXP=round(exp, 3),
                         liq_dist=round(liq, 2), single_loss=round(exp * (hsd / 100.0) * 100, 2),
                         ret=round((r['cap'] / START - 1) * 100), mdd=round(r['mdd'], 1), pf=round(r['pf'], 2),
                         rec_n=r['rec_n'], rec_loss=round(r['rec_loss'], 0), dir_n=r['dir_n'],
                         ret_recsave=round((r['cap_recsave'] / START - 1) * 100),
                         recsave_gap=round((r['cap_recsave'] - r['cap']) / START * 100)))
    sw = pd.DataFrame(rows); sw.to_csv(SCAN_CSV, index=False, encoding='utf-8-sig')

    bi = sw['ret'].idxmax(); bl = int(sw.loc[bi, 'lev']); bexp = float(sw.loc[bi, 'EXP'])
    p25 = cpcv(R, MAE, fund, mult, bexp / bl * 100.0, bl, k=6)
    bestrow = sw.loc[[bi]].copy(); bestrow['cpcv_p25'] = round(p25)
    bestrow.to_csv(BEST_CSV, index=False, encoding='utf-8-sig')

    print(f"[save] {os.path.basename(SCAN_CSV)} / {os.path.basename(BEST_CSV)}")
    print("\n=== 레버×EXP 스캔 (손실한도7.5%+MDD-20%, Ch1 정확공식 통일) ===")
    print(sw[['lev', 'EXP', 'liq_dist', 'single_loss', 'ret', 'mdd', 'pf', 'rec_n', 'dir_n', 'recsave_gap']].to_string(index=False))
    print(f"\n[최대복리] 레버{bl} EXP{bexp} → +{int(sw.loc[bi,'ret'])}% MDD{sw.loc[bi,'mdd']}% PF{sw.loc[bi,'pf']} "
          f"회복죽임{int(sw.loc[bi,'rec_n'])}건(손해{int(sw.loc[bi,'recsave_gap'])}%p) CPCV-p25 +{int(p25)}%")
    print("→ 표를 보고 레버 상한·PF하한·회복죽임 한도를 결정하세요(제약은 미적용, 출력만).")


if __name__ == "__main__":
    main()
