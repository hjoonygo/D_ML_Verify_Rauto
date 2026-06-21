# -*- coding: utf-8 -*-
# [파일명] check_07Prj_Ch1_Slippage_stg4_MaeLiqLimit.py
# 코드길이: 약 130줄 | 내부버전: 07Prj_Ch1_stg4_MaeLiqLimit_v1 | 로직 전체 출력(축약/생략 없음)
# ---------------------------------------------------------------------------------------------
# [이 코드가 하는 일] stg4 MAE 격리튕김 결과 오염검사 + 분석txt + INDEX 한 줄.
#   ① 엔진 무수정 해시검증(SpTrd 7f9192e3 / SidewayDCA dfdfac43)
#   ② 결과 CSV 존재·정합성(거래수·청산수·수수료 상수) 검사 — test 실패시 깔끔히 안내 후 종료
#   ③ 5설정 요약 + 회복/직행 분해 + 순효과 분석을 (분단위).txt로 D:\ML\verify\00WorkHstr 저장
#   ④ 00WorkHstr_INDEX.txt 한 줄 추가
# [In]  하위폴더의 stg4_mae_summary.csv / stg4_mae_ledger.csv / stg4_mae_coverage.csv
# [Out] D:\ML\verify\00WorkHstr\(분단위).txt + INDEX 한 줄. 콘솔 요약.
# [함수 In/Out] sha(path) In:파일경로 Out:sha256hex / read_csv_safe(path) In:경로 Out:DataFrame or None
#   / main() In:- Out:분석txt·INDEX
# [변수] ENGINE_HASH(엔진2종 기대해시) REQ_CSV(필수결과3종) NAME(이번 스테이지명)
# =============================================================================================
import os, sys, hashlib, datetime
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
NAME = "07Prj_Ch1_Slippage_stg4_MaeLiqLimit"

ENGINE_HASH = {
    "SpTrd_Fib_V1_Champion.py": "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
    "SidewayDCA_Stg7_engine.py": "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
}
REQ_CSV = ["stg4_mae_summary.csv", "stg4_mae_ledger.csv", "stg4_mae_coverage.csv"]


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

    w(f"[check] {NAME} 오염검사 시작")
    w("=" * 70)

    # ── ① 엔진 해시 검증 ──
    hash_ok = True
    for fn, want in ENGINE_HASH.items():
        p = os.path.join(HERE, "bots", fn)
        got = sha(p) if os.path.exists(p) else "없음"
        ok = (got == want)
        hash_ok = hash_ok and ok
        w(f"  [엔진해시] {fn}: {'OK 무수정' if ok else 'FAIL 변조/누락! got=' + got[:16]}")

    # ── ② 결과 CSV 존재 검사 (test 성공 여부) ──
    missing = [c for c in REQ_CSV if not os.path.exists(os.path.join(HERE, c))]
    if missing:
        w(f"  [결과파일] 누락: {missing}")
        w("  → test가 정상 완료되지 않았습니다(데이터 경로/엔진 확인). 깔끔히 종료합니다.")
        w("    필요 데이터: Merged_Data_with_Regime_Features.csv 등이 D:\\ML\\verify 에 있어야 합니다.")
        _save(lines, "FAIL_결과누락")
        return

    summ = read_csv_safe(os.path.join(HERE, "stg4_mae_summary.csv"))
    cov = read_csv_safe(os.path.join(HERE, "stg4_mae_coverage.csv"))
    led = read_csv_safe(os.path.join(HERE, "stg4_mae_ledger.csv"))

    # summary가 missing 메시지면 데이터 부재
    if summ is None or 'setting' not in summ.columns:
        w("  [결과] summary가 비정상(데이터 부재 가능). 종료.")
        _save(lines, "FAIL_summary비정상")
        return

    # ── ③ 정합성 검사 ──
    w("\n  [정합성]")
    if cov is not None and len(cov):
        c0 = cov.iloc[0]
        w(f"    거래수 {int(c0['n_trades'])} / 1분봉 {int(c0['n_1min_bars']):,} / 7h봉 {int(c0['n_7h_bars'])}")
        w(f"    펀딩 {c0['funding']} / FNG커버 {c0['fng_coverage_pct']}% / 장세출처 {c0['regime_source']}")
        w(f"    비용상수 cost_rt={c0['cost_rt']} fee_liq={c0['fee_liq']} half_cost={c0['half_cost']}")
        if abs(float(c0['cost_rt']) - 0.0014) > 1e-9 or abs(float(c0['half_cost']) - 0.0007) > 1e-9:
            w("    [경고] 수수료 상수가 14bp/7bp와 다름!")
    if led is not None and 'mae' in led.columns:
        n_dup = led.duplicated(subset=['entry_t', 'exit_t', 'side']).sum()
        w(f"    원장 거래 {len(led)}건 / 중복 {n_dup}건 / MAE 컬럼 존재 OK")
        if n_dup > 0:
            w("    [경고] 원장 중복 거래 발견!")

    # ── ④ 5설정 요약 + 회복/직행 분해 ──
    w("\n  [5설정 요약] (격리튕김 OFF vs ON, 순효과 = ON-OFF)")
    for _, r in summ.iterrows():
        w(f"    {r['setting']:>10} | 청산거리 {r['LIQ_dist']}% | "
          f"OFF ${r['cap_off']:>10,.0f}({r['mdd_off']}%) | ON ${r['cap_on']:>10,.0f}({r['mdd_on']}%) | "
          f"순효과 ${r['net_effect']:>+10,.0f}")
        w(f"               청산 {int(r['n_liq'])}건 = 회복 {int(r['recover_n'])}(놓친수익 {r['recover_loss_pct']}%p) "
          f"+ 직행 {int(r['direct_n'])}(방어 {r['direct_gain_pct']}%p)")

    # ── 결론(사장님 질문: 낮은 손실한도가 36개월 전체로 이득인가) ──
    w("\n  [결론] 순효과(ON-OFF)가 양(+)이면 격리튕김이 36개월 전체로 이득.")
    best = summ.loc[summ['net_effect'].idxmax()]
    w(f"    순효과 최대 = {best['setting']} (${best['net_effect']:+,.0f}). "
      f"양(+) 설정수 {int((summ['net_effect'] > 0).sum())}/{len(summ)}.")
    w(f"    → 직행 방어 > 회복 손실 이면 사장님 가설(낮은 손실한도가 수익) 성립.")

    _save(lines, _one_line(summ))
    w(f"\n[check] 완료. 분석txt·INDEX 저장 → {HSTR}")


def _one_line(summ):
    pos = int((summ['net_effect'] > 0).sum())
    best = summ.loc[summ['net_effect'].idxmax()]
    return f"MAE격리튕김 5설정검증 | 순효과+ {pos}/{len(summ)} | 최선 {best['setting']}(${best['net_effect']:+,.0f})"


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
