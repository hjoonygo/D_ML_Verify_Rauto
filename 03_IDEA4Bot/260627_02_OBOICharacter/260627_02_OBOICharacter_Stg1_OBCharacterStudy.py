# -*- coding: utf-8 -*-
# [260627_02_OBOICharacter_Stg1_OBCharacterStudy.py]
# OB Character 검증 1단계 — OB(ICT 오더블록) 기계추출 + ★기저 Bounce 성공률.
#   목적: "OB 재방문 시 Bounce 성공률이 50% 동전던지기인가"부터 정직 확인.
#         (선행연구 경계 = 청산맵 자석 51~53% 약함. 여기 안 넘으면 OI/CVD 얹기 전에 멈춘다.)
#   ★검증엔진 무수정 호출(§8·§15.1): TS.resample_tf · TS.pivots_lr · TS.compute_atr.
#   ★룩어헤드0: ① pivots_lr 우측1 확정(c+right) ② OB는 BOS 확정봉(i)에서만 라벨
#               ③ 재방문·Bounce 판정은 i+1봉부터(미래 안 봄) ④ 같은봉 stop·target 동시=stop 우선(낙관금지).
#   1단계는 OB-TF 봉 해상도(빠른 기저확인). 1m 정밀체결·OI/CVD feature·CPCV·사이징백테는 2단계.
import os, sys
import numpy as np, pandas as pd


def find_root():
    """self-locating(§1): 스크립트 위치에서 상위로 올라가며 RfRauto 루트(08_BTC_Data+04_공용엔진코드) 탐색."""
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(7):
        if os.path.isdir(os.path.join(d, "08_BTC_Data")) and os.path.isdir(os.path.join(d, "04_공용엔진코드")):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return r"D:\ML\RfRauto"


ROOT = find_root()
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
import trendstack_signal_engine as TS   # 검증엔진(무수정 호출)

DATA = os.path.join(ROOT, "08_BTC_Data", "derived", "Merged_Data.csv")
OUTDIR = os.path.join(ROOT, "00_WorkHstr", "BackTest_Output",
                      "260627_02_OBOICharacter_Stg1_OBCharacterStudy")

# ── 파라미터(상단 모음, 조정 쉽게) ──────────────────────────────
N_SWING = 5            # swing 좌봉수(우1 확정). bt_full best N=5 참조
OB_TFS = [240, 60]     # OB 정의 TF: 4h, 1h
ATR_PD = 14
MAX_OB_LOOKBACK = 10   # BOS봉서 OB(마지막 반대색봉) 거꾸로 탐색 최대
X_ATR = 1.0            # Bounce 성공 목표 = OB방향 +X*ATR
Y_ATR = 0.5            # 관통 실패 = OB반대 -Y*ATR
MAX_WAIT_REVISIT = 60  # OB 확정 후 재방문 대기(OB-TF 봉)
MAX_HOLD_AFTER = 30    # 재방문 후 Bounce 판정 윈도우(OB-TF 봉)
MAGNET_LO, MAGNET_HI = 51.0, 53.0   # 선행연구 청산맵 자석(약함 경계)


