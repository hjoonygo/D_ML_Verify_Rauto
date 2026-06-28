# -*- coding: utf-8 -*-
# [M20MaxBack2TV] R+P70 §26 4단게이트 + MDD−20% 이빠이 최대수익 → M20승자 Back2TV (세션 260626_02_Rauto2_Sys).
#   캡틴: MDD−20% 이빠이 찾아먹기(극한레버는 청산절벽이라 저레버로 exposure 채움) + 강제청산 확인 + Back2TV(TV눈검증).
#   확정청산 = R+P(70%): REVoi + 레짐적응스텝(build_scale ×1.4) + 부분익절 tp_frac0.7 (세션01 확정).
#   ★검증엔진 무수정 호출(§15.1): rev_side·build_scale·gen_trades·curve(liq_eval)·bt_report·make_pine·make_cases.
import os, sys, json
ROOT = os.path.dirname(os.path.abspath(__file__))
for _ in range(5):
    if os.path.isdir(os.path.join(ROOT, "08_BTC_Data")) and os.path.isdir(os.path.join(ROOT, "04_공용엔진코드")): break
    ROOT = os.path.dirname(ROOT)
RES = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp")
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, RES)
from path_finder import ensure_paths; ensure_paths()
import numpy as np, pandas as pd
from datetime import datetime
from fib_replay_1m import load_1m, load_funding
import bt_full as B
from blend_opt import rev_side
import exit_upgrade as EU
import bt_report as BR, make_pine as MP, make_cases as MC


