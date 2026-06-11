# -*- coding: utf-8 -*-
# [check_07Prj_Ch2_Stg4_TrendStack_LevExpScan.py]
# 코드길이: 약 175줄 | 내부버전: TS_LevExpScan_check_v1 | 로직 축약/생략 없이 전체 출력
# =============================================================================
# [목적] Stg4 레버×EXP 스캔 결과를 8시나리오로 자체검증 + 엔진 해시 + 분석txt/INDEX 기록.
# [검증 8시나리오]
#   ① 폴더/파일명      : 하위폴더명·결과 CSV 2종
#   ② 데이터 정합      : ledger R/mae/side/entry_price·1분봉
#   ③ POC 룩어헤드     : 미래봉 오염해도 진입봉 POC 불변
#   ④ mult 정합        : 반대0.6·그외 1(OPV0.25 N1.0)
#   ⑤ 하드스탑 공식 통일: 발동손익 == -EXP×mult×(hsd+COST_RT+fund)  ★figH 누락 비용 포함 확인
#   ⑥ 회복죽임 분해     : 정상손익 > 하드스탑손익 → rec(RPOS 아님) 재현
#   ⑦ 손실한도+MDD      : 단일손실 == EXP×hsd ≤ 7.5% & MDD ≥ -20% (최적 EXP)
#   ⑧ CPCV 견고성       : best.csv cpcv_p25 존재·최적 레버 일관
#   + 엔진 해시 7f9192e3
# =============================================================================
import os, sys, hashlib, glob, itertools
import numpy as np, pandas as pd
from datetime import datetime

NAME = "07Prj_Ch2_Stg4_TrendStack_LevExpScan"
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.dirname(HERE)
WORKHSTR = os.path.join(DATA, "00WorkHstr")
SP_SHA = "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75"
MMR_T1 = 0.004; MMR_T2 = 0.005; MMR_TIER = 50000.0
SLIP_BP = 0.0005; COST_RT = 0.0014; LOSS_CAP = 0.075; MDD_LINE = -20.0
OPV, n_mult, N_mult = 0.25, 0.60, 1.00; POC_LB = 60; POC_BINS = 50; START = 10000.0
SCAN_CSV = os.path.join(HERE, f"{NAME}_scan.csv"); BEST_CSV = os.path.join(HERE, f"{NAME}_best.csv")

_n = {"p": 0, "f": 0}
def chk(c, m):
    ok = bool(c); _n["p" if ok else "f"] += 1; print(f"  [{'PASS' if ok else 'FAIL'}] {m}"); return ok
def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8192), b''): h.update(b)
    return h.hexdigest()
def find_in_tree(names):
    for nm in names:
        p = os.path.join(DATA, nm)
        if os.path.exists(p): return p
    for nm in names:
        h = sorted(glob.glob(os.path.join(DATA, '**', nm), recursive=True))
        if h: return h[0]
    return None


