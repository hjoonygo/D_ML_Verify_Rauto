# [파일명] mock_feed.py
# 코드길이: 약 110줄 / 내부버전: mock_feed_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] Binance 접근이 막힌 환경에서 수집·아카이브 로직을 검증하기 위한 '합성 피드'.
#        @kline_1m·@forceOrder·@aggTrade·@depth WS 메시지(JSON 문자열)와 REST OI/롱숏 응답을 만든다.
#        호가는 정상 시퀀스(U/u/pu 연속)와 '갭'(pu 불일치) 시나리오를 모두 생성.
# [Lookahead] 해당 없음(테스트 데이터).
# ── 사용 파일 ── 없음(표준 라이브러리 json만)
# ── 함수 In/Out ──
#  wrap(stream,data)            In: 스트림명·data → Out: 결합스트림 JSON 문자열
#  kline/agg_trade/force_order(...)  → 각 WS 메시지 JSON
#  snapshot(luid,bids,asks)     → REST 스냅샷 dict
#  depth(E,T,U,u,pu,bids,asks)  → @depth WS 메시지 JSON
#  fake_oi(oi,ts)/fake_lsr(r,ts) → REST 응답 dict
#  build_sequence()             In: - → Out: (snapshot, [WS JSON ...], gap_event_index)
# ── 상수 ── SYM
# ─────────────────────────────────────────────────────────────────────────
import json

SYM = "BTCUSDT"
SYM_L = "btcusdt"


def wrap(stream, data):
    return json.dumps({"stream": stream, "data": data})


def kline(ts_open, ts_close, o, h, l, c, v, closed=True):
    return wrap(f"{SYM_L}@kline_1m", {"e": "kline", "E": ts_close, "s": SYM,
        "k": {"t": ts_open, "T": ts_close, "s": SYM, "i": "1m", "o": str(o), "h": str(h),
              "l": str(l), "c": str(c), "v": str(v), "x": closed}})


def agg_trade(ts, price, qty, is_buyer_maker=False):
    return wrap(f"{SYM_L}@aggTrade", {"e": "aggTrade", "E": ts, "s": SYM,
        "p": str(price), "q": str(qty), "T": ts, "m": is_buyer_maker})


def force_order(ts, side, qty, price, avg_price=None):
    return wrap(f"{SYM_L}@forceOrder", {"e": "forceOrder", "E": ts,
        "o": {"s": SYM, "S": side, "q": str(qty), "p": str(price),
              "ap": str(avg_price if avg_price is not None else price), "T": ts}})


def depth(E, T, U, u, pu, bids, asks):
    return wrap(f"{SYM_L}@depth", {"e": "depthUpdate", "E": E, "T": T, "s": SYM,
        "U": U, "u": u, "pu": pu,
        "b": [[str(p), str(q)] for p, q in bids], "a": [[str(p), str(q)] for p, q in asks]})


def snapshot(last_update_id, bids, asks):
    return {"lastUpdateId": last_update_id,
            "bids": [[str(p), str(q)] for p, q in bids],
            "asks": [[str(p), str(q)] for p, q in asks]}


def fake_oi(open_interest, ts):
    return {"symbol": SYM, "openInterest": str(open_interest), "time": ts}


def fake_lsr(ratio, ts, long_acc=0.6, short_acc=0.4):
    return {"symbol": SYM, "longShortRatio": str(ratio),
            "longAccount": str(long_acc), "shortAccount": str(short_acc), "timestamp": ts}


def build_sequence():
    """정상 시퀀스 + 갭 시나리오를 포함한 WS 메시지열 생성.
       반환: (snapshot_dict, [raw_json...], gap_index)"""
    base_t = 1_700_000_000_000
    snap = snapshot(1000, bids=[(50000, 1.0), (49990, 2.0)], asks=[(50010, 1.5), (50020, 2.5)])

    raws = []
    # 캔들 2개(1개 마감)
    raws.append(kline(base_t, base_t + 60000, 50000, 50100, 49900, 50050, 12.3, closed=True))
    raws.append(kline(base_t + 60000, base_t + 120000, 50050, 50200, 50000, 50150, 8.1, closed=False))
    # 틱 거래 2건
    raws.append(agg_trade(base_t + 1000, 50050, 0.5, is_buyer_maker=False))
    raws.append(agg_trade(base_t + 2000, 50040, 0.3, is_buyer_maker=True))
    # 청산 1건
    raws.append(force_order(base_t + 3000, "SELL", 1.2, 49980))
    # 호가 증분: 정상 연속 (U/u/pu)
    # 첫 이벤트: U<=1000<=u
    raws.append(depth(base_t + 1100, base_t + 1100, 999, 1002, 998, bids=[(50000, 1.2)], asks=[(50010, 0.0)]))   # 50010 제거
    raws.append(depth(base_t + 1200, base_t + 1200, 1003, 1005, 1002, bids=[(49990, 0.0)], asks=[(50015, 0.7)]))  # 49990 제거, 50015 추가
    gap_index = len(raws)
    # 갭: pu(1010) != 직전 u(1005)
    raws.append(depth(base_t + 1300, base_t + 1300, 1011, 1013, 1010, bids=[(49980, 3.0)], asks=[]))
    return snap, raws, gap_index
