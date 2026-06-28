# -*- coding: utf-8 -*-
# [260627_02_OBOICharacter_Stg11_ComboRegMonthly.py]
# COMBO 레짐별 월수익(REG_MONTHLY) 산출 — Rauto2 Bot리스트 '예상수익률'(상/하/횡)용.
#   ★산출법 검증: 기존 M20챔피언(R+P70 tp0.7·regime1.4·lev6/sz55) 산출 → 기존 REG_MONTHLY값(up4.5/down28.7/range10.5) 대조.
#   맞으면 COMBO(tp0.7+early_tp1.0%·lev5/sz75) 산출값 채택. 7일추세 레짐(rauto_live cur_regime 통일·룩어헤드0).
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

PJSON = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")
MMR, SLIP, COST = 0.004, 0.0005, 0.0008


def regime_label(d1m, et):
    """7일추세 레짐(rauto_live 통일): close 7일전 대비 >+3%=up / <-3%=down / else range. 룩어헤드0(et 시점)."""
    c = d1m["close"]
    try:
        now = c.asof(et); past = c.asof(et - pd.Timedelta(days=7))
        if past and past > 0:
            ch = (now / past - 1) * 100
            return "up" if ch > 3.0 else ("down" if ch < -3.0 else "range")
    except Exception:
        pass
    return "range"


def reg_monthly(T, d1m, lev, sz):
    """레짐별 월수익(%) = 레짐별 sized 거래 복리^(1/레짐개월)-1. 격리마진 강제청산 반영."""
    exp = sz / 100.0 * lev; hsd = 1.0 / lev - MMR - SLIP
    # 봉 레짐라벨(전체 4h) → 레짐별 개월
    g = d1m["close"].resample("240min", label="left", closed="left").last().dropna()
    labs = []
    gv = g.values; gi = g.index
    for i in range(len(gv)):
        j = gi.get_indexer([gi[i] - pd.Timedelta(days=7)], method="nearest")[0]
        ch = (gv[i] / gv[j] - 1) * 100 if gv[j] > 0 else 0
        labs.append("up" if ch > 3 else ("down" if ch < -3 else "range"))
    bars_per_month = 30 * 6  # 4h봉
    reg_months = {}
    for lab in ("up", "down", "range"):
        reg_months[lab] = max(0.5, labs.count(lab) / bars_per_month)
    # 거래별 레짐 + sized pnl
    comp = {"up": 1.0, "down": 1.0, "range": 1.0}
    for _, tr in T.iterrows():
        lab = regime_label(d1m, pd.Timestamp(tr["et"]))
        mae = float(tr["mae"]); R = float(tr["R"]); fund = float(tr.get("fund", 0.0))
        p = -exp * (hsd + COST + abs(fund)) if mae <= -hsd else R * exp
        comp[lab] *= (1.0 + p)
    out = {}
    for lab in ("up", "down", "range"):
        out[lab] = round((comp[lab] ** (1.0 / reg_months[lab]) - 1.0) * 100, 1)
    return out


def main():
    p = json.load(open(PJSON))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    # ① 검증: M20챔피언(R+P70 tp0.7·regime1.4·lev6/sz55) vs 기존 REG_MONTHLY(up4.5/down28.7/range10.5)
    T_champ = REVoiBot({**p, "tp_frac": 0.7, "regime_factor": 1.4}).make_trades(d1m, fund)
    rm_champ = reg_monthly(T_champ, d1m, 6.0, 55.0)
    print(f"[검증] M20챔피언 산출 {rm_champ} vs 기존 {{'up':4.5,'down':28.7,'range':10.5}}", flush=True)
    # ② COMBO(tp0.7 + early_tp1.0% · lev5/sz75 = M20)
    T_combo = REVoiBot({**p, "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0}).make_trades(d1m, fund)
    rm_combo = reg_monthly(T_combo, d1m, 5.0, 75.0)
    print(f"[COMBO] tp0.7+early1.0% lev5/sz75 레짐별 월수익 = {rm_combo}", flush=True)
    print(f"\n[REG_MONTHLY 추가용] \"COMBO청산(tp.7+조기익절1%)\": {json.dumps(rm_combo, ensure_ascii=False)}", flush=True)


if __name__ == "__main__":
    main()
