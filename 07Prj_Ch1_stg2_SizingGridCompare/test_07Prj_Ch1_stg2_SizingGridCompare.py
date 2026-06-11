# -*- coding: utf-8 -*-
# [파일명] test_07Prj_Ch1_stg2_SizingGridCompare.py
# 코드길이: 약 215줄 | 내부버전: 07Prj_Ch1_stg2_test_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   stg1 모듈(IsoBounceSim, liq_distance=-0.0724 정직화)을 06Prj_Ch7_stg4의 best 원장에 적용.
#   ★stg4의 stg4_best_ledger.csv를 입력 원장으로 사용 (사장님 PC에 stg4 굴린 결과 있음).
#   ★4모드(M0/M1/M2/M3) 각각 적용해서 잔고 곡선·MDD·연도별·청산건수 비교.
#   ★★★ M0 동치검증: M0 잔고 == stg4의 .stg4_metric의 best_end. 일치하면 모듈 무변형 입증.
#
# [엔진 무수정] stg4 코드·챔피언 엔진 한 줄도 안 건드림. 이미 만들어진 원장에 사후필터만.
#
# [PATH] 실행 D:\ML\verify\07Prj_Ch1_stg2_SizingGridCompare\
#   입력: stg4 폴더의 stg4_best_ledger.csv + .stg4_metric (find_file로 자동 탐색)
#   출력: 같은 폴더 csv 5종 + .stg2_metric. 분석txt·INDEX는 check.py가 D:\ML\verify\00WorkHstr\로.
#
# [In/Out 태그]
#   isolated_bounce_simulator.IsoBounceSim / MODE_PRESETS / ALPHA_PROVENANCE 사용
#   본코드: find_file(In 후보경로 / Out 경로) / read_metric(In .stg4_metric / Out dict) /
#           compound_end(In trades / Out 최종잔고·수익률·곡선) — stg4 동일 로직 재사용
#           mdd_of(In 곡선 / Out MDD%) — stg4 동일 로직 재사용
#           apply_mode(In trades, 모드명 / Out 모드별 결과 dict + 변환된 trades)
#           main()
#   변수: START=10000 (stg4와 동일 시작자본)
# ==============================================================================
import os, sys, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from isolated_bounce_simulator import IsoBounceSim, MODE_PRESETS, ALPHA_PROVENANCE

START = 10000.0
YEARS = [2023, 2024, 2025, 2026]
MODE_ORDER = ["M0_base", "M1_cross_now", "M2_iso_notail", "M3_iso_tailcut"]


def find_file(candidates):
    # stg4 결과 파일을 여러 경로에서 탐색 — 사장님 PC 폴더 구조 추정 X, 명시 후보만
    search_dirs = [
        PARENT,                                            # D:\ML\verify
        os.path.join(PARENT, "06Prj_Ch7_stg4_GreedShortGuard"),
        os.path.join(PARENT, "06Prj_Ch7_stg4_GreedShortGuard", "code"),
        HERE,
    ]
    for d in search_dirs:
        for name in candidates:
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p
    return None


def read_metric(path):
    # .stg4_metric 파싱 — k=v 줄 dict로
    d = {}
    if not (path and os.path.exists(path)):
        return d
    for ln in open(path, encoding="utf-8"):
        if "=" in ln:
            k, v = ln.strip().split("=", 1)
            d[k] = v
    return d


def compound_end(trades, start=START, r_key="R"):
    # stg4의 compound_end와 동일 — exit_t 정렬 후 R을 곱해 복리. 곡선·최종잔고 반환
    if not trades:
        return start, 0.0, []
    s = sorted(trades, key=lambda t: pd.Timestamp(t['exit_t']).value)
    cap = start; curve = []
    for t in s:
        cap *= (1.0 + float(t[r_key])); curve.append(cap)
    return cap, round((cap / start - 1) * 100, 2), curve


def mdd_of(curve, start=START):
    # stg4의 mdd_of와 동일
    peak = start; mdd = 0.0
    for cap in curve:
        peak = max(peak, cap); mdd = min(mdd, (cap - peak) / peak)
    return round(mdd * 100, 2)


def apply_mode(trades_dict, mode_name):
    # 거래 dict 리스트에 한 모드 적용 → 잔고·MDD·연도별·청산건수
    sim = IsoBounceSim.from_preset(mode_name)
    converted, n_liq = sim.apply_to_trades(trades_dict, r_key="R")
    cap_end, ret_pct, curve = compound_end(converted, START, r_key="R")
    mdd_pct = mdd_of(curve, START)
    # 연도별 R 단순합 (참고용; 잔고는 복리)
    by_year = {y: 0.0 for y in YEARS}
    for t in converted:
        y = int(t.get('year', 0))
        if y in by_year:
            by_year[y] += float(t['R'])
    # 연도별 복리 잔고 비율
    by_year_compound = {y: 1.0 for y in YEARS}
    for t in converted:
        y = int(t.get('year', 0))
        if y in by_year_compound:
            by_year_compound[y] *= (1.0 + float(t['R']))
    return dict(
        mode=mode_name, exposure=sim.exposure, tail_cut=sim.tail_cut,
        liq_distance=sim.liq_distance, enable_tail_cut=sim.enable_tail_cut,
        n_total=len(converted), n_liquidated=n_liq,
        end=round(cap_end, 2), ret_pct=ret_pct, mdd_pct=mdd_pct,
        yr2023_R=round(by_year[2023]*100, 2), yr2024_R=round(by_year[2024]*100, 2),
        yr2025_R=round(by_year[2025]*100, 2), yr2026_R=round(by_year[2026]*100, 2),
        yr2023_comp=round((by_year_compound[2023]-1)*100, 2),
        yr2024_comp=round((by_year_compound[2024]-1)*100, 2),
        yr2025_comp=round((by_year_compound[2025]-1)*100, 2),
        yr2026_comp=round((by_year_compound[2026]-1)*100, 2),
    ), converted, curve


