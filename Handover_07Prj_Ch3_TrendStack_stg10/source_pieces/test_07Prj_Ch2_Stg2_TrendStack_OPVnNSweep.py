# -*- coding: utf-8 -*-
# [test_07Prj_Ch2_Stg2_TrendStack_OPVnNSweep.py]
# 코드길이: 약 235줄 | 내부버전: TS_OPVnN_v1 (추세봇엔진 7f9192e3 import·무수정) | 로직 축약/생략 없이 전체 출력
# =============================================================================
# [목적] 추세봇(TrendStack) 거래에 POC 평균회귀 기반 진입수량 조절을 사후 적용·최적화(엔진 무수정).
#   dev=(진입가-POC)/ATR. |dev|>=OPV일 때: 진입방향이 POC 회귀방향과 동일=N배(늘림)/반대=n배(줄임), 그외 1배.
#   수량변경은 R 스케일(청산·MAE 불변) → 엔진 재실행 불필요. OPV·n·N 3D 그리드 + 노출(EXP) 동반최적화(MDD=-20%) + CPCV.
#   ★사장님 지시: MDD-20% 고정·노출동반·총수익최대. OPV·n·N 모두 최적화대상(장세/성향 변화시 재최적화).
#
# [경로] 하위폴더(HERE) 안 실행, 데이터는 상위 D:\ML\verify(=dirname(HERE)). 결과는 HERE, 분석/INDEX는 check가 00WorkHstr로.
#
# [사용 파일 — In/Out]
#   In : bots/SpTrd_Fib_V1_Champion.py(추세봇엔진, import: resample_tf·compute_atr·TF_MIN·ATR_PERIOD)
#        stg6_levsweep_ledger.csv(추세봇 거래 264건) / Merged_Data_with_Regime_Features.csv(1분봉 OHLCV+volume)
#   Out: <NAME>_devledger.csv(거래별 POC/dev/회귀방향) / <NAME>_sweep.csv(OPV×n×N 조합) / <NAME>_best.csv(최적+CPCV+분해)
#
# [핵심 상수]
#   START=10000 MMR_T1=0.4% MMR_T2=0.5%($50k) MDD_LINE=-0.20(절대선) POC_LB=60 POC_BINS=50
#   OPV_GRID[0.25~4.0 step0.25] n_GRID[0.1~0.9 step0.05] N_GRID[1.0~3.0 step0.1] EXP_GRID[0.3~3.0 step0.05]
#   EXP_FIX=0.825(추세봇 확정노출, 순수 수량효과 참고용)
#
# [함수 — In/Out]
#   compute_poc(high,low,mid,vol,lb,bins)->poc배열   횡보봇 compute_poc 로직 복제(volume 가중, [i-lb:i) 과거→룩어헤드無)
#   build_dev(ledger,df7,atr,poc)->(dev,rdir,side,R)  거래별 dev=(entry-POC)/ATR·회귀방향 rdir=-sign(dev)
#   mult_of(dev,rdir,side,OPV,n,N)->배수배열          |dev|>=OPV & 방향: 동일N/반대n/그외1
#   mdd_ret(Rs,exp)->(mdd,ret)                        R스케일 복리의 MDD·총수익
#   best_exp(Rs)->(exp,ret)                           EXP_GRID서 MDD<=-20% 최대노출·그때 총수익
#   cpcv_p25(Rs,exp)->float                           6그룹 2-leave-out 15경로 수익 p25
#   main()->결과 CSV 3종
# =============================================================================
import os, sys
from itertools import combinations
import numpy as np, pandas as pd

NAME = "07Prj_Ch2_Stg2_TrendStack_OPVnNSweep"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.dirname(HERE)                       # 상위 = D:\ML\verify

_ENG = os.path.join(HERE, "bots")
if _ENG not in sys.path: sys.path.insert(0, _ENG)
import SpTrd_Fib_V1_Champion as st                 # 추세봇 엔진(무수정 import)

START = 10000.0; MMR_T1 = 0.004; MMR_T2 = 0.005; MMR_TIER = 50000.0
MDD_LINE = -0.20; POC_LB = 60; POC_BINS = 50; EXP_FIX = 0.825
OPV_GRID = np.round(np.arange(0.25, 4.001, 0.25), 3)
n_GRID   = np.round(np.arange(0.10, 0.901, 0.05), 3)
N_GRID   = np.round(np.arange(1.00, 3.001, 0.10), 3)
EXP_GRID = np.round(np.arange(0.30, 3.001, 0.05), 3)
LEDGER_IN = "stg6_levsweep_ledger.csv"; M1 = "Merged_Data_with_Regime_Features.csv"

DEV_CSV  = os.path.join(HERE, f"{NAME}_devledger.csv")
SWEEP_CSV= os.path.join(HERE, f"{NAME}_sweep.csv")
BEST_CSV = os.path.join(HERE, f"{NAME}_best.csv")


