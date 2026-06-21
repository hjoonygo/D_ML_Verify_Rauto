# -*- coding: utf-8 -*-
# [check_07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep.py]
# 코드길이: 142줄 | 내부버전: SDCA_ExpCutLiqSweep_check_v1 | 로직 축약/생략 없이 전체 출력
# =============================================================================
# [목적] test가 만든 결과물을 8시나리오로 오염검사하고, 분석txt와 INDEX 한 줄을
#        D:\ML\verify\00WorkHstr 로 출력한다. (하위폴더 아님 — 지침 3②)
#
# [경로] HERE=하위폴더 / WORKHSTR=os.path.join(dirname(HERE),'00WorkHstr')=D:\ML\verify\00WorkHstr
#
# [8 시나리오]
#   ① 폴더/파일명 일치   ② 엔진 해시 dfdfac43 대조   ③ 결과CSV 3종 존재·행수
#   ④ MAE 물리정합(mae<=최종손실)   ⑤ 격리상한 정합(어떤 손실도 entry% 초과 불가)
#   ⑥ MDD 절대선 -15%(best 후보 전부)   ⑦ 실효노출 한 축(EXP고정·무발동시 PF 불변)
#   ⑧ 컷 분해 정합(n_rec+n_dir==n_cut)
#
# [함수 In/Out]
#   sha(path)->hex / load(name)->DataFrame / w(msg)→lines append
#   main(): 8검사 → 분석txt + INDEX 한 줄 → 00WorkHstr
# =============================================================================

import os, sys, hashlib, datetime
import pandas as pd

NAME = "07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep"
HERE = os.path.dirname(os.path.abspath(__file__))
WORKHSTR = os.path.join(os.path.dirname(HERE), "00WorkHstr")     # = D:\ML\verify\00WorkHstr
INDEX = os.path.join(WORKHSTR, "00WorkHstr_INDEX.txt")

ENGINE_HASH = {"SidewayDCA_Stg7_engine.py":
               "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086"}
REQ_CSV = [f"{NAME}_ledger.csv", f"{NAME}_sweep.csv", f"{NAME}_best.csv"]
MDD_LINE = -0.15


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def load(name):
    return pd.read_csv(os.path.join(HERE, name))