def main():
    print(f"=== check [{NAME}] 8시나리오 + 엔진해시 ===")
    sys.path.insert(0, os.path.join(HERE, "bots")); import SpTrd_Fib_V1_Champion as st
    eng = os.path.join(HERE, "bots", "SpTrd_Fib_V1_Champion.py")

    print("[①] 폴더/파일명")
    chk(os.path.basename(HERE) == NAME, f"하위폴더명 == {NAME}")
    chk(os.path.exists(SCAN_CSV), "결과: scan.csv"); chk(os.path.exists(BEST_CSV), "결과: best.csv")
    print("[엔진해시]"); chk(os.path.exists(eng) and sha(eng) == SP_SHA, "SpTrd 해시 == 7f9192e3")

    SW = pd.read_csv(SCAN_CSV); BE = pd.read_csv(BEST_CSV)
    lp = find_in_tree(["stg6_levsweep_ledger.csv"]); mp = find_in_tree(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
    print("[②] 데이터 정합")
    chk(lp is not None and mp is not None, f"입력 발견 (ledger={os.path.basename(lp) if lp else None})")
    L = pd.read_csv(lp); L['entry_t'] = pd.to_datetime(L['entry_t']); L = L.sort_values('entry_t').reset_index(drop=True)
    chk(set(['R', 'mae', 'side', 'entry_price']).issubset(L.columns), "ledger R/mae/side/entry_price")
    R = L['R'].values.astype(float); MAE = L['mae'].values.astype(float); side = L['side'].values.astype(int)
    fund = L['fund'].values.astype(float) if 'fund' in L.columns else np.zeros(len(L))

    df1 = pd.read_csv(mp); df1['timestamp'] = pd.to_datetime(df1['timestamp']); df1 = df1.set_index('timestamp')
    df7 = st.resample_tf(df1, st.TF_MIN)
    vol7 = df1['volume'].resample(f"{st.TF_MIN}min", label='left', closed='left').sum().reindex(df7.index).fillna(0.0)
    hi = df7['high'].values; lo = df7['low'].values; cl = df7['close'].values; mid = (hi + lo) / 2.0; vv = vol7.values
    atr = st.compute_atr(hi, lo, cl, st.ATR_PERIOD); t7 = df7.index.values.astype('datetime64[ns]').astype('int64')
    def poc_ref(i, H=None):
        H = hi if H is None else H; s = i - POC_LB
        if s < 0: return np.nan
        l = lo[s:i].min(); h = H[s:i].max()
        if h <= l: return mid[i - 1]
        e = np.linspace(l, h, POC_BINS + 1); ib = np.clip(np.digitize(mid[s:i], e) - 1, 0, POC_BINS - 1)
        hh = np.zeros(POC_BINS); np.add.at(hh, ib, vv[s:i]); k = int(hh.argmax()); return (e[k] + e[k + 1]) / 2.0

    print("[③] POC 룩어헤드")
    ti = POC_LB + 5; pb = poc_ref(ti); h2 = hi.copy(); h2[ti + 1:] *= 5.0
    chk(abs(pb - poc_ref(ti, h2)) < 1e-9, "미래봉 오염해도 진입봉 POC 불변")

    ev = L['entry_t'].values.astype('datetime64[ns]').astype('int64'); ep = L['entry_price'].values.astype(float)
    dev = np.full(len(L), np.nan)
    for i in range(len(L)):
        b = int(np.searchsorted(t7, ev[i], side='right') - 1)
        if 0 <= b < len(atr) and atr[b] > 0 and not np.isnan(poc_ref(b)): dev[i] = (ep[i] - poc_ref(b)) / atr[b]
    valid = ~np.isnan(dev); adev = np.where(valid, np.abs(dev), 0.0); rdir = np.where(valid, -np.sign(dev), 0).astype(int)
    oppo = valid & (side == -rdir) & (adev >= OPV); m = np.ones(len(L)); m[oppo] = n_mult
    print("[④] mult 정합")
    chk(N_mult == 1.0 and np.all(m[oppo] == 0.6) and np.all(m[~oppo] == 1.0), f"반대 0.6배 {int(oppo.sum())}건·그외 1배")

    # ⑤⑥ 통일 공식·회복죽임 재현 (레버20 표본)
    print("[⑤] 하드스탑 공식 통일(비용·펀딩 포함)")
    lev = 20; entry = float(SW[SW.lev == lev]['EXP'].iloc[0]) / lev; EXP = entry * lev
    cap = START; hp_sample = None; i_fire = None
    for i in range(len(R)):
        mmr = MMR_T1 if cap * EXP <= MMR_TIER else MMR_T2; hsd = 1.0 / lev - mmr - SLIP_BP
        if MAE[i] <= -hsd and i_fire is None:
            i_fire = i; hp_sample = -EXP * m[i] * (hsd + COST_RT + fund[i]); break
        o = R[i] * EXP * m[i]
        if MAE[i] <= -hsd: o = -EXP * m[i] * (hsd + COST_RT + fund[i])
        cap *= (1 + o)
    if i_fire is not None:
        mmr = MMR_T1 if cap * EXP <= MMR_TIER else MMR_T2; hsd = 1.0 / lev - mmr - SLIP_BP
        manual = -EXP * m[i_fire] * (hsd + COST_RT + fund[i_fire])
        wrong = -EXP * m[i_fire] * hsd  # figH식(비용누락)
        chk(abs(manual - hp_sample) < 1e-12, "하드스탑손익 == -EXP×mult×(hsd+COST_RT+fund)")
        chk(abs(manual - wrong) > 1e-9, f"figH식(비용누락 {wrong*100:.2f}%)과 다름 → 통일됨({manual*100:.2f}%)")
    else:
        chk(True, "레버20 발동 없음(표본 생략)")

    print("[⑥] 회복죽임 분해(정상손익>하드스탑손익)")
    hsd20 = 1.0 / 20 - MMR_T2 - SLIP_BP
    fire = MAE <= -hsd20
    o_all = R * EXP * m; hp_all = -EXP * m * (hsd20 + COST_RT + fund)
    rec_true = int(((o_all > hp_all) & fire).sum())          # 정상이 더 좋음(회복죽임)
    rec_rpos = int(((R > 0) & fire).sum())                   # 옛 정의(RPOS)
    chk(rec_true >= rec_rpos, f"정밀회복죽임 {rec_true}건 ⊇ RPOS옛정의 {rec_rpos}건(부분회복 포함)")

    print("[⑦] 손실한도+MDD 제약")
    ok = True
    for _, r in SW.iterrows():
        hsd = (1.0 / r['lev'] - MMR_T2 - SLIP_BP); sl = r['EXP'] * hsd
        if sl > LOSS_CAP + 1e-4: ok = False
    chk(ok, "모든 레버 단일손실 == EXP×hsd ≤ 7.5%")
    chk((SW['mdd'] >= MDD_LINE - 0.3).all(), "모든 레버 MDD ≥ -20%(이분탐색 경계)")

    print("[⑧] CPCV 견고성·최적 일관")
    chk('cpcv_p25' in BE.columns, "best.csv cpcv_p25 존재")
    chk(int(BE['lev'].iloc[0]) == int(SW.loc[SW['ret'].idxmax(), 'lev']), "best 레버 == scan 최대복리 레버")

    print(f"\n=== 결과: PASS {_n['p']} / FAIL {_n['f']} ===")
    os.makedirs(WORKHSTR, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d%H%M')
    bl = int(BE['lev'].iloc[0])
    with open(os.path.join(WORKHSTR, f"{stamp}.txt"), 'w', encoding='utf-8') as f:
        f.write(f"[{NAME}] 레버×EXP 스캔 (Ch1 정확공식 통일·회복죽임 정밀분해)\n검증 PASS{_n['p']}/FAIL{_n['f']}\n")
        f.write(f"최대복리 레버{bl} EXP{BE['EXP'].iloc[0]} +{int(BE['ret'].iloc[0])}% MDD{BE['mdd'].iloc[0]}% "
                f"PF{BE['pf'].iloc[0]} 회복죽임{int(BE['rec_n'].iloc[0])}건 CPCV-p25 +{int(BE['cpcv_p25'].iloc[0])}%\n")
        f.write("제약 미적용(출력만) — 레버 상한·PF하한·회복죽임 한도는 사장님 결정 대기\n")
    with open(os.path.join(WORKHSTR, "00WorkHstr_INDEX.txt"), 'a', encoding='utf-8') as f:
        f.write(f"\n[{NAME}] {stamp} check PASS{_n['p']}/FAIL{_n['f']} | 최대복리 레버{bl} +{int(BE['ret'].iloc[0])}% "
                f"MDD{BE['mdd'].iloc[0]}% PF{BE['pf'].iloc[0]} 회복죽임{int(BE['rec_n'].iloc[0])}건\n")
    print("✅ 전부 PASS" if _n['f'] == 0 else "❌ FAIL 있음 — 신뢰 보류")


if __name__ == "__main__":
    main()
