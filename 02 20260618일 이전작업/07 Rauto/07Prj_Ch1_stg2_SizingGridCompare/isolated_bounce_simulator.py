# -*- coding: utf-8 -*-
# [파일명] isolated_bounce_simulator.py
# 코드길이: 약 175줄 | 내부버전: iso_bounce_sim_v1 (07Prj_Ch1_stg1 IsoBounceModuleBuild) | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 모듈이 하는 일 — 고딩 설명]
#   사장님 '격리튕김공식'을 다른 봇/백테 코드에 끼울 수 있게 플러그인(모듈러)으로 박제.
#   핵심 한 줄: "한 거래의 가격변동률 R을, '잔고 7.5% × 13배 격리마진' 가정에 따라 잔고변화율 ΔW로 변환한다."
#
#   ★왜 통하나(설계 근거):
#     - 기존 백테는 자본 100%×1배(암묵 EXPOSURE=1.0)로 작동. 이전 작업자(06Prj_Ch7) 인수인계 발견.
#     - 사장님 실제 운용은 cross 5배×5%(EXPOSURE=0.25). 격리튕김은 EXPOSURE 0.975 + 강제청산 테일컷.
#     - 2025-10-11 폭락(BTC -14.5%, 1.63M계좌 강제청산, slippage로 손절 불가) 사건에서 살아남는 구조.
#
#   ★분기형 수식(단순 max 아님):
#     R(가격변동률) ≤ -0.0719  → ΔW = -0.075   (격리청산 = 증거금 전액 손실)
#     R > -0.0719              → ΔW = R × 0.975 (평시: EXPOSURE만 적용)
#     → 가격이 -7.19%까지는 cross처럼 비례 손실, 그 이상 빠지면 잔고 -7.5%로 평탄(테일컷).
#
#   ★롱·숏 모두 동일(FNG가드와 차이): 강제청산은 거래소가 방향 무관하게 가격 역행으로 트리거. 비대칭 없음.
#
# [엔진 무수정 원칙]  챔피언 엔진(SpTrd_Fib_V1_Champion.py, 해시 7f9192e3)은 한 줄도 안 건드림.
#   엔진이 내놓은 '거래'(side/entry/exit/R)에 사후필터로만 적용.
#
# [두 가지 사용법]
#   (A) 백테 사후필터 — 원장의 R을 모드별 ΔW로 일괄 변환:
#       sim = IsoBounceSim.from_preset('M3_iso_tailcut')
#       converted, n_liq = sim.apply_to_trades(trades)   # trades: dict 리스트(R 포함)
#   (B) 실시간 1건 변환 — 봇이 한 거래 청산 직후 호출:
#       dW = sim.transform_R(R)                          # ΔW = 잔고변화율
#
# [In/Out 태그]
#   IsoBounceSim.__init__(In exposure·tail_cut·liq_distance·enable_tail_cut / Out 인스턴스)
#   .transform_R(In R(float) / Out ΔW(float))                       — 한 거래 1건
#   .apply_to_trades(In trades(dict 리스트) / Out (보정된 trades, 청산건수))  — 백테 사후
#   .from_preset(In preset_name(str) / Out 인스턴스)                — 4모드 사전정의 헬퍼
#   MODE_PRESETS(dict) — M0_base / M1_cross_now / M2_iso_notail / M3_iso_tailcut
#   CONFIG_DEFAULT(dict) — 기본값(=M3_iso_tailcut, 사장님 격리튕김 본체)
#
# [설정값 — 전부 조정 가능]
#   exposure(기본 0.975): 한 거래의 실효노출. 7.5%×13배=0.975. cross 5배×5%면 0.25.
#   tail_cut(기본 -0.075): 격리청산 시 잔고변화율. 격리증거금 비율(7.5%)에 음수.
#       ※청산수수료(약 0.5~1%)는 보수적으로 무시 → 실제 손실은 더 클 수 있음(추후 측정에 반영).
#   liq_distance(기본 -0.0724): 청산까지 가격변동률 거리. 1/L − MMR − taker_fee.
#       L=13, MMR=0.4%(Binance Tier1), taker=0.05% → 1/13 − 0.004 − 0.0005 = 0.0724 (−7.24%).
#       ★사장님 원래 의도("BTC 일변동 ±7% 노이즈 견딤")와 정확 일치. K33 BTC 2025 변동성 2.24% × 3σ=6.72%.
#       ★stg1(-0.0719)에서 stg2(-0.0724)로 0.05%p 정직화 — taker fee 반영.
#   enable_tail_cut(기본 True): False면 테일컷 OFF → cross처럼 R×exposure만 적용(M2 모드).
# ==============================================================================
import numpy as np