def compute_poc(high, low, mid, vol, lb, bins):
    # 횡보봇 SidewayDCA compute_poc 로직 복제: [i-lb:i) 과거 거래량분포 최빈가(룩어헤드 없음)
    n = len(mid); poc = np.full(n, np.nan)
    for i in range(lb, n):
        s = i - lb; lo = low[s:i].min(); hi = high[s:i].max()
        if hi <= lo: poc[i] = mid[i - 1]; continue
        edges = np.linspace(lo, hi, bins + 1)
        idxb = np.clip(np.digitize(mid[s:i], edges) - 1, 0, bins - 1)
        hist = np.zeros(bins); np.add.at(hist, idxb, vol[s:i])
        k = int(hist.argmax()); poc[i] = (edges[k] + edges[k + 1]) / 2.0
    return poc


def mdd_ret(Rs, exp):
    eq = np.cumprod(1.0 + Rs * exp); pk = np.maximum.accumulate(eq)
    return ((eq - pk) / pk).min(), eq[-1] - 1.0


def best_exp(Rs):
    # EXP_GRID에서 MDD<=-20% 만족하는 최대 노출과 그때 총수익
    best = (None, -1.0)
    for e in EXP_GRID:
        m, r = mdd_ret(Rs, e)
        if m >= MDD_LINE and r > best[1]: best = (e, r)
    return best


def cpcv_p25(Rs, exp, ng=6):
    g = np.array_split(np.arange(len(Rs)), ng); rr = []
    for lv in combinations(range(ng), 2):
        idx = np.concatenate([x for j, x in enumerate(g) if j not in lv])
        eq = np.cumprod(1.0 + Rs[idx] * exp); rr.append(eq[-1] - 1.0)
    return round(float(np.percentile(rr, 25)), 4)


def find_in_tree(names):
    # D:\ML\Verify(DATA) 루트 우선, 없으면 트리 전체에서 파일명으로 탐색(Ch1 하위폴더 등)
    import glob
    for nm in names:
        p = os.path.join(DATA, nm)
        if os.path.exists(p): return p
    for nm in names:
        h = sorted(glob.glob(os.path.join(DATA, '**', nm), recursive=True))
        if h: return h[0]
    return None


