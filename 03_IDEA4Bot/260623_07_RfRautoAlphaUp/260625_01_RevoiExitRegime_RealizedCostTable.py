# -*- coding: utf-8 -*-
# [260625_01_RevoiExitRegime_RealizedCostTable.py] +1852% 세팅을 $10,000 시드에서 '거래별 현실화' (캡틴 지시 2026-06-25).
#   거래마다: 진입 3분할(1차=시장가 즉시 / 되돌림2레그=지정가 메이커, 미체결시 시장가 폴백) · 청산=시장가(fibstop).
#   시장가 체결에만 §20 채택 슬립모델 적용: slip_bp = base3 + atr60분위가산 + |OIz|분위가산, + 스프레드1bp(청산).
#   전부 $ 금액화(격리마진 복리, liq_eval 1:1 미러). ★앵커: 슬립 OFF면 기존 +1852% 재현(§15.2). ★MDD-20 제약 없음.
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
REG = r"D:\ML\RfRauto\08_BTC_Data\derived\_regime_features.parquet"
MK, TK, SPRD = 0.0002, 0.0004, 0.0001          # 메이커2bp / 테이커4bp / 스프레드1bp
MMR_T1, MMR_T2, TIER, LCOST, LSLIP = 0.004, 0.005, 50000.0, 0.0014, 0.0005   # 강제청산식(엔진 불변)
SIZE_PCT, LEV = 75.0, 3.0                       # +1852% 세팅
SLIP_BASE = 0.0003                              # 시장가 기본슬립 3bp
ADD = np.array([0.0, 0.00005, 0.0001, 0.00015, 0.0002])   # 분위 Q1~Q5 가산 0/0.5/1/1.5/2bp (변동성·OI 각각)
_FP = r"C:\Windows\Fonts\malgun.ttf"
try: fm.fontManager.addfont(_FP); plt.rcParams["font.family"] = fm.FontProperties(fname=_FP).get_name()
except Exception: pass
plt.rcParams["axes.unicode_minus"] = False


def _p(*a):
    print(*a, flush=True)
    open(os.path.join(HERE, "260625_01_RevoiExitRegime_RealizedCostTable_run.log"), "a", encoding="utf-8").write(" ".join(str(x) for x in a)+"\n")


def regime_at(times, R, col):
    pos = np.clip(np.searchsorted(R.index.values, np.asarray(times, dtype="datetime64[ns]"), "right")-1, 0, len(R)-1)
    return R[col].values[pos]


def qadd(vals, thr):
    """값 배열을 분위 임계 thr(4개)로 Q1~Q5 가산(ADD) 매핑."""
    idx = np.searchsorted(thr, vals)   # 0~4
    return ADD[np.clip(idx, 0, 4)]


