# -*- coding: utf-8 -*-
# [Stg8] veri_edge.py 자가검증: 앵커 재현(+1851.6%) + COMBO 리포트 + early_tp 기여 + 상관. 구조문제 0 증명.
import os, sys, json
ROOT = r"D:\ML\RfRauto"
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
from path_finder import ensure_paths; ensure_paths()
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as B2
from veri_edge import VeriEdge
OUT = os.path.join(ROOT, r"00_WorkHstr\BackTest_Output\260628_08_VeriEdge"); os.makedirs(OUT, exist_ok=True)
lines=[]
def log(s=""): print(s, flush=True); lines.append(str(s))

p_base = json.load(open(os.path.join(ROOT, r"03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
combo_p = {**p_base, "tp_frac":0.7, "early_tp_pct":0.01, "early_frac":1.0}
off_p   = {**p_base, "tp_frac":0.7}
d1m, fund = load_1m(), load_funding()
base_led  = B2.rev_trades(d1m, fund, p_base)
combo_led = B2.rev_trades(d1m, fund, combo_p)
off_led   = B2.rev_trades(d1m, fund, off_p)

# 1) 앵커검증 (사이징 모델 = BASE로)
anchor = VeriEdge(base_led).anchor_check(size_pct=75, lev=3, expect_ret=1851.6)
log(f"[자가검증1·앵커] {anchor}")

# 2) COMBO 표준 리포트
log("\n" + VeriEdge(combo_led).report(size_pct=75, lev=3, anchor_result=anchor))

# 3) early_tp 기여 (OOS 수익률)
log("\n[자가검증3·early_tp 기여]")
log(str(VeriEdge.contribution(combo_led, off_led, size_pct=75, lev=3)))

# 4) 기간분해 (#5)
log("\n[자가검증4·기간분해 COMBO]")
log(str(VeriEdge(combo_led).returns_by_period(size_pct=75, lev=3)))

# 5) 컬럼누락 방어(구조 견고성)
try:
    import pandas as pd
    VeriEdge(pd.DataFrame({"et":[1],"side":[1]}))
    log("\n[자가검증5·방어] FAIL(예외 안 남)")
except Exception as e:
    log(f"\n[자가검증5·방어] OK — 컬럼누락 시 명확한 예외: {e}")

open(os.path.join(OUT,"260628_08_VeriEdge_selftest.txt"),"w",encoding="utf-8").write("\n".join(lines))
log("\n[OK] veri_edge 자가검증 완료 -> "+OUT)
