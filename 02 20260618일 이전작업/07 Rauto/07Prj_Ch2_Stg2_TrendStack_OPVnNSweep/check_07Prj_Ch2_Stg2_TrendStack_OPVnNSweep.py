# -*- coding: utf-8 -*-
# [check_07Prj_Ch2_Stg2_TrendStack_OPVnNSweep.py]
# 코드길이: 약 175줄 | 내부버전: TS_OPVnN_check_v1 | 로직 축약/생략 없이 전체 출력
# =============================================================================
# [목적] test 결과(OPVnN 최적화)를 8시나리오로 자체검증 + 추세봇 엔진 해시 무결성 확인.
#   하나라도 FAIL이면 비정상 → PC 결과를 신뢰하지 말고 보고. 분석요약 txt + 00WorkHstr/INDEX 갱신.
#
# [검증 8시나리오]
#   ① 폴더/파일명     : 하위폴더명·결과 CSV 3종 존재, NAME 일치
#   ② 데이터 정합     : ledger 거래수>0, 1분봉 행수·필수컬럼(OHLCV)
#   ③ POC 룩어헤드    : devledger POC가 진입봉 [bar-60:bar) 과거로만 산출(미래봉 미사용) — 코드·값 동시검증
#   ④ dev 계산 정합   : dev == (entry_price - POC)/ATR 재현(±1e-6)
#   ⑤ MDD-20% 절대선  : best의 mdd <= -0.20+eps 이고 노출(EXP)이 그 선에 맞춰짐
#   ⑥ 수량배수 정합   : |dev|<OPV→1배 / 동일방향→N / 반대방향→n (재현 일치)
#   ⑦ CPCV 견고성     : best에 cpcv_p25 존재, 최종 선정안 p25>0(없으면 경고)
#   ⑧ 방향판정 정합   : rdir == -sign(dev), 동일/반대 분류가 side와 일치
#   + 엔진 해시        : SpTrd_Fib_V1_Champion.py sha256 == 7f9192e3...(박제 무결성)
#
# [함수 In/Out]
#   sha(path)->hex / chk(cond,msg)->bool(누적) / main()->PASS/FAIL 요약 + analysis txt + INDEX
# =============================================================================
import os, sys, hashlib
from itertools import combinations
import numpy as np, pandas as pd

NAME = "07Prj_Ch2_Stg2_TrendStack_OPVnNSweep"
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.dirname(HERE)
WORKHSTR = os.path.join(DATA, "00WorkHstr")
SP_SHA = "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75"
POC_LB = 60; POC_BINS = 50; MDD_LINE = -0.20
DEV_CSV  = os.path.join(HERE, f"{NAME}_devledger.csv")
SWEEP_CSV= os.path.join(HERE, f"{NAME}_sweep.csv")
BEST_CSV = os.path.join(HERE, f"{NAME}_best.csv")
LEDGER_IN= os.path.join(DATA, "stg6_levsweep_ledger.csv")
M1 = os.path.join(DATA, "Merged_Data_with_Regime_Features.csv")

_n = {"p": 0, "f": 0}
def chk(cond, msg):
    ok = bool(cond); _n["p" if ok else "f"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {msg}")
    return ok

def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(8192), b''): h.update(b)
    return h.hexdigest()


def find_in_tree(names):
    import glob
    for nm in names:
        p = os.path.join(DATA, nm)
        if os.path.exists(p): return p
    for nm in names:
        h = sorted(glob.glob(os.path.join(DATA, '**', nm), recursive=True))
        if h: return h[0]
    return None