def load_data():
    cols = ["timestamp", "open", "high", "low", "close", "volume",
            "taker_buy_volume", "oi_sum", "oi_change_1h_pct", "oi_zscore_24h"]
    df = pd.read_csv(DATA, usecols=cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.set_index("timestamp").sort_index()


def extract_obs(g, atr):
    """OB-TF 리샘플 g에서 ICT OB 추출. 반환 OB dict 리스트(룩어헤드0).
       Bullish OB = 직전 확정 swing high 종가돌파(BOS) 만든 임펄스 직전 '마지막 음봉'.
       Bearish OB = 직전 확정 swing low 종가돌파 만든 임펄스 직전 '마지막 양봉'."""
    H = g["high"].values; L = g["low"].values; C = g["close"].values; O = g["open"].values
    idx = g.index; n = len(C)
    ph, pl = TS.pivots_lr(H, L, N_SWING, 1)        # key=확정인덱스(c+1), val=(c, price)
    ph_at = {k: v[1] for k, v in ph.items()}       # 확정봉 k에서 비로소 알게된 swing high price
    pl_at = {k: v[1] for k, v in pl.items()}
    obs = []
    last_ph = last_pl = np.nan
    for i in range(n):
        if i in ph_at: last_ph = ph_at[i]          # i까지 확정된 swing만 반영(룩어헤드0)
        if i in pl_at: last_pl = pl_at[i]
        # Bullish BOS
        if not np.isnan(last_ph) and C[i] > last_ph:
            j = i
            while j >= max(0, i - MAX_OB_LOOKBACK) and not (C[j] < O[j]):
                j -= 1
            if j >= max(0, i - MAX_OB_LOOKBACK) and C[j] < O[j]:
                obs.append(dict(conf_i=i, conf_time=idx[i], side=1,
                                ob_lo=float(L[j]), ob_hi=float(H[j]),
                                atr=float(atr[i]), bos_size=float(C[i] - last_ph)))
            last_ph = np.nan                        # swing 소비(중복 BOS 방지)
        # Bearish BOS
        if not np.isnan(last_pl) and C[i] < last_pl:
            j = i
            while j >= max(0, i - MAX_OB_LOOKBACK) and not (C[j] > O[j]):
                j -= 1
            if j >= max(0, i - MAX_OB_LOOKBACK) and C[j] > O[j]:
                obs.append(dict(conf_i=i, conf_time=idx[i], side=-1,
                                ob_lo=float(L[j]), ob_hi=float(H[j]),
                                atr=float(atr[i]), bos_size=float(last_pl - C[i])))
            last_pl = np.nan
    return obs, idx, H, L, C


def eval_ob(ob, idx, H, L, C, x_atr=X_ATR, y_atr=Y_ATR, entry_at_edge=False):
    """재방문 + Bounce 판정(룩어헤드0: i+1봉부터). outcome 1=성공/-1=실패(관통)/0=미결.
       entry_at_edge=True면 진입가=OB경계(되돌림 limit체결) 기준 대칭 RR → Random과 동일기하 공정비교."""
    i = ob["conf_i"]; side = ob["side"]; lo = ob["ob_lo"]; hi = ob["ob_hi"]; atr = ob["atr"]
    n = len(C)
    if not (atr > 0):
        return None
    rev_j = None
    for j in range(i + 1, min(i + 1 + MAX_WAIT_REVISIT, n)):     # 재방문 = OB zone 터치 첫 봉
        if H[j] >= lo and L[j] <= hi:
            rev_j = j; break
    if rev_j is None:
        return None
    if entry_at_edge:
        entry = hi if side == 1 else lo                          # OB 경계 limit 체결(되돌림 진입가)
        target = entry + x_atr * atr if side == 1 else entry - x_atr * atr
        stop = entry - y_atr * atr if side == 1 else entry + y_atr * atr
    else:
        target = hi + x_atr * atr if side == 1 else lo - x_atr * atr
        stop = lo - y_atr * atr if side == 1 else hi + y_atr * atr
    outcome = 0
    for j in range(rev_j, min(rev_j + MAX_HOLD_AFTER, n)):
        if side == 1:
            hit_stop = L[j] <= stop; hit_tgt = H[j] >= target
        else:
            hit_stop = H[j] >= stop; hit_tgt = L[j] <= target
        if hit_stop:                                # 같은봉 동시면 stop 우선(낙관금지)
            outcome = -1; break
        if hit_tgt:
            outcome = 1; break
    r = dict(ob); r.update(rev_time=idx[rev_j], rev_j=rev_j, outcome=outcome)
    return r


def baseline_random(g, atr, x_atr, y_atr, step=1):
    """★대조군: OB 무관하게 매 봉 close서 long·short 진입 → 같은 X/Y/윈도우 성공률.
       OB 성공률이 이 baseline을 넘어야 'OB 추가효과'. BTC 상승장 bias도 여기 드러난다(룩어헤드0)."""
    H = g["high"].values; L = g["low"].values; C = g["close"].values
    n = len(C); res = {1: [0, 0, 0], -1: [0, 0, 0]}
    for i in range(0, n - 1, step):
        if not (atr[i] > 0):
            continue
        px = C[i]
        for side in (1, -1):
            target = px + x_atr * atr[i] if side == 1 else px - x_atr * atr[i]
            stop = px - y_atr * atr[i] if side == 1 else px + y_atr * atr[i]
            oc = 0
            for j in range(i + 1, min(i + 1 + MAX_HOLD_AFTER, n)):
                hs = (L[j] <= stop) if side == 1 else (H[j] >= stop)
                ht = (H[j] >= target) if side == 1 else (L[j] <= target)
                if hs:
                    oc = -1; break
                if ht:
                    oc = 1; break
            res[side][0 if oc == 1 else (1 if oc == -1 else 2)] += 1
    return res


def _wr(triplet):
    w, l, _ = triplet
    return 100.0 * w / (w + l) if (w + l) else float("nan")


def summarize(evals, tf):
    """기저 성공률 집계(전체/롱/숏). 결판=성공+실패(미결 제외)."""
    def rate(rows):
        win = sum(1 for e in rows if e["outcome"] == 1)
        lose = sum(1 for e in rows if e["outcome"] == -1)
        und = sum(1 for e in rows if e["outcome"] == 0)
        dec = win + lose
        return win, lose, und, (100.0 * win / dec if dec else float("nan"))
    longs = [e for e in evals if e["side"] == 1]
    shorts = [e for e in evals if e["side"] == -1]
    out = {"tf": tf, "n_revisited": len(evals)}
    for nm, rows in [("ALL", evals), ("LONG", longs), ("SHORT", shorts)]:
        w, l, u, rt = rate(rows)
        out[nm] = dict(win=w, lose=l, undecided=u, win_rate=rt)
    return out


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    df = load_data()
    print(f"[데이터] {len(df):,}행 | {df.index[0]} ~ {df.index[-1]}", flush=True)
    print(f"[설정] N_SWING={N_SWING} X_ATR={X_ATR} Y_ATR={Y_ATR} "
          f"재방문대기={MAX_WAIT_REVISIT}봉 판정창={MAX_HOLD_AFTER}봉", flush=True)
    print("=" * 70, flush=True)
    all_rows = []
    summaries = []
    for tf in OB_TFS:
        g = TS.resample_tf(df, tf)
        atr = TS.compute_atr(g["high"].values, g["low"].values, g["close"].values, ATR_PD)
        obs, idx, H, L, C = extract_obs(g, atr)
        evals = [eval_ob(o, idx, H, L, C) for o in obs]
        evals = [e for e in evals if e is not None]
        s = summarize(evals, tf)
        summaries.append((s, len(obs)))
        tfh = f"{tf}m({tf // 60}h)" if tf % 60 == 0 else f"{tf}m"
        print(f"\n### OB-TF = {tfh}", flush=True)
        print(f"  추출 OB 총 {len(obs)}개 | 재방문 {s['n_revisited']}개 "
              f"({100.0 * s['n_revisited'] / max(1, len(obs)):.0f}%)", flush=True)
        for nm in ["ALL", "LONG", "SHORT"]:
            d = s[nm]
            print(f"  [{nm:5s}] 성공 {d['win']:4d} / 실패 {d['lose']:4d} / 미결 {d['undecided']:4d}"
                  f"  → 성공률(결판중) {d['win_rate']:.1f}%", flush=True)
        wr = s["ALL"]["win_rate"]
        verdict = ("기저≈동전(자석 51~53% 영역) → OI/CVD 얹기 전 경계" if MAGNET_LO - 2 <= wr <= MAGNET_HI + 3
                   else ("기저 우위 有 → 2단계 가치" if wr > MAGNET_HI + 3 else "기저 열위 → 역방향/재정의 검토"))
        print(f"  ▶ 판정: ALL 성공률 {wr:.1f}% vs 자석기저 51~53% → {verdict}", flush=True)
        for e in evals:
            all_rows.append({"ob_tf": tf, "conf_time": e["conf_time"], "side": e["side"],
                             "ob_lo": e["ob_lo"], "ob_hi": e["ob_hi"], "atr": e["atr"],
                             "bos_size": e["bos_size"], "rev_time": e["rev_time"],
                             "outcome": e["outcome"]})
    # 산출(§4 check 역할 일부): OB 이벤트 원장 csv
    ev = pd.DataFrame(all_rows)
    csv_path = os.path.join(OUTDIR, "260627_02_OBOICharacter_Stg1_OB_events.csv")
    ev.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print("\n" + "=" * 70, flush=True)
    print(f"[산출] OB 이벤트 원장: {csv_path} ({len(ev)}행)", flush=True)
    print("[해석] 성공률이 자석기저(51~53%)를 유의하게 넘으면 2단계(OI/CVD feature·CPCV·사이징백테).", flush=True)
    print("       넘지 못하면 OB '발견'은 약함 재확인 → ChatGPT 가설(OB '생존평가')도 신중.", flush=True)

    # ── 대조군: 아티팩트 vs 진짜 OB효과 ──────────────────────────
    print("\n" + "=" * 70, flush=True)
    print("[대조군] 아티팩트 분리 — OB 우위가 진짜인가 (X/Y대칭 · Random baseline · 추세통제)", flush=True)
    for tf in OB_TFS:
        g = TS.resample_tf(df, tf)
        atr = TS.compute_atr(g["high"].values, g["low"].values, g["close"].values, ATR_PD)
        C = g["close"].values
        obs, idx, H, L, Cc = extract_obs(g, atr)
        tfh = f"{tf}m({tf // 60}h)" if tf % 60 == 0 else f"{tf}m"
        ev_a = [e for e in (eval_ob(o, idx, H, L, Cc, X_ATR, Y_ATR) for o in obs) if e]
        ev_s = [e for e in (eval_ob(o, idx, H, L, Cc, 1.0, 1.0) for o in obs) if e]
        sa = summarize(ev_a, tf)["ALL"]; ss = summarize(ev_s, tf)["ALL"]
        bl_a = baseline_random(g, atr, X_ATR, Y_ATR); bl_s = baseline_random(g, atr, 1.0, 1.0)
        bla = _wr([bl_a[1][0] + bl_a[-1][0], bl_a[1][1] + bl_a[-1][1], 0])
        bls = _wr([bl_s[1][0] + bl_s[-1][0], bl_s[1][1] + bl_s[-1][1], 0])
        bla_L = _wr(bl_a[1]); bla_S = _wr(bl_a[-1])
        LB = max(1, 1440 // tf)
        align = [e for e in ev_a if e["conf_i"] - LB >= 0 and (1 if C[e["conf_i"]] > C[e["conf_i"] - LB] else -1) == e["side"]]
        against = [e for e in ev_a if e["conf_i"] - LB >= 0 and (1 if C[e["conf_i"]] > C[e["conf_i"] - LB] else -1) != e["side"]]
        wa = summarize(align, tf)["ALL"]["win_rate"] if align else float("nan")
        wg = summarize(against, tf)["ALL"]["win_rate"] if against else float("nan")
        print(f"\n### OB-TF {tfh}", flush=True)
        print(f"  (1) OB 성공률   비대칭1.0/0.5={sa['win_rate']:.1f}%   대칭1.0/1.0={ss['win_rate']:.1f}%", flush=True)
        print(f"  (2) Random      비대칭={bla:.1f}%(L{bla_L:.1f}/S{bla_S:.1f})   대칭={bls:.1f}%   ← 시장 baseline", flush=True)
        print(f"      ▶ OB 순효과(비대칭) = {sa['win_rate'] - bla:+.1f}%p", flush=True)
        print(f"  (3) 추세통제    추세순행 OB={wa:.1f}%(n{len(align)})   추세역행 OB={wg:.1f}%(n{len(against)})", flush=True)
        # (4) ★진입가-경계 대칭 RR (Random과 동일기하 = 기하학 착시 제거)
        ev_e = [e for e in (eval_ob(o, idx, H, L, Cc, 1.0, 1.0, entry_at_edge=True) for o in obs) if e]
        se = summarize(ev_e, tf)["ALL"]
        print(f"  (4) ★진입가기준 OB 대칭1/1={se['win_rate']:.1f}%(n{se['win']+se['lose']})  vs Random대칭={bls:.1f}%"
              f"  → 순효과 {se['win_rate'] - bls:+.1f}%p", flush=True)
        gap = sa["win_rate"] - bla
        gap4 = se["win_rate"] - bls
        print(f"      ▶ 판정: zone기준 {'有' if gap > 5 else '미미'}({gap:+.1f}%p) / "
              f"★진입가기준 {'有(진짜)' if gap4 > 5 else '미미(기하착시였음)'}({gap4:+.1f}%p)", flush=True)


if __name__ == "__main__":
    main()