def main():
    print("[stg2 SizingGridCompare] stg4 best 원장에 4모드(M0/M1/M2/M3) 적용 + 동치검증")
    print(f"  ALPHA_PROVENANCE: {ALPHA_PROVENANCE['source']}")
    print(f"  liq_distance(M3): {MODE_PRESETS['M3_iso_tailcut']['liq_distance']} (stg1 -0.0719에서 정직화)")
    print()

    # ── 입력 파일 탐색 ───────────────────────────────────────────────────
    ledger_path = find_file(["stg4_best_ledger.csv"])
    metric_path = find_file([".stg4_metric"])
    if ledger_path is None:
        msg = "[ERR] stg4_best_ledger.csv 없음 — D:\\ML\\verify\\06Prj_Ch7_stg4_*\\code\\에서 stg4 먼저 굴려주세요"
        print(msg)
        pd.DataFrame([{'error': msg}]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
        with open(os.path.join(HERE, ".stg2_metric"), "w", encoding="utf-8") as f:
            f.write("input_missing=True\nledger_found=False\n")
        return

    print(f"[입력] ledger: {ledger_path}")
    if metric_path:
        print(f"[입력] metric: {metric_path}")

    # ── 원장 로드 ────────────────────────────────────────────────────────
    led = pd.read_csv(ledger_path)
    if 'R' not in led.columns:
        print(f"[ERR] R 컬럼 없음 (있는 컬럼: {list(led.columns)})")
        return
    if 'year' not in led.columns:
        led['year'] = pd.to_datetime(led['entry_t']).dt.year
    trades_dict = led.to_dict('records')
    print(f"[원장] {len(trades_dict)}거래 (컬럼: {list(led.columns)})")

    # ── stg4 기준값(best_end) 읽기 ──────────────────────────────────────
    stg4_metric = read_metric(metric_path) if metric_path else {}
    stg4_best_end = float(stg4_metric.get('best_end', 0)) if stg4_metric.get('best_end', '').replace('.','',1).isdigit() else None
    if stg4_best_end:
        print(f"[stg4 기준] best_end = ${stg4_best_end:,.0f} (case={stg4_metric.get('best_case','?')})")
    else:
        print(f"[stg4 기준] best_end 못 읽음 — 동치검증 생략 가능")

    # ── 4모드 적용 ──────────────────────────────────────────────────────
    print()
    summary_rows = []; curves = {}
    for mode in MODE_ORDER:
        result, converted, curve = apply_mode(trades_dict, mode)
        summary_rows.append(result)
        curves[mode] = curve
        print(f"  [{mode}] end=${result['end']:,.0f} ret={result['ret_pct']}% mdd={result['mdd_pct']}% "
              f"liq={result['n_liquidated']}/{result['n_total']}")

    # ── 동치검증 ────────────────────────────────────────────────────────
    m0_end = summary_rows[0]['end']
    equivalence_ok = None
    equiv_diff_pct = None
    if stg4_best_end:
        equiv_diff_pct = abs(m0_end - stg4_best_end) / stg4_best_end * 100
        equivalence_ok = (equiv_diff_pct < 0.1)  # 0.1% 허용 오차
        print()
        print(f"[★동치검증] stg4 best_end ${stg4_best_end:,.0f} vs stg2 M0 ${m0_end:,.0f} "
              f"(diff {equiv_diff_pct:.4f}%) → {'OK' if equivalence_ok else 'FAIL'}")

    # ── 결과 CSV 저장 ───────────────────────────────────────────────────
    df_summary = pd.DataFrame(summary_rows)
    df_summary.to_csv(os.path.join(HERE, "stg2_summary_4modes.csv"), index=False, encoding='utf-8-sig')

    # 잔고곡선: 한 CSV에 4모드 열로
    max_len = max(len(c) for c in curves.values()) if curves else 0
    df_curve = pd.DataFrame({mode: curves[mode] + [None]*(max_len-len(curves[mode])) for mode in MODE_ORDER})
    df_curve.index.name = 'trade_seq'
    df_curve.to_csv(os.path.join(HERE, "stg2_balance_curve_4modes.csv"), encoding='utf-8-sig')

    # 연도별 분해표 (4모드 × 4년)
    yr_rows = []
    for r in summary_rows:
        for y in YEARS:
            yr_rows.append(dict(mode=r['mode'], year=y,
                                R_sum_pct=r[f'yr{y}_R'],
                                compound_pct=r[f'yr{y}_comp']))
    pd.DataFrame(yr_rows).to_csv(os.path.join(HERE, "stg2_by_year_4modes.csv"), index=False, encoding='utf-8-sig')

    # 합리성 비교 (M0 > M2 > M3 > M1 패턴 + M3 청산건수)
    sanity_rows = [
        dict(check="M0 > M1 (자본1배 > cross 0.25배)", pass_=(summary_rows[0]['end'] > summary_rows[1]['end']),
             m0=summary_rows[0]['end'], m1=summary_rows[1]['end']),
        dict(check="M0 > M2 (1.0 > 0.975, 미세차이)", pass_=(summary_rows[0]['end'] > summary_rows[2]['end']),
             m0=summary_rows[0]['end'], m2=summary_rows[2]['end']),
        dict(check="M2 vs M3 (테일컷 효과)",
             pass_=(summary_rows[2]['end'] != summary_rows[3]['end']),  # 다르기만 해도 OK(어느쪽이 클지는 데이터 의존)
             m2=summary_rows[2]['end'], m3=summary_rows[3]['end']),
        dict(check="M0,M1,M2 청산 0건 (테일컷 OFF)",
             pass_=all(summary_rows[i]['n_liquidated']==0 for i in [0,1,2]),
             m0_liq=summary_rows[0]['n_liquidated'], m1_liq=summary_rows[1]['n_liquidated'],
             m2_liq=summary_rows[2]['n_liquidated']),
        dict(check="M3 청산건수 = (R<=-0.0724 거래수)",
             pass_=(summary_rows[3]['n_liquidated'] == sum(1 for t in trades_dict if t['R'] <= -0.0724)),
             m3_liq=summary_rows[3]['n_liquidated'],
             expected=sum(1 for t in trades_dict if t['R'] <= -0.0724)),
    ]
    pd.DataFrame(sanity_rows).to_csv(os.path.join(HERE, "stg2_sanity.csv"), index=False, encoding='utf-8-sig')

    # summary
    pd.DataFrame([
        dict(section="입력", result="OK", detail=f"{len(trades_dict)}거래 from {os.path.basename(ledger_path)}"),
        dict(section="stg4 기준", result="OK" if stg4_best_end else "SKIP",
             detail=f"best_end=${stg4_best_end:,.0f}" if stg4_best_end else "metric 못 읽음"),
        dict(section="M0 동치", result="OK" if equivalence_ok else ("FAIL" if equivalence_ok is False else "SKIP"),
             detail=f"diff {equiv_diff_pct:.4f}%" if equiv_diff_pct is not None else "metric 없음"),
        dict(section="4모드 잔고",
             result="OK", detail=f"M0=${summary_rows[0]['end']:,.0f} M1=${summary_rows[1]['end']:,.0f} "
                                 f"M2=${summary_rows[2]['end']:,.0f} M3=${summary_rows[3]['end']:,.0f}"),
        dict(section="M3 청산", result="OK",
             detail=f"{summary_rows[3]['n_liquidated']}건 / {summary_rows[3]['n_total']}거래"),
        dict(section="M3 MDD", result="WARN" if summary_rows[3]['mdd_pct'] < -15 else "OK",
             detail=f"{summary_rows[3]['mdd_pct']}% (한도 -15%)"),
    ]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')

    # .stg2_metric
    with open(os.path.join(HERE, ".stg2_metric"), "w", encoding="utf-8") as f:
        f.write(f"input_missing=False\nledger_path={os.path.basename(ledger_path)}\nn_trades={len(trades_dict)}\n")
        f.write(f"stg4_best_end={stg4_best_end if stg4_best_end else 'NONE'}\n")
        f.write(f"equivalence_ok={equivalence_ok}\nequiv_diff_pct={equiv_diff_pct}\n")
        for r in summary_rows:
            f.write(f"{r['mode']}_end={r['end']}\n")
            f.write(f"{r['mode']}_mdd={r['mdd_pct']}\n")
            f.write(f"{r['mode']}_liq={r['n_liquidated']}\n")
        f.write(f"M3_liq_distance={MODE_PRESETS['M3_iso_tailcut']['liq_distance']}\n")
        f.write(f"M3_tail_cut={MODE_PRESETS['M3_iso_tailcut']['tail_cut']}\n")
        f.write(f"lookahead_block=postfilter_only_no_engine_change\nlabel_in_feature=False\n")

    print()
    print(f"[verdict] stg2 SizingGridCompare — 4모드 적용 완료. M0 동치 {'OK' if equivalence_ok else ('FAIL' if equivalence_ok is False else 'SKIP')}")
    print(f"          다음: stg3 CrashStressTest — 2025-10-11 폭락 구간 + intrabar 청산검증")


if __name__ == "__main__":
    main()