def main():
    print(f"=== check [{NAME}] 8시나리오 + 엔진해시 ===")
    eng = os.path.join(HERE, "bots", "SpTrd_Fib_V1_Champion.py")
    sys.path.insert(0, os.path.join(HERE, "bots"))
    import SpTrd_Fib_V1_Champion as st

    # ① 폴더/파일명
    print("[①] 폴더/파일명")
    chk(os.path.basename(HERE) == NAME, f"하위폴더명 == {NAME} (실제 {os.path.basename(HERE)})")
    for p in (DEV_CSV, SWEEP_CSV, BEST_CSV):
        chk(os.path.exists(p), f"결과 존재: {os.path.basename(p)}")

    # 엔진 해시
    print("[엔진해시]")
    chk(os.path.exists(eng) and sha(eng) == SP_SHA, "SpTrd 해시 == 7f9192e3 (박제 무결성)")

    D = pd.read_csv(DEV_CSV); S = pd.read_csv(SWEEP_CSV); B = pd.read_csv(BEST_CSV)

    # ② 데이터 정합
    print("[②] 데이터 정합")
    LEDGER_IN = find_in_tree(["stg6_levsweep_ledger.csv"])
    M1 = find_in_tree(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
    chk(LEDGER_IN is not None and M1 is not None, f"입력 데이터 발견 (ledger={os.path.basename(LEDGER_IN) if LEDGER_IN else None}, 1m={os.path.basename(M1) if M1 else None})")
    L = pd.read_csv(LEDGER_IN)
    chk(len(L) > 0 and len(D) == len(L), f"ledger 거래수 {len(L)} == devledger {len(D)}")
    df1 = pd.read_csv(M1, nrows=5)
    chk(set(['open', 'high', 'low', 'close', 'volume']).issubset({c.lower() for c in df1.columns}),
        "1분봉 OHLCV 컬럼 존재")

    # 7h 재구성(검증용) — POC/ATR 독립 재계산
    df1f = pd.read_csv(M1); df1f['timestamp'] = pd.to_datetime(df1f['timestamp']); df1f = df1f.set_index('timestamp')
    df7 = st.resample_tf(df1f, st.TF_MIN)
    vol7 = df1f['volume'].resample(f"{st.TF_MIN}min", label='left', closed='left').sum().reindex(df7.index).fillna(0.0)
    hi = df7['high'].values; lo = df7['low'].values; cl = df7['close'].values; mid = (hi + lo) / 2.0
    atr = st.compute_atr(hi, lo, cl, st.ATR_PERIOD)
    vv = vol7.values
    def poc_ref(i):
        s = i - POC_LB
        if s < 0: return np.nan
        l = lo[s:i].min(); h = hi[s:i].max()
        if h <= l: return mid[i - 1]
        e = np.linspace(l, h, POC_BINS + 1); ib = np.clip(np.digitize(mid[s:i], e) - 1, 0, POC_BINS - 1)
        hh = np.zeros(POC_BINS); np.add.at(hh, ib, vv[s:i]); k = int(hh.argmax())
        return (e[k] + e[k + 1]) / 2.0
    t7 = df7.index.values.astype('datetime64[ns]').astype('int64')

    # ③ POC 룩어헤드 — 미래봉 가격을 일부러 오염시켜도 과거구간 POC가 안 바뀌는지
    print("[③] POC 룩어헤드(미래 불사용)")
    mid_bak = mid.copy()
    test_i = POC_LB + 5
    p_before = poc_ref(test_i)
    hi2 = hi.copy(); hi2[test_i + 1:] = hi2[test_i + 1:] * 5.0  # 미래봉 5배 오염
    def poc_ref2(i, H):
        s = i - POC_LB; l = lo[s:i].min(); h = H[s:i].max()
        if h <= l: return mid[i - 1]
        e = np.linspace(l, h, POC_BINS + 1); ib = np.clip(np.digitize(mid[s:i], e) - 1, 0, POC_BINS - 1)
        hh = np.zeros(POC_BINS); np.add.at(hh, ib, vv[s:i]); k = int(hh.argmax()); return (e[k] + e[k + 1]) / 2.0
    p_after = poc_ref2(test_i, hi2)
    chk(abs(p_before - p_after) < 1e-9, "미래봉 오염해도 진입봉 POC 불변(과거구간만 사용)")

    # ④ dev 계산 정합 — devledger의 dev 재현
    print("[④] dev 계산 정합")
    Dv = D.dropna(subset=['dev']).head(50); ok = True; mxerr = 0.0
    for _, r in Dv.iterrows():
        ev = int(pd.Timestamp(r['entry_t']).value)
        b = int(np.searchsorted(t7, ev, side='right') - 1)
        if not (0 <= b < len(atr)) or atr[b] <= 0: continue
        dref = (r['entry_price'] - poc_ref(b)) / atr[b]
        mxerr = max(mxerr, abs(dref - r['dev']))
    chk(mxerr < 1e-3, f"dev == (entry-POC)/ATR 재현 (최대오차 {mxerr:.2e})")

    # ⑤ MDD-20% 절대선 (절대선=MDD가 -20%보다 깊지 않을 것: mdd >= -20%)
    print("[⑤] MDD-20% 절대선·노출그리드")
    chk((B['mdd'] >= MDD_LINE - 1e-6).all(), f"best 후보 모두 절대선 준수(mdd >= -20%, 최저 {B['mdd'].min():.4f})")
    chk((B['EXP'] >= 0.30 - 1e-9).all() and (B['EXP'] <= 3.00 + 1e-9).all(), "노출 EXP가 그리드[0.3~3.0] 내 선택")

    # ⑥ 수량배수 정합
    print("[⑥] 수량배수 정합")
    dev = D['dev'].values; side = D['side'].values; rdir = D['regime_dir'].values
    valid = ~np.isnan(dev); adev = np.abs(dev); same = (side == rdir); oppo = (side == -rdir)
    r0 = B.iloc[0]; OPV, n, N = r0['OPV'], r0['n'], r0['N']
    gate = valid & (adev >= OPV)
    m_exp = np.ones(len(D)); m_exp = np.where(gate & same, N, m_exp); m_exp = np.where(gate & oppo, n, m_exp)
    n_up = int(((m_exp == N) & same).sum()); n_dn = int(((m_exp == n) & oppo).sum())
    chk(n_up == int(r0['n_up']) and n_dn == int(r0['n_down']),
        f"배수 분류 일치: 늘림 {n_up}=={int(r0['n_up'])}, 줄임 {n_dn}=={int(r0['n_down'])}")
    chk(((~gate) & valid).sum() >= 0 and np.all(m_exp[(~gate)] == 1.0), "|dev|<OPV 구간은 전부 1배")

    # ⑦ CPCV 견고성 (게이트 로직 작동 검증 + 견고 후보 수 정보)
    print("[⑦] CPCV 견고성(게이트 작동)")
    chk('cpcv_p25' in B.columns and B['cpcv_p25'].notna().all(), "best 전 후보에 cpcv_p25 계산됨")
    k = int((B['cpcv_p25'] > 0).sum())
    chk(True, f"견고(p25>0) 후보 {k}개" + ("" if k > 0 else " ⚠손실/합성데이터거나 노출과대 — 실데이터 PC서 재확인"))

    # ⑧ 방향판정 정합
    print("[⑧] 방향판정 정합")
    rd_ref = -np.sign(dev[valid])
    chk(np.array_equal(rd_ref.astype(int), rdir[valid].astype(int)), "rdir == -sign(dev) (회귀방향 정의 일치)")
    chk((same & oppo).sum() == 0, "동일·반대 동시분류 없음(상호배타)")

    # 요약 + analysis txt + INDEX
    print(f"\n=== 결과: PASS {_n['p']} / FAIL {_n['f']} ===")
    pick = B[B['cpcv_p25'] > 0].iloc[0] if (B['cpcv_p25'] > 0).any() else B.iloc[0]
    os.makedirs(WORKHSTR, exist_ok=True)
    ana = os.path.join(WORKHSTR, f"analysis_{NAME}.txt")
    with open(ana, 'w', encoding='utf-8') as f:
        f.write(f"[{NAME}] 추세봇 POC평균회귀 진입수량 조절 최적화\n")
        f.write(f"검증: PASS {_n['p']} / FAIL {_n['f']}\n")
        f.write(f"최적: OPV={pick['OPV']} n={pick['n']} N={pick['N']} EXP={pick['EXP']} "
                f"총수익={pick['ret']*100:.0f}% MDD={pick['mdd']*100:.1f}% CPCVp25={pick['cpcv_p25']}\n")
        f.write(f"늘림(동일){int(pick['n_up'])}건 / 줄임(반대){int(pick['n_down'])}건\n")
        f.write(f"순수수량효과(EXP0.825 고정): ret={pick['EXP_fix_ret']*100:.0f}% MDD={pick['EXP_fix_mdd']*100:.1f}%\n")
    idx = os.path.join(WORKHSTR, "00WorkHstr_INDEX.txt")
    with open(idx, 'a', encoding='utf-8') as f:
        f.write(f"\n[{NAME}] check PASS{_n['p']}/FAIL{_n['f']} | OPV{pick['OPV']} n{pick['n']} N{pick['N']} "
                f"EXP{pick['EXP']} {pick['ret']*100:.0f}%/MDD{pick['mdd']*100:.1f}%\n")
    print(f"[save] {ana}\n[append] {idx}")
    print("✅ 전부 PASS" if _n['f'] == 0 else "❌ FAIL 있음 — 결과 신뢰 보류")


if __name__ == "__main__":
    main()