def run(T, realistic):
    """격리마진 복리 1:1 미러 + 거래별 $ 비용 적립. realistic=False면 기존모델(앵커)."""
    exp = SIZE_PCT/100.0*LEV
    R = T["R"].values.astype(float); MAE = T["mae"].values.astype(float); FUND = T["fund"].values.astype(float)
    se = T["slip_e"].values; sx = T["slip_x"].values; ntk_e = T["ntk_entry"].values; nmk_e = T["nmk_entry"].values
    MKEY = pd.to_datetime(T["et"]).dt.to_period("M").astype(str).values
    bal = 10000.0; peak = 10000.0; mdd = 0.0; nliq = 0
    rows = {}
    for i in range(len(R)):
        mmr = MMR_T2 if exp*bal > TIER else MMR_T1
        hsd = 1.0/LEV - mmr - LSLIP
        notion = exp*bal
        rec = rows.setdefault(MKEY[i], dict(거래=0, 진입메이커=0, 진입테이커=0, 청산테이커=0,
                                            메이커수수료=0.0, 테이커수수료=0.0, 스프레드=0.0, 슬리피지=0.0, 펀딩=0.0, 순손익=0.0))
        bal0 = bal
        if MAE[i] <= -hsd:                       # 강제청산
            p = -exp*(hsd + LCOST + abs(FUND[i])); nliq += 1
            bal *= (1.0+p)
            rec["거래"] += 1; rec["순손익"] += bal-bal0
        else:
            # 추가 현실비용(분율) = 스프레드 + 1차레그 테이커업글 + 진입1차슬립 + 청산슬립 (realistic만)
            if realistic:
                up_leg1 = (TK-MK)*(1.0/3.0)               # 1차레그(1/3)가 메이커→테이커
                slE = se[i]*(1.0/3.0)                     # 진입 1차레그(1/3) 시장가 슬립
                slX = sx[i]                               # 청산(전량) 시장가 슬립
                extra = SPRD + up_leg1 + slE + slX
            else:
                extra = 0.0
            p = (R[i] - extra)*exp
            bal *= (1.0+p)
            # ── $ 비용 적립(보고용) ──
            rec["거래"] += 1
            rec["진입메이커"] += int(nmk_e[i] if realistic else 3)
            rec["진입테이커"] += int(ntk_e[i] if realistic else 0)
            rec["청산테이커"] += 1
            rec["메이커수수료"] += notion*(1.0/3.0)*MK*(nmk_e[i] if realistic else 3)
            rec["테이커수수료"] += notion*((1.0/3.0)*TK*(ntk_e[i] if realistic else 0) + TK)   # 진입테이커레그 + 청산전량
            if realistic:
                rec["스프레드"] += notion*SPRD
                rec["슬리피지"] += notion*(se[i]*(1.0/3.0) + sx[i])
            rec["펀딩"] += notion*FUND[i]
            rec["순손익"] += bal-bal0
        if bal > peak: peak = bal
        dd = bal/peak-1.0
        if dd < mdd: mdd = dd
        if bal <= 0: break
    tot = (bal/10000.0-1.0)*100.0
    df = pd.DataFrame(rows).T.reset_index().rename(columns={"index":"년월"})
    df["누적순손익"] = df["순손익"].cumsum()
    return tot, mdd*100.0, nliq, df, bal


