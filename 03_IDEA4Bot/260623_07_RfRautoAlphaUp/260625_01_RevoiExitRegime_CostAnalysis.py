# -*- coding: utf-8 -*-
# [260625_01_RevoiExitRegime_CostAnalysis.py] +1852% 세팅(260624_13, MDD-25)의 실비용 정밀분해 +
#   §20 현실 시장가슬립을 단계별(0/3/5/8/10bp)로 넣어 '진짜 순수익'이 얼마까지 줄어드는지 분기수익률로 (캡틴 지시 2026-06-25).
#   ★MDD-20 제약 안 검 (MDD-25 세팅 그대로). ★앵커: 슬립0 = 기존 +1852% 재현 대조(§15.2).
#   ★검증엔진만(§15.1): 거래원장은 back2tv_REVoi 산출 그대로 · 사이징/청산 = back2tv_REVoi.liq_eval(rauto_paper_engine 1:1).
import os, sys, time
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
import back2tv_REVoi as BR
import bt_report as RP
HERE = os.path.dirname(os.path.abspath(__file__))
DROOT = r"D:\ML\RfRauto\00_WorkHstr\BackTest_Output\260624_13_REVoi_MDD25_36mo_v6"
MONTHLY = os.path.join(DROOT, "260624_13_REVoi_MDD25_36mo_v6_월별통합표.csv")
LEDGER  = os.path.join(DROOT, "260624_13_REVoi_MDD25_36mo_v6_거래원장.csv")
SIZE_PCT, LEV = 75.0, 3.0    # +1852% 세팅 (노출 2.2)
_FP = r"C:\Windows\Fonts\malgun.ttf"
try: fm.fontManager.addfont(_FP); plt.rcParams["font.family"] = fm.FontProperties(fname=_FP).get_name()
except Exception: pass
plt.rcParams["axes.unicode_minus"] = False


def _p(*a):
    print(*a, flush=True)
    open(os.path.join(HERE, "260625_01_RevoiExitRegime_CostAnalysis_run.log"), "a", encoding="utf-8").write(" ".join(str(x) for x in a)+"\n")


