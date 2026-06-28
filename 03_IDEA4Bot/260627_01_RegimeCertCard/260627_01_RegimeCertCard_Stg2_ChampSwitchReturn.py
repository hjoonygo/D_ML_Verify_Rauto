# -*- coding: utf-8 -*-
# [260627_01_RegimeCertCard_Stg2_ChampSwitchReturn] ★레짐 챔피언 로테이션 수익률 시뮬 (세션 260627_01_RegimeCertCard).
#   캡틴 질문: "장세판단해서 챔피언교체를 하면 수익률의 변화는? 단, 진입 포지션 즉시청산 없이 정상 매매종료 후 교체."
#   → M20 자격 5봇 풀 · 매 거래 경계에서만 교체(강제청산 없음) · 현실비용(§24 RautoCEX) · 선발기준 둘(검증 기대수익 vs 최근실현) 비교.
#   ★검증엔진 무수정 호출(§8·§15.1). 무손상 = 각 봇 standalone 현실수익률이 Stg1 인증카드와 동일.
#   ★경계: M20 자격 풀만 로테(레버 섞으면 MDD폭발, STATE:42). in-sample 천장(§20).
import os, sys, json
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
for _ in range(6):
    if os.path.isdir(os.path.join(ROOT, "08_BTC_Data")) and os.path.isdir(os.path.join(ROOT, "04_공용엔진코드")):
        break
    ROOT = os.path.dirname(ROOT)
RES = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp")
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, RES)
from path_finder import ensure_paths
ensure_paths()
import numpy as np
import pandas as pd
from fib_replay_1m import load_1m, load_funding
from REVoi_bot import REVoiBot
from rauto_cex import FeeModel, SlipModel, MMR_T1, MMR_T2, TIER, LIQ_SLIP, LIQ_COST, MK, TK

WINNERS = os.path.join(RES, "back2tv_rev_winners.json")
BASE = "260627_02_ChampSwitchReturn"
OUTDIR = os.path.join(ROOT, "00_WorkHstr", "BackTest_Output")
WH = os.path.join(ROOT, "00_WorkHstr")
INDEX = os.path.join(ROOT, "00_WorkHstr", "00WorkHstr_INDEX.txt")
RECENT_DAYS = 21    # 최근실현 선발 윈도(라이브 recent2w≈)

# ── M20 자격 5봇(mdd≥-22) — 같은 위험등급만 로테(레버 섞으면 MDD폭발, STATE:42) ──
POOL = [
    {"name": "M20챔피언",   "lev": 6.0, "sz": 55.0, "tp_frac": 0.7, "regime_factor": 1.4},
    {"name": "R+P70단순",  "lev": 6.0, "sz": 55.0, "tp_frac": 0.7},
    {"name": "M4b",       "lev": 6.0, "sz": 55.0, "tp_frac": 0.7, "dd_cut": [-0.08, 0.5]},
    {"name": "M5게이트",    "lev": 6.0, "sz": 55.0, "tp_frac": 0.7, "gate": True},
    {"name": "결합R+P80",  "lev": 6.0, "sz": 75.0, "tp_frac": 0.8, "gate": True, "dd_cut": [-0.08, 0.5]},
]


def _p(*a):
    print(*a, flush=True)


def alpha_key(b):
    return (float(b.get("tp_frac", 0.0)), float(b.get("regime_factor", 1.0)), bool(b.get("gate", False)))


def make_ledger(p, tp_frac, regime_factor, gate, d1m, fund):
    params = dict(p); params["tp_frac"] = tp_frac; params["regime_factor"] = regime_factor; params["gate"] = gate
    return REVoiBot(params).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)


def cost_real(T):
    """현실 비용(§24 RautoCEX: maker2+taker4+스프1bp+측정슬립~0+펀딩) per-trade Rnet."""
    R = T["R"].values.astype(float); F = T["fund"].values.astype(float)
    REA = T["reason"].values if "reason" in T else np.array(["fibstop"] * len(R))
    fee = FeeModel(); sl = SlipModel(0.0, 1.0).market_exit_slip()
    return np.array([R[i] + MK + TK + F[i] - fee.entry_cost(False) - fee.exit_cost(REA[i]) - F[i]
                     - (sl if REA[i] != "tp" else 0.0) for i in range(len(R))])


