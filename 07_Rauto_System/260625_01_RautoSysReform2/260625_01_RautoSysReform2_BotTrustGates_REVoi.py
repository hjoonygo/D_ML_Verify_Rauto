# -*- coding: utf-8 -*-
# [260625_01_RautoSysReform2_BotTrustGates_REVoi.py] ★봇 신뢰 4관문 — REVoi 적용 (세션 260625_01_RautoSysReform2).
#   REVoi 봇을 bot_trust_gates에 끼워 ①앵커(기준+1851.6%) ②환각 ③CPCV ④현실비용을 자동검증.
#   = "봇 온보딩 표준"이 알려진 좋은 봇(REVoi)에서 제대로 작동하는지 실증(다음=TS·SW 같은 방식).
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
from path_finder import ensure_paths
ensure_paths()
from fib_replay_1m import load_1m, load_funding  # noqa: E402
from REVoi_bot import REVoiBot  # noqa: E402
from bot_trust_gates import run_gates  # noqa: E402

LOG = os.path.join(HERE, "260625_01_RautoSysReform2_BotTrustGates_REVoi_run.log")


def _p(*a):
    print(*a, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(" ".join(str(x) for x in a) + "\n")


def main():
    cfg = json.load(open(os.path.join(ensure_paths(), "03_IDEA4Bot", "260623_07_RfRautoAlphaUp",
                                       "back2tv_rev_winners.json")))
    p = cfg["REV_MDD25_36mo"]["p"]
    d1m = load_1m()
    fund = load_funding()

    bot = REVoiBot(p)
    res = run_gates(bot, d1m, fund, size_pct=75.0, lev=3.0, sig_tf=int(p["rev_tf"]),
                    ref_anchor=1851.6, log=_p)
    return res["verdict"]


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