def main():
    print(f"[{NAME}] 추세봇 POC평균회귀 수량조절 최적화 (엔진 7f9192e3 무수정 import)")
    lp = find_in_tree(["stg6_levsweep_ledger.csv"])
    mp = find_in_tree(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
    if lp is None or mp is None:
        import glob
        csvs = [os.path.relpath(x, DATA) for x in glob.glob(os.path.join(DATA, '**', '*.csv'), recursive=True)]
        print(f"[ERROR] 입력 데이터를 못 찾음 (탐색 루트 DATA={DATA})")
        print(f"        추세봇 원장(ledger)={lp}  /  1분봉(1m)={mp}")
        print(f"        DATA 트리 내 csv {len(csvs)}개: {csvs[:25]}")
        raise SystemExit("→ stg6_levsweep_ledger.csv 와 Merged_Data_with_Regime_Features.csv 를 "
                         "D:\\ML\\Verify 또는 그 하위에 두세요. (파일명이 다르면 알려주세요)")
    print(f"[in] ledger={lp}\n     1m={mp}")
    L = pd.read_csv(lp)
    L['entry_t'] = pd.to_datetime(L['entry_t']); L = L.sort_values('entry_t').reset_index(drop=True)
    print(f"[ledger] 추세봇 거래 {len(L)}건 | {L.entry_t.min()} ~ {L.entry_t.max()}")

    # ── 1분봉 → 7h resample (OHLC: 엔진 resample_tf / volume: sum 별도) ──
    df1 = pd.read_csv(mp); df1['timestamp'] = pd.to_datetime(df1['timestamp']); df1 = df1.set_index('timestamp')
    df7 = st.resample_tf(df1, st.TF_MIN)
    vol7 = df1['volume'].resample(f"{st.TF_MIN}min", label='left', closed='left').sum().reindex(df7.index).fillna(0.0)
    high = df7['high'].values; low = df7['low'].values; close = df7['close'].values
    mid = (high + low) / 2.0
    atr = st.compute_atr(high, low, close, st.ATR_PERIOD)
    poc = compute_poc(high, low, mid, vol7.values, POC_LB, POC_BINS)
    t7 = df7.index.values.astype('datetime64[ns]').astype('int64')
    print(f"[7h] {len(df7)}봉 | ATR(p{st.ATR_PERIOD})·POC(lb{POC_LB}) 계산 완료")

    # ── 거래별 dev=(진입가-POC)/ATR, 회귀방향 rdir=-sign(dev) ──
    R = L['R'].values.astype(float); side = L['side'].values.astype(int)
    ev = L['entry_t'].values.astype('datetime64[ns]').astype('int64'); ep = L['entry_price'].values.astype(float)
    dev = np.full(len(L), np.nan); pocv = np.full(len(L), np.nan)
    for i in range(len(L)):
        b = int(np.searchsorted(t7, ev[i], side='right') - 1)  # 진입봉(닫힌 봉)
        if 0 <= b < len(poc) and not np.isnan(poc[b]) and atr[b] > 0:
            pocv[i] = poc[b]; dev[i] = (ep[i] - poc[b]) / atr[b]
    valid = ~np.isnan(dev)
    rdir = -np.sign(dev)                                       # POC 회귀방향(가격>POC면 숏-1, <면 롱+1)
    print(f"[dev] 유효 {valid.sum()}/{len(L)}건 | dev 범위 {np.nanmin(dev):.2f}~{np.nanmax(dev):.2f} 중앙 {np.nanmedian(np.abs(dev)):.2f}")
    pd.DataFrame({'entry_t': L['entry_t'].dt.strftime('%Y-%m-%d %H:%M'), 'side': side, 'regime': L.get('regime', ''),
                  'entry_price': np.round(ep, 2), 'POC': np.round(pocv, 2), 'dev': np.round(dev, 3),
                  'regime_dir': rdir.astype(int), 'R': np.round(R, 6)}).to_csv(DEV_CSV, index=False, encoding='utf-8-sig')

    # ── 배수 적용 함수(벡터화): |dev|>=OPV & 동일=N/반대=n/그외=1 ──
    adev = np.abs(dev); same = (side == rdir); oppo = (side == -rdir)
    def mult(OPV, n, N):
        m = np.ones(len(L)); gate = valid & (adev >= OPV)
        m = np.where(gate & same, N, m); m = np.where(gate & oppo, n, m)
        return m

    # ── 3D 스윕: 각 조합 R스케일 → 노출동반(MDD-20%) 최대수익 ──
    base_exp, base_ret = best_exp(R)                            # 무조절 기준선(배수 전부 1)
    base_mdd = mdd_ret(R, base_exp)[0]
    rows = []
    for OPV in OPV_GRID:
        for n in n_GRID:
            for N in N_GRID:
                Rs = R * mult(OPV, n, N)
                e, r = best_exp(Rs)
                if e is None: continue
                m, _ = mdd_ret(Rs, e)
                g = mult(OPV, n, N); ng_same = int(((g == N) & same).sum()); ng_oppo = int(((g == n) & oppo).sum())
                rows.append(dict(OPV=OPV, n=n, N=N, EXP=round(e, 3), ret=round(r, 4), mdd=round(m, 4),
                                 n_up=ng_same, n_down=ng_oppo))
    sweep = pd.DataFrame(rows); sweep.to_csv(SWEEP_CSV, index=False, encoding='utf-8-sig')
    print(f"[sweep] 조합 {len(sweep)} (OPV{len(OPV_GRID)}×n{len(n_GRID)}×N{len(N_GRID)}) | 기준선 EXP{base_exp} ret{base_ret*100:.0f}% MDD{base_mdd*100:.1f}%")

    # ── 후보(수익 상위 40) CPCV-p25 게이트 → 최적 ──
    cand = sweep.sort_values('ret', ascending=False).head(40).reset_index(drop=True)
    cp = []
    for _, r in cand.iterrows():
        Rs = R * mult(r['OPV'], r['n'], r['N']); cp.append(cpcv_p25(Rs, r['EXP']))
    cand['cpcv_p25'] = cp
    cand['EXP_fix_ret'] = [round(mdd_ret(R * mult(r['OPV'], r['n'], r['N']), EXP_FIX)[1], 4) for _, r in cand.iterrows()]
    cand['EXP_fix_mdd'] = [round(mdd_ret(R * mult(r['OPV'], r['n'], r['N']), EXP_FIX)[0], 4) for _, r in cand.iterrows()]
    cand.to_csv(BEST_CSV, index=False, encoding='utf-8-sig')

    rob = cand[cand['cpcv_p25'] > 0]
    pick = (rob if len(rob) else cand).iloc[0]
    print(f"[save] {os.path.basename(DEV_CSV)} / {os.path.basename(SWEEP_CSV)} / {os.path.basename(BEST_CSV)}")
    print(f"[BEST] OPV{pick['OPV']} n{pick['n']} N{pick['N']} → EXP{pick['EXP']} 총수익{pick['ret']*100:.0f}% "
          f"MDD{pick['mdd']*100:.1f}% CPCVp25 {pick['cpcv_p25']} | 늘림{int(pick['n_up'])}/줄임{int(pick['n_down'])}건")
    print(f"   vs 기준선(무조절) EXP{base_exp} {base_ret*100:.0f}% MDD{base_mdd*100:.1f}% → 개선 {(pick['ret']-base_ret)*100:+.0f}%p")


if __name__ == "__main__":
    main()