def sized_series(Rc, MAE, FUND, lev, sz, dd_cut=None):
    """standalone 격리마진 사이징 → per-trade p, 강제청산 mask, 전체수익%, MDD%."""
    exp0 = sz / 100.0 * lev; bal = 10000.0; peak = 10000.0; mdd = 0.0
    p = np.empty(len(Rc)); liq = np.zeros(len(Rc), dtype=bool)
    dthr, dscale = (dd_cut if dd_cut else (None, None))
    for i in range(len(Rc)):
        m = dscale if (dd_cut and (bal / peak - 1.0) <= dthr) else 1.0
        exp = exp0 * m; mmr = MMR_T2 if exp * bal > TIER else MMR_T1; hsd = 1.0 / lev - mmr - LIQ_SLIP
        if MAE[i] <= -hsd:
            pp = -exp * (hsd + LIQ_COST + abs(FUND[i])); liq[i] = True
        else:
            pp = Rc[i] * exp
        bal *= (1.0 + pp); peak = max(peak, bal); mdd = min(mdd, bal / peak - 1.0); p[i] = pp
    return p, liq, (bal / 1e4 - 1) * 100, mdd * 100


def curve_metrics(p_seq):
    """per-trade p 시퀀스 → 전체수익%·MDD%."""
    bal = 10000.0; peak = 10000.0; mdd = 0.0
    for x in p_seq:
        bal *= (1.0 + x); peak = max(peak, bal); mdd = min(mdd, bal / peak - 1.0)
    return (bal / 1e4 - 1) * 100, mdd * 100


