# -*- coding: utf-8 -*-
# [260625_01_RautoSysReform2_Back2TV_Full.py] ★Back2TV 전량(§20) — REVoi·SW (세션 260625_01_RautoSysReform2).
#   §20 전부: ①환각검증 + ②MDD해제·③MDD−25 최고수익(격자스윕) + 결과데이터(28열 월별통합표·거래원장) + Pine v6 + 사례6선.
#   ★검증엔진 무수정·호출/분석만. 비용=RautoCEX 단일출처(현실=청산 스프1bp). 헤드라인=수익률(§19).
import os
import sys
import json
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
from path_finder import ensure_paths  # noqa: E402
ensure_paths()
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402
from fib_replay_1m import load_1m, load_funding  # noqa: E402
from REVoi_bot import REVoiBot  # noqa: E402
from rauto_cex import RautoCEX, SlipModel, FeeModel, MK, TK  # noqa: E402
from make_pine import build_pine  # noqa: E402
from make_cases import build_cases  # noqa: E402
import bt_full as B  # noqa: E402

OUT = os.path.join(ROOT, "00_WorkHstr", "BackTest_Output", "260626_01_REVoi_SW_Back2TV")
os.makedirs(OUT, exist_ok=True)
LEVS = list(range(1, 31)); SIZES = list(range(10, 101, 5))
try:
    fm.fontManager.addfont(r"C:\Windows\Fonts\malgun.ttf")
    plt.rcParams["font.family"] = fm.FontProperties(fname=r"C:\Windows\Fonts\malgun.ttf").get_name()
except Exception:
    pass
plt.rcParams["axes.unicode_minus"] = False


def _p(*a):
    print(*a, flush=True)
    with open(os.path.join(OUT, "260626_01_REVoi_SW_Back2TV_분석.txt"), "a", encoding="utf-8") as f:
        f.write(" ".join(str(x) for x in a) + "\n")


def sweep(T, mdd_cap=None):
    best = None
    for lev in LEVS:
        for sz in SIZES:
            r = RautoCEX(float(sz), float(lev), slip=SlipModel(0.0, 1.0)).run(T.copy())
            if mdd_cap is not None and r["mdd"] < mdd_cap:
                continue
            if best is None or r["tot"] > best["tot"]:
                best = dict(tot=r["tot"], mdd=r["mdd"], size=float(sz), lev=float(lev), final=r["final"], nliq=r["nliq"])
    return best


def _pass(T, size_pct, lev, realistic):
    """per-trade 복제 → ym별 누적. realistic=True(수수료+슬립1bp) / False(무비용 상한)."""
    fee = FeeModel() if realistic else FeeModel(mk=0.0, tk=0.0)
    slip = SlipModel(0.0, 1.0) if realistic else SlipModel(0.0, 0.0)
    cex = RautoCEX(size_pct, lev, fee=fee, slip=slip)
    R = T["R"].values.astype(float); MAE = T["mae"].values.astype(float); FUND = T["fund"].values.astype(float)
    REASON = T["reason"].values; SIDE = T["side"].values.astype(int); YM = T["_ym"].values
    FILLS = T["fills"].values if "fills" in T.columns else None
    NFILL = T["nfilled"].values if "nfilled" in T.columns else None
    bal = 10000.0; per = {}

    def acc():
        return dict(cnt=0, wins=0, gw=0.0, gl=0.0, profit=0.0)

    for i in range(len(R)):
        gR = cex._gross_R(R[i], FUND[i]); ec = cex.fee.entry_cost(cex.leg1_taker); xc = cex.fee.exit_cost(REASON[i])
        is_mkt = REASON[i] != "tp"; sl = cex.slip.market_exit_slip()
        R_net = gR - ec - xc - FUND[i] - (sl if is_mkt else 0.0)
        bal0 = bal; p, liq = cex.margin.step(bal, R_net, MAE[i], FUND[i]); bal *= (1.0 + p)
        notion = cex.margin.exp * bal0; delta = bal - bal0; ym = YM[i]
        d = per.setdefault(ym, dict(tot=acc(), long=acc(), short=acc(), maker=0.0, taker=0.0, slip=0.0, fund=0.0, lim=0, mkt=0))
        for key in ("tot", "long" if SIDE[i] == 1 else "short"):
            a = d[key]; a["cnt"] += 1
            if delta > 0:
                a["wins"] += 1; a["gw"] += delta
            else:
                a["gl"] += -delta
            a["profit"] += delta
        if not liq:
            d["maker"] += notion * (ec if not cex.leg1_taker else MK)
            d["taker"] += notion * (xc if is_mkt else 0.0)
            d["slip"] += notion * (sl if is_mkt else 0.0)
            d["fund"] += notion * FUND[i]
        nf = (len(FILLS[i]) if (FILLS is not None and isinstance(FILLS[i], list)) else (int(NFILL[i]) if NFILL is not None else 1))
        d["lim"] += nf; d["mkt"] += (1 if is_mkt else 0)
    return per, (bal / 10000.0 - 1.0) * 100.0


