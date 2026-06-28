# -*- coding: utf-8 -*-
# [REVoi_bot.py] ★REVoi 매매봇 — [1] 매매신호 모듈(봇별) (세션 260625_01_RautoSysReform2).
#   ★봇 계약(모든 봇 공통 — TS·SW도 같은 계약): make_trades(d1m, fund) → 거래원장 DataFrame{et, R, mae, fund, reason}.
#     봇은 '신호 + 진입/청산 전술(알파)'만 만든다. R은 '언사이즈드'(레버·증거금 안 곱함).
#     사이징·리스크·배분·챔피언 = Rauto 결정두뇌 / 체결·비용·마진 = RautoCEX.
#     (퀀트 표준 경계: Alpha(봇)→Portfolio·Risk(Rauto)→Execution(CEX). QuantConnect LEAN·QuantStart 동일.)
#   REVoi = REV(역추세 mom_24h + OI_z 합성) 방향 + 눌림목(피봇) 정렬 진입 + 피보 스텝업(fibstop) 청산.
#   ★검증엔진 무수정·'호출'만(§8·§15.1): 방향=blend_opt.rev_side, 진입/청산=bt_full.gen_trades.
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # engines를 path에(=path_finder 임포트용)
from path_finder import ensure_paths
ensure_paths()                                                   # research 폴더를 path에(=blend_opt·bt_full)
from blend_opt import rev_side       # 검증된 REV 역추세 방향함수 (재구현 아님)
import bt_full as B                  # 검증된 거래생성(신호+눌림목+1m체결). 본문 무수정.


class REVoiBot:
    """[1] REVoi 봇. 봇 계약 = make_trades(d1m, fund) → 거래원장. 비용·사이징은 모른다(경계)."""

    NAME = "REVoi"

    def __init__(self, params):
        p = params
        # 신호(방향) 파라미터
        self.rev_tf = int(p["rev_tf"])
        self.q = float(p["q"])
        self.qwin = int(p["qwin"])
        # 진입(눌림목)·청산(피보스텝업) 전술 파라미터
        self.piv = int(p["piv"])
        self.N = int(p["N"])
        self.fib = (p["f1"], p["f2"], p["f3"])
        self.iam = float(p["iam"])
        self.arm = int(p["arm"])
        # ★청산향상(opt-in, 검증완료 260626_02): 구조 부분익절 tp_frac(0=off=기존). R+P70 챔피언후보=0.7.
        #   효과: MDD-24.6%→-16~20%·복리↑·CPCV p25↑(held-out OOS+CPCV표준6 통과). 끄면 기존 앵커 동일.
        self.tp_frac = float(p.get("tp_frac", 0.0))
        # ★조기익절(opt-in, 검증완료 260627_02): 진입 후 +early_tp_pct(가격%) 도달시 early_frac maker 익절. 0=off=앵커동일.
        #   발견: REVoi fibstop이 이익을 늦게 청산(되돌려줌) → 조기익절(0.75~1%)이 수익↑·MDD↓(held-out·CPCV 통과).
        self.early_tp_pct = float(p.get("early_tp_pct", 0.0))
        self.early_frac = float(p.get("early_frac", 0.0))
        # ★레짐 오버레이(opt-in, 멀티봇 fleet 260626_02): 봇 알파 도메인(§25).
        self.regime_factor = float(p.get("regime_factor", 1.0))   # 레짐적응스텝 배수(1.0=off, 1.4=저변동봉 타이트)
        self.gate = bool(p.get("gate", False))                    # 추세역행 진입게이트(지속하락서 롱·지속상승서 숏 차단)
        self.gate_lo = float(p.get("gate_lo", -10.0))
        self.gate_hi = float(p.get("gate_hi", 12.0))

    def make_trades(self, d1m, fund, capture_fills=False):
        """★봇 계약: 중앙 1m + 펀딩 → 거래원장. R=언사이즈드(사이징은 Rauto/CEX).
           컬럼 = {et, xt, xt_fill, side, entry, exit, R, mae, fund, reason, fills}.
           capture_fills=True면 진입 체결점 리스트(fills)를 채움 → 환각검증(1m 겹침)용. R엔 영향 없음."""
        _, side = rev_side(d1m, self.rev_tf, self.q, self.qwin)          # ① 방향신호(REV 역추세)
        fsc = None
        if self.gate or self.regime_factor > 1.0:
            import revoi_regime as RR                                    # 레짐 오버레이(자기완결·룩어헤드0)
            if self.gate:
                side = RR.trend_gate(side, d1m, self.rev_tf, self.gate_lo, self.gate_hi)  # 추세역행 진입 차단
            if self.regime_factor > 1.0:
                fsc = RR.regime_step(d1m, self.rev_tf, self.regime_factor)                # 저변동봉 스텝 타이트
        T = B.gen_trades(d1m, fund, self.rev_tf, self.piv, self.N, self.fib, self.iam,
                         er_gate=0.0, ext_side=side, align_pivot=True,
                         use_trend_flip=False, arm_bars=self.arm,
                         fib_scale=fsc, tp_frac=self.tp_frac,            # ★레짐스텝 + 구조 부분익절(끄면 기존 앵커 동일)
                         early_tp_pct=self.early_tp_pct, early_frac=self.early_frac,  # ★조기익절(끄면 앵커 동일)
                         capture_fills=capture_fills)                    # ② 진입(눌림목)·청산(피보스텝업 fibstop)
        return T
