# -*- coding: utf-8 -*-
# [Back2TV_RP70.py] 세션 260626_01_REVoiLevelUp · Stg5 (확정본 R+P(70%) Back2TV)
# 목적: 청산세팅 확정본 = REVoi + 레짐적응스텝(R ×1.4) + 구조 부분익절(P 70%), 레버3/증거금75(검증노출).
#   현실비용(측정청산갭0 + 스프1bp, §24) 적용. make_back2tv 로직 차용(검증엔진 무수정 §15.1, import 재사용).
#   산출(§20): 거래원장 + 월별통합표 + Pine v6(≤400임베드) + 사례6선(TV가시범위·영문/한글) + 분석txt + INDEX.
#   ★4단 MDD 게이트(§26) 수치는 분석txt에 병기(Stg4 결과). 강제청산 0회.
import os, sys, json
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
sys.path.insert(0, r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork\bots")
import numpy as np, pandas as pd
from datetime import datetime
from fib_replay_1m import load_1m, load_funding
import bt_full as B
from blend_opt import rev_side
import exit_upgrade as EU
import bt_report as BR, make_pine as MP, make_cases as MC

LEV, SZ = 3, 75
SPRD = 0.0001


def _p(*a): print(*a, flush=True)


def main():
    p = json.load(open(os.path.join(r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    EU.T_TF = p["rev_tf"]
    d1m = load_1m(); fund = load_funding()
    _, side = rev_side(d1m, p["rev_tf"], p["q"], p["qwin"])
    sc14, _ = EU.build_scale(d1m, p, 1.4)
    T = B.gen_trades(d1m, fund, p["rev_tf"], p["piv"], p["N"], (p["f1"], p["f2"], p["f3"]), p["iam"],
                     er_gate=0.0, ext_side=side, align_pivot=True, use_trend_flip=False,
                     arm_bars=p["arm"], fib_scale=sc14, tp_frac=0.7, capture_fills=True).sort_values("et").reset_index(drop=True)
    expo = SZ / 100.0 * LEV
    cfg = dict(sig_tf=p["rev_tf"], pivot_tf=p["piv"], N=p["N"], fib1=p["f1"], fib2=p["f2"], fib3=p["f3"],
               init_atr_mult=p["iam"], er_gate=0.0, size_pct=float(SZ), lev=float(LEV))

    today = datetime.now().strftime("%y%m%d"); ts = datetime.now().strftime("%Y%m%d%H%M")
    os.makedirs(BR.BTO, exist_ok=True)
    nn = len([d for d in os.listdir(BR.BTO) if d.startswith(today + "_")]) + 1
    base = f"{today}_{nn:02d}_REVoi_RP70_Real_Back2TV"; folder = os.path.join(BR.BTO, base); os.makedirs(folder, exist_ok=True)

    T.drop(columns=["fills"]).to_csv(os.path.join(folder, f"{base}_거래원장.csv"), index=False, encoding="utf-8-sig")
    L, an, ag = BR.per_trade(T, cfg); U = BR.unified_table(L)
    U.to_csv(os.path.join(folder, f"{base}_월별통합표.csv"), index=False, encoding="utf-8-sig")
    nemb, _, _, ntot = MP.build_pine(T, expo, out=os.path.join(folder, f"{base}.pine"), title=f"REVoi R+P70 Real (lev{LEV}/{SZ}%)")
    cpng, ctxt, csel = MC.build_cases(T, p, d1m, folder, base, max_embed=nemb)
    if cpng is None: _p("  ⚠ 사례6선 생략: TV가시범위 거래<5 (침묵금지)")
    else: _p(f"  사례6선: {os.path.basename(cpng)} (채택 {[c[0][:6] for c in csel]})")
    ret, mdd, cal = an.metrics()

    def pf(s): g = s[s > 0].sum(); b = -s[s < 0].sum(); return g / b if b > 0 else np.inf
    head = (f"[Back2TV·REVoi R+P(70%) 현실] {base}\n"
            f"[세팅] REV_TF={p['rev_tf']} 눌림목={p['piv']} N={p['N']} 피보=({p['f1']:.2f},{p['f2']:.2f},{p['f3']:.2f}) ATR×{p['iam']:.2f}\n"
            f"       청산향상 = 레짐적응스텝 R×1.4 + 구조 부분익절 P 70% (저변동·극단쏠림 봉만 타이트, 고변동 불간섭 §20)\n"
            f"[사이징] 레버={LEV}배 · 증거금={SZ}% · 노출={expo:.2f} (격리마진·유지증거금·강제청산 캡틴캡모델)\n"
            f"[★수익률 §19] 36개월 복리 {ret:+.0f}% (${an.bal:,.0f}, 시작$10k) · MDD {mdd:.0f}% · 강제청산 {an.n_liq}회\n"
            f"[성적] 거래{len(L)}·승률{100*(L.net>0).mean():.0f}%·PF{pf(L.net):.2f}·손익비 (Pine 임베드 {nemb}/전체 {ntot})\n"
            f"[비용] 측정 청산슬립~0bp(§24)+스프1bp 적용 = 현실. 순손익${L.net.sum():+,.0f}\n"
            f"[★MDD 4단 게이트(§26)·Stg4] M0 무제한 L15/100%+3.1억% / M30 L6/80%+48910% / M25 L4/100%+19162% / M20(실거래자격) L3/100%+5579%(MDD-19%)·전구간 강제청산0\n"
            f"[경계 §20] 36개월 최고세팅=과적합 상한·참고. 채택=held-out·CPCV 표준6·M20 인증 별도통과 必.")
    body = head + "\n\n[월별 통합표]\n" + U.to_string(index=False)
    open(os.path.join(BR.WH, f"{ts}_{base}.txt"), "w", encoding="utf-8").write(body)
    open(os.path.join(folder, f"{base}_분석.txt"), "w", encoding="utf-8").write(body)
    with open(BR.INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|260626_01_REVoiLevelUp|{base}: Back2TV R+P(70%) 현실 복리{ret:+.0f}%·MDD{mdd:.0f}%·청산{an.n_liq}·Pine임베드{nemb}/{ntot}|src=Back2TV_RP70.py\n")
    _p("\n" + head)
    _p(f"[저장] {folder}\\  ·  Pine: {base}.pine → TV BINANCE:BTCUSDT.P·UTC·{p['rev_tf']//60}h")


if __name__ == "__main__":
    main()
