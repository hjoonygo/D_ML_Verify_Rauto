# -*- coding: utf-8 -*-
# [TradeProbe_0624] 6/24 롱 거래 정밀분석 — "차트선 익절로 보이는데 손절표시" 진위 (세션 260626_02_Rauto2_Sys).
#   캡틴 지시: 에러부터 잡고 진행. 디스플레이 버그 vs 실제 손실(조기청산 후 상승) vs 로직 버그 판별.
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
from path_finder import ensure_paths; ensure_paths()
import numpy as np, pandas as pd
import rauto_datafeed as DF
from fib_replay_1m import load_funding
from REVoi_bot import REVoiBot
from rauto_live import per_trade_pnl
from rauto_cex import SlipModel

cfg = json.load(open(os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")))
p = cfg["REV_MDD25_36mo"]["p"]
print("운영 워밍업 30일 빌드(라이브와 동일)...", flush=True)
d1m, fund, meta = DF.build_warmup(days=30, prefer_dauto=True)
print("  meta:", meta, flush=True)
bot = REVoiBot(p)
T = bot.make_trades(d1m, fund, capture_fills=True).sort_values("et").reset_index(drop=True)
pnl, fin, mdd, nl = per_trade_pnl(T, 75.0, 3.0, SlipModel(0.0, 0.0))
T["pnl"] = pnl

# 6/24~6/25 거래 추출
T["et_d"] = pd.to_datetime(T["et"])
sub = T[(T["et_d"] >= "2026-06-23 12:00") & (T["et_d"] <= "2026-06-25 23:59")]
print(f"\n=== 6/23~6/25 거래 {len(sub)}건 ===", flush=True)
o = d1m["open"].values; h = d1m["high"].values; l = d1m["low"].values; c = d1m["close"].values
idx = d1m.index
for r in sub.itertuples():
    et = pd.Timestamp(r.et); xt = pd.Timestamp(r.xt); xtf = pd.Timestamp(getattr(r, "xt_fill", r.xt))
    side = int(r.side); entry = float(r.entry); exitp = float(r.exit)
    ia = int(idx.searchsorted(et)); ix = int(idx.searchsorted(xtf))
    seg_h = h[ia:ix+1].max() if ix >= ia else np.nan
    seg_l = l[ia:ix+1].min() if ix >= ia else np.nan
    # 청산 후 12시간 가격
    after = c[ix:ix+720] if ix+1 < len(c) else np.array([])
    aft_max = after.max() if len(after) else np.nan
    aft_min = after.min() if len(after) else np.nan
    print(f"\n[거래] {'롱' if side==1 else '숏'} 진입 {et} @ {entry:.1f}", flush=True)
    print(f"       청산(봉) {xt} / 실체결 {xtf} @ {exitp:.1f} · reason={r.reason}", flush=True)
    print(f"       방향손익: exit-entry = {exitp-entry:+.1f} ({(exitp-entry)/entry*100*side:+.3f}% × side)", flush=True)
    print(f"       원장 R={r.R:+.4f} · 사이즈드 pnl={r.pnl:+.2f}%", flush=True)
    print(f"       보유창 1m: 최고 {seg_h:.1f} / 최저 {seg_l:.1f} (보유 {ix-ia}분)", flush=True)
    if side == 1:
        print(f"       → 롱: 진입후 최고 {seg_h:.1f}(={(seg_h-entry)/entry*100:+.2f}%) · 청산가 {exitp:.1f}는 {'진입위(이익)' if exitp>entry else '진입아래(손실)'}", flush=True)
    print(f"       청산後 12h: 최고 {aft_max:.1f} / 최저 {aft_min:.1f} (청산 뒤 가격이 올랐나)", flush=True)
print(f"\n전체 거래 {len(T)} · 복리 {(fin/10000-1)*100:+.2f}% · 승률 {sum(1 for x in pnl if x>0)/len(pnl)*100:.0f}%", flush=True)
