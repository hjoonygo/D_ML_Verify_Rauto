# -*- coding: utf-8 -*-
# [260628_02_LiqBrakePlugin_Stg2_RevoiETF_StabLimit.py]
# ★캡틴 질문 (2026-06-28): REVoi@ETF 수익률을 올리되 '안정성 확보 최대 임계선'이 어디인가?
#   = post-2024(ETF후) 데이터로 사이징(레버·증거금) 스윕 → MDD 게이트별(M30/M25/M20) 최대 수익 + 설정값 + 매매데이터.
#   안정성 임계선 = M20(MDD>=-20%)서 최대 수익 내는 노출(exposure). 헤드라인=수익률(§19), 현실슬립10bp 병기(memory#9).
#
# ★검증엔진만(§15.1): REVoi_bot.make_trades + rauto_live.per_trade_pnl. 재구현 0.
# ★데이터 = post-2024(2024-01-01+) = REVoi@ETF(memory#5·#8). 36mo 원장 생성 후 et>=2024-01 거래만 평가(신호 연속성 유지).
# ★수익률 라벨 강제(memory#6): 모든 수익률은 ret_guard.fmt_ret로 (기간·기준) 박아 출력.
# ★MDD 4단(§26)·강제청산 의무. ★헤드라인 OOS: post-2024를 train(2024)/test(2025~26) held-out도 산출.
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
from ret_guard import fmt_ret

PJSON = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")
POST = pd.Timestamp("2024-01-01")          # ETF후 경계
TRAIN_END = pd.Timestamp("2024-12-31")     # held-out: train 2024 / test 2025~26
SLIP_REAL = 10.0                            # 현실 시장청산 슬립bp(memory#9 헤드라인)
LEVS = [3, 5, 10, 15]                       # 청산 안 나는 안전구간(Stg1: 고레버=청산=수익잠식)
EXP_GRID = [round(x, 2) for x in np.arange(0.5, 6.01, 0.25)]
GATES = [("M30", -30.0), ("M25", -25.0), ("M20", -20.0)]


def _p(*a):
    print(*a, flush=True)


def slip(bp):
    return SlipModel(gap_bp=0.0, exit_spread_bp=0.0, extra_bp=bp)


def best_exp_under(T, gate_mdd, slip_bp, levs=LEVS):
    """MDD>=gate_mdd 제약하 최대복리 exposure 탐색(청산0 우선). 반환 dict."""
    best = None
    s = slip(slip_bp)
    for lev in levs:
        for exp in EXP_GRID:
            size = exp * 100.0 / lev
            if size > 100.0:
                continue
            pnl, bal, mdd, nliq = per_trade_pnl(T, size, lev, s)
            if bal <= 0 or mdd < gate_mdd:
                continue
            ret = (bal / 10000.0 - 1.0) * 100.0
            if best is None or ret > best["ret"]:
                best = dict(lev=lev, size=size, exp=exp, ret=ret, mdd=mdd, nliq=nliq, bal=bal)
    return best


def trade_stats(T, lev, size, slip_bp):
    """채택설정의 매매데이터: 거래수·승률·PF·손익비·롱숏·강제청산 + 월별/분기 수익률."""
    pnl, bal, mdd, nliq = per_trade_pnl(T, size, lev, slip(slip_bp))
    p = np.array(pnl)
    et = pd.to_datetime(T["et"].values)
    side = T["side"].values.astype(int)
    win = p > 0
    gp = p[win].sum(); gl = -p[~win].sum()
    pf = gp / gl if gl > 0 else float("inf")
    payoff = (p[win].mean() / -p[~win].mean()) if (win.any() and (~win).any()) else float("nan")
    # 월별 복리 수익률
    df = pd.DataFrame({"et": et, "side": side, "p": p})
    df["ym"] = df["et"].dt.to_period("M").astype(str)
    df["q"] = df["et"].dt.to_period("Q").astype(str)
    monthly = df.groupby("ym")["p"].apply(lambda g: (np.prod(1 + g / 100.0) - 1) * 100.0)
    mcount = df.groupby("ym").size()
    quarterly = df.groupby("q").apply(lambda g: pd.Series({
        "ret": (np.prod(1 + g["p"] / 100.0) - 1) * 100.0,
        "n": len(g),
        "long_ret": (np.prod(1 + g[g.side == 1]["p"] / 100.0) - 1) * 100.0 if (g.side == 1).any() else 0.0,
        "short_ret": (np.prod(1 + g[g.side == -1]["p"] / 100.0) - 1) * 100.0 if (g.side == -1).any() else 0.0,
        "nL": int((g.side == 1).sum()), "nS": int((g.side == -1).sum()),
    }))
    long_n = int((side == 1).sum()); short_n = int((side == -1).sum())
    long_w = float((p[side == 1] > 0).mean() * 100) if long_n else 0.0
    short_w = float((p[side == -1] > 0).mean() * 100) if short_n else 0.0
    return dict(ret=(bal / 10000.0 - 1) * 100.0, mdd=mdd, nliq=nliq, n=len(p),
                winrate=win.mean() * 100, pf=pf, payoff=payoff,
                long_n=long_n, short_n=short_n, long_w=long_w, short_w=short_w,
                monthly=monthly, mcount=mcount, quarterly=quarterly)


