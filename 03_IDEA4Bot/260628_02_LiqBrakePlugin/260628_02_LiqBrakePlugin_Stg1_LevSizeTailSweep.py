# -*- coding: utf-8 -*-
# [260628_02_LiqBrakePlugin_Stg1_LevSizeTailSweep.py]
# ★캡틴 향후3 (2026-06-28): "강제청산 이용 슬리피지 브레이크" 직접 백테 검증.
#   가설 = 고레버 + 소사이즈(동일 노출)로 가면 급변동 꼬리손실을 격리마진 강제청산이 잘라준다(브레이크).
#   질문 = 그렇게 해도 ⓐ수익이 안 깎이고 ⓑ MDD/꼬리가 줄어드는가?
#
# ★검증엔진만(§15.1): REVoi_bot.make_trades(검증 거래원장) + rauto_live.per_trade_pnl(격리마진·강제청산 1:1).
#   재구현 0. per_trade_pnl 청산식: MAE<=-hsd면 손실=-exp*(hsd+LIQ_COST+|fund|) [슬립 면제=브레이크] / 아니면 R_net*exp [슬립 부담].
#   hsd=1/lev-mmr-LIQ_SLIP (레버만의 함수). → 레버↑=hsd↓=청산↑=손실 cap↑(but 정상 역행도 잘림).
#
# ★꼬리슬립 = 시장청산(taker) 슬립 bp. 1m봉은 분 안쪽 플래시크래시 슬립을 못 봄(낙관) → bp로 보수 가산.
#   엔진 비대칭: 슬립은 '생존(저레버)' 거래만 부담, '청산(고레버)'은 면제 → 꼬리bp↑일수록 브레이크 효과 드러남.
#   ★정직경계: flat bp는 근사(모든 시장청산 일률). 진짜 틱-실측 꼬리는 안전장치7(WO TickSlippage)=별도. 여기선 '방향'을 본다.
#
# ★알파 = 현재 확정 COMBO (§9, 캡틴 채택승인 260627_02): tp_frac0.7 + early_tp1.0%/early_frac1.0.
#   무손상 게이트 = tp0/early0 lev3/sz75 → +1851.65% 재현(REV_MDD25_36mo).
# ★MDD 4단(§26): M0 무제한 / M30>=-30 / M25>=-25 / M20>=-20 각 최대수익 + 강제청산수.
import os, sys, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))


def find_root():
    d = HERE
    for _ in range(7):
        if os.path.isdir(os.path.join(d, "08_BTC_Data")) and os.path.isdir(os.path.join(d, "04_공용엔진코드")):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return r"D:\ML\RfRauto"


ROOT = find_root()
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
from path_finder import ensure_paths
ensure_paths()
from fib_replay_1m import load_1m, load_funding
from REVoi_bot import REVoiBot
from rauto_live import per_trade_pnl
from rauto_cex import SlipModel

PJSON = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")
ANCHOR = 1851.6491162901439   # REV_MDD25_36mo tot (무손상 기준값)

LEVS = [3, 5, 10, 15, 22, 30, 50, 75, 100]
# 사이즈(증거금%) 격자: 저~고 촘촘 + 고레버용 소수점. exposure=size/100*lev.
SIZE_GRID = sorted(set([round(x, 2) for x in
                        list(np.arange(0.25, 5, 0.25)) + list(np.arange(5, 30, 1)) +
                        list(np.arange(30, 101, 5))]))
TAIL_BP = [0.0, 10.0, 30.0, 50.0, 100.0]   # 시장청산 총슬립bp. 0=순수슬립0(앵커) · 10=현실기준(memory#9) · 30+=꼬리스트레스
GATES = [("M0", None), ("M30", -30.0), ("M25", -25.0), ("M20", -20.0)]


def _p(*a):
    print(*a, flush=True)


def slip_for(total_bp):
    """총 시장청산 슬립 total_bp → SlipModel. 진입 지정가=무슬립(엔진 기본).
       ★0bp=순수 슬립0(앵커 +1851.65% 재현) · 10bp=현실 기준(memory#9). 1bp 스프 미포함(앵커 무손상 위해 분리)."""
    return SlipModel(gap_bp=0.0, exit_spread_bp=0.0, extra_bp=max(0.0, total_bp))


def best_under_gate(T, lev, slip, gate_mdd):
    """레버 고정·사이즈 스윕 → MDD>=gate_mdd 제약하 최대 복리. 반환 dict or None."""
    best = None
    for s in SIZE_GRID:
        pnl, bal, mdd, nliq = per_trade_pnl(T, s, lev, slip)
        if bal <= 0:
            continue
        ret = (bal / 10000.0 - 1.0) * 100.0
        if (gate_mdd is None or mdd >= gate_mdd):
            if best is None or ret > best["ret"]:
                best = dict(size=s, exp=s / 100.0 * lev, ret=ret, mdd=mdd, nliq=nliq)
    return best


