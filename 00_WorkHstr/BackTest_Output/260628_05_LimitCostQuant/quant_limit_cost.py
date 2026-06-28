# -*- coding: utf-8 -*-
# [Stg5] 실제 COMBO 원장으로 '지정가/시장가 청산' 비용 정량화 (post-2024).
#   목적: 청산 사유(reason) 분포 → 메이커(지정가) 가능 청산 vs 테이커(시장가=손절) 비율 → 현재 비용 vs 절감여지.
#   검증엔진 무수정 호출(back2tv_REVoi.rev_trades). 수수료=리서치 확정: maker 2bp/taker 5bp(VIP0), 스프1bp.
import os, sys, json
import numpy as np, pandas as pd
ROOT = r"D:\ML\RfRauto"
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
from path_finder import ensure_paths; ensure_paths()
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as B2

OUT = os.path.join(ROOT, r"00_WorkHstr\BackTest_Output\260628_05_LimitCostQuant"); os.makedirs(OUT, exist_ok=True)
PJSON = os.path.join(ROOT, r"03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json")
START = pd.Timestamp("2024-01-01")
MK, TK, SPRD = 0.0002, 0.0005, 0.0001   # ★리서치 확정: VIP0 maker 2bp / taker 5bp (프로젝트 기존 4bp는 BNB할인 가정)
lines=[]
def log(s=""): print(s, flush=True); lines.append(str(s))

p_base = json.load(open(PJSON))["REV_MDD25_36mo"]["p"]
combo_p = {**p_base, "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0}
log("="*78); log("COMBO 청산비용 정량화 — 지정가(메이커) 가능분 vs 시장가(테이커=손절)  [post-2024]"); log("="*78)
d1m = load_1m(); fund = load_funding()
T = B2.rev_trades(d1m, fund, combo_p)
Tp = T[pd.to_datetime(T["et"]) >= START].copy()
log(f"COMBO 거래: 전체 {len(T)} · post-2024 {len(Tp)}")
log(f"\n[청산 사유(reason) 분포 — post-2024]")
log(Tp["reason"].value_counts().to_string())

# 분류: 메이커 가능(익절·구조부분익절=지정가로 가격이 와서 체결) vs 테이커(손절/스톱=시장가 즉시)
def leg_kind(r):
    s = str(r).lower()
    if "stop" in s or "fib" in s or "sl" in s:   # fibstop/stop = 손절성 = 시장가 테이커
        return "taker(시장가/손절)"
    return "maker(지정가/익절)"                    # early_tp/tp/target = 익절성 = 지정가 메이커
Tp["xkind"] = Tp["reason"].map(leg_kind)
log(f"\n[청산 유형 분류]")
log(Tp["xkind"].value_counts().to_string())
maker_x = (Tp["xkind"].str.startswith("maker")).mean()*100
log(f"  → 청산의 {maker_x:.0f}%는 지정가(메이커) 가능, 나머지 {100-maker_x:.0f}%는 손절=시장가(테이커) 불가피")

# 비용 시나리오(왕복, bp): 진입은 항상 메이커(되돌림 지정가). 청산만 비교.
n = len(Tp)
n_maker_x = int((Tp["xkind"].str.startswith("maker")).sum()); n_taker_x = n - n_maker_x
def rt_cost_bp(exit_all_taker=False, exit_all_maker=False):
    # 진입 maker 2bp + 스프 일부. 청산: 분류대로(현실) 또는 가정.
    entry = MK
    cost = 0.0
    for k in Tp["xkind"]:
        if exit_all_taker: x = TK + SPRD
        elif exit_all_maker: x = MK
        else: x = (MK if k.startswith("maker") else TK + SPRD)
        cost += entry + x
    return cost/n*1e4   # 평균 왕복 bp
log(f"\n[평균 왕복 거래비용(bp) — 진입 메이커2bp 고정, 청산만 비교]")
log(f"  ⒜ 현실(분류대로: 익절=메이커·손절=테이커)     = {rt_cost_bp():.2f} bp")
log(f"  ⒝ 만약 청산 전부 테이커(시장가)            = {rt_cost_bp(exit_all_taker=True):.2f} bp")
log(f"  ⒞ 만약 청산 전부 메이커(불가능·갭리스크)    = {rt_cost_bp(exit_all_maker=True):.2f} bp")
save_now = rt_cost_bp(exit_all_taker=True) - rt_cost_bp()
log(f"  → 이미 익절을 지정가로 돌려 절감중 = {save_now:.2f} bp/왕복 (⒝−⒜)")
log(f"  → 손절을 지정가로 더 돌리면 추가 = {rt_cost_bp()-rt_cost_bp(exit_all_maker=True):.2f} bp/왕복 (불가능·실행시 갭관통=무방비)")

# 손익 대비 비용 비중(post-2024 무사이징 R 기준)
mean_abs_R = np.abs(Tp["R"].values).mean()*1e4
log(f"\n[비용 vs 손익 규모] 거래당 |R| 평균 = {mean_abs_R:.0f} bp · 현실 왕복비용 = {rt_cost_bp():.1f} bp")
log(f"  → 비용은 거래 손익규모의 {rt_cost_bp()/mean_abs_R*100:.1f}% (3bp 수수료차는 손익을 좌우 못함)")
open(os.path.join(OUT,"260628_05_LimitCostQuant_analysis.txt"),"w",encoding="utf-8").write("\n".join(lines))
log(f"\n[OK] -> {OUT}")