def main():
    df = pd.read_csv(MONTHLY)
    # ── 1. 비용 분해 (이미 계산된 월별통합표) ──
    gross = df["손익금_무비용($)"].sum(); net = df["순손익금_현실($)"].sum()
    mk = df["지정가_수수료($)"].sum(); tk = df["시장가_수수료($)"].sum()
    fd = df["펀딩비($)"].sum(); sp = df["슬리피지($)"].sum(); tc = df["총비용($)"].sum()
    rawfee = mk + tk + abs(fd)
    _p("="*72)
    _p("[+1852% 세팅(MDD-25, 레버3/증거금75%/노출2.2) 비용 분해 — 36개월]")
    _p(f"  손익금 무비용(이론상한)  = {gross:>13,.0f}  = +{gross/100:,.0f}%")
    _p(f"  순손익  현실(헤드라인)    = {net:>13,.0f}  = +{net/100:,.0f}%   <== +1852%는 '이미 비용 뺀' 값")
    _p(f"  총비용(이론-현실)         = {tc:>13,.0f}  (이론수익의 {100*tc/gross:.0f}%를 비용이 먹음)")
    _p(f"   ├ 지정가(메이커)수수료   = {mk:>13,.0f}")
    _p(f"   ├ 시장가(테이커)수수료   = {tk:>13,.0f}")
    _p(f"   ├ 슬리피지               = {sp:>13,.0f}  <== 0! (1m재현상 0bp = 낙관·미반영, §20)")
    _p(f"   ├ 펀딩비(절대)           = {abs(fd):>13,.0f}")
    _p(f"   └ 복리드래그(수수료가 자본 깎아 이후 포지션 축소) = {tc-rawfee:>12,.0f}")
    _p(f"  생수수료+펀딩 합 {rawfee:,.0f} (총비용의 {100*rawfee/tc:.0f}%) · 복리드래그 {tc-rawfee:,.0f} ({100*(tc-rawfee)/tc:.0f}%)")

    # ── 2. 분기별 현실 순손익 (복리 equity path) ──
    df["ym"] = pd.PeriodIndex(df["년월"], freq="M"); df["Q"] = df["ym"].dt.asfreq("Q")
    df["eq"] = 10000 + df["총합_누적수익금($)"]
    qrows = []; prev = 10000.0
    for q, g in df.groupby("Q"):
        eq_end = g["eq"].iloc[-1]; pct = 100*(eq_end/prev-1)
        L = g["롱_수익금($)"].sum(); S = g["숏_수익금($)"].sum()
        qrows.append(dict(분기=str(q), 분기수익률pct=round(pct,1), 롱_순손익=round(L), 숏_순손익=round(S), 분기말자본=round(eq_end)))
        prev = eq_end
    qdf = pd.DataFrame(qrows)
    _p("\n[분기별 현실 순손익(복리·이미 비용 뺀 값) · MDD-20 제약 없음]")
    _p(qdf.to_string(index=False))

    # ── 3. §20 현실 시장가슬립 단계 적용 (청산 fibstop=테이커, 한쪽 슬립 0/3/5/8/10bp) ──
    L = pd.read_csv(LEDGER)
    R = L["R"].values.astype(float); MAE = L["mae"].values.astype(float); FUND = L["fund"].values.astype(float)
    MK = pd.to_datetime(L["et"]).dt.to_period("M").astype(str).values
    _p("\n" + "="*72)
    _p("[§20 현실 시장가슬립 단계 적용 — 청산(테이커)에 추가슬립 bp만큼 R 차감 후 격리마진 재복리]")
    srows = []
    for extra in [0.0, 3.0, 5.0, 8.0, 10.0]:
        Radj = R - extra/1e4
        tot, mdd, bm, nl = BR.liq_eval(Radj, MAE, FUND, MK, SIZE_PCT, LEV)
        srows.append(dict(추가슬립bp=extra, 복리수익률pct=round(tot,0), MDDpct=round(mdd,0), 강제청산=int(nl), 단일최고월pct=round(bm,0)))
        anc = " ★앵커(=기존 +1852%)" if extra == 0.0 else ""
        _p(f"  추가슬립 {extra:>4.0f}bp → 복리 {tot:+7.0f}% · MDD {mdd:+5.0f}% · 강제청산 {nl}회{anc}")
    sdf = pd.DataFrame(srows)

    # ── 저장 (§19) ──
    from datetime import datetime
    import re
    today = datetime.now().strftime("%y%m%d"); ts = datetime.now().strftime("%Y%m%d%H%M")
    nn = (max([int(m.group(1)) for d in os.listdir(RP.BTO) if (m:=re.match(rf"{today}_(\d+)_", d))]+[0])+1)
    base = f"{today}_{nn:02d}_RevoiExitRegime_CostAnalysis"; folder = os.path.join(RP.BTO, base); os.makedirs(folder, exist_ok=True)
    qdf.to_csv(os.path.join(folder, f"{base}_분기별순손익.csv"), index=False, encoding="utf-8-sig")
    sdf.to_csv(os.path.join(folder, f"{base}_슬립민감도.csv"), index=False, encoding="utf-8-sig")

    fig, ax = plt.subplots(2, 1, figsize=(15, 11))
    x = np.arange(len(qdf)); c = ["#26a69a" if v >= 0 else "#ef5350" for v in qdf.분기수익률pct]
    ax[0].bar(x, qdf.분기수익률pct, color=c); ax[0].axhline(0, color="black", lw=0.8)
    ax[0].set_title("분기별 현실 순손익률(복리·비용반영) — +1852% 세팅(MDD-25) / Quarterly NET return", fontweight="bold")
    ax[0].set_ylabel("분기수익률 (%)"); ax[0].set_xticks(x); ax[0].set_xticklabels(qdf.분기, rotation=45, fontsize=8); ax[0].grid(alpha=0.3, axis="y")
    for i, v in enumerate(qdf.분기수익률pct): ax[0].text(i, v, f"{v:+.0f}", ha="center", va="bottom" if v >= 0 else "top", fontsize=7)
    xs = np.arange(len(sdf))
    ax[1].bar(xs, sdf.복리수익률pct, color="#42a5f5"); ax[1].axhline(net/100, color="green", ls="--", lw=1, label=f"기존 +{net/100:.0f}%")
    ax[1].set_title("청산 추가슬립(bp)별 36개월 복리 순수익률 — '진짜 비용'이 수익을 얼마나 깎나 / Slippage sensitivity", fontweight="bold")
    ax[1].set_ylabel("복리 수익률 (%)"); ax[1].set_xticks(xs); ax[1].set_xticklabels([f"+{int(v)}bp" for v in sdf.추가슬립bp]); ax[1].grid(alpha=0.3, axis="y"); ax[1].legend()
    for i, v in enumerate(sdf.복리수익률pct): ax[1].text(i, v, f"{v:+.0f}%", ha="center", va="bottom", fontsize=9)
    fig.suptitle(f"REVoi +1852% 세팅 실비용 분석 — 이론 +{gross/100:,.0f}% → 비용차감 현실 +{net/100:,.0f}% → 추가슬립 민감도 — {base}\n"
                 f"슬립0(현행)=+{net/100:.0f}% · +5bp=+{sdf.복리수익률pct.iloc[2]:.0f}% · +10bp=+{sdf.복리수익률pct.iloc[4]:.0f}% (MDD-20 제약없음·영문/한글 병기)",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.93]); png = os.path.join(folder, f"{base}_분석그래프.png"); fig.savefig(png, dpi=130); plt.close(fig)

    body = (f"[REVoi +1852% 세팅 실비용 정밀분석] {base}\n"+"="*72+"\n"
        f"대상: 260624_13_REVoi_MDD25 (레버3/증거금75%/노출2.2, MDD-25, 거래932) — MDD-20 제약 안 검.\n\n"
        f"[비용 분해 36개월]\n"
        f"  이론(무비용 상한)  +{gross/100:,.0f}%  ({gross:,.0f}$)\n"
        f"  현실(=헤드라인)    +{net/100:,.0f}%  ({net:,.0f}$)  ← +1852%는 '이미 비용 뺀' 순수익\n"
        f"  총비용             {tc:,.0f}$  (이론의 {100*tc/gross:.0f}%)\n"
        f"   = 메이커수수료 {mk:,.0f} + 테이커수수료 {tk:,.0f} + 슬리피지 {sp:,.0f}(0!) + 펀딩 {abs(fd):,.0f} + 복리드래그 {tc-rawfee:,.0f}\n"
        f"   생수수료+펀딩은 총비용의 {100*rawfee/tc:.0f}%뿐 · 나머지 {100*(tc-rawfee)/tc:.0f}%는 복리드래그(수수료가 자본 깎아 이후 포지션 축소).\n\n"
        f"[분기별 현실 순손익(복리·비용반영)]\n{qdf.to_string(index=False)}\n\n"
        f"[§20 현실 시장가슬립 민감도 — 청산(테이커)에 추가슬립 bp 차감 후 격리마진 재복리]\n{sdf.to_string(index=False)}\n\n"
        f"핵심: ① +1852%는 GROSS 아님 = 이미 수수료·펀딩·강제청산 반영된 NET. 이론상한은 +{gross/100:,.0f}%였음.\n"
        f"  ② 단 '슬리피지=0'이 §20대로 낙관 — 청산 시장가에 현실슬립을 넣으면 +5bp서 +{sdf.복리수익률pct.iloc[2]:.0f}%, +10bp서 +{sdf.복리수익률pct.iloc[4]:.0f}%로 더 줄어듦(레버3 복리라 슬립 민감).\n"
        f"  ③ held-out +87%(16개월 OOS)와 이 +1852%(full 36개월)는 서로 다른 측정 — 빼서 나온 관계 아님.\n"
        f"한계: full표본 과적합 상한(참고용). 진짜 채택은 held-out·CPCV 별도. 본 분석은 '실비용 규명'에 한정.")
    open(os.path.join(folder, f"{base}_분석.txt"), "w", encoding="utf-8").write(body)
    open(os.path.join(RP.WH, f"{ts}_{base}.txt"), "w", encoding="utf-8").write(body)
    with open(RP.INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|260625_01_RevoiExitRegime|{base}: +1852%실비용분해 이론+{gross/100:.0f}%->현실+{net/100:.0f}%(이미NET)·슬립+5bp +{sdf.복리수익률pct.iloc[2]:.0f}%/+10bp +{sdf.복리수익률pct.iloc[4]:.0f}%·MDD25|src=260625_01_RevoiExitRegime_CostAnalysis.py\n")
    _p(f"\n[저장] {folder}")


if __name__ == "__main__":
    main()