def main():
    p = json.load(open(os.path.join(RES, "back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    EU.T_TF = p["rev_tf"]
    d1m = load_1m(); fund = load_funding()
    _, side = rev_side(d1m, p["rev_tf"], p["q"], p["qwin"])
    sc14, advf = EU.build_scale(d1m, p, 1.4)
    # R+P(70%) 거래(capture_fills=Pine용)
    T = B.gen_trades(d1m, fund, p["rev_tf"], p["piv"], p["N"], (p["f1"],p["f2"],p["f3"]), p["iam"],
                     er_gate=0.0, ext_side=side, align_pivot=True, use_trend_flip=False,
                     arm_bars=p["arm"], fib_scale=sc14, tp_frac=0.7, capture_fills=True).sort_values("et").reset_index(drop=True)
    print("="*88)
    print(f"[R+P(70%) §26 4단게이트 + MDD−20% 이빠이] 거래 {len(T)} · 레짐적응봉 {advf*100:.0f}%")
    print("="*88)

    # ── (lev,size) 격자 스윕 (size≤100=실제증거금 현실상한, lev은 청산절벽 포함 폭넓게) ──
    LEVG = [3,4,5,6,8,10,13,16,20,25,30]; SZG = list(range(5,101,5))
    best = {}  # stage -> (tot,mdd,nliq,lev,sz,exp)
    def consider(stg, limit, tot, mdd, nliq, lev, sz):
        if limit is not None and mdd < limit: return
        e = sz/100.0*lev
        if stg not in best or tot > best[stg][0]: best[stg] = (tot, mdd, nliq, lev, sz, e)
    for lev in LEVG:
        for sz in SZG:
            c = EU.curve(T, sz, lev)
            consider("M0", None, c["tot"], c["mdd"], c["nliq"], lev, sz)
            consider("M30", -30.0, c["tot"], c["mdd"], c["nliq"], lev, sz)
            consider("M25", -25.0, c["tot"], c["mdd"], c["nliq"], lev, sz)
            consider("M20", -20.0, c["tot"], c["mdd"], c["nliq"], lev, sz)
    print("\n★ §26 MDD 4단 게이트 (각 단계 최대수익 + 격리마진 강제청산)")
    print(f"  {'단계':<6}{'제약':<10}{'레버':>5}{'증거금%':>8}{'노출':>6}{'복리(슬립0)':>13}{'MDD':>8}{'강제청산':>8}")
    nm = {"M0":"무제한(천장)","M30":"≥−30%","M25":"≥−25%","M20":"≥−20%(실거래자격)"}
    for stg in ["M0","M30","M25","M20"]:
        tot,mdd,nliq,lev,sz,e = best[stg]
        print(f"  {stg:<6}{nm[stg]:<14}{lev:>4}x{sz:>7}%{e:>6.1f}{tot:>+12.0f}%{mdd:>7.1f}%{nliq:>7}")

    m20 = best["M20"]; LEV, SZ = int(m20[3]), int(m20[4]); expo = SZ/100.0*LEV
    print(f"\n[M20 이빠이 채택] 레버{LEV}x·증거금{SZ}%·노출{expo:.1f} → 복리 {m20[0]:+.0f}% · MDD {m20[1]:.1f}% · 강제청산 {m20[2]}")

    # ── Back2TV (M20 승자) ──
    cfg = dict(sig_tf=p["rev_tf"], pivot_tf=p["piv"], N=p["N"], fib1=p["f1"], fib2=p["f2"], fib3=p["f3"],
               init_atr_mult=p["iam"], er_gate=0.0, size_pct=float(SZ), lev=float(LEV))
    today = datetime.now().strftime("%y%m%d"); ts = datetime.now().strftime("%Y%m%d%H%M")
    os.makedirs(BR.BTO, exist_ok=True)
    nn = EU.next_nn(today)
    base = f"{today}_{nn:02d}_REVoi_RP70_M20Max_Back2TV"; folder = os.path.join(BR.BTO, base); os.makedirs(folder, exist_ok=True)
    T.drop(columns=["fills"]).to_csv(os.path.join(folder, f"{base}_거래원장.csv"), index=False, encoding="utf-8-sig")
    L, an, ag = BR.per_trade(T, cfg); U = BR.unified_table(L)
    U.to_csv(os.path.join(folder, f"{base}_월별통합표.csv"), index=False, encoding="utf-8-sig")
    nemb, _, _, ntot = MP.build_pine(T, expo, out=os.path.join(folder, f"{base}.pine"), title=f"REVoi R+P70 M20max (lev{LEV}/{SZ}%)")
    cpng, ctxt, csel = MC.build_cases(T, p, d1m, folder, base, max_embed=nemb)
    if cpng is None: print("  ⚠ 사례6선 생략: TV가시범위 거래<5")
    else: print(f"  사례6선: {os.path.basename(cpng)}")
    ret, mdd, cal = an.metrics()
    def pf(s): g=s[s>0].sum(); b=-s[s<0].sum(); return g/b if b>0 else np.inf
    g4 = best
    head = (f"[Back2TV·REVoi R+P(70%) M20이빠이] {base}\n"
            f"[세팅] REV_TF={p['rev_tf']} 눌림목={p['piv']} N={p['N']} 피보=({p['f1']:.2f},{p['f2']:.2f},{p['f3']:.2f}) ATR×{p['iam']:.2f}\n"
            f"       청산 = R+P(70%): 레짐적응스텝×1.4(불리봉 {advf*100:.0f}%·고변동불간섭) + 구조 부분익절 70%\n"
            f"[사이징] M20 이빠이 = 레버{LEV}x·증거금{SZ}%·노출{expo:.1f} (격리마진·강제청산 {m20[2]}회)\n"
            f"[★수익률 §19] 36개월 복리(현실비용) {ret:+.0f}% (${an.bal:,.0f}, 시작$10k) · MDD {mdd:.1f}% · 강제청산 {an.n_liq}회\n"
            f"[성적] 거래{len(L)}·승률{100*(L.net>0).mean():.0f}%·PF{pf(L.net):.2f} (Pine 임베드 {nemb}/전체 {ntot})\n"
            f"[★§26 4단게이트(슬립0 상한)] M0 L{g4['M0'][3]}/{g4['M0'][4]}% {g4['M0'][0]:+.0f}%(MDD{g4['M0'][1]:.0f}·청산{g4['M0'][2]}) / "
            f"M30 L{g4['M30'][3]}/{g4['M30'][4]}% {g4['M30'][0]:+.0f}%(MDD{g4['M30'][1]:.0f}·청산{g4['M30'][2]}) / "
            f"M25 L{g4['M25'][3]}/{g4['M25'][4]}% {g4['M25'][0]:+.0f}%(MDD{g4['M25'][1]:.0f}·청산{g4['M25'][2]}) / "
            f"M20 L{g4['M20'][3]}/{g4['M20'][4]}% {g4['M20'][0]:+.0f}%(MDD{g4['M20'][1]:.0f}·청산{g4['M20'][2]})\n"
            f"[비용] 측정청산슬립~0bp(§24)+스프1bp=현실. 순손익${L.net.sum():+,.0f}\n"
            f"[경계 §20] 36개월 최고세팅=과적합 상한·참고. 채택=held-out·CPCV표준6·M20인증 별도통과 必.")
    body = head + "\n\n[월별 통합표]\n" + U.to_string(index=False)
    open(os.path.join(BR.WH, f"{ts}_{base}.txt"), "w", encoding="utf-8").write(body)
    open(os.path.join(folder, f"{base}_분석.txt"), "w", encoding="utf-8").write(body)
    with open(BR.INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|260626_02_Rauto2_Sys|{base}: R+P70 M20이빠이 레버{LEV}/{SZ}% 복리{ret:+.0f}%·MDD{mdd:.0f}%·청산{an.n_liq}·Pine{nemb}/{ntot}|src=M20MaxBack2TV.py\n")
    print("\n" + head)
    print(f"\n[저장] {folder}\\  ·  Pine: {base}.pine → TV BINANCE:BTCUSDT.P·UTC·{p['rev_tf']//60}h")
    return True


if __name__ == "__main__":
    main()
