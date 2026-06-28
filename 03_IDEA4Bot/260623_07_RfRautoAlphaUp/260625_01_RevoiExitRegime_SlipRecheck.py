# -*- coding: utf-8 -*-
# [260625_01_RevoiExitRegime_SlipRecheck.py] 슬립 재산정 (캡틴 지적 2026-06-25): 내가 지어낸 슬립모델 폐기.
#   근거: ⒜진입·구조청산 = 반전예상 '정해진 레벨' → 지정가(메이커)·체결가능 1m사전판정(bt_full) ⒝청산 fibstop 캡틴 측정 갭슬립=0.00bp(exec_realism 932거래).
#   따라서 기존 +1852% 대비 '진짜 누락비용' = 호가스프레드(1m봉이 못 보는 sub-bar)뿐. 스프레드 0~2bp 민감도로 정직 산정.
#   ★격리마진 복리 = back2tv_REVoi.liq_eval 1:1. ★앵커: 스프레드0 = +1852% 재현. ★MDD-20 제약 없음.
import os, sys, json
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as BR
import bt_report as RP
HERE = os.path.dirname(os.path.abspath(__file__))
SIZE_PCT, LEV = 75.0, 3.0
_FP = r"C:\Windows\Fonts\malgun.ttf"
try: fm.fontManager.addfont(_FP); plt.rcParams["font.family"] = fm.FontProperties(fname=_FP).get_name()
except Exception: pass
plt.rcParams["axes.unicode_minus"] = False


def _p(*a):
    print(*a, flush=True)
    open(os.path.join(HERE, "260625_01_RevoiExitRegime_SlipRecheck_run.log"), "a", encoding="utf-8").write(" ".join(str(x) for x in a)+"\n")


def compound_monthly(R, MAE, FUND, MKEY, extra):
    """liq_eval 1:1 미러 + 월별 순손익$ 적립. extra=청산 스프레드(분율) 추가차감."""
    exp = SIZE_PCT/100.0*LEV
    bal = 10000.0; peak = 10000.0; mdd = 0.0; nliq = 0; rows = {}
    for i in range(len(R)):
        mmr = BR.MMR_T2 if exp*bal > BR.TIER else BR.MMR_T1
        hsd = 1.0/LEV - mmr - BR.SLIP
        bal0 = bal
        if MAE[i] <= -hsd:
            p = -exp*(hsd + BR.COST + abs(FUND[i])); nliq += 1
        else:
            p = (R[i] - extra)*exp
        bal *= (1.0+p)
        rows[MKEY[i]] = rows.get(MKEY[i], 0.0) + (bal-bal0)
        if bal > peak: peak = bal
        dd = bal/peak-1.0
        if dd < mdd: mdd = dd
    tot = (bal/10000.0-1.0)*100.0
    return tot, mdd*100.0, nliq, rows