def main():
    _p("=" * 100)
    _p("[260628_02_LiqBrakePlugin Stg1] 강제청산 슬리피지 브레이크 — 레버×사이즈×꼬리슬립 스윕")
    _p("=" * 100)

    p = json.load(open(PJSON, encoding="utf-8"))["REV_MDD25_36mo"]["p"]
    d1m = load_1m()
    fund = load_funding()
    _p(f"데이터: 1m {len(d1m)}행 · {d1m.index.min()} ~ {d1m.index.max()} · 펀딩 {len(fund)}건")

    # ── 무손상 게이트: tp0/early0 lev3/sz75 = 앵커 ──
    T0 = REVoiBot({**p, "tp_frac": 0.0, "early_tp_pct": 0.0, "early_frac": 0.0}).make_trades(d1m, fund)
    T0 = T0.sort_values("et").reset_index(drop=True)
    _, bal0, mdd0, nl0 = per_trade_pnl(T0, 75.0, 3, slip_for(0.0))
    ret0 = (bal0 / 10000.0 - 1.0) * 100.0
    gate_ok = abs(ret0 - ANCHOR) < 1.0
    _p(f"\n[무손상 게이트] tp0/early0 lev3/sz75 슬립0 → {ret0:+.4f}% (기준 {ANCHOR:+.4f}%) "
       f"· 차이 {ret0 - ANCHOR:+.4f}%p → {'✅ 무손상' if gate_ok else '❌ 손상! 중단'}")
    if not gate_ok:
        _p("앵커 재현 실패 — 데이터/엔진 변경 의심. 스윕 중단.")
        return

    # ── COMBO 거래원장(확정 알파) ──
    T = REVoiBot({**p, "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0}).make_trades(d1m, fund)
    T = T.sort_values("et").reset_index(drop=True)
    nliq_share = []
    for lev in LEVS:
        from rauto_cex import MMR_T1, LIQ_SLIP
        hsd = 1.0 / lev - MMR_T1 - LIQ_SLIP
        nliqp = int((T["mae"].values.astype(float) <= -hsd).sum())
        nliq_share.append((lev, hsd, nliqp))
    _p(f"\n[COMBO 거래원장] {len(T)}건 (tp_frac0.7 + early_tp1.0%)")
    _p(f"  mae 분포: 중앙{np.median(T['mae'])*100:.2f}% · 5%{np.percentile(T['mae'],5)*100:.2f}% · "
       f"1%{np.percentile(T['mae'],1)*100:.2f}% · 최악{T['mae'].min()*100:.2f}%")
    _p("  [레버별 청산문턱 hsd & 그 문턱 걸리는 거래수]")
    for lev, hsd, nq in nliq_share:
        _p(f"    {lev:>4}x  hsd {hsd*100:>6.2f}%  →  청산걸림 {nq:>4}건 ({100*nq/len(T):.0f}%)")

    # ── 메인 스윕: 꼬리슬립별 × 레버별 × MDD 4단 ──
    for tail in TAIL_BP:
        slip = slip_for(tail)
        _p("\n" + "=" * 100)
        _p(f"[꼬리슬립 {tail:.0f}bp]  레버별 · MDD 4단 게이트 최대복리 (증거금%·복리%·MDD%·강제청산)")
        _p("=" * 100)
        header = f"  {'레버':>5} | " + " | ".join(f"{g[0]:>22}" for g in GATES)
        _p(header)
        _p("  " + "-" * (len(header) - 2))
        gate_best = {g[0]: None for g in GATES}
        for lev in LEVS:
            cells = []
            for gname, gmdd in GATES:
                b = best_under_gate(T, lev, slip, gmdd)
                if b is None:
                    cells.append(f"{'(해없음)':>22}")
                else:
                    cells.append(f"sz{b['size']:>4.1f} {b['ret']:>+8.0f}% {b['mdd']:>5.1f}% L{b['nliq']:>3}")
                    gb = gate_best[gname]
                    if gb is None or b["ret"] > gb["ret"]:
                        gate_best[gname] = {**b, "lev": lev}
            _p(f"  {lev:>4}x | " + " | ".join(cells))
        _p("  " + "-" * (len(header) - 2))
        line = []
        for gname, _ in GATES:
            gb = gate_best[gname]
            line.append(f"{gname}: lev{gb['lev']}·sz{gb['size']:.1f} {gb['ret']:+.0f}%/MDD{gb['mdd']:.1f}%/청{gb['nliq']}"
                        if gb else f"{gname}: 없음")
        _p("  ▶ 최적: " + "  |  ".join(line))

    # ── 캡틴 가설 직접검증: 동일 exposure(앵커 2.25) 고정, 레버 올리며 꼬리슬립별 수익/MDD/청산 ──
    _p("\n" + "=" * 100)
    _p("[캡틴 가설 직접검증] 동일 exposure=2.25 고정 · 레버↑(=사이즈↓) · 꼬리슬립별 (복리%/MDD%/청산)")
    _p("=" * 100)
    EXP_FIX = 2.25
    _p(f"  {'레버':>5}{'증거금%':>8} | " + " | ".join(f"{'꼬리'+str(int(t))+'bp':>20}" for t in TAIL_BP))
    for lev in LEVS:
        size = EXP_FIX * 100.0 / lev
        if size > 100:
            continue
        cells = []
        for tail in TAIL_BP:
            _, bal, mdd, nliq = per_trade_pnl(T, size, lev, slip_for(tail))
            ret = (bal / 10000.0 - 1.0) * 100.0
            cells.append(f"{ret:>+10.0f}% {mdd:>5.1f}% L{nliq:>3}")
        _p(f"  {lev:>4}x{size:>7.2f}% | " + " | ".join(cells))
    _p("\n[읽는 법] 꼬리슬립이 커질수록(오른쪽) 저레버는 수익이 깎이고 고레버는 청산이 손실을 잘라줌(브레이크)이면 캡틴 가설 성립.")
    _p("[정직경계] flat bp 근사 · 진짜 틱슬립=안전장치7(WO) · 수치는 36mo in-sample 상한(실전=OOS·다음Stg).")
    return True


if __name__ == "__main__":
    main()