def regime_series(d1m):
    """1m 인덱스별 7일추세 레짐(>+3 up/<-3 down/else range, 룩어헤드0). 반환 (mt_ms, reg_arr)."""
    c = d1m["close"].values; mt = (d1m.index.values.astype("int64") // 1_000_000).astype("int64")
    out = np.empty(len(c), dtype=object)
    for i in range(len(c)):
        ch = (c[i] / c[max(0, i - 10080)] - 1.0) * 100.0 if i > 0 else 0.0
        out[i] = "up" if ch > 3 else ("down" if ch < -3 else "range")
    return mt, out


def reg_at(mt, reg, ms):
    i = int(np.searchsorted(mt, ms, "right")) - 1
    return reg[max(0, i)] if len(reg) else "range"


def build_bots(d1m, fund, p):
    """풀 봇별 거래배열(et_ms,xt_ms,side,Rnet,mae,fund) + 메타(lev,exp0,dd_cut) + standalone p."""
    ledgers = {}
    for b in POOL:
        k = alpha_key(b)
        if k not in ledgers:
            ledgers[k] = make_ledger(p, k[0], k[1], k[2], d1m, fund)
    bots = {}
    for b in POOL:
        T = ledgers[alpha_key(b)]
        Rnet = cost_real(T); MAE = T["mae"].values.astype(float); FUND = T["fund"].values.astype(float)
        et = (pd.to_datetime(T["et"]).values.astype("int64") // 1_000_000).astype("int64")
        xt = (pd.to_datetime(T["xt"]).values.astype("int64") // 1_000_000).astype("int64")
        side = T["side"].astype(int).values
        pstd, liq, tot, mdd = sized_series(Rnet, MAE, FUND, b["lev"], b["sz"], b.get("dd_cut"))
        bots[b["name"]] = dict(et=et, xt=xt, side=side, Rnet=Rnet, mae=MAE, fund=FUND,
                               lev=b["lev"], exp0=b["sz"] / 100.0 * b["lev"], dd_cut=b.get("dd_cut"),
                               pstd=pstd, liq=liq, tot=tot, mdd=mdd, n=len(T))
    return bots


def apply_trade(bot, idx, bal, peak):
    """공유계좌 bal에서 bot의 idx거래 손익분율 p (격리마진·강제청산·dd컷=공유계좌DD 기준)."""
    exp = bot["exp0"]
    if bot["dd_cut"] and (bal / peak - 1.0) <= bot["dd_cut"][0]:
        exp *= bot["dd_cut"][1]
    lev = bot["lev"]; mmr = MMR_T2 if exp * bal > TIER else MMR_T1; hsd = 1.0 / lev - mmr - LIQ_SLIP
    mae = bot["mae"][idx]; fund = bot["fund"][idx]
    if mae <= -hsd:
        return -exp * (hsd + LIQ_COST + abs(fund)), True
    return bot["Rnet"][idx] * exp, False


def rotate(bots, mt, reg, rule, regmap_static):
    """순차 로테이션(≤1 포지션·플랫시점에만 교체·강제청산 없음).
       rule='static'=레짐별 검증 기대수익 1위(regmap_static) / 'recent'=최근RECENT_DAYS 실현 1위."""
    names = list(bots.keys())
    ptr = {n: 0 for n in names}                      # 봇별 다음 미사용 거래 인덱스
    bal = 10000.0; peak = 10000.0; mdd = 0.0
    now = min(bots[n]["et"][0] for n in names) - 1
    nliq = 0; nsw = 0; prev = None
    taken = []                                       # (et_ms, side, p)
    win_ms = RECENT_DAYS * 86400000
    guard = 0
    while True:
        guard += 1
        if guard > 100000:
            break
        cur_reg = reg_at(mt, reg, now)
        # 선발
        if rule == "static":
            champ = regmap_static[cur_reg]
        else:  # recent: 각 봇 standalone 최근창 실현 1위(과거만=룩어헤드0)
            best = None; bv = -9e9
            for n in names:
                et = bots[n]["et"]; ps = bots[n]["pstd"]
                m = (et >= now - win_ms) & (et < now)
                v = (np.prod(1.0 + ps[m]) - 1.0) if m.any() else -9e9
                if v > bv:
                    bv = v; best = n
            champ = best if best is not None else regmap_static[cur_reg]
        # champ의 now 이후 다음 거래
        et = bots[champ]["et"]; i = ptr[champ]
        while i < len(et) and et[i] < now:
            i += 1
        ptr[champ] = i
        if i >= len(et):
            # champ 소진 → 풀 전체에 now 이후 거래 남았나? 없으면 종료
            if all(ptr[n] >= len(bots[n]["et"]) or bots[n]["et"][ptr[n]] < now for n in names) and \
               all(not (bots[n]["et"][min(ptr[n], len(bots[n]["et"]) - 1)] >= now) for n in names):
                break
            # champ만 소진 → 다음 후보시각으로 now 전진(가장 이른 풀 거래)
            nxts = [bots[n]["et"][ptr[n]] for n in names if ptr[n] < len(bots[n]["et"]) and bots[n]["et"][ptr[n]] >= now]
            if not nxts:
                break
            now = min(nxts)
            continue
        # 거래 체결
        p, liq = apply_trade(bots[champ], i, bal, peak)
        if liq:
            nliq += 1
        bal *= (1.0 + p); peak = max(peak, bal); mdd = min(mdd, bal / peak - 1.0)
        taken.append((int(et[i]), int(bots[champ]["side"][i]), float(p)))
        ptr[champ] = i + 1
        now = int(bots[champ]["xt"][i])               # ★정상 매매종료 후에만 교체(강제청산 없음)
        if champ != prev:
            nsw += 1; prev = champ
    tot = (bal / 1e4 - 1) * 100
    return dict(tot=tot, mdd=mdd * 100, nliq=nliq, nsw=nsw, taken=taken, final=bal)


def parallel_equal(bots, mt):
    """병행 균등: 5 서브계좌 각 $2000 standalone → 합산 곡선(MDD·전체수익)."""
    names = list(bots.keys()); seed = 10000.0 / len(names)
    events = []   # (xt_ms, name, new_subbal)
    for n in names:
        bal = seed
        for i in range(bots[n]["n"]):
            bal *= (1.0 + bots[n]["pstd"][i])
            events.append((int(bots[n]["xt"][i]), n, bal))
    events.sort()
    subbal = {n: seed for n in names}
    peak = 10000.0; mdd = 0.0
    for t, n, nb in events:
        subbal[n] = nb; tot = sum(subbal.values())
        peak = max(peak, tot); mdd = min(mdd, tot / peak - 1.0)
    final = sum(subbal.values())
    nliq = sum(int(bots[n]["liq"].sum()) for n in names)
    return dict(tot=(final / 1e4 - 1) * 100, mdd=mdd * 100, nliq=nliq, final=final)


def quarterly(taken):
    """taken[(et_ms,side,p)] → 분기별 수익률% + 롱숏 거래수."""
    if not taken:
        return pd.DataFrame()
    df = pd.DataFrame(taken, columns=["et", "side", "p"])
    df["q"] = pd.to_datetime(df["et"], unit="ms").dt.to_period("Q").astype(str)
    rows = []
    for q, g in df.groupby("q"):
        rows.append(dict(분기=q, 수익률=round((np.prod(1 + g.p) - 1) * 100, 1), 거래=len(g),
                         롱=int((g.side == 1).sum()), 숏=int((g.side == -1).sum()),
                         승률=round(100 * (g.p > 0).mean(), 0)))
    return pd.DataFrame(rows)


def main():
    _p(f"[{BASE}] 레짐 챔피언 로테이션 수익률 — M20 5봇풀 · 현실비용 · 즉시청산없음(매 거래경계 교체)")
    p = json.load(open(WINNERS, encoding="utf-8"))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    bots = build_bots(d1m, fund, p)
    mt, reg = regime_series(d1m)

    # 무손상: 각 봇 standalone 현실수익률 = Stg1 인증카드 일치
    _p("\n[무손상 — 고정 각 봇 standalone 현실수익률 (Stg1 인증카드와 동일해야)]")
    EXP_CARD = {"M20챔피언": 7670, "R+P70단순": 8669, "M4b": 4151, "M5게이트": 3812, "결합R+P80": 4245}
    okall = True
    for n in bots:
        got = bots[n]["tot"]; exp = EXP_CARD.get(n, 0)
        ok = abs(got - exp) <= max(50, abs(exp) * 0.02); okall &= ok
        _p(f"  {'✅' if ok else '❌'} {n:<10} {got:>+9.0f}% (카드 {exp:+}%) · MDD {bots[n]['mdd']:.0f}% · 강제청산 {int(bots[n]['liq'].sum())}")
    if not okall:
        _p("❌ 무손상 실패 — 중단."); return False

    # 레짐별 검증 기대수익 1위(인증카드 현실 레짐수익률) = static 선발맵
    card = pd.read_csv(os.path.join(OUTDIR, "260627_01_RegimeCertCard", "260627_01_RegimeCertCard_인증카드.csv"))
    nmap = {"M20챔피언(R+P70)": "M20챔피언", "R+P70단순": "R+P70단순", "M4b(DD컷·M20최고)": "M4b",
            "M5게이트(음수월최소)": "M5게이트", "결합R+P80(방어수익)": "결합R+P80"}
    regmap = {}
    _p("\n[레짐별 검증 기대수익 1위 (인증카드 현실, M20풀)]")
    for rg, rgk in [("up", "상승"), ("down", "하락"), ("range", "횡보")]:
        sub = card[(card.비용 == "현실(스프1bp)") & (card.레짐 == rgk) & (card.봇.isin(nmap.keys()))]
        sub = sub.assign(short=sub.봇.map(nmap))
        best = sub.loc[sub.수익률.idxmax()]
        regmap[rg] = best.short
        _p(f"  {rgk}: {best.short} ({best.수익률:+.0f}%)  /  후보 " + ", ".join(f"{nmap[r.봇]}{r.수익률:+.0f}" for _, r in sub.iterrows()))

    # 시뮬
    rotA = rotate(bots, mt, reg, "static", regmap)
    rotB = rotate(bots, mt, reg, "recent", regmap)
    par = parallel_equal(bots, mt)
    best_fixed = max(bots, key=lambda n: bots[n]["tot"])

    # ── 보고 ──
    L = []
    L.append(f"[레짐 챔피언 로테이션 수익률] {BASE}")
    L.append("[조건] M20 자격 5봇풀 · 현실비용(§24 RautoCEX) · 매 거래경계에서만 교체(진입중 강제청산 없음) · 7일추세 레짐 · 36mo in-sample 천장(§20)")
    L.append(f"[레짐맵] 상승→{regmap['up']} · 하락→{regmap['down']} · 횡보→{regmap['range']} (검증 기대수익 1위·in-sample)")
    L.append("")
    L.append("[★수익률 헤드라인 §19 — 36개월 복리, $10k, 현실비용]")
    L.append(f"{'전략':<28}{'전체%':>12}{'MDD%':>8}{'강제청산':>8}{'전환수':>7}")
    L.append(f"{'고정 ' + best_fixed + '(최고단일)':<28}{bots[best_fixed]['tot']:>+11.0f}%{bots[best_fixed]['mdd']:>+7.0f}%{int(bots[best_fixed]['liq'].sum()):>8}{'-':>7}")
    for n in bots:
        if n != best_fixed:
            L.append(f"{'  고정 ' + n:<28}{bots[n]['tot']:>+11.0f}%{bots[n]['mdd']:>+7.0f}%{int(bots[n]['liq'].sum()):>8}{'-':>7}")
    L.append(f"{'병행 균등(5봇 1/5씩)':<28}{par['tot']:>+11.0f}%{par['mdd']:>+7.0f}%{par['nliq']:>8}{'-':>7}")
    L.append(f"{'★로테 A(검증 기대수익)':<28}{rotA['tot']:>+11.0f}%{rotA['mdd']:>+7.0f}%{rotA['nliq']:>8}{rotA['nsw']:>7}")
    L.append(f"{'★로테 B(최근실현 ' + str(RECENT_DAYS) + 'd)':<28}{rotB['tot']:>+11.0f}%{rotB['mdd']:>+7.0f}%{rotB['nliq']:>8}{rotB['nsw']:>7}")
    L.append("")
    # 분기별(로테 A)
    L.append("[분기별 수익률 — 로테 A(검증 기대수익), 현실비용]")
    qa = quarterly(rotA["taken"])
    L.append(qa.to_string(index=False) if len(qa) else "  (없음)")
    L.append("")
    # 판정
    diff_best = rotA["tot"] - bots[best_fixed]["tot"]
    diff_par = rotA["tot"] - par["tot"]
    L.append("[판정]")
    L.append(f"  · 로테A vs 최고단일({best_fixed}): {diff_best:+.0f}%p  · 로테A vs 병행: {diff_par:+.0f}%p")
    L.append(f"  · 선발기준 A(검증) {rotA['tot']:+.0f}% vs B(최근실현) {rotB['tot']:+.0f}% → " +
             ("검증 우위(최근실현=performance-chasing 손해)" if rotA['tot'] > rotB['tot'] else "최근실현 우위(예상밖, 재검토)"))
    L.append("  · ★경계: in-sample 레짐맵=과적합 상한(채택=held-out·CPCV 별도). 같은 위험등급(M20풀)만 로테=레버 섞으면 MDD폭발.")
    body = "\n".join(L)

    folder = os.path.join(OUTDIR, BASE); os.makedirs(folder, exist_ok=True)
    pd.DataFrame([
        dict(전략=f"고정_{best_fixed}", 전체=round(bots[best_fixed]['tot'], 1), MDD=round(bots[best_fixed]['mdd'], 1), 강제청산=int(bots[best_fixed]['liq'].sum()), 전환수="-"),
        *[dict(전략=f"고정_{n}", 전체=round(bots[n]['tot'], 1), MDD=round(bots[n]['mdd'], 1), 강제청산=int(bots[n]['liq'].sum()), 전환수="-") for n in bots if n != best_fixed],
        dict(전략="병행균등", 전체=round(par['tot'], 1), MDD=round(par['mdd'], 1), 강제청산=par['nliq'], 전환수="-"),
        dict(전략="로테A_검증", 전체=round(rotA['tot'], 1), MDD=round(rotA['mdd'], 1), 강제청산=rotA['nliq'], 전환수=rotA['nsw']),
        dict(전략="로테B_최근실현", 전체=round(rotB['tot'], 1), MDD=round(rotB['mdd'], 1), 강제청산=rotB['nliq'], 전환수=rotB['nsw']),
    ]).to_csv(os.path.join(folder, f"{BASE}_비교표.csv"), index=False, encoding="utf-8-sig")
    if len(qa):
        qa.to_csv(os.path.join(folder, f"{BASE}_로테A_분기별.csv"), index=False, encoding="utf-8-sig")
    open(os.path.join(folder, f"{BASE}_분석.txt"), "w", encoding="utf-8").write(body)
    ts = datetime.now().strftime("%Y%m%d%H%M")
    open(os.path.join(WH, f"{ts}_{BASE}.txt"), "w", encoding="utf-8").write(body)
    with open(INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|{BASE}|레짐 챔피언 로테이션(M20 5봇·즉시청산없음·현실): "
                f"로테A {rotA['tot']:+.0f}%/MDD{rotA['mdd']:.0f}% vs 최고단일 {bots[best_fixed]['tot']:+.0f}% vs 병행 {par['tot']:+.0f}%·무손상 PASS|src={BASE}.py\n")

    _draw(bots, best_fixed, par, rotA, rotB, regmap, os.path.join(folder, f"{BASE}_곡선.png"))
    _p("\n" + body)
    _p(f"\n[저장] {folder}\\  · 비교표.csv · 로테A_분기별.csv · 분석.txt · 곡선.png")
    return True


def _draw(bots, best_fixed, par, rotA, rotB, regmap, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams["font.family"] = "Malgun Gothic"; plt.rcParams["axes.unicode_minus"] = False
    except Exception as e:
        _p(f"  ⚠ 그래프 생략: {e}"); return
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 6))

    def eq(taken):
        t = sorted(taken); bal = 10000.0; xs = []; ys = []
        for et, sd, pp in t:
            bal *= (1 + pp); xs.append(pd.to_datetime(et, unit="ms")); ys.append(bal)
        return xs, ys
    xa, ya = eq(rotA["taken"]); xb, yb = eq(rotB["taken"])
    ax.plot(xa, ya, label=f"로테A 검증 Rotate-validated {rotA['tot']:+.0f}%", color="tab:green", lw=2)
    ax.plot(xb, yb, label=f"로테B 최근실현 Rotate-recent {rotB['tot']:+.0f}%", color="tab:orange", lw=1.5)
    # 최고단일 standalone 곡선
    n = best_fixed; bal = 10000.0; xs = []; ys = []
    order = np.argsort(bots[n]["et"])
    for i in order:
        bal *= (1 + bots[n]["pstd"][i]); xs.append(pd.to_datetime(int(bots[n]["et"][i]), unit="ms")); ys.append(bal)
    ax.plot(xs, ys, label=f"고정 최고단일 Fixed-best({n}) {bots[n]['tot']:+.0f}%", color="tab:blue", lw=1.5, ls="--")
    ax.set_yscale("log"); ax.set_ylabel("자본 Equity ($, log)"); ax.set_xlabel("시간 Time")
    ax.set_title(f"레짐 챔피언 로테이션 vs 고정 · 현실비용 36mo\nRegime champion rotation (M20 pool, no force-close)\n레짐맵 상승→{regmap['up']}/하락→{regmap['down']}/횡보→{regmap['range']}", fontsize=10)
    ax.legend(fontsize=9); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)
    _p(f"  그래프: {os.path.basename(path)}")


if __name__ == "__main__":
    main()