def main():
    w = json.load(open(os.path.join(HERE, "back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    T = BR.rev_trades(d1m, fund, w).sort_values("et").reset_index(drop=True)
    R = T["R"].values.astype(float); MAE = T["mae"].values.astype(float); FUND = T["fund"].values.astype(float)
    MK = pd.to_datetime(T["et"]).dt.to_period("M").astype(str).values
    _p(f"[거래] {len(T)} · 레버{LEV}/증거금{SIZE_PCT}%/노출{SIZE_PCT/100*LEV:.1f} · 측정 갭슬립=0.00bp(exec_realism)")

    _p("\n[청산 스프레드(=1m봉이 못 보는 sub-bar 비용)만 추가 — 진입/구조청산은 지정가 메이커·슬립0]")
    sens = []
    for bp in [0.0, 0.5, 1.0, 1.5, 2.0]:
        tot, mdd, nl, _ = compound_monthly(R, MAE, FUND, MK, bp/1e4)
        sens.append(dict(청산스프레드bp=bp, 복리수익률pct=round(tot,0), MDDpct=round(mdd,0), 강제청산=nl))
        anc = " ★앵커(=기존 +1852%)" if bp == 0.0 else ""
        _p(f"  스프레드 {bp:>3.1f}bp → 복리 {tot:+7.0f}% · MDD {mdd:.0f}%{anc}")
    sdf = pd.DataFrame(sens)

    # 정직 채택치 = 1bp (BTC Perp 호가 스프레드 통상)
    tot1, mdd1, nl1, rows = compound_monthly(R, MAE, FUND, MK, 1.0/1e4)
    mdf = pd.DataFrame([dict(년월=k, 순손익=v) for k, v in rows.items()])
    mdf["년월"] = pd.PeriodIndex(mdf["년월"], freq="M"); mdf = mdf.sort_values("년월")
    mdf["eq"] = 10000 + mdf["순손익"].cumsum(); mdf["Q"] = mdf["년월"].dt.asfreq("Q")
    qrows = []; prev = 10000.0
    for q, g in mdf.groupby("Q"):
        eqe = g["eq"].iloc[-1]; qrows.append(dict(분기=str(q), 분기수익률pct=round(100*(eqe/prev-1),1), 순손익=round(g.순손익.sum()), 분기말자본=round(eqe))); prev = eqe
    qdf = pd.DataFrame(qrows)
    _p(f"\n[정직 채택 = 스프레드 1bp] 36개월 복리 {tot1:+.0f}% · MDD {mdd1:.0f}%")
    _p(f"[분기별 수익률 (스프레드1bp 반영, MDD-20 제약없음)]\n{qdf.to_string(index=False)}")

    # ── 저장 ──
    from datetime import datetime
    import re
    today = datetime.now().strftime("%y%m%d"); ts = datetime.now().strftime("%Y%m%d%H%M")
    nn = (max([int(m.group(1)) for d in os.listdir(RP.BTO) if (m:=re.match(rf"{today}_(\d+)_", d))]+[0])+1)
    base = f"{today}_{nn:02d}_RevoiExitRegime_SlipRecheck"; folder = os.path.join(RP.BTO, base); os.makedirs(folder, exist_ok=True)
    sdf.to_csv(os.path.join(folder, f"{base}_스프레드민감도.csv"), index=False, encoding="utf-8-sig")
    qdf.to_csv(os.path.join(folder, f"{base}_분기수익률_1bp.csv"), index=False, encoding="utf-8-sig")

    fig, ax = plt.subplots(2, 1, figsize=(15, 11))
    x = np.arange(len(qdf)); c = ["#26a69a" if v >= 0 else "#ef5350" for v in qdf.분기수익률pct]
    ax[0].bar(x, qdf.분기수익률pct, color=c); ax[0].axhline(0, color="black", lw=0.8)
    ax[0].set_title(f"분기별 순수익률 (스프레드1bp·메이커진입·갭슬립0) — 36개월 {tot1:+.0f}% / Quarterly NET return", fontweight="bold")
    ax[0].set_ylabel("분기수익률 (%)"); ax[0].set_xticks(x); ax[0].set_xticklabels(qdf.분기, rotation=45, fontsize=8); ax[0].grid(alpha=0.3, axis="y")
    for i, v in enumerate(qdf.분기수익률pct): ax[0].text(i, v, f"{v:+.0f}", ha="center", va="bottom" if v >= 0 else "top", fontsize=7)
    xs = np.arange(len(sdf)); ax[1].bar(xs, sdf.복리수익률pct, color="#42a5f5")
    ax[1].set_title("청산 스프레드(bp)별 36개월 복리 — 0bp=기존+1852% / Spread sensitivity (gap slip=0 measured)", fontweight="bold")
    ax[1].set_ylabel("복리 수익률 (%)"); ax[1].set_xticks(xs); ax[1].set_xticklabels([f"{v:.1f}bp" for v in sdf.청산스프레드bp]); ax[1].grid(alpha=0.3, axis="y")
    for i, v in enumerate(sdf.복리수익률pct): ax[1].text(i, v, f"{v:+.0f}%", ha="center", va="bottom", fontsize=9)
    fig.suptitle(f"REVoi +1852% 슬립 재산정 — 측정 갭슬립0(캡틴 로직)+스프레드만 — {base}\n"
                 f"기존 +1852% → 스프레드1bp {tot1:+.0f}% (내 과대모델 +253%는 폐기) · MDD {mdd1:.0f}% · 영문/한글 병기",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.93]); png = os.path.join(folder, f"{base}_분석그래프.png"); fig.savefig(png, dpi=130); plt.close(fig)

    body = (f"[REVoi +1852% 슬립 재산정 — 캡틴 지적 반영] {base}\n"+"="*72+"\n"
        f"폐기: 내 슬립모델(base3+분위가산, 청산 4.7bp)은 과대 — 진입/구조청산이 '반전예상 정해진 레벨=지정가 메이커'인 걸 무시했음.\n"
        f"근거: ⒜bt_full: 진입 되돌림·구조부분익절(P)=지정가(MK), 체결은 1m 도달시에만(사전판정) ⒝캡틴 측정(exec_realism 932거래): 청산 fibstop 갭슬립 = 전부 0.00bp.\n"
        f"남은 진짜 누락비용 = 호가 스프레드(1m봉이 못 보는 sub-bar)뿐.\n\n"
        f"[청산 스프레드 민감도]\n{sdf.to_string(index=False)}\n\n"
        f"[정직 채택 = 스프레드 1bp] 36개월 복리 {tot1:+.0f}% · MDD {mdd1:.0f}%\n"
        f"[분기별 수익률]\n{qdf.to_string(index=False)}\n\n"
        f"캡틴 측정 로직 충분성: 갭슬립(=가격이 스톱을 갭관통)은 0으로 정확히 잡음 — 단 호가스프레드+호가충격(sub-1m)은 1m OHLC가 구조적으로 못 봄.\n"
        f"  → 필요(갭)+추가(스프레드1bp 바닥)면 충분. BTC Perp 유동성·이 노션($수십만)서 호가충격은 ~0.5bp 이하라 1bp가 보수적 바닥.\n"
        f"한계: full표본 과적합 상한·참고용(§7). 채택은 held-out·CPCV·MDD별도. 1차레그 즉시진입의 메이커 가정은 유일한 소프트스폿(±0.67bp).")
    open(os.path.join(folder, f"{base}_분석.txt"), "w", encoding="utf-8").write(body)
    open(os.path.join(RP.WH, f"{ts}_{base}.txt"), "w", encoding="utf-8").write(body)
    with open(RP.INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|260625_01_RevoiExitRegime|{base}: 슬립재산정 측정갭0+스프1bp -> +1852%->{tot1:+.0f}%(내과대모델+253%폐기)·MDD{mdd1:.0f}|src=260625_01_RevoiExitRegime_SlipRecheck.py\n")
    _p(f"\n[저장] {folder}")


if __name__ == "__main__":
    main()
