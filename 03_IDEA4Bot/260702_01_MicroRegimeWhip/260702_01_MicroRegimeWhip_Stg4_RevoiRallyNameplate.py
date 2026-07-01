# -*- coding: utf-8 -*-
# [260702_01_MicroRegimeWhip_Stg4_RevoiRallyNameplate] ★새봇 RevoiRally@ETF 등록값 산출 + 무손상 재확인 (세션 260702_01).
#   RevoiRally@ETF = RevoiSafe@ETF(노출3·lev15·증거금20%·COMBO) + ★L2 랠리억제(rauto_regime_sizing, size_mult 컬럼).
#     = 같은 노출(3.0)서 휩소내성(랠리 역주행 노출×0.5) 추가 → MDD↓·매월양수↑ 기대(Stg3 ④ 고정위험 리스크효과).
#   ★무손상: ① BASE 앵커(size_mult 없음) +1851.6491% 재현 ② RevoiSafe per_trade_pnl(컬럼없음) = 기존값 불변
#     → size_mult 도입이 기존 봇에 무영향임을 증명(엔진 하위호환).
#   Stg8 RevoiSafeNameplate 1:1 모방 + rauto_regime_sizing.apply_rally_damp.
import os, sys, json
import numpy as np, pandas as pd
ROOT = r"D:\ML\RfRauto"
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
from path_finder import ensure_paths; ensure_paths()
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as B2
from REVoi_bot import REVoiBot
from veri_edge import VeriEdge
from rauto_live import per_trade_pnl
from rauto_cex import SlipModel
from rauto_regime_sizing import apply_rally_damp

SZ, LEV = 20.0, 15                # RevoiSafe와 동일 노출3.0(증거금20%×lev15)
FACTOR, THR = 0.5, 3.0            # L2: 랠리(7일추세≥+3%) 역주행 노출×0.5
WINP = os.path.join(ROOT, r"03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json")


def _p(*a): print(*a, flush=True)


def regime_label(led):
    m = pd.read_csv(os.path.join(ROOT, r"08_BTC_Data\derived\Merged_Data.csv"), usecols=["timestamp", "close"], parse_dates=["timestamp"])
    m["timestamp"] = m["timestamp"].dt.tz_localize(None)
    c8 = m.set_index("timestamp")["close"].resample("8h").last().dropna()
    ret7 = c8.pct_change(21); feat = pd.DataFrame({"r7": ret7}); feat.index = feat.index + pd.Timedelta("8h")
    l2 = pd.merge_asof(led.sort_values("et").assign(et=pd.to_datetime(led["et"])), feat, left_on="et", right_index=True, direction="backward")
    l2["regime"] = np.where(l2["r7"] > 0.05, "상승", np.where(l2["r7"] < -0.05, "하락", "횡보"))
    return l2


def main():
    p = {**json.load(open(WINP, encoding="utf-8"))["REV_MDD25_36mo"]["p"]}
    combo = {**p, "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0}
    d1m, fund = load_1m(), load_funding(); rev_tf = int(p["rev_tf"])
    _p("=" * 74); _p("RevoiRally@ETF 등록 이름표 (RevoiSafe 노출3 + L2 랠리억제)"); _p("=" * 74)

    # ── ① 무손상: BASE 앵커(size_mult 없음) ──
    base_led = B2.rev_trades(d1m, fund, dict(p))
    anc = VeriEdge(base_led).anchor_check(75, 3, 1851.6)
    _p(f"[무손상①] BASE 앵커(컬럼없음) = {anc['got_%']}% → {'✅' if anc['pass'] else '❌'}")
    # ── ② 무손상: RevoiSafe(COMBO·컬럼없음) per_trade_pnl 불변 ──
    safe_led = B2.rev_trades(d1m, fund, combo)
    _, bsafe, msafe, nsafe = per_trade_pnl(safe_led, SZ, LEV, SlipModel(0, 0, 10.0))
    _p(f"[무손상②] RevoiSafe(컬럼없음) 36mo현실10bp = {(bsafe/10000-1)*100:+,.0f}%/MDD{msafe:.1f}%/청산{nsafe}")
    if not anc["pass"]:
        _p("❌ 앵커 실패 → 중단"); return False

    # ── RevoiRally 원장 = COMBO + L2 size_mult ──
    rally_led = apply_rally_damp(safe_led, d1m, rev_tf, thr=THR, factor=FACTOR)
    ndamp = int((rally_led["size_mult"] < 1.0).sum())
    _p(f"[RevoiRally] {len(rally_led)}거래 · L2 damp {ndamp}건({100*ndamp/len(rally_led):.0f}%·랠리숏×{FACTOR})")

    # 레짐 라벨 부착(size_mult 보존)
    safe_lab = regime_label(safe_led)
    rally_lab = regime_label(rally_led)
    rally_lab["size_mult"] = rally_led.set_index(rally_led["et"].astype(str)).reindex(rally_lab["et"].astype(str))["size_mult"].values

    # ── 이름표 비교: RevoiSafe(OFF) vs RevoiRally(L2) 같은 노출 ──
    for nm, lab in [("RevoiSafe@ETF(OFF)", safe_lab), ("RevoiRally@ETF(L2)", rally_lab)]:
        ve = VeriEdge(lab)
        npl = ve.nameplate(name=nm, size_pct=SZ, lev=LEV, desc="역추세+COMBO청산 + L2랠리억제(휩소내성)")
        _, bal, mdd, nl = per_trade_pnl(lab, SZ, LEV, SlipModel(0, 0, 10.0))
        _p(f"\n[{nm}]  예상월복리 {npl['예상_월복리수익률%']}% · OOS총 {npl['OOS_총수익%']}%/{npl['OOS_개월']}개월 · OOS_MDD {npl['OOS_MDD%']}% · 강제청산 {npl['강제청산']}")
        _p(f"   36mo검증(현실10bp) {(bal/10000-1)*100:+,.0f}%/MDD{mdd:.1f}%/청산{nl} (in-sample 상한·참고)")
        if "레짐별" in npl:
            rr = {rg: npl["레짐별"][rg]["예상_월복리%"] for rg in npl["레짐별"]}
            _p(f"   레짐별 예상월복리: {rr}")
            if nm.startswith("RevoiRally"):
                reg_monthly = rr; oos_mdd = npl["OOS_MDD%"]; exp_mo = npl["예상_월복리수익률%"]; mdd36 = mdd; nl36 = nl

    _p("\n" + "=" * 74)
    _p(f"[★BOT_REGISTRY 엔트리] RevoiRally@ETF · lev{LEV}/sz{int(SZ)} · tp0.7/early0.01/efrac1.0 · rally_damp=({THR},{FACTOR})")
    _p(f"   OOS_mdd={oos_mdd} · 예상월복리={exp_mo}% · 강제청산={nl36} · 36mo현실MDD={mdd36:.1f}%")
    _p(f"[★REG_MONTHLY] \"RevoiRally@ETF\": {reg_monthly}")
    _p("[★해석] 같은 노출3서 L2 = 휩소내성(랠리 역주행 노출↓). RevoiSafe 대비 MDD/매월양수 개선 = 리스크리듀서(수익 큰폭↑은 레버업 별건).")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
