# -*- coding: utf-8 -*-
# [Stg10] REVoi@ETF 인증 이름표 — OOS×현실슬립×lev3 → 예상 월복리수익률 + 레짐별(7일추세 상승/하락/횡보).
import os, sys, json
import numpy as np, pandas as pd
ROOT = r"D:\ML\RfRauto"
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
from path_finder import ensure_paths; ensure_paths()
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as B2
from veri_edge import VeriEdge
OUT = os.path.join(ROOT, r"00_WorkHstr\BackTest_Output\260628_10_CertNameplate"); os.makedirs(OUT, exist_ok=True)
lines=[];
def log(s=""): print(s, flush=True); lines.append(str(s))
p = {**json.load(open(os.path.join(ROOT, r"03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"],
     "tp_frac":0.7, "early_tp_pct":0.01, "early_frac":1.0}
d1m, fund = load_1m(), load_funding()
led = B2.rev_trades(d1m, fund, p)

# 레짐 라벨(7일추세) — 8H봉 close 7일전 대비. 상승>+5%·하락<-5%·횡보 그외. (v1, 향후 디테일화)
m = pd.read_csv(os.path.join(ROOT, r"08_BTC_Data\derived\Merged_Data.csv"), usecols=["timestamp","close"], parse_dates=["timestamp"])
m["timestamp"]=m["timestamp"].dt.tz_localize(None); c8=m.set_index("timestamp")["close"].resample("8h").last().dropna()
ret7=c8.pct_change(21)  # 21*8h=7일
feat=pd.DataFrame({"r7":ret7}); feat.index=feat.index+pd.Timedelta("8h")
led2=pd.merge_asof(led.sort_values("et").assign(et=pd.to_datetime(led["et"])), feat, left_on="et", right_index=True, direction="backward")
T=0.05
led2["regime"]=np.where(led2["r7"]>T,"상승",np.where(led2["r7"]<-T,"하락","횡보"))

ve=VeriEdge(led2)
anchor=VeriEdge(B2.rev_trades(d1m,fund,{**json.load(open(os.path.join(ROOT, r"03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]})).anchor_check(75,3,1851.6)
log("="*64); log("REVoi@ETF 인증 이름표 (캡틴 채택 기준 2026-06-28)"); log("="*64)
log(f"[앵커] {anchor['pass']} ({anchor['got_%']}%)")
np_ = ve.nameplate(name="REVoi@ETF", size_pct=75, lev=3, desc="역추세+눌림목진입+COMBO청산(조기익절1%+구조익절)")
log("\n[인증 이름표]")
for k,v in np_.items():
    if k=="레짐별":
        log("  레짐별:")
        for rg,rv in v.items(): log(f"    {rg}: 예상 월복리 {rv['예상_월복리%']}% · {rv['개월']}개월 · {rv['거래']}거래")
    else: log(f"  {k}: {v}")
# Rauto2 REG_MONTHLY 형식(레짐별 월복리%) 출력
reg_monthly={rg: np_["레짐별"][rg]["예상_월복리%"] for rg in np_.get("레짐별",{})}
log(f"\n[Rauto2 REG_MONTHLY 엔트리] \"REVoi@ETF\": {reg_monthly}")
log(f"[Rauto2 BOT_REGISTRY 엔트리] name=REVoi@ETF · key=REV_MDD25_36mo · lev3/sz75 · tp_frac0.7/early_tp0.01/early_frac1.0 · mdd={np_['OOS_MDD%']} · 예상월복리{np_['예상_월복리수익률%']}%")
open(os.path.join(OUT,"260628_10_CertNameplate_analysis.txt"),"w",encoding="utf-8").write("\n".join(lines))
log("[OK]")