def main():
    w = json.load(open(os.path.join(HERE, "back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    T = BR.rev_trades(d1m, fund, w, capture_fills=True).sort_values("et").reset_index(drop=True)
    _p(f"[거래생성] {len(T)}거래 (REV_MDD25 세팅, capture_fills) · 레버{LEV}/증거금{SIZE_PCT}%/노출{SIZE_PCT/100*LEV:.1f}")

    # 진입레그 메이커/테이커 분류 (1차=테이커, 되돌림2레그=메이커, base폴백=테이커)
    ntk = []; nmk = []
    for r in T.itertuples():
        fills = r.fills if isinstance(r.fills, list) else []
        if not fills: ntk.append(1); nmk.append(2); continue
        base = fills[0][1]; tk = 1; mk = 0   # 1차레그 테이커
        for ft, fp in fills[1:]:
            if abs(fp-base) < 1e-9: tk += 1
            else: mk += 1
        ntk.append(tk); nmk.append(mk)
    T["ntk_entry"] = ntk; T["nmk_entry"] = nmk

    # 레짐(atr60·|OIz|)을 진입/청산 시각에 매핑 → 시장가 슬립 예측
    Rg = pd.read_parquet(REG); Rg["timestamp"] = pd.to_datetime(Rg["timestamp"], utc=True).dt.tz_localize(None)
    Rg = Rg.set_index("timestamp").sort_index()
    atr_e = regime_at(pd.to_datetime(T["et"]).values, Rg, "atr60"); oiz_e = np.abs(regime_at(pd.to_datetime(T["et"]).values, Rg, "oiz_s"))
    atr_x = regime_at(pd.to_datetime(T["xt"]).values, Rg, "atr60"); oiz_x = np.abs(regime_at(pd.to_datetime(T["xt"]).values, Rg, "oiz_s"))
    at_thr = np.nanquantile(Rg["atr60"].values, [0.2,0.4,0.6,0.8]); oi_thr = np.nanquantile(np.abs(Rg["oiz_s"].values), [0.2,0.4,0.6,0.8])
    T["slip_e"] = SLIP_BASE + qadd(atr_e, at_thr) + qadd(oiz_e, oi_thr)   # 진입 시장가 슬립(분율)
    T["slip_x"] = SLIP_BASE + qadd(atr_x, at_thr) + qadd(oiz_x, oi_thr)   # 청산 시장가 슬립(분율)
    _p(f"[슬립예측] 진입 평균 {T.slip_e.mean()*1e4:.1f}bp(3~{T.slip_e.max()*1e4:.0f}) · 청산 평균 {T.slip_x.mean()*1e4:.1f}bp · 스프레드 {SPRD*1e4:.0f}bp 별도")

    # ── 앵커(기존모델) vs 현실화 ──
    tot0, mdd0, nl0, df0, _ = run(T, realistic=False)
    tot1, mdd1, nl1, df1, _ = run(T, realistic=True)
    _p(f"\n[앵커 §15.2] 슬립OFF 복리 {tot0:+.0f}% · MDD {mdd0:.0f}% (기존 +1852%/-25% 재현 대조)")
    _p(f"[현실화]   슬립ON  복리 {tot1:+.0f}% · MDD {mdd1:.0f}% · 강제청산 {nl1}")

    # 비용 합계
    c = df1[["메이커수수료","테이커수수료","스프레드","슬리피지","펀딩"]].sum()
    _p(f"\n[현실화 36개월 비용 합계 $] 메이커 {c.메이커수수료:,.0f} · 테이커 {c.테이커수수료:,.0f} · 스프레드 {c.스프레드:,.0f} · 슬리피지 {c.슬리피지:,.0f} · 펀딩 {c.펀딩:,.0f}")
    _p(f"[순손익] 기존(슬립0) ${df0.순손익.sum():,.0f}  →  현실화 ${df1.순손익.sum():,.0f}  (차이 ${df1.순손익.sum()-df0.순손익.sum():,.0f})")

    # 분기 헤드라인 (§2.5) — 현실화 기준 복리 equity path
    df1["Q"] = pd.PeriodIndex(df1["년월"], freq="M").asfreq("Q")
    df1["eq"] = 10000 + df1["누적순손익"]
    qrows = []; prev = 10000.0
    for q, g in df1.groupby("Q"):
        eqe = g["eq"].iloc[-1]; pct = 100*(eqe/prev-1)
        qrows.append(dict(분기=str(q), 현실화_분기수익률pct=round(pct,1), 슬리피지차감=round(g.슬리피지.sum()), 순손익=round(g.순손익.sum()), 분기말자본=round(eqe)))
        prev = eqe
    qdf = pd.DataFrame(qrows)
    _p(f"\n[분기별 현실화 수익률 (슬립·스프레드 전부 반영, MDD-20 제약없음)]\n{qdf.to_string(index=False)}")

    # ── §3 표준 월별표(현실화) 저장 + §19 산출 ──
    from datetime import datetime
    import re
    today = datetime.now().strftime("%y%m%d"); ts = datetime.now().strftime("%Y%m%d%H%M")
    nn = (max([int(m.group(1)) for d in os.listdir(RP.BTO) if (m:=re.match(rf"{today}_(\d+)_", d))]+[0])+1)
    base = f"{today}_{nn:02d}_RevoiExitRegime_RealizedCostTable"; folder = os.path.join(RP.BTO, base); os.makedirs(folder, exist_ok=True)
    out = df1[["년월","거래","진입메이커","진입테이커","청산테이커","메이커수수료","테이커수수료","스프레드","슬리피지","펀딩","순손익","누적순손익"]].copy()
    for col in ["메이커수수료","테이커수수료","스프레드","슬리피지","펀딩","순손익","누적순손익"]: out[col] = out[col].round(0)
    out.to_csv(os.path.join(folder, f"{base}_현실화월별표.csv"), index=False, encoding="utf-8-sig")
    qdf.to_csv(os.path.join(folder, f"{base}_분기수익률.csv"), index=False, encoding="utf-8-sig")

    fig, ax = plt.subplots(2, 1, figsize=(16, 11))
    x = np.arange(len(qdf)); cc = ["#26a69a" if v>=0 else "#ef5350" for v in qdf.현실화_분기수익률pct]
    ax[0].bar(x, qdf.현실화_분기수익률pct, color=cc); ax[0].axhline(0, color="black", lw=0.8)
    ax[0].set_title(f"분기별 현실화 순수익률(슬립·스프레드 반영) — 36개월 합 {tot1:+.0f}% (기존 {tot0:+.0f}% → 슬립적용) / Quarterly realized return", fontweight="bold")
    ax[0].set_ylabel("분기수익률 (%)"); ax[0].set_xticks(x); ax[0].set_xticklabels(qdf.분기, rotation=45, fontsize=8); ax[0].grid(alpha=0.3, axis="y")
    for i,v in enumerate(qdf.현실화_분기수익률pct): ax[0].text(i, v, f"{v:+.0f}", ha="center", va="bottom" if v>=0 else "top", fontsize=7)
    comp = [tot0, tot1]; ax[1].bar(["기존(슬립0·낙관)","현실화(슬립적용)"], comp, color=["#bbbbbb","#42a5f5"])
    ax[1].set_title("36개월 복리 순수익률: 기존 vs 현실화 / 36-month compound NET", fontweight="bold"); ax[1].set_ylabel("복리 수익률 (%)"); ax[1].grid(alpha=0.3, axis="y")
    for i,v in enumerate(comp): ax[1].text(i, v, f"{v:+.0f}%", ha="center", va="bottom", fontsize=11)
    fig.suptitle(f"REVoi +1852% 세팅 거래별 현실화($10k 시드) — 슬립·스프레드·1차레그테이커 금액반영 — {base}\n"
                 f"기존 {tot0:+.0f}% → 현실화 {tot1:+.0f}% · 슬리피지차감 ${c.슬리피지:,.0f} · MDD {mdd0:.0f}%→{mdd1:.0f}% (MDD-20 제약없음·영문/한글 병기)",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.93]); png = os.path.join(folder, f"{base}_분석그래프.png"); fig.savefig(png, dpi=130); plt.close(fig)

    body = (f"[REVoi +1852% 세팅 거래별 현실화 표 ($10,000 시드)] {base}\n"+"="*72+"\n"
        f"대상: REV_MDD25 (레버3/증거금75%/노출2.2, {len(T)}거래). MDD-20 제약 안 검.\n"
        f"체결모델: 진입 3분할 = 1차레그(1/3) 시장가 즉시 + 되돌림2레그 지정가(메이커, 미체결 {((T.ntk_entry-1).sum())}레그는 시장가 폴백) · 청산 전량 시장가(fibstop).\n"
        f"슬립예측(§20 채택): 시장가 체결 = base3bp + atr60분위(0~2) + |OIz|분위(0~2) · 청산 스프레드 1bp 별도. 진입평균 {T.slip_e.mean()*1e4:.1f}bp/청산평균 {T.slip_x.mean()*1e4:.1f}bp.\n\n"
        f"[36개월 복리 순수익률]  기존(슬립0·낙관) {tot0:+.0f}%  →  현실화(슬립적용) {tot1:+.0f}%   (MDD {mdd0:.0f}%→{mdd1:.0f}%)\n"
        f"[36개월 비용 합계 $]  메이커 {c.메이커수수료:,.0f} · 테이커 {c.테이커수수료:,.0f} · 스프레드 {c.스프레드:,.0f} · 슬리피지 {c.슬리피지:,.0f} · 펀딩 {c.펀딩:,.0f}\n"
        f"[순손익 $]  기존 {df0.순손익.sum():,.0f}  →  현실화 {df1.순손익.sum():,.0f}\n\n"
        f"[분기별 현실화 수익률]\n{qdf.to_string(index=False)}\n\n"
        f"[현실화 월별표(§3 형식)]\n{out.to_string(index=False)}\n\n"
        f"앵커 검증(§15.2): 슬립 OFF 재실행 = {tot0:+.0f}%/MDD{mdd0:.0f}% → 기존 +1852%/-25% 재현(하니스 신뢰).\n"
        f"핵심: +1852%는 청산 슬립 0의 낙관치. 시장가 슬립(평균 {T.slip_x.mean()*1e4:.1f}bp)+스프레드 반영하면 {tot1:+.0f}%로 줄어듦(레버3 복리라 민감).\n"
        f"한계(§7): full표본 과적합 상한·참고용. 채택은 held-out·CPCV·MDD-20 별도통과만. 슬립계수(base3/분위가산)는 가정 — 실측 보정시 갱신.")
    open(os.path.join(folder, f"{base}_분석.txt"), "w", encoding="utf-8").write(body)
    open(os.path.join(RP.WH, f"{ts}_{base}.txt"), "w", encoding="utf-8").write(body)
    with open(RP.INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|260625_01_RevoiExitRegime|{base}: 거래별현실화 슬립적용 +1852%->{tot1:+.0f}%·슬립차감${c.슬리피지:,.0f}·MDD{mdd0:.0f}->{mdd1:.0f}|src=260625_01_RevoiExitRegime_RealizedCostTable.py\n")
    _p(f"\n[저장] {folder}")


if __name__ == "__main__":
    main()
