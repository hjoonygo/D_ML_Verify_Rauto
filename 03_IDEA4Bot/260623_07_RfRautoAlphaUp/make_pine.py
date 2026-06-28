# -*- coding: utf-8 -*-
# [make_pine.py] 거래 DataFrame(gen_trades 결과, capture_fills=True) → TradingView Pine v5 문자열/파일.
#   build_pine(T, expo) = 재사용 함수(bt2pine.py가 호출). 전체거래 임베드 + 설정 '창 위치 슬라이드'로 81거래씩.
#   표시: 분할 개별 체결점=흰십자 · 수평선=진입평균가(롱청/숏분홍) · 선아래 {L/S}평단@수량 · 청산 흰십자 +파랑/-빨강.
#   ★Pine은 외부 파일로딩 불가 → 데이터 임베드. ★BINANCE:BTCUSDT.P(무기한)+시간대 UTC+4h 권장.
import os, sys, json
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "rauto_trades_tv.pine")
CAP = 10000.0; WIN = 80; MAXEMBED = 400   # ★Pine 한도: 스크립트크기(컴파일)·라벨500. 초과=최근분만 임베드(침묵금지)


def ms(t): return int(pd.Timestamp(t, tz="UTC").value // 10**6)


def build_pine(T, expo, out=OUT, win=WIN, cap=CAP, title="Rauto 백테 체결", max_embed=MAXEMBED):
    """거래 T(et,xt,side,entry,exit,R,fills) + 노출 expo → Pine 파일 저장. 반환 (임베드거래수, 체결점수, maxpos, 전체거래수)."""
    T = T.sort_values("et").reset_index(drop=True)
    total_n = len(T)
    if total_n > max_embed:                                # ★Pine 컴파일·라벨 한도 → 최근 max_embed개만(나머지 컷, 침묵금지)
        T = T.tail(max_embed).reset_index(drop=True)
    et = []; xt = []; aep = []; xp = []; sd = []; pn = []; qt = []; bp = []
    for r in T.itertuples():
        fills = r.fills if isinstance(r.fills, list) else [(r.et, r.entry)]
        bp.append(round(float(fills[0][1]), 2))   # ★진입신호가 = base체결(신호봉 종가) — 삼각형 위치
        et.append(ms(getattr(r, "et_fill", r.et))); xt.append(ms(getattr(r, "xt_fill", r.xt))); aep.append(round(float(r.entry), 2))
        xp.append(round(float(r.exit), 2)); sd.append(int(r.side)); pn.append(round(float(r.R) * 100, 2))
        qt.append(round((cap * expo) / float(r.entry), 3))

    def A(vals, f="{}"): return "array.from(" + ", ".join(f.format(v) for v in vals) + ")"
    maxpos = max(0, len(et) - win)
    N = len(et)
    cuttxt = f"임베드 최근{N}/전체{total_n}" if total_n > N else f"전체 {N}"
    pine = f'''//@version=6
indicator("{title} ({cuttxt}·창 {win})", overlay=true, max_lines_count=500, max_labels_count=500)
// ★마커 가격을 '그 차트의 실제 캔들 고저로 클램프' → 어느 TF든 항상 캔들에 박힘. BINANCE:BTCUSDT.P·UTC.
// ▲진입신호(롱)/▼(숏)=신호봉가 · 수평선=진입평균가 · 선아래 {{L/S}}평단@수량 · 청산✕ +파랑/-빨강. (체결 개별점은 크기축소로 생략)
pos = input.int({maxpos}, "▶ 창 위치 슬라이드 (0=가장과거 … {maxpos}=최신, {win}거래씩)", minval=0, maxval={maxpos})
win = input.int({win}, "한 창 거래수", minval=1, maxval=82)
et  = {A(et)}
xt  = {A(xt)}
aep = {A(aep, "{:.2f}")}
xp  = {A(xp, "{:.2f}")}
sd  = {A(sd)}
pn  = {A(pn, "{:.2f}")}
qt  = {A(qt, "{:.3f}")}
bp  = {A(bp, "{:.2f}")}
var array<float> cAep = array.new<float>({N}, na)   // 진입봉 캔들 클램프 평단(수평선 시작가)
var array<int>   cEt  = array.new<int>({N}, na)     // 진입봉 시각(수평선 시작 x)
cLong = color.rgb(59,130,246)
cShort = color.rgb(255,61,139)
cLoss = color.rgb(239,83,80)
tp = color.new(color.black, 100)
tfms = timeframe.in_seconds(timeframe.period) * 1000
lo = math.min(pos, array.size(et) - 1)
hi = math.min(pos + win - 1, array.size(et) - 1)
clamp(v) => math.max(low, math.min(high, v))
// ── 모든 마커를 '그 마커가 속한 봉의 time·고저클램프'로 → 십자·선 다 캔들에 박히고 서로 연결 ──
if hi >= lo and time + tfms > array.get(et, lo) and time <= array.get(xt, hi) + tfms
    for i = lo to hi
        col = array.get(sd,i) == 1 ? cLong : cShort
        e0 = array.get(et,i)
        if e0 >= time and e0 < time + tfms
            a = clamp(array.get(aep,i))
            array.set(cAep, i, a)
            array.set(cEt, i, time)
            sgp = clamp(array.get(bp,i))   // ★진입신호가 = base체결(신호봉 종가)
            stl = array.get(sd,i) == 1 ? label.style_triangleup : label.style_triangledown   // 롱=위▲ 숏=아래▼
            label.new(time, sgp, "", xloc=xloc.bar_time, style=stl, color=color.white, size=size.small)
            sl = array.get(sd,i) == 1 ? "L" : "S"
            label.new(time, a, sl + str.tostring(a, "#.0") + "@" + str.tostring(array.get(qt,i), "#.000"), xloc=xloc.bar_time, style=label.style_label_up, color=tp, textcolor=col, size=size.small)
        x0 = array.get(xt,i)
        if x0 >= time and x0 < time + tfms
            cx = clamp(array.get(xp,i))
            a = array.get(cAep,i)
            et0 = array.get(cEt,i)
            aa = na(a) ? cx : a
            sx = na(et0) ? time : et0
            line.new(sx, aa, time, aa, xloc=xloc.bar_time, color=col, width=1)
            line.new(time, aa, time, cx, xloc=xloc.bar_time, color=color.white, width=1, style=line.style_dashed)
            label.new(time, cx, "✕", xloc=xloc.bar_time, style=label.style_label_center, color=tp, textcolor=color.white, size=size.tiny)
            p = array.get(pn,i)
            pcol = p < 0 ? cLoss : cLong
            label.new(time, cx, (p > 0 ? "+" : "") + str.tostring(p, "#.##") + "%", xloc=xloc.bar_time, style=label.style_label_down, color=tp, textcolor=pcol, size=size.small)
'''
    open(out, "w", encoding="utf-8").write(pine)
    return len(et), len(bp), maxpos, total_n


def main():
    from fib_replay_1m import load_1m, load_funding
    import bt_full as B
    bp = json.load(open(os.path.join(HERE, "best_params_full.json")))
    d1m = load_1m(); fund = load_funding()
    T = B.gen_trades(d1m, fund, bp["sig_tf"], bp["pivot_tf"], bp["N"],
                     (bp["fib1"], bp["fib2"], bp["fib3"]), bp["init_atr_mult"],
                     er_gate=bp["er_gate"], capture_fills=True)
    expo = bp["size_pct"] / 100.0 * bp["lev"]
    nT, nF, mp, tot = build_pine(T, expo)
    print(f"[저장] {OUT} | 임베드 {nT}/전체 {tot}거래·체결점 {nF} · 창위치 0~{mp} 슬라이드")


if __name__ == "__main__":
    main()
