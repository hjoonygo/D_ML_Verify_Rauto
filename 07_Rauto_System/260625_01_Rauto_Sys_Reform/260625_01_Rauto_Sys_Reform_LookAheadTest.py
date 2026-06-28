# -*- coding: utf-8 -*-
# [260625_01_Rauto_Sys_Reform_LookAheadTest.py] ★안전장치3 — DataHub 미래참조차단 게이트 단위테스트 (세션 260625_01_Rauto_Sys_Reform).
#   검증: ⒜무손상(중앙 resample == 기존 TS.resample_tf) ⒝게이트가 '마감 전 봉'을 절대 안 줌(룩어헤드 0)
#         ⒞일부러 in-progress(미래) 봉을 노려도 차단 ⒟경계(마감 1분전=차단, 마감시각=공개).
import os, sys
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd
from fib_replay_1m import load_1m
import trendstack_signal_engine as TS
from rauto_datahub import DataHub
HERE = os.path.dirname(os.path.abspath(__file__))


def _p(*a):
    print(*a, flush=True)
    open(os.path.join(HERE, "260625_01_Rauto_Sys_Reform_LookAheadTest_run.log"), "a", encoding="utf-8").write(" ".join(str(x) for x in a)+"\n")


def main():
    d1m = load_1m()
    hub = DataHub(d1m)
    TF = 240   # 4h봉
    _p(f"[1m 단일출처] {len(d1m):,}행 · {d1m.index.min()} ~ {d1m.index.max()}")
    fails = 0

    # ⒜ 무손상: 중앙 resample(close_time 제외) == 기존 TS.resample_tf
    a = hub.resample(TF)[["open","high","low","close"]]
    b = TS.resample_tf(d1m, TF)
    same = a.equals(b)
    _p(f"\n[⒜ 무손상] DataHub.resample({TF}) == TS.resample_tf : {same}  (봉수 {len(a)})")
    fails += 0 if same else 1
    # close_time = 라벨 + TF분 확인
    chk = (hub.resample(TF)["close_time"] - hub.resample(TF).index == pd.Timedelta(minutes=TF)).all()
    _p(f"   close_time = 라벨 + {TF}분 : {chk}")
    fails += 0 if chk else 1

    # ⒝ 룩어헤드 0: 임의 now 1000개에서 반환봉의 close_time이 now 초과하면 위반
    rng = np.random.default_rng(7)
    idx = d1m.index
    nows = idx[rng.integers(TF, len(idx), size=1000)]
    viol = 0; leak_naive = 0
    for now in nows:
        g = hub.bars(TF, now)
        if len(g) and g["close_time"].max() > now: viol += 1            # 게이트 위반(있으면 안 됨)
        n = hub._naive_label_leq(TF, now)                               # 게이트 없는 잘못된 접근
        if len(n) and (n.index + pd.Timedelta(minutes=TF)).max() > now: leak_naive += 1
    _p(f"\n[⒝ 룩어헤드 0] now 1000개:")
    _p(f"   ★게이트 적용(DataHub.bars) 미래봉 누수 = {viol}건  → {'PASS(0건)' if viol==0 else 'FAIL'}")
    _p(f"   게이트 없는 라벨접근(잘못된 방식) 누수 = {leak_naive}건 ({100*leak_naive/1000:.0f}%)  ← 게이트가 막아준 양")
    fails += 0 if viol == 0 else 1

    # ⒞ 일부러 in-progress(미래) 봉을 노림: 한 4h봉 라벨 t0, now = t0+1분 (봉 진행 중)
    t0 = hub.resample(TF).index[500]                                    # 임의 4h봉 시작
    now_mid = t0 + pd.Timedelta(minutes=1)                              # 봉 시작 1분 후(아직 3h59m 남음)
    g_mid = hub.bars(TF, now_mid); n_mid = hub._naive_label_leq(TF, now_mid)
    in_g = (t0 in g_mid.index); in_n = (t0 in n_mid.index)
    future_min = TF - 1                                                 # 그 봉은 now보다 239분 미래까지 봄
    _p(f"\n[⒞ 미래봉 주입] 4h봉 {t0} 진행 중(now={now_mid}, 마감까지 {TF-1}분 남음):")
    _p(f"   게이트 없는 접근: 그 봉 포함={in_n} ← 미래 {future_min}분 데이터 누수(룩어헤드)")
    _p(f"   ★게이트 적용:     그 봉 포함={in_g}  → {'PASS(차단)' if not in_g else 'FAIL(누수)'}")
    fails += 0 if not in_g else 1

    # ⒟ 경계: 마감 1분전=차단, 마감시각=공개
    just_before = t0 + pd.Timedelta(minutes=TF-1); at_close = t0 + pd.Timedelta(minutes=TF)
    before_has = t0 in hub.bars(TF, just_before).index
    close_has = t0 in hub.bars(TF, at_close).index
    _p(f"\n[⒟ 경계] 봉 {t0}: 마감1분전({just_before}) 포함={before_has}(차단기대) · 마감시각({at_close}) 포함={close_has}(공개기대)")
    ok_b = (not before_has) and close_has
    _p(f"   → {'PASS' if ok_b else 'FAIL'}")
    fails += 0 if ok_b else 1

    _p("\n" + "="*60)
    _p(f"[안전장치3 판정] {'★ALL PASS — 미래참조차단 게이트 검증완료' if fails==0 else f'FAIL {fails}건 — 멈추고 원인규명'}")
    _p("[다음] DataHub를 봇 신호계산에 연결(latest_closed로 확정봉만) → ③신호/결정 분리")


if __name__ == "__main__":
    main()