def main():
    lines = []
    def w(m): lines.append(m); print(m)
    passed = 0
    w(f"=== CHECK {NAME} (8시나리오 오염검사) ===")

    # ① 폴더/파일명 일치
    ok1 = os.path.basename(HERE) == NAME
    w(f"[1.파일명] 폴더={os.path.basename(HERE)} {'OK' if ok1 else 'FAIL 불일치(기대 '+NAME+')'}")
    passed += ok1

    # ② 엔진 해시
    ok2 = True
    for fn, want in ENGINE_HASH.items():
        p = os.path.join(HERE, "bots", fn)
        got = sha(p) if os.path.exists(p) else "없음"
        good = (got == want); ok2 = ok2 and good
        w(f"[2.엔진해시] {fn}: {'OK 무수정' if good else 'FAIL 변조/누락 got='+got[:16]}")
    passed += ok2

    # ③ 결과 CSV 존재·행수
    miss = [c for c in REQ_CSV if not os.path.exists(os.path.join(HERE, c))]
    if miss:
        w(f"[3.결과파일] 누락 {miss} → test 미완료. 데이터(D:\\ML\\verify) 확인.")
        _save(lines, 0); return
    led = load(REQ_CSV[0]); swp = load(REQ_CSV[1]); bst = load(REQ_CSV[2])
    ok3 = len(led) > 0 and len(swp) > 0
    w(f"[3.결과파일] 3종 존재 | 원장 {len(led)} 스윕 {len(swp)} 후보 {len(bst)} {'OK' if ok3 else 'FAIL 비어있음'}")
    passed += ok3

    # ④ MAE 물리정합 (mae <= 최종 가격손익; 손실거래 한정)
    fp = led['side'] * (led['exit_price'] - led['entry_price']) / led['entry_price']
    bad4 = int(((led['mae'] > fp + 1e-6) & (fp < 0)).sum())
    ok4 = (bad4 == 0)
    w(f"[4.MAE정합] 물리위반 {bad4}건 {'OK' if ok4 else 'FAIL'}")
    passed += ok4

    # ⑤ 격리상한 정합 (worst >= -entry_pct, 어떤 손실도 격리증거금 초과 불가)
    bad5 = int((swp['worst'] < -swp['entry_pct'] - 1e-6).sum())
    ok5 = (bad5 == 0)
    w(f"[5.격리상한] entry% 초과손실 {bad5}건 {'OK' if ok5 else 'FAIL 격리모델 오류'}")
    passed += ok5

    # ⑥ MDD 절대선 (best 후보 전부 -15% 이내)
    bad6 = int((bst['mdd'] < MDD_LINE - 1e-9).sum()) if len(bst) else 0
    ok6 = (bad6 == 0)
    w(f"[6.MDD절대선] 후보 중 -15% 초과 {bad6}건 {'OK' if ok6 else 'FAIL'}")
    passed += ok6

    # ⑦ 실효노출 한 축 (cut=none·무발동(n_cut=0,n_liq=0) 행은 EXP고정시 PF 불변)
    base = swp[(swp['cut_L'] == 'none') & (swp['n_cut'] == 0) & (swp['n_liq'] == 0)]
    ok7 = True; detail7 = []
    for exp, g in base.groupby('EXP'):
        if len(g) >= 2:
            spread = float(g['PF'].max() - g['PF'].min())
            if spread > 1e-6: ok7 = False; detail7.append(f"EXP{exp}편차{spread:.4f}")
    w(f"[7.실효노출한축] PF 불변성 {'OK' if ok7 else 'FAIL '+','.join(detail7)}")
    passed += ok7

    # ⑧ 컷 분해 정합 (n_rec + n_dir == n_cut)
    bad8 = int(((swp['n_rec'] + swp['n_dir']) != swp['n_cut']).sum())
    ok8 = (bad8 == 0)
    w(f"[8.컷분해] n_rec+n_dir != n_cut {bad8}건 {'OK' if ok8 else 'FAIL'}")
    passed += ok8

    # ── VERDICT (best 한 줄 요약) ──
    if len(bst):
        b = bst.iloc[0]
        verdict = (f"best EXP{b['EXP']}×lev{b['lev']} cut{b['cut_L']} "
                   f"ret{b['ret']*100:.1f}% MDD{b['mdd']*100:.1f}% worst{b['worst']*100:.1f}% "
                   f"CPCVp25 {b['cpcv_p25']} | recover{int(b['n_rec'])}/direct{int(b['n_dir'])} "
                   f"| 원장 {len(led)}건 | 컷없음기준선 포함 스윕 {len(swp)}")
    else:
        verdict = f"MDD<=-15%&한도내 후보 0개 | 원장 {len(led)}건 스윕 {len(swp)}"
    w(f"[VERDICT] {verdict}")
    w(f"[결과] 8시나리오 {passed}/8 {'PASS' if passed == 8 else 'FAIL'}")
    _save(lines, passed, verdict)


def _save(lines, passed, verdict=""):
    os.makedirs(WORKHSTR, exist_ok=True)
    now = datetime.datetime.now()
    txt = os.path.join(WORKHSTR, now.strftime("%Y%m%d_%H%M") + ".txt")
    with open(txt, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    line = (f"{now.strftime('%Y-%m-%d %H:%M')} | {NAME} | 분석:{os.path.basename(txt)} "
            f"| VERDICT {verdict} | 8시나리오 {passed}/8 {'PASS' if passed == 8 else 'FAIL'} "
            f"| check:{'PASS' if passed == 8 else 'FAIL'}")
    with open(INDEX, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(f"[저장] 분석txt → {txt}")
    print(f"[저장] INDEX 한 줄 추가 → {INDEX}")


if __name__ == "__main__":
    main()