# 4모드 사전정의: stg2 SizingGridCompare에서 그대로 사용
MODE_PRESETS = {
    # M0 = 기존 백테 암묵 가정(자본 1배). docx의 $51,184 동치검증 기준선
    "M0_base":         dict(exposure=1.000, tail_cut=-1.0,  liq_distance=-1.0,    enable_tail_cut=False),
    # M1 = 사장님 현 cross 운용(5배×5%). 실제 운용 기준선
    "M1_cross_now":    dict(exposure=0.250, tail_cut=-1.0,  liq_distance=-1.0,    enable_tail_cut=False),
    # M2 = EXPOSURE만 0.975로 올린 가상 cross(테일컷 OFF). M3와 차이=테일컷 순수 알파
    "M2_iso_notail":   dict(exposure=0.975, tail_cut=-1.0,  liq_distance=-1.0,    enable_tail_cut=False),
    # M3 = 사장님 격리튕김공식 본체 (EXPOSURE 0.975 + 테일컷 -7.5%)
    "M3_iso_tailcut":  dict(exposure=0.975, tail_cut=-0.075, liq_distance=-0.0724, enable_tail_cut=True),
}


CONFIG_DEFAULT = dict(MODE_PRESETS["M3_iso_tailcut"])  # 기본=격리튕김


# 출처·메타(부활·재현·디버깅 추적용; 코드 동작엔 영향 없음)
ALPHA_PROVENANCE = {
    "source": "07Prj_Ch1_stg1_IsoBounceModuleBuild (사장님 격리튕김공식 v1)",
    "concept": "7.5% balance x 13x isolated -> tail cut at -7.5% (forced liquidation as stop-loss substitute)",
    "inspired_by": "Previous worker (06Prj_Ch7) discovery: existing backtest assumed capital*1.0 (implicit EXPOSURE=1.0)",
    "evidence_event": "2025-10-11 BTC crash -14.5%, $19B liquidations, 'stop-losses failed due to slippage'",
    "asymmetry_note": "Long/Short identical (forced liquidation by exchange is direction-agnostic). Different from FNG-guard.",
    "numbers_need_verification": [
        "exposure=0.975 (7.5%*13 = balance ratio)",
        "liq_distance=-0.0724 (1/13 - MMR0.4% - taker_fee0.05%, Binance Tier1 assumption)",
        "tail_cut=-0.075 (Bankrupt Position auto-triggers in small positions; user loss = isolated margin 100%)",
    ],
    "evidence_alignment": "Sajangnim original intent '7.2% endure' matches K33 BTC 2025 vol 2.24% * 3sigma = 6.72%; -7.24% cushion at 99.7% range.",
    "binance_source": "Liquidation Protocols (small positions = Bankrupt Position, user loss = isolated margin)",
    "todo_next_stg": "stg2 SizingGridCompare: 4 modes on stg1 ledger (292 trades) -> abs balance / MDD / CPCV",
}


