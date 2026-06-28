# -*- coding: utf-8 -*-
# [REVoi_Validate] R+P70 M20이빠이 채택검증 — CPCV표준6 + held-out OOS + 민감도 (세션 260626_02_Rauto2_Sys).
#   캡틴 1·2: held-out+CPCV 최종채택검증 + tp_frac/레짐배수 민감도. ★M20 사이징(lev6/증거금55=exp3.3)에서.
#   ★검증엔진 무수정 호출(§15.1): rev_side·build_scale·gen_trades·curve·monthly_liq·cpcv_std6(전부 exit_upgrade).
import os, sys, json
ROOT = os.path.dirname(os.path.abspath(__file__))
for _ in range(6):
    if os.path.isdir(os.path.join(ROOT, "08_BTC_Data")) and os.path.isdir(os.path.join(ROOT, "04_공용엔진코드")): break
    ROOT = os.path.dirname(ROOT)
RES = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp")
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines")); sys.path.insert(0, RES)
from path_finder import ensure_paths; ensure_paths()
import numpy as np, pandas as pd
from fib_replay_1m import load_1m, load_funding
import bt_full as B
from blend_opt import rev_side
import exit_upgrade as EU

LEV_M20, SZ_M20 = 6, 55   # M20 이빠이 사이징(exp 3.3)


def main():
    p = json.load(open(os.path.join(RES, "back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    EU.T_TF = p["rev_tf"]
    d1m = load_1m(); fund = load_funding()
    _, side = rev_side(d1m, p["rev_tf"], p["q"], p["qwin"])
    sc14, _ = EU.build_scale(d1m, p, 1.4)

    def revp(scale, tp):
        return B.gen_trades(d1m, fund, p["rev_tf"], p["piv"], p["N"], (p["f1"],p["f2"],p["f3"]), p["iam"],
                            er_gate=0.0, ext_side=side, align_pivot=True, use_trend_flip=False,
                            arm_bars=p["arm"], fib_scale=scale, tp_frac=tp).sort_values("et").reset_index(drop=True)

    print("="*92)
    print(f"[R+P70 M20이빠이 채택검증] 사이징 레버{LEV_M20}/증거금{SZ_M20}%(exp{SZ_M20/100*LEV_M20:.1f})")
    print("="*92)

    # ───────── #1-A: CPCV 표준6 @ M20 사이징 ─────────
    T = revp(sc14, 0.7)
    c = EU.curve(T, SZ_M20, LEV_M20)
    mo, rt = EU.monthly_liq(T, SZ_M20, LEV_M20); cp = EU.cpcv_std6(mo, rt)
    print(f"\n[#1-A CPCV 표준6] full 복리{c['tot']:+.0f}%·MDD{c['mdd']:.1f}%·청산{c['nliq']}")
    print(f"  CPCV: p25 {cp['p25']:+.1f}%/yr · 중앙 {cp['median']:+.1f}% · 최악경로 {cp['worst']:+.1f}% · 음수폴드 {cp['neg']:.0f}%")
    print(f"        폴드 최악MDD {cp['mdd_worst']:.1f}% · ★MDD−20 위반율 {cp['mdd_viol']:.0f}%")
    g1 = (cp['p25'] > 0) and (cp['neg'] == 0) and (cp['mdd_viol'] == 0)
    print(f"  → {'✅통과(p25>0·음수폴드0·MDD-20위반0)' if g1 else '❌미달'}")

    # ───────── #1-B: held-out OOS (train 24m → test 12m, 사이징도 train서 결정) ─────────
    T["etd"] = pd.to_datetime(T["et"]); cut = pd.Timestamp("2025-05-01")
    Ttr = T[T["etd"] < cut].copy(); Tte = T[T["etd"] >= cut].copy()
    # train서 MDD−20 맞추는 size(lev6 고정) 탐색 → test 적용
    def find_size_mdd20(Tsub, lev):
        best = 5
        for sz in range(5, 101, 1):
            cc = EU.curve(Tsub, sz, lev)
            if cc["mdd"] >= -20.0: best = sz
            else: break
        return best
    sz_tr = find_size_mdd20(Ttr, LEV_M20)
    ctr = EU.curve(Ttr, sz_tr, LEV_M20); cte = EU.curve(Tte, sz_tr, LEV_M20)
    print(f"\n[#1-B held-out OOS] train(2023-05~2025-04 {len(Ttr)}거래) → test(2025-05~2026-04 {len(Tte)}거래)")
    print(f"  train서 MDD−20 맞춘 사이징 = 레버{LEV_M20}/증거금{sz_tr}% (train 복리{ctr['tot']:+.0f}%·MDD{ctr['mdd']:.1f}%)")
    print(f"  ★그대로 test 적용 → 복리{cte['tot']:+.0f}%·MDD{cte['mdd']:.1f}%·청산{cte['nliq']}·승{cte['win']:.0f}%·PF{cte['pf']:.2f}")
    g2 = (cte['tot'] > 0) and (cte['mdd'] >= -25.0)   # OOS 양수 + MDD 과도이탈 없음(버퍼 -25)
    print(f"  → {'✅통과(OOS 양수·MDD−25내)' if g2 else '⚠ OOS 약함(사이징 버퍼 필요)'}")

    # ───────── #2: 민감도 (tp_frac × 레짐배수) — 칼날 아닌지 ─────────
    print(f"\n[#2 민감도 @ M20 사이징] full 복리/MDD · CPCV p25/MDD-20위반")
    print(f"  {'세팅':<18}{'복리':>10}{'MDD':>8}{'p25':>8}{'MDD20위반':>10}")
    def line(tag, scale, tp):
        Tx = revp(scale, tp); cx = EU.curve(Tx, SZ_M20, LEV_M20)
        mx, rx = EU.monthly_liq(Tx, SZ_M20, LEV_M20); cpx = EU.cpcv_std6(mx, rx)
        print(f"  {tag:<18}{cx['tot']:>+9.0f}%{cx['mdd']:>7.1f}%{cpx['p25']:>+7.1f}{cpx['mdd_viol']:>8.0f}%")
    for tp in [0.5, 0.6, 0.7, 0.8]:
        line(f"R×1.4+P{int(tp*100)}", sc14, tp)
    for fct in [1.0, 1.2, 1.6, 2.0]:
        sc = None if fct == 1.0 else EU.build_scale(d1m, p, fct)[0]
        line(f"R×{fct}+P70", sc, 0.7)

    print("\n[종합]")
    print(f"  #1 CPCV @M20: {'✅' if g1 else '❌'} · #1 held-out OOS: {'✅' if g2 else '⚠'}")
    print(f"  → 둘 다 통과면 R+P70 M20이빠이 = 채택자격(챔피언후보). 민감도서 이웃세팅도 양호하면 칼날 아님.")
    return g1 and g2


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