def monthly_28col(T, size_pct, lev):
    real, tot_real = _pass(T, size_pct, lev, True)
    gross, _ = _pass(T, size_pct, lev, False)

    def blk(a):
        wr = 100.0 * a["wins"] / a["cnt"] if a["cnt"] else 0.0
        pf = a["gw"] / a["gl"] if a["gl"] > 0 else float("inf") if a["gw"] > 0 else 0.0
        loss = a["cnt"] - a["wins"]
        payoff = (a["gw"] / a["wins"]) / (a["gl"] / loss) if (a["wins"] and loss and a["gl"] > 0) else 0.0
        return a["cnt"], round(wr, 0), round(pf, 2), round(payoff, 2), round(a["profit"], 0)

    rows = []; cum = 0.0; cum_l = 0.0; cum_s = 0.0
    for ym in sorted(real.keys()):
        d = real[ym]; g = gross.get(ym, {"tot": {"profit": 0.0}})
        tc, tw, tpf, tpo, tpr = blk(d["tot"]); lc, lw, lpf, lpo, lpr = blk(d["long"]); sc, sw, spf, spo, spr = blk(d["short"])
        cum += tpr; cum_l += lpr; cum_s += spr
        gprofit = round(g["tot"]["profit"], 0)
        tcost = round(gprofit - tpr, 0)
        rows.append([ym, tc, tw, tpf, tpo, tpr, round(cum, 0),
                     lc, lw, lpf, lpo, lpr, round(cum_l, 0),
                     sc, sw, spf, spo, spr, round(cum_s, 0),
                     d["lim"], round(d["maker"], 0), d["mkt"], round(d["taker"], 0),
                     round(d["slip"], 0), round(d["fund"], 0), gprofit, tcost, tpr])
    cols = ["년월", "총_거래수", "총_승률%", "총_PF", "총_손익비", "총_수익금$", "총_누적$",
            "롱_거래수", "롱_승률%", "롱_PF", "롱_손익비", "롱_수익금$", "롱_누적$",
            "숏_거래수", "숏_승률%", "숏_PF", "숏_손익비", "숏_수익금$", "숏_누적$",
            "지정가_체결수", "지정가_수수료$", "시장가_체결수", "시장가_수수료$",
            "슬리피지$", "펀딩비$", "손익금_무비용$", "총비용$", "순손익금_현실$"]
    return pd.DataFrame(rows, columns=cols), tot_real


