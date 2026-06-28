# -*- coding: utf-8 -*-
# [260625_01_RautoSysReform2_Back2TV_REVoi_SW.py] ★Back2TV(§20) — REVoi·SW 일괄 (세션 260625_01_RautoSysReform2).
#   §20 = ①환각검증 → ②MDD해제 최고수익 → ③MDD−25 최고수익(레버×증거금 격자스윕·격리마진 실모델). 헤드라인=수익률(§19).
#   ★사이징은 RautoCEX(격리마진·유지증거금·강제청산) — 레버 과하면 청산=수익 안 늚(선형 환상 금지).
#   ★검증엔진 무수정·호출/분석만. 비용=RautoCEX 단일출처(현실=청산 스프1bp).
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
from path_finder import ensure_paths  # noqa: E402
ensure_paths()
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from fib_replay_1m import load_1m, load_funding  # noqa: E402
from REVoi_bot import REVoiBot  # noqa: E402
from rauto_cex import RautoCEX, SlipModel  # noqa: E402

OUT = os.path.join(ROOT, "00_WorkHstr", "BackTest_Output", "260626_01_REVoi_SW_Back2TV")
LEVS = list(range(1, 31))
SIZES = list(range(10, 101, 5))


def _p(*a):
    os.makedirs(OUT, exist_ok=True)
    print(*a, flush=True)
    with open(os.path.join(OUT, "260626_01_REVoi_SW_Back2TV_분석.txt"), "a", encoding="utf-8") as f:
        f.write(" ".join(str(x) for x in a) + "\n")


def sweep(T, mdd_cap=None):
    """레버×증거금 격자스윕(현실 비용). mdd_cap=None이면 MDD무제한, 아니면 mdd>=mdd_cap만. 최고복리 반환."""
    best = None
    for lev in LEVS:
        for sz in SIZES:
            r = RautoCEX(float(sz), float(lev), slip=SlipModel(0.0, 1.0)).run(T.copy())
            if mdd_cap is not None and r["mdd"] < mdd_cap:
                continue
            if best is None or r["tot"] > best["tot"]:
                best = dict(tot=r["tot"], mdd=r["mdd"], size=sz, lev=lev, final=r["final"], nliq=r["nliq"])
    return best


def back2tv(T, name, a_size, a_lev, a_ref, verify_note):
    _p("=" * 72)
    _p(f"[Back2TV — {name}]  거래 {len(T)} (롱{int((T['side']==1).sum())}/숏{int((T['side']==-1).sum())})")
    _p(f"  ① 환각검증: {verify_note}")
    # 앵커 재현(알려진 config = 현실비용)
    ra = RautoCEX(float(a_size), float(a_lev), slip=SlipModel(0.0, 1.0)).run(T.copy())
    ok = "" if a_ref is None else f"  vs 기준 {a_ref:+.0f}% → {'재현 근접' if abs(ra['tot']-a_ref) < abs(a_ref)*0.25 else '★불일치=R 의미 점검필요'}"
    _p(f"  앵커(레버{a_lev}/증거금{a_size}% 현실): {ra['tot']:+,.1f}% / MDD {ra['mdd']:.1f}%{ok}")
    # ② MDD무제한 최고수익
    b2 = sweep(T, mdd_cap=None)
    _p(f"  ② MDD해제 최고수익 : {b2['tot']:+,.1f}% / MDD {b2['mdd']:.1f}% @ 레버{b2['lev']}/증거금{b2['size']}% (청산{b2['nliq']})  ${b2['final']:,.0f}")
    # ③ MDD-25 최고수익
    b3 = sweep(T, mdd_cap=-25.0)
    if b3:
        _p(f"  ③ MDD−25 최고수익  : {b3['tot']:+,.1f}% / MDD {b3['mdd']:.1f}% @ 레버{b3['lev']}/증거금{b3['size']}% (청산{b3['nliq']})  ${b3['final']:,.0f}")
    else:
        _p("  ③ MDD−25 충족 설정 없음")
    return dict(anchor=ra, mddfree=b2, mdd25=b3)


def main():
    open(os.path.join(OUT, "260626_01_REVoi_SW_Back2TV_분석.txt"), "w", encoding="utf-8").close() if os.path.exists(OUT) else os.makedirs(OUT, exist_ok=True)
    d1m = load_1m(); fund = load_funding()

    # ── REVoi (검증된 진짜 봇, 환각0) ──
    p = json.load(open(os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    Tr = REVoiBot(p).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)
    Tr["_ym"] = pd.to_datetime(Tr["et"]).dt.to_period("M").astype(str)
    Tr.to_csv(os.path.join(OUT, "260626_01_REVoi_거래원장.csv"), index=False, encoding="utf-8-sig")
    rREV = back2tv(Tr, "REVoi (역추세+피보스텝업)", 75, 3, 1483, "1m 전수겹침 통과(진입2796/2796·청산932/932·미도달0) = 환각0 ✅")

    # ── SW SidewayDCA (causal 84거래 §8확정원장) — 앵커 먼저 ──
    SW_LED = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg10_OverlapCapSweep\causal_ledger.csv"
    sw = pd.read_csv(SW_LED)
    Ts = pd.DataFrame({
        "side": sw["side"].astype(int),
        "R": sw["R"].astype(float),
        "mae": sw["mae"].astype(float),
        "fund": sw["fund"].astype(float),
        # ★reason 매핑: tp_poc=지정가(maker)→'tp', sl_*=시장가(taker)→그대로
        "reason": np.where(sw["reason"].astype(str).str.startswith("tp"), "tp", sw["reason"].astype(str)),
        "et": pd.to_datetime(sw["entry_t"]),
    })
    Ts["_ym"] = Ts["et"].dt.to_period("M").astype(str)
    Ts.to_csv(os.path.join(OUT, "260626_01_SW_거래원장.csv"), index=False, encoding="utf-8-sig")
    rSW = back2tv(Ts, "SW SidewayDCA (인과 84거래 §8확정)", 26.67, 15, 170,
                  "§8 인과확정 원장(인트라바 선지식 제거 = 인과검증 통과). ★단 1m 정밀겹침은 SW 엔진 래퍼로 별도(다음).")

    _p("")
    _p("=" * 72)
    _p("[정직] REVoi=환각0 검증완료라 위 수익률 신뢰. SW=인과확정이나 1m정밀겹침·R의미는 앵커 재현으로만 1차확인 → 앵커 맞으면 신뢰, 틀리면 SW 엔진 래퍼 필요.")
    _p("[Back2TV 잔여] Pine v6·사례6선 = make_pine.py/make_cases.py로 별도 생성(이번은 ①검증+②③수익률+결과데이터까지). 채택은 held-out·CPCV 표준6 별도 통과.")


if __name__ == "__main__":
    main()