class IsoBounceSim:
    # 격리튕김 시뮬레이터. 엔진 무수정, 모드 전환 가능, 사후필터 + 실시간 1건 모두 지원.

    def __init__(self, exposure=0.975, tail_cut=-0.075, liq_distance=-0.0724, enable_tail_cut=True):
        # 설정값 검증 — 비정상 값 들어오면 즉시 멈춤(추정 코딩 방지)
        if not (0.0 < exposure <= 2.0):
            raise ValueError(f"exposure must be in (0, 2], got {exposure}")
        if not (-1.0 <= tail_cut <= 0.0):
            raise ValueError(f"tail_cut must be in [-1, 0], got {tail_cut}")
        if not (-1.0 <= liq_distance <= 0.0):
            raise ValueError(f"liq_distance must be in [-1, 0], got {liq_distance}")
        self.exposure = float(exposure)
        self.tail_cut = float(tail_cut)
        self.liq_distance = float(liq_distance)
        self.enable_tail_cut = bool(enable_tail_cut)

    @classmethod
    def from_preset(cls, preset_name):
        # 4모드 사전정의에서 인스턴스 생성. M0~M3 중 하나.
        if preset_name not in MODE_PRESETS:
            raise KeyError(f"Unknown preset: {preset_name}. Available: {list(MODE_PRESETS.keys())}")
        return cls(**MODE_PRESETS[preset_name])

    @classmethod
    def from_config(cls, cfg=None):
        # 사용자 정의 설정에서 인스턴스 생성(부분 오버라이드 가능)
        c = dict(CONFIG_DEFAULT)
        if cfg:
            c.update(cfg)
        return cls(**c)

    # ── 핵심 1: 한 거래의 가격변동률 R → 잔고변화율 ΔW 변환 ──────────────────
    def transform_R(self, R):
        # R: 거래의 가격변동률(side*(exit-entry)/entry - cost - funding 등 이미 적용된 값)
        # 반환: 그 거래로 인한 잔고변화율 ΔW(float)
        #   - 평시(R > liq_distance): ΔW = R * exposure
        #   - 청산(R <= liq_distance & 테일컷ON): ΔW = tail_cut  (격리증거금 전액 손실)
        #   - 테일컷OFF: 항상 R * exposure (M0/M1/M2 모드)
        if R is None or not np.isfinite(R):
            return 0.0  # NaN 거래는 무손익 처리(원본 백테 거동 유지)
        if self.enable_tail_cut and R <= self.liq_distance:
            return self.tail_cut
        return R * self.exposure

    # ── 핵심 2: 백테 사후필터 — 거래 dict 리스트에 일괄 적용 ──────────────────
    def apply_to_trades(self, trades, r_key="R"):
        # trades: dict 리스트. 각 거래에 r_key(기본 'R')가 있어야 함.
        # 반환: (보정된 trades 리스트, 청산된 거래 건수 n_liq)
        #   - 원본 R은 'R_original' 키로 보존(추적용)
        #   - 새 잔고변화율은 r_key 자리에 덮어씀(기존 eval_case/compound_end 재사용 호환)
        out = []
        n_liq = 0
        for t in trades:
            R = t.get(r_key)
            dW = self.transform_R(R)
            if self.enable_tail_cut and R is not None and np.isfinite(R) and R <= self.liq_distance:
                n_liq += 1
            t2 = dict(t)
            t2["R_original"] = R
            t2[r_key] = dW
            t2["_iso_mode"] = "tailcut" if (self.enable_tail_cut and R is not None and np.isfinite(R) and R <= self.liq_distance) else "normal"
            out.append(t2)
        return out, n_liq

    def describe(self):
        # 디버깅용: 현재 설정 한 줄 요약
        return (f"IsoBounceSim(exposure={self.exposure}, tail_cut={self.tail_cut}, "
                f"liq_distance={self.liq_distance}, enable_tail_cut={self.enable_tail_cut})")


