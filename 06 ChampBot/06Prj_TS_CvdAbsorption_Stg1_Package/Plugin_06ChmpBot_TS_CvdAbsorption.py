# -*- coding: utf-8 -*-
# ============================================================================
# [Plugin_06ChmpBot_TS_CvdAbsorption.py] 챔피언봇(성급왕TS) 신규 레버 단일출처 (§16)
#   설정 + 확정수치 + 재현함수 + Rauto연동. CCproject=TS_CvdAbsorption, 06Prj_Stg1.
#   ※ 본 레버는 챗GPT5.5↔Opus4.8 토론(2026-06-19)에서 8개 후보 중 유일 생존 알파.
# ----------------------------------------------------------------------------
# [정체] 챔피언 성급왕TS(TrendStack_KING, +11397%/MDD-17.3%, §15) 위에 얹는 2-기제 결합:
#   (A) CVD 흡수 사이징: absorption = -side*cvd_7h (진입직전 7H 순매수흐름이 거래방향과 역행=흡수).
#        IC +0.167(롱숏 통합). 평균중립 z가중 w=clip(1+0.40*z,0.55,1.45)/mean → 흡수에 비중↑, 추격에 ↓.
#        ★순수 배분스킬(총노출 불변). OOS(학습23-24→검증25-26) 양쪽 개선, GAIN 0.2~0.6 단조견고.
#   (B) OI 손절거리: 진입직전 OI변화(1h) 하락=좋은눌림 손절 1.3%, 상승=나쁜눌림 0.8%(롱전용이 견고).
#        in-sample 롱 OI하락눌림 PF2.38 vs 상승 1.42. 사이징(PQS)으론 CPCV중립, 손절거리(롱)론 PASS.
# [확정수치 — 36개월 668거래 검증엔진(led36_king 무수정 재가중/재실행), $10k·k1.0·lev22·5bp 스톱슬립]
#   변종           수익률     최종$       MDD(5bp)   슬리피지 견고성
#   TS_CvdLong    +22319%   $2.24M     -16.4%     ★20bp까지 -19.2% (견고, 권장)
#   TS_CvdBoth    +33405%   $3.35M     -18.9%     10bp서 -21.3% (최고수익, 슬립칼날)
#   TS_CvdRcBoth  +25455%   $2.56M     -19.9%     10bp서 -22.6% (중간)
#   (베이스 king  +11397%   $1.15M     -17.3%)
# [검증관문 통과(§15·§5.6/5.7)] 동치(OFF=king 재현)·CPCV 표준6 p25/최악 동반개선·OOS 일반화·파라미터 견고·
#   ★청산안전(실역행 최악 -2.33%, 청산거리 -4.1% 미도달, 강제청산 손실캡)·수익허수 역산 0(실저점 보정해도 불변).
# [기각된 동료 레버(재시도 금지)] OI사이징(PQS)·Risk-Constant Stop(MDD악화)·거래량수축(부호반대)·
#   PFF(2.8%만)·RFI(균열가설 거짓)·LSI(추세봇은 변동성을 먹음, severe진입 PF6.15) — 전부 사망.
# [데이터] cvd_7h = rolling(420min) sum(2*taker_buy_volume - volume) from Merged_Data.csv. oi_change_1h_pct 동봉.
#   ★Funding은 Merged에 없음(LSI 미완 사유). 실역행/슬립 측정은 반드시 진입체결(et+7H)부터(룩어헤드 금지).
# ============================================================================
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ── 설정(변종별) ──────────────────────────────────────────────────────────
CVD = dict(GAIN=0.40, W_LO=0.55, W_HI=1.45)        # CVD 흡수 가중(평균중립)
OISTOP = dict(SL_GOOD=1.3, SL_BAD=0.8, OI_LO=-0.5, OI_HI=0.5)   # OI 눌림품질 손절거리(%)

VARIANTS = {
    # name           OIstop both/long  risk_const  cvd   확정수치(5bp)
    "TS_CvdLong":  dict(LONG_ONLY=True,  RISK_CONSTANT=False, USE_CVD=True,
                        ret=22319, final=2241942, mdd=-16.4, slip_safe_bp=20, role="견고·권장"),
    "TS_CvdBoth":  dict(LONG_ONLY=False, RISK_CONSTANT=False, USE_CVD=True,
                        ret=33405, final=3350524, mdd=-18.9, slip_safe_bp=7,  role="최고수익·슬립칼날"),
    "TS_CvdRcBoth":dict(LONG_ONLY=False, RISK_CONSTANT=True,  USE_CVD=True,
                        ret=25455, final=2555518, mdd=-19.9, slip_safe_bp=7,  role="중간"),
}


def cvd_weight_series(side_arr, cvd7_arr):
    """absorption=-side*cvd_7h → 평균중립 z가중. (라이브: 진입직전 cvd_7h를 aux로 받아 동일 계산)"""
    import numpy as np
    ab = (-np.asarray(side_arr, float) * np.asarray(cvd7_arr, float))
    z = np.nan_to_num((ab - np.nanmean(ab)) / (np.nanstd(ab) + 1e-9))
    w = np.clip(1.0 + CVD["GAIN"] * z, CVD["W_LO"], CVD["W_HI"])
    return w / w.mean()


def reproduce():
    """동봉 검증PY/데이터로 3변종 확정수치 재현(§16 재현함수). build_package_analysis가 주인공."""
    sys.path.insert(0, HERE)
    import build_package_analysis as B
    print("[재현] Plugin_06ChmpBot_TS_CvdAbsorption — 3변종(TS_CvdLong/Both/RcBoth) 36개월 검증")
    B.main()
    print("\n[기대] TS_CvdLong +22319%/MDD-16.4% · TS_CvdBoth +33405%/MDD-18.9% · TS_CvdRcBoth +25455%/MDD-19.9% (5bp)")


# ── Rauto 연동(라이브 적용 지침) ────────────────────────────────────────────
RAUTO_INTEGRATION = """
[Rauto 라이브 연동]
1) 봇: TrendStackImpatientKingBot(챔피언, §8 무수정) 상속 → bot_stop_quality.StopQualityKingBot
   + _compute_size에서 CVD 가중 곱(cvd_weight). aux로 oi_change_1h_pct(손절품질)·cvd_7h(흡수가중) 공급.
2) Dauto 수집: oi_change_1h_pct는 이미 수집중. cvd_7h = rolling(420min) sum(2*taker_buy - volume) 추가 산출.
3) 변종 선택: 라이브는 TS_CvdLong(견고) 권장 — 실슬립 불확실 구간에서 -20% 절대선 여유 큼.
   고수익 원하면 TS_CvdBoth(단 실슬립 8bp 넘으면 -20% 위반 가능 → 슬립 모니터 필수).
4) OFF(가중1.0)이면 챔피언 king과 100% 동치 → 무위험 롤백 가능.
"""

if __name__ == "__main__":
    print(__doc__ if False else "Plugin_06ChmpBot_TS_CvdAbsorption — 단일출처")
    for k, v in VARIANTS.items():
        print(f"  {k:12s}: +{v['ret']}% ${v['final']:,} MDD{v['mdd']}% (slip safe ~{v['slip_safe_bp']}bp) [{v['role']}]")
    print(RAUTO_INTEGRATION)
    print("재현: python -c \"import Plugin_06ChmpBot_TS_CvdAbsorption as P; P.reproduce()\"")
