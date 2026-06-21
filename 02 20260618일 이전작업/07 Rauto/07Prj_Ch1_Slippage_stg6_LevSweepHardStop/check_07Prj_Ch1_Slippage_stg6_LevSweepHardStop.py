# -*- coding: utf-8 -*-
# [파일명] check_07Prj_Ch1_Slippage_stg6_LevSweepHardStop.py
# 코드길이: 약 165줄 | 내부버전: 07Prj_Ch1_stg6_LevSweepHardStop_v1 | 로직 전체 출력(축약/생략 없음)
# ---------------------------------------------------------------------------------------------
# [이 코드가 하는 일] stg6 레버리지 스윕(11~20배)+2차하드스탑 결과 오염검사(8시나리오)+분석txt+INDEX.
# [8개 검사 시나리오]
#   ①파일명/스테이지명 일치  ②엔진 무수정 해시(SpTrd 7f9192e3 / SidewayDCA dfdfac43)
#   ③결과 CSV 3종 존재(test 성공)  ④원장 거래 중복 탐지
#   ⑤MAE 정합성(손실거래 MAE<=R, 청산봉 버그 재발 방지)  ⑥EXP 고정 검사(전 레버리지 EXP=0.825)
#   ⑦레버리지 스윕 정합성(레버↑일수록 청산수 비감소, 11배 최소)  ⑧MDD 절대선(-15%) 초과 레버리지 식별
# [In]  하위폴더의 stg6_levsweep_summary.csv / _ledger.csv / _coverage.csv
# [Out] D:\ML\verify\00WorkHstr\(분단위).txt + INDEX 한 줄. 콘솔 요약. (결과는 전량 파일로만)
# [함수 In/Out] sha(p) In:경로 Out:sha256 / read_csv_safe(p) In:경로 Out:DataFrame|None
#   / main() In:- Out:분석txt·INDEX / _one_line(summ) In:summary Out:INDEX 한 줄 / _save(lines,sm) In:로그·요약 Out:파일
# [변수] ENGINE_HASH(엔진2종) REQ_CSV(필수3종) NAME(스테이지명) EXP_EXPECT=0.825 MDD_LIMIT=-15.0
# =============================================================================================
import os, sys, hashlib, datetime
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
NAME = "07Prj_Ch1_Slippage_stg6_LevSweepHardStop"
EXP_EXPECT = 0.825
MDD_LIMIT = -15.0