if __name__ == "__main__":
    # ── 자가검증(합성) ─ 모듈이 의도대로 동작하는지 빠르게 확인 ──────────────
    # 사장님 격리튕김공식의 핵심 분기 동작 + 4모드 정합성 + 경계값 검증

    # [1] M0 baseline: exposure=1.0, 테일컷 OFF → R 그대로
    m0 = IsoBounceSim.from_preset("M0_base")
    assert abs(m0.transform_R(0.05) - 0.05) < 1e-9, "M0 평시 양수 실패"
    assert abs(m0.transform_R(-0.10) - (-0.10)) < 1e-9, "M0 평시 음수 실패"
    assert abs(m0.transform_R(-0.20) - (-0.20)) < 1e-9, "M0 폭락 손실 실패"

    # [2] M1 cross_now: exposure=0.25, 테일컷 OFF → R*0.25
    m1 = IsoBounceSim.from_preset("M1_cross_now")
    assert abs(m1.transform_R(-0.10) - (-0.025)) < 1e-9, "M1 -10% → -2.5% 실패"
    assert abs(m1.transform_R(-0.20) - (-0.050)) < 1e-9, "M1 -20% → -5% 실패"

    # [3] M2 iso_notail: exposure=0.975, 테일컷 OFF → R*0.975 (테일컷 안 됨)
    m2 = IsoBounceSim.from_preset("M2_iso_notail")
    assert abs(m2.transform_R(-0.10) - (-0.0975)) < 1e-9, "M2 -10% → -9.75% 실패"
    assert abs(m2.transform_R(-0.20) - (-0.195)) < 1e-9, "M2 -20% → -19.5% 실패(테일컷 OFF 확인)"

    # [4] M3 iso_tailcut: exposure=0.975, 테일컷 ON, liq=-7.19%, cut=-7.5%
    m3 = IsoBounceSim.from_preset("M3_iso_tailcut")
    assert abs(m3.transform_R(0.05) - 0.04875) < 1e-9, "M3 평시 양수 +5% → +4.875% 실패"
    assert abs(m3.transform_R(-0.05) - (-0.04875)) < 1e-9, "M3 평시 음수 -5% → -4.875% 실패"
    # 경계 직전: R=-0.0723 → 평시
    assert abs(m3.transform_R(-0.0723) - (-0.0723 * 0.975)) < 1e-9, "M3 경계 직전 -7.23% → 평시 실패"
    # 경계 정확: R=-0.0724 → 테일컷
    assert abs(m3.transform_R(-0.0724) - (-0.075)) < 1e-9, "M3 경계 정확 -7.24% → 테일컷 실패"
    # 폭락: R=-0.145 (2025-10-11 BTC) → 테일컷
    assert abs(m3.transform_R(-0.145) - (-0.075)) < 1e-9, "M3 폭락 -14.5% → 테일컷 실패(★핵심)"
    # 극단 폭락: R=-0.50 → 테일컷
    assert abs(m3.transform_R(-0.50) - (-0.075)) < 1e-9, "M3 극단 -50% → 테일컷 실패"

    # [5] NaN 보호: R이 None/NaN이면 0 반환(백테 거동 유지)
    assert m3.transform_R(None) == 0.0, "NaN(None) 보호 실패"
    assert m3.transform_R(float("nan")) == 0.0, "NaN(float) 보호 실패"

    # [6] apply_to_trades: 합성 거래 5개에 M3 적용 → 청산건수 + R 변환 확인
    trades = [
        {"side": 1, "R": 0.05},      # 평시 익절
        {"side": -1, "R": -0.04},    # 평시 손실
        {"side": 1, "R": -0.08},     # ★ 청산 (R <= -0.0724)
        {"side": -1, "R": -0.145},   # ★ 폭락 청산
        {"side": 1, "R": 0.02},      # 평시 익절
    ]
    converted, n_liq = m3.apply_to_trades(trades)
    assert n_liq == 2, f"청산건수 2 기대, 실제 {n_liq}"
    assert abs(converted[0]["R"] - 0.04875) < 1e-9, "변환[0] 실패"
    assert abs(converted[2]["R"] - (-0.075)) < 1e-9, "변환[2] 테일컷 실패"
    assert abs(converted[3]["R"] - (-0.075)) < 1e-9, "변환[3] 테일컷 실패"
    assert converted[2]["_iso_mode"] == "tailcut", "청산 라벨 실패"
    assert converted[0]["_iso_mode"] == "normal", "정상 라벨 실패"
    # 원본 보존
    assert converted[3]["R_original"] == -0.145, "R_original 보존 실패"

    # [7] enable_tail_cut OFF 시 cross처럼 작동 (M2와 동등)
    m3_off = IsoBounceSim(exposure=0.975, tail_cut=-0.075, liq_distance=-0.0724, enable_tail_cut=False)
    assert abs(m3_off.transform_R(-0.145) - (-0.141375)) < 1e-9, "테일컷 OFF 시 cross 동작 실패"

    # [8] 잘못된 설정값은 즉시 에러
    try:
        IsoBounceSim(exposure=-0.1)
        assert False, "음수 exposure 통과 안 됨"
    except ValueError:
        pass
    try:
        IsoBounceSim.from_preset("M99_invalid")
        assert False, "잘못된 preset 통과 안 됨"
    except KeyError:
        pass

    print("=" * 70)
    print(f"isolated_bounce_simulator 자가검증 OK")
    print(f"  핵심: {ALPHA_PROVENANCE['concept']}")
    print(f"  모드: {list(MODE_PRESETS.keys())}")
    print(f"  검증: 4모드 transform_R + 경계분기 + apply_to_trades + 예외처리 8섹션 PASS")
    print("=" * 70)