def cases_generic(T, d1m, folder, base, tf_min):
    """SW용 범용 사례6선(REVoi 전용 build_cases 대체): 캔들+진입/청산 마커+R%. 영문/한글 병기."""
    T = T.sort_values("et").reset_index(drop=True); V = T.copy(); V["R%"] = V.R * 100
    seen = set(); cands = []
    def pick(nm, mask, asc):
        s = V[mask & (~V.index.isin(seen))].sort_values("R%", ascending=asc)
        if len(s):
            seen.add(s.index[0]); cands.append((nm, s.index[0]))
    pick("①큰수익 BIG WIN", V.R > 0, False); pick("②롱 수익 LONG WIN", (V.R > 0) & (V.side == 1), False)
    pick("③최대낙폭 LOSS", V.R < 0, True); pick("④숏 수익 SHORT WIN", (V.R > 0) & (V.side == -1), False)
    pick("⑤롱 손실 LONG LOSS", (V.R < 0) & (V.side == 1), True); pick("⑥숏 손실 SHORT LOSS", (V.R < 0) & (V.side == -1), True)
    for ix in list(V.sort_values("R%").index) + list(V.sort_values("R%", ascending=False).index):
        if len(cands) >= 6:
            break
        if ix not in seen:
            seen.add(ix); cands.append(("⑦보충 Extra", ix))
    cands = cands[:6]
    if len(cands) < 5:
        return None, None
    df = B.TS.resample_tf(d1m[["open", "high", "low", "close"]], tf_min)
    fig, axes = plt.subplots(3, 2, figsize=(17, 15)); axes = axes.flatten(); expl = []
    for ax, (nm, ix) in zip(axes, cands):
        r = T.loc[ix]; side = int(r.side); win = r.R > 0
        t0 = pd.Timestamp(r.et) - pd.Timedelta(minutes=tf_min * 8); t1 = pd.Timestamp(r.xt) + pd.Timedelta(minutes=tf_min * 5)
        g = df.loc[t0:t1]
        if len(g) < 3:
            continue
        w = (g.index[1] - g.index[0]) * 0.6 if len(g) > 1 else pd.Timedelta(hours=2)
        for t, rr in g.iterrows():
            col = "#26a69a" if rr.close >= rr.open else "#ef5350"
            ax.plot([t, t], [rr.low, rr.high], color=col, lw=0.8)
            lo, hi = min(rr.open, rr.close), max(rr.open, rr.close); ax.bar(t, hi - lo, bottom=lo, width=w, color=col)
        mk = "^" if side == 1 else "v"; ecol = "#1e88e5" if side == 1 else "#d81b60"
        ax.scatter([r.et], [r.entry], marker=mk, s=240, color=ecol, edgecolor="black", zorder=5, label="Entry 진입")
        ax.hlines(r.entry, r.et, r.xt, color=ecol, lw=1.4, label="Avg entry 평단")
        ax.scatter([r.xt], [r.exit], marker="X", s=240, color=("#1565c0" if win else "#c62828"), edgecolor="black", zorder=6, label="Exit 청산")
        sd = "Long 롱" if side == 1 else "Short 숏"; res = "WIN 수익" if win else "LOSS 손실"
        ax.set_title(f"{nm}\n#{ix} · {sd} · R={r.R*100:+.2f}% · {res}", fontsize=11, fontweight="bold")
        ax.set_ylabel("Price 가격 (USDT)", fontsize=9); ax.grid(alpha=0.25)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M")); ax.tick_params(labelsize=7.5)
        if ax is axes[0]:
            ax.legend(fontsize=7.5, loc="lower left")
        expl.append(f"[{nm}] #{ix} {sd} 진입 {pd.Timestamp(r.et):%Y-%m-%d %H:%M} @${r.entry:,.0f} → 청산 {pd.Timestamp(r.xt):%Y-%m-%d %H:%M} @${r.exit:,.0f} · R={r.R*100:+.2f}% ({res}) · 청산={r.reason}")
    fig.suptitle(f"{base} 거래 예시 6선 — Case Studies (영문/한글 병기) · ▲▼진입 · 선=평단 · X=청산", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    png = os.path.join(folder, f"{base}_사례6선_CaseStudies.png"); fig.savefig(png, dpi=130); plt.close(fig)
    txt = os.path.join(folder, f"{base}_사례6선_해설.txt")
    open(txt, "w", encoding="utf-8").write(f"{base} 거래 예시 6선 (TV가시범위·캡틴 TV대조용)\n" + "=" * 60 + "\n" + "\n".join(expl) + "\n")
    return png, txt


def do_bot(name, base, T, p_or_none, anchor, mddfree, mdd25, d1m, is_revoi):
    _p("\n" + "=" * 72); _p(f"[Back2TV 전량 — {name}]  거래 {len(T)}")
    T.to_csv(os.path.join(OUT, f"{base}_거래원장.csv"), index=False, encoding="utf-8-sig")
    for tag, st in (("②MDD해제", mddfree), ("③MDD-25", mdd25)):
        if not st:
            continue
        tbl, tot = monthly_28col(T, st["size"], st["lev"])
        tbl.to_csv(os.path.join(OUT, f"{base}_{tag}_월별통합표.csv"), index=False, encoding="utf-8-sig")
        _p(f"  [{tag}] 레버{st['lev']:.0f}/증거금{st['size']:.0f}% → 28열표 {len(tbl)}월 · 총수익 {tot:+,.1f}% (표합검증)")
        expo = st["size"] / 100.0 * st["lev"]
        try:
            nT, nF, mp, totn = build_pine(T, expo, out=os.path.join(OUT, f"{base}_{tag}.pine"), title=f"{name} {tag}")
            _p(f"    Pine v6 저장: {base}_{tag}.pine (임베드 {nT}/{totn}·체결점 {nF})")
        except Exception as e:
            _p(f"    Pine 실패: {e}")
    try:
        if is_revoi:
            png, txt, picks = build_cases(T, p_or_none, d1m, OUT, base)
        else:
            png, txt = cases_generic(T, d1m, OUT, base, tf_min=240)
        _p(f"  사례6선: {'OK ' + os.path.basename(png) if png else '생략(가시거래<5)'}")
    except Exception:
        _p("  사례6선 실패:\n" + traceback.format_exc())


def main():
    open(os.path.join(OUT, "260626_01_REVoi_SW_Back2TV_분석.txt"), "w", encoding="utf-8").close()
    d1m = load_1m(); fund = load_funding()

    p = json.load(open(os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    Tr = REVoiBot(p).make_trades(d1m, fund, capture_fills=True).sort_values("et").reset_index(drop=True)
    Tr["_ym"] = pd.to_datetime(Tr["et"]).dt.to_period("M").astype(str)
    do_bot("REVoi", "260626_01_REVoi", Tr, p, sweep(Tr), sweep(Tr), sweep(Tr, -25.0), d1m, True)

    SW_LED = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg10_OverlapCapSweep\causal_ledger.csv"
    sw = pd.read_csv(SW_LED)
    Ts = pd.DataFrame({"side": sw["side"].astype(int), "R": sw["R"].astype(float), "mae": sw["mae"].astype(float),
                       "fund": sw["fund"].astype(float), "reason": np.where(sw["reason"].astype(str).str.startswith("tp"), "tp", sw["reason"].astype(str)),
                       "et": pd.to_datetime(sw["entry_t"]), "xt": pd.to_datetime(sw["exit_t"]),
                       "entry": sw["entry_price"].astype(float), "exit": sw["exit_price"].astype(float),
                       "nfilled": sw["nfilled"], "fills": [None] * len(sw)})
    Ts["_ym"] = Ts["et"].dt.to_period("M").astype(str)
    do_bot("SW SidewayDCA", "260626_01_SW", Ts, None, sweep(Ts), sweep(Ts), sweep(Ts, -25.0), d1m, False)
    _p("\n[완료] Back2TV 전량(28열표·Pine v6·사례6선) REVoi·SW. 채택은 held-out·CPCV 표준6·MDD-20 별도 통과必.")


if __name__ == "__main__":
    main()