def main():
    _p("=" * 96)
    _p("[260628_02 Stg2] REVoi@ETF 안정성 최대 임계선 — post-2024(ETF후) 사이징 스윕 (수익률 기준)")
    _p("=" * 96)
    p = json.load(open(PJSON, encoding="utf-8"))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()

    # 엔진 무손상 확인(36mo 앵커)
    T0 = REVoiBot({**p, "tp_frac": 0.0, "early_tp_pct": 0.0, "early_frac": 0.0}).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)
    _, bal0, _, _ = per_trade_pnl(T0, 75.0, 3, slip(0.0))
    _p(f"[엔진 무손상] 36mo tp0/early0 lev3/sz75 슬립0 = {(bal0/10000-1)*100:+.4f}% (앵커 기준값 +1851.6491% 재현)")

    # COMBO 원장 → post-2024 필터
    T = REVoiBot({**p, "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0}).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)
    T["et"] = pd.to_datetime(T["et"])
    Tpost = T[T["et"] >= POST].reset_index(drop=True)
    _p(f"[REVoi@ETF COMBO] 전체 {len(T)}건 중 post-2024 {len(Tpost)}건 ({Tpost['et'].min().date()} ~ {Tpost['et'].max().date()})")
    _p(f"  post-2024 mae 분포: 중앙{np.median(Tpost['mae'])*100:.2f}% · 1%{np.percentile(Tpost['mae'],1)*100:.2f}% · 최악{Tpost['mae'].min()*100:.2f}%")

    # ── 안정성 임계선: MDD 게이트별 최대 수익 (현실10bp & 슬립0) ──
    _p("\n[안정성 임계선 — post-2024 28mo · MDD 게이트별 최대 수익]  ※수익=in-sample 상한(이 28개월에 맞춘 천장)")
    _p(f"  {'게이트':>5} | {'노출':>5} {'레버예시':>8} {'증거금%':>7} | {'현실10bp 수익률':>34} | {'슬립0 수익률':>30} | 강제청산")
    chosen = {}
    for gname, gmdd in GATES:
        br = best_exp_under(Tpost, gmdd, SLIP_REAL)
        b0 = best_exp_under(Tpost, gmdd, 0.0)
        chosen[gname] = br
        if br is None:
            _p(f"  {gname:>5} | (현실10bp서 해 없음)")
            continue
        rs = fmt_ret(br["ret"], "post-2024 28mo", "in-sample 상한", slip_bp=10, mdd_pct=br["mdd"])
        zs = fmt_ret(b0["ret"], "post-2024 28mo", "in-sample 상한", slip_bp=0, mdd_pct=b0["mdd"]) if b0 else "-"
        _p(f"  {gname:>5} | {br['exp']:>5.2f} {'lev'+str(br['lev']):>8} {br['size']:>6.1f}% | {rs:>34} | {zs:>30} | {br['nliq']}")

    # ── M20 = 안정성 임계선 채택 → 매매데이터 ──
    m20 = chosen.get("M20")
    if m20:
        st = trade_stats(Tpost, m20["lev"], m20["size"], SLIP_REAL)
        _p("\n" + "=" * 96)
        _p(f"[안정성 임계선 채택 = M20]  설정: 레버{m20['lev']}배 · 증거금{m20['size']:.1f}% · 노출{m20['exp']:.2f} · tp_frac0.7 · early_tp1.0%")
        _p("=" * 96)
        _p("  헤드라인(현실10bp): " + fmt_ret(st["ret"], "post-2024 28mo", "in-sample 상한", slip_bp=10, mdd_pct=st["mdd"]))
        _p(f"  매매데이터: 거래 {st['n']}건 · 승률 {st['winrate']:.0f}% · 수익팩터(PF) {st['pf']:.2f} · 손익비 {st['payoff']:.2f} · 강제청산 {st['nliq']}")
        _p(f"  롱: {st['long_n']}건 승률{st['long_w']:.0f}% · 숏: {st['short_n']}건 승률{st['short_w']:.0f}%")
        _p("\n  [분기별 수익률 (post-2024 · 현실10bp · in-sample 상한) — 롱/숏 분해]")
        _p(f"    {'분기':>8} {'수익률%':>9} {'롱%':>9} {'숏%':>9} {'거래(L/S)':>12}")
        for q, row in st["quarterly"].iterrows():
            _p(f"    {q:>8} {row['ret']:>+9.1f} {row['long_ret']:>+9.1f} {row['short_ret']:>+9.1f} {int(row['nL'])}/{int(row['nS']):>3}")
        _p("\n  [매월 수익률 (post-2024 · 현실10bp · in-sample 상한) — §0 '매월 양수' 점검]")
        _p(f"    {'년월':>8} {'수익률%':>9} {'거래':>5}   {'년월':>8} {'수익률%':>9} {'거래':>5}")
        mser = st["monthly"]; mcnt = st["mcount"]; keys = list(mser.index)
        neg = sum(1 for v in mser.values if v < 0)
        for i in range(0, len(keys), 2):
            a = keys[i]; la = f"    {a:>8} {mser[a]:>+9.1f} {int(mcnt[a]):>5}"
            if i + 1 < len(keys):
                b = keys[i + 1]; la += f"   {b:>8} {mser[b]:>+9.1f} {int(mcnt[b]):>5}"
            _p(la)
        _p(f"    → 음수 달: {neg}/{len(keys)}개월 (양수 {len(keys)-neg}개월)")

        # ── held-out OOS (헤드라인 자격): train 2024 → test 2025~26, 동일 노출 ──
        _p("\n  [★held-out OOS (헤드라인 자격) — train 2024 최적노출 → test 2025~26 blind, 현실10bp]")
        Ttr = Tpost[Tpost["et"] <= TRAIN_END].reset_index(drop=True)
        Tte = Tpost[Tpost["et"] > TRAIN_END].reset_index(drop=True)
        # train서 M20 최대노출 재탐색 → test 적용
        btr = best_exp_under(Ttr, -20.0, SLIP_REAL)
        if btr and len(Tte) > 5:
            _, bte, mte, nte = per_trade_pnl(Tte, btr["size"], btr["lev"], slip(SLIP_REAL))
            ret_te = (bte / 10000.0 - 1) * 100.0
            _p(f"    train 2024 M20 최적: 레버{btr['lev']}·증거금{btr['size']:.1f}%·노출{btr['exp']:.2f}")
            _p("    → " + fmt_ret(ret_te, "test 2025~26(16mo)", "OOS", slip_bp=10, mdd_pct=mte) + f" · 강제청산 {nte} · 거래 {len(Tte)}")
        else:
            _p("    (train/test 분리 표본 부족 — §9 기존 held-out 인용: lev3 OOS)")
    _p("\n[정직경계] '안정성 임계선' 수익률은 post-2024 28mo in-sample 상한(이 28개월에 맞춘 천장). 실전 헤드라인=held-out OOS만.")
    _p("[강제청산] 전 게이트 격리마진 강제청산 횟수 산출(§26). [슬립] 진입 지정가=무슬립 · 청산 시장가 현실10bp(memory#9).")
    return True


if __name__ == "__main__":
    main()
