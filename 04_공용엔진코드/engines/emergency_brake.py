# -*- coding: utf-8 -*-
# [emergency_brake.py] ★Rauto 비상시 안전장치 1호 — 강제청산 슬리피지 브레이크 (PlugIn).
#   캡틴 향후3(2026-06-28) → 세션 260628_02_LiqBrakePlugin 검증 → 비상 안전장치로 결정·모듈화(캡틴 지시4 2026-06-29).
#
#   ★원리: 격리마진에서 '안전 레버 상한'을 지키면 —
#     ⒜ 정상장(봇 정상 역행 -1~5%): 강제청산 0 = 수익 무손실 (Stg4: REVoi 최악역행 -5.10% → 강제청산0 = lev≤17).
#     ⒝ 순간 급변동(스톱 갭): 청산문턱이 급변동폭을 흡수 = '청산조차 못 함(갭관통)' 0 (Stg6: 36mo 최악 6.27% → lev≤14).
#     ⒞ 극단 급락(롱 -17% 등): 격리마진 강제청산이 한방손실을 '증거금'으로 cap = 계좌 전멸 방어 (Stg5: lev17 -16% vs lev3 -51%).
#   ★봇 무관 PlugIn: 어떤 봇이든 (worst_mae, 시장 최악급변동폭)만 주면 안전 사이징을 산출/검증. Rauto 결정두뇌(사이징)가 호출.
#   ★검증엔진 무손상: 사이징 '결정/진단'만 한다. per_trade pnl·앵커엔 손대지 않음(§8·§15.2).
#
#   시장상수(BTC 36mo 실측, 260628_02): 최악 순간 1분봉 한방향폭 = 6.27%(Stg6). 갱신 시 MARKET_FLASH_MAX만 교체.

MMR_T1, MMR_T2 = 0.004, 0.005          # 유지증거금(rauto_cex 동일). 보수=T2(고잔고).
LIQ_SLIP = 0.0005                       # 청산식 슬립버퍼(rauto_cex 동일).
MARKET_FLASH_MAX = 0.0627               # ★BTC 36mo 최악 순간 1분봉 한방향폭(Stg6). 미래 갱신용 단일상수.
DEFAULT_BUFFER = 0.85                   # 권장 = 안전상한 × 0.85 (미지의 더 큰 급변동 여유).


def _hsd(lev, mmr=MMR_T2, slip=LIQ_SLIP):
    """청산문턱(하드스탑 거리) = 1/lev - mmr - slip. lev 클수록 작아짐(청산 가까움)."""
    return 1.0 / float(lev) - mmr - slip


def liq_zero_max_lev(worst_mae, mmr=MMR_T2, slip=LIQ_SLIP):
    """봇 최악 역행(worst_mae<0, 분율)에서 '강제청산 0' 최대 정수 레버.
       조건: hsd > |worst_mae|. 보수=MMR_T2(잔고 커지면 T2)."""
    w = abs(float(worst_mae))
    lev = 1
    while _hsd(lev + 1, mmr, slip) > w:
        lev += 1
        if lev > 125:
            break
    return lev


def gap_zero_max_lev(flash_move=MARKET_FLASH_MAX, mmr=MMR_T2, slip=LIQ_SLIP):
    """시장 최악 순간급변동폭(flash_move>0, 분율)을 청산문턱이 흡수하는 '갭관통 0' 최대 정수 레버.
       조건: hsd > flash_move. 이 레버 이하면 급변동 시 청산이 1분봉 시가에 깔끔히 체결(갭관통 회피)."""
    f = abs(float(flash_move))
    lev = 1
    while _hsd(lev + 1, mmr, slip) > f:
        lev += 1
        if lev > 125:
            break
    return lev


def hard_loss_cap_pct(size_pct, lev, mmr=MMR_T2, slip=LIQ_SLIP):
    """한방 최대손실(계좌 %). 격리마진 강제청산 손실 ≈ 노출×hsd ≈ 증거금. = '비상시 최악 1거래 손실 한도'."""
    exp = float(size_pct) / 100.0 * float(lev)
    return exp * _hsd(lev, mmr, slip) * 100.0


def recommend(worst_mae, target_exposure=3.0, flash_move=MARKET_FLASH_MAX, buffer=DEFAULT_BUFFER):
    """★권장 안전 사이징: 강제청산0·갭관통0 둘 다 만족하는 안전레버 상한 → 버퍼 적용 → (lev, size_pct, 한방손실, 근거).
       target_exposure 고정(노출=명목/시드). 봇 알파는 무손상, 사이징만 안전하게."""
    lz = liq_zero_max_lev(worst_mae)
    gz = gap_zero_max_lev(flash_move)
    safe_cap = min(lz, gz)                       # 둘 다 만족 = 더 보수적(갭관통0이 보통 더 낮음)
    rec_lev = max(1, int(safe_cap * buffer))     # 버퍼 = 미지의 더 큰 급변동 여유
    size = round(target_exposure / rec_lev * 100.0, 1)
    size = min(size, 100.0)
    return {
        "권장레버": rec_lev, "권장증거금%": size, "노출": target_exposure,
        "한방최대손실%": round(hard_loss_cap_pct(size, rec_lev), 1),
        "강제청산0_상한레버": lz, "갭관통0_상한레버": gz, "안전상한레버": safe_cap,
        "버퍼": buffer, "근거": f"강제청산0 lev≤{lz}(worst_mae {worst_mae*100:.2f}%)·갭관통0 lev≤{gz}(급변동 {flash_move*100:.2f}%)",
    }


def assess(lev, size_pct, worst_mae, flash_move=MARKET_FLASH_MAX):
    """봇 사이징 안전 진단(비상 안전장치 관점). 반환: 등급 + 항목별 판정."""
    lz = liq_zero_max_lev(worst_mae)
    gz = gap_zero_max_lev(flash_move)
    liq0 = lev <= lz
    gap0 = lev <= gz
    cap = hard_loss_cap_pct(size_pct, lev)
    if liq0 and gap0:
        grade = "안전(정상장 무손실+급변동 갭관통0)"
    elif liq0:
        grade = "주의(강제청산0이나 일부 급변동 갭관통 가능)"
    else:
        grade = "위험(정상 역행서도 강제청산 발생=수익잠식)"
    return {"등급": grade, "강제청산0": liq0, "갭관통0": gap0, "한방최대손실%": round(cap, 1),
            "현레버": lev, "강제청산0_상한": lz, "갭관통0_상한": gz}


if __name__ == "__main__":
    # 자가테스트 — REVoi@ETF 검증값(260628_02): worst_mae -5.10%, 시장 급변동 6.27%
    wm = -0.0510
    print("[강제청산0 최대레버]", liq_zero_max_lev(wm), "(기대 17, Stg4)")
    print("[갭관통0 최대레버]", gap_zero_max_lev(), "(기대 14, Stg6)")
    print("[권장 사이징]", recommend(wm))
    print("[RevoiSafe lev15 진단]", assess(15, 20.0, wm))
    print("[lev3/증거금100% 진단]", assess(3, 100.0, wm))
    print("[lev30 진단]", assess(30, 10.0, wm))