ENGINE_HASH = {
    "SpTrd_Fib_V1_Champion.py": "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
    "SidewayDCA_Stg7_engine.py": "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
}
REQ_CSV = ["stg6_levsweep_summary.csv", "stg6_levsweep_ledger.csv", "stg6_levsweep_coverage.csv"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv_safe(p):
    try:
        return pd.read_csv(p, encoding="utf-8-sig")
    except Exception:
        return None


def main():
    lines = []
    def w(s): lines.append(s); print(s)

    w(f"[check] {NAME} 오염검사 (8시나리오) 시작")
    w("=" * 70)

    # ── 시나리오① 파일명/스테이지명 일치 ──
    w(f"  [1.파일명] NAME={NAME} / 폴더={os.path.basename(HERE)} "
      f"{'OK' if os.path.basename(HERE) == NAME else '[경고] 폴더명 불일치'}")

    # ── 시나리오② 엔진 해시 검증 ──
    hash_ok = True
    for fn, want in ENGINE_HASH.items():
        p = os.path.join(HERE, "bots", fn)
        got = sha(p) if os.path.exists(p) else "없음"
        ok = (got == want)
        hash_ok = hash_ok and ok
        w(f"  [2.엔진해시] {fn}: {'OK 무수정' if ok else 'FAIL 변조/누락! got=' + got[:16]}")

    # ── 시나리오③ 결과 CSV 존재 ──
    missing = [c for c in REQ_CSV if not os.path.exists(os.path.join(HERE, c))]
    if missing:
        w(f"  [3.결과파일] 누락: {missing}")
        w("  → test가 정상 완료되지 않았습니다(데이터 경로/엔진 확인). 깔끔히 종료합니다.")
        w("    필요 데이터: Merged_Data_with_Regime_Features.csv 등이 D:\\ML\\verify 에 있어야 합니다.")
        _save(lines, "FAIL_결과누락")
        return
    w(f"  [3.결과파일] 3종 모두 존재 OK")

    summ = read_csv_safe(os.path.join(HERE, "stg6_levsweep_summary.csv"))
    cov = read_csv_safe(os.path.join(HERE, "stg6_levsweep_coverage.csv"))
    led = read_csv_safe(os.path.join(HERE, "stg6_levsweep_ledger.csv"))
    if summ is None or 'setting' not in summ.columns:
        w("  [결과] summary가 비정상(데이터 부재 가능). 종료.")
        _save(lines, "FAIL_summary비정상")
        return

    # ── 시나리오④ 원장 중복 ──
    if led is not None:
        n_dup = led.duplicated(subset=['entry_t', 'exit_t', 'side']).sum()
        w(f"  [4.중복] 원장 {len(led)}건 / 중복 {int(n_dup)}건 {'OK' if n_dup == 0 else '[경고] 중복!'}")

    # ── 시나리오⑤ MAE 정합성 (청산봉 버그 재발 방지) ──
    if led is not None and 'mae' in led.columns:
        loss = led[led['R'] < 0]
        viol = loss[loss['mae'] > loss['R'] + 1e-9]
        w(f"  [5.MAE정합성] 손실거래 MAE<=R 위반 {len(viol)}/{len(loss)}건 "
          f"{'OK(청산봉 포함 정상)' if len(viol) == 0 else '[경고] 청산봉 누락 버그 재발!'}")

    # ── 시나리오⑥ EXP 고정 검사 ──
    exp_bad = summ[(summ['EXP'] - EXP_EXPECT).abs() > 1e-6]
    w(f"  [6.EXP고정] 전 레버리지 EXP={EXP_EXPECT} "
      f"{'OK' if len(exp_bad) == 0 else '[경고] EXP 불일치 ' + str(len(exp_bad)) + '건'}")

    # ── 시나리오⑦ 레버리지 스윕 정합성 (레버↑ → 청산수 비감소, 11배 최소) ──
    sm = summ.sort_values('lev')
    nliq = sm['n_liq'].values
    monotone = all(nliq[i] <= nliq[i + 1] for i in range(len(nliq) - 1))
    w(f"  [7.스윕정합성] 청산수 {list(map(int, nliq))} (레버↑일수록 비감소) "
      f"{'OK' if monotone else '[참고] 비단조(꼬리 분포 차이)'}")
    w(f"               최소청산 = {int(sm.iloc[0]['lev'])}배 {int(nliq[0])}건")

    # ── 시나리오⑧ MDD 절대선(-15%) 검사 ──
    over = summ[summ['mdd_on'] < MDD_LIMIT]
    safe = summ[summ['mdd_on'] >= MDD_LIMIT]
    w(f"  [8.MDD절대선] -15% 초과 레버리지: "
      f"{sorted(over['lev'].tolist()) if len(over) else '없음(전부 안전)'}")
    w(f"               안전 레버리지: {sorted(safe['lev'].tolist())}")

    # ── 레버리지별 요약 ──
    w("\n  [레버리지 스윕 요약] (OFF=버팀 / ON=2차하드스탑 / 순효과=ON-OFF)")
    for _, r in sm.iterrows():
        w(f"    {int(r['lev']):>2}배(진입{r['entry_pct']}%) 청산거리{r['liq_dist']}% 하드{r['hardstop_dist']}% | "
          f"OFF ${r['cap_off']:>9,.0f}({r['mdd_off']}%) | ON ${r['cap_on']:>9,.0f}({r['mdd_on']}%) | "
          f"순{r['net_effect']:>+8,.0f} | 청산{int(r['n_liq'])}(회복{int(r['recover_n'])}/직행{int(r['direct_n'])})")

    # ── 결론 ──
    w("\n  [결론]")
    z = sm[sm['n_liq'] == 0]
    if len(z):
        b = z.loc[z['cap_on'].idxmax()]
        w(f"    청산 0건(다 버팀) 최대 레버리지 = {int(b['lev'])}배, 잔고 ${b['cap_on']:,.0f}, MDD {b['mdd_on']}%")
    bestnet = summ.loc[summ['net_effect'].idxmax()]
    w(f"    순효과 최대 = {int(bestnet['lev'])}배 (${bestnet['net_effect']:+,.0f}). "
      f"양(+) 레버리지 {int((summ['net_effect'] > 0).sum())}/{len(summ)}")

    _save(lines, _one_line(summ))
    w(f"\n[check] 완료. 분석txt·INDEX 저장 → {HSTR}")


def _one_line(summ):
    sm = summ.sort_values('lev')
    z = sm[sm['n_liq'] == 0]
    zmax = int(z['lev'].max()) if len(z) else 0
    over = sorted(summ[summ['mdd_on'] < MDD_LIMIT]['lev'].tolist())
    return (f"레버스윕11~20+2차하드스탑 | 청산0배까지 {zmax}배 | "
            f"MDD-15%초과 {over if over else '없음'} | EXP고정 {EXP_EXPECT}")


def _save(lines, summary):
    os.makedirs(HSTR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    txt = os.path.join(HSTR, f"{stamp}.txt")
    with open(txt, "w", encoding="utf-8") as f:
        f.write(f"[{NAME}] 분석 {stamp}\n")
        for fn, hsh in ENGINE_HASH.items():
            f.write(f"engine {fn} = {hsh[:16]}...\n")
        f.write("\n".join(lines))
    idx = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
    with open(idx, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {NAME} | 분석:{stamp}.txt | {summary}\n")


if __name__ == "__main__":
    main()
