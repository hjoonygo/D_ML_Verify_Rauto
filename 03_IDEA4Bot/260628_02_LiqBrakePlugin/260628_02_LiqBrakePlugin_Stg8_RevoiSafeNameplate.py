# -*- coding: utf-8 -*-
# [260628_02_LiqBrakePlugin_Stg8_RevoiSafeNameplate.py]
# ★새 봇 RevoiSafe@ETF (노출3·lev15·증거금20%·COMBO) 등록값 산출 — cert_nameplate(260628_10) 1:1 모방.
#   = 예상 월복리(OOS×현실슬립) · OOS MDD · 레짐별 REG_MONTHLY · 36mo 검증 MDD(병기) + 무손상 앵커.
import os, sys, json
import numpy as np, pandas as pd
ROOT = r"D:\ML\RfRauto"
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
from path_finder import ensure_paths; ensure_paths()
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as B2
from veri_edge import VeriEdge
from rauto_live import per_trade_pnl
from rauto_cex import SlipModel

SZ, LEV = 20.0, 15      # ★노출3.0 = 증거금20% × lev15 (캡틴 확정 260628)
p = {**json.load(open(os.path.join(ROOT, r"03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"],
     "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0}
d1m, fund = load_1m(), load_funding()
led = B2.rev_trades(d1m, fund, p)

# 레짐 라벨(7일추세, cert_nameplate 동일)
m = pd.read_csv(os.path.join(ROOT, r"08_BTC_Data\derived\Merged_Data.csv"), usecols=["timestamp", "close"], parse_dates=["timestamp"])
m["timestamp"] = m["timestamp"].dt.tz_localize(None); c8 = m.set_index("timestamp")["close"].resample("8h").last().dropna()
ret7 = c8.pct_change(21); feat = pd.DataFrame({"r7": ret7}); feat.index = feat.index + pd.Timedelta("8h")
led2 = pd.merge_asof(led.sort_values("et").assign(et=pd.to_datetime(led["et"])), feat, left_on="et", right_index=True, direction="backward")
led2["regime"] = np.where(led2["r7"] > 0.05, "상승", np.where(led2["r7"] < -0.05, "하락", "횡보"))

print("=" * 70); print("RevoiSafe@ETF 등록 이름표 (노출3·lev15·증거금20%·COMBO)"); print("=" * 70)
anchor = VeriEdge(B2.rev_trades(d1m, fund, {**json.load(open(os.path.join(ROOT, r"03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]})).anchor_check(75, 3, 1851.6)
print(f"[무손상 앵커] {anchor['pass']} ({anchor['got_%']}%)")

ve = VeriEdge(led2)
np_ = ve.nameplate(name="RevoiSafe@ETF", size_pct=SZ, lev=LEV,
                   desc="역추세+눌림목진입+COMBO청산 · 안전사이징(강제청산0·조기익절·저레버)")
print("\n[인증 이름표]")
for k, v in np_.items():
    if k == "레짐별":
        print("  레짐별:")
        for rg, rv in v.items():
            print(f"    {rg}: 예상 월복리 {rv['예상_월복리%']}% · {rv['개월']}개월 · {rv['거래']}거래")
    else:
        print(f"  {k}: {v}")

# 36mo 검증 MDD(현실10bp) 병기
ledf = led2.copy()
_, balf, mddf, nlf = per_trade_pnl(ledf, SZ, LEV, SlipModel(0, 0, 10.0))
print(f"\n[36mo 검증(현실10bp)] 수익 {(balf/10000-1)*100:+,.0f}% / MDD {mddf:.1f}% / 강제청산 {nlf}  (in-sample 상한·참고)")

reg_monthly = {rg: np_["레짐별"][rg]["예상_월복리%"] for rg in np_.get("레짐별", {})}
print(f"\n[★Rauto2 REG_MONTHLY 엔트리] \"RevoiSafe@ETF\": {reg_monthly}")
print(f"[★BOT_REGISTRY] name=RevoiSafe@ETF · lev15/sz20 · tp0.7/early0.01/efrac1.0 · OOS_mdd={np_['OOS_MDD%']} · 예상월복리{np_['예상_월복리수익률%']}% · 강제청산{np_['강제청산']}")
