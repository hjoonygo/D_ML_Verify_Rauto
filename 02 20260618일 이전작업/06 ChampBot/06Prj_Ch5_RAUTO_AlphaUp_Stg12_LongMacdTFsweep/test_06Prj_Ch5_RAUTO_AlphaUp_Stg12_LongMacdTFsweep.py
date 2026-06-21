# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch5_RAUTO_AlphaUp_Stg12_LongMacdTFsweep.py
# 코드길이: 약 300줄 | 내부버전: RAUTO_AlphaUp_06_Ch5_Stg12_LongMacdTFsweep | 로직 전체 출력
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   엔진 무수정. 사장님 직관 검증: "장기MACD를 1분봉 등 짧은 봉으로 보면 장세판별이 되나?"
#   장기MACD(210-420 EMA차, 정규화)를 여러 봉에서 계산해 각각 label_smc 4장세 OOS 정확도를 잰다.
#     TF: 1분 / 5분 / 15분 / 60분(1h) / 240분(4h) / 420분(7h, 기존)
#   ★핵심 추적: 'uptrend(상승추세) 재현율(recall)' — Stg11에서 7h는 상승을 0번 맞혔다.
#     어느 TF부터 상승을 잡기 시작하는지가 사장님 직관의 진위.
#   ★중요(시간축 정합): label_smc는 4h기반. 각 TF의 장기MACD 판별을 그 TF격자에서 label과 맞춘다.
#     (이번엔 판별 '정확도'만 본다. 추세봇 진입 매칭/사이징은 정확도가 살아날 때 다음 단계.)
#   [정규화] 장기MACD = (EMA210 - EMA420)/close*100. [임계=학습기간(앞70%) 분위수만] [label 미사용 in 판별입력]
#   [Lookahead 없음] EMA·임계 모두 과거봉 기반.
#
# [PATH] 실행: D:\ML\Verify\06Prj_..._Stg12_LongMacdTFsweep\ . 데이터: 상위 (Merged_Data_with_Regime_Features.csv 필수).
# [OUTPUT] tf_accuracy.csv / confusion_by_tf.csv / uptrend_recall.csv / summary.csv + .stg12_metric
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE); BOTS = os.path.join(HERE, "bots")
F3, S3 = 210, 420
TFS = [1, 5, 15, 60, 240, 420]    # 1분~7h
REGIME_MAP = {'uptrend': 0, 'downtrend': 1, 'volatile_range': 2, 'dead_range': 3}
REGIME_NAME = {0: 'uptrend', 1: 'downtrend', 2: 'volatile_range', 3: 'dead_range', -1: 'unknown'}


def load_engine(p, nm):
    s = importlib.util.spec_from_file_location(nm, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def find_file(c):
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for x in c:
            p = os.path.join(d, x)
            if os.path.exists(p):
                return p
    return None


champ = load_engine(os.path.join(BOTS, "SpTrd_Fib_V1_Champion.py"), "champ_engine")
DATA = find_file(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])


def ema(x, span):
    a = 2.0 / (span + 1.0); out = np.full(len(x), np.nan); m = None
    for i, v in enumerate(x):
        if np.isnan(v):
            out[i] = m if m is not None else np.nan; continue
        m = v if m is None else a * v + (1 - a) * m
        out[i] = m
    return out


def main():
    print("[Stg12] 장기MACD 다중TF 장세판별 정확도 (사장님 직관 검증)")
    open(os.path.join(HERE, ".run_start"), "w").close()
    if DATA is None:
        pd.DataFrame([{'x': '데이터없음'}]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig'); return

    head = list(pd.read_csv(DATA, nrows=1).columns)
    lbl = next((c for c in head if c.startswith('label_smc_8')), None) or next((c for c in head if c.startswith('label_smc')), None)
    # 1분 원본 로드(OHLC + label)
    raw = pd.read_csv(DATA, usecols=['timestamp', 'close', lbl], index_col='timestamp', parse_dates=True)
    if getattr(raw.index, 'tz', None) is not None:
        raw.index = raw.index.tz_localize(None)
    raw = raw.sort_index()
    close1 = raw['close']
    lab1 = raw[lbl].map(REGIME_MAP)

    acc_rows = []; recall_rows = []; conf_rows = []
    for TF in TFS:
        # 해당 TF 종가
        if TF == 1:
            c = close1.copy(); lab_tf = lab1.copy()
        else:
            c = close1.resample(f"{TF}min", label='left', closed='left').last().dropna()
            lab_tf = lab1.resample(f"{TF}min", label='left', closed='left').last().reindex(c.index)
        cv = c.values.astype('float64')
        macd3 = (ema(cv, F3) - ema(cv, S3)) / np.where(cv > 0, cv, np.nan) * 100.0
        nb = len(cv); cut = int(nb * 0.7)
        if cut < 500:
            acc_rows.append(dict(tf_min=TF, n=nb, note='샘플부족')); continue
        str_hi = np.nanquantile(np.abs(macd3[:cut]), 0.60)
        reg = np.full(nb, -1)
        for i in range(nb):
            a = macd3[i]
            if np.isnan(a):
                continue
            strong = abs(a) >= str_hi
            reg[i] = (0 if a > 0 else 1) if strong else (2 if a > 0 else 3)
        lab_v = lab_tf.values.astype('float64')
        te = np.arange(cut, nb)
        valid = te[(reg[te] >= 0) & (~np.isnan(lab_v[te]))]
        if len(valid) == 0:
            acc_rows.append(dict(tf_min=TF, n=nb, note='검증불가')); continue
        acc = round(100 * float((reg[valid] == lab_v[valid]).mean()), 1)
        maj = round(100 * float(pd.Series(lab_v[:cut][~np.isnan(lab_v[:cut])]).value_counts(normalize=True).max()), 1)
        # 상승추세 recall: 실제 상승 중 상승으로 맞힌 비율
        up_actual = valid[lab_v[valid] == 0]
        up_recall = round(100 * float((reg[up_actual] == 0).mean()), 1) if len(up_actual) else 0.0
        down_actual = valid[lab_v[valid] == 1]
        down_recall = round(100 * float((reg[down_actual] == 1).mean()), 1) if len(down_actual) else 0.0
        acc_rows.append(dict(tf=f"{TF}m" if TF < 60 else f"{TF//60}h", tf_min=TF, n_test=len(valid),
                             acc4=acc, baseline=maj, beats_baseline=('YES' if acc > maj else 'NO')))
        recall_rows.append(dict(tf=f"{TF}m" if TF < 60 else f"{TF//60}h", uptrend_recall=up_recall, downtrend_recall=down_recall))
        # 혼동행렬(각 TF)
        conf = np.zeros((4, 4), int)
        for a, p in zip(lab_v[valid], reg[valid]):
            conf[int(a), int(p)] += 1
        for i in range(4):
            conf_rows.append(dict(tf=f"{TF}m" if TF < 60 else f"{TF//60}h", actual=REGIME_NAME[i],
                                  **{f"pred_{REGIME_NAME[j]}": int(conf[i, j]) for j in range(4)}))
        print(f"[{TF}m] acc {acc}% (기준선 {maj}%) | 상승recall {up_recall}% 하락recall {down_recall}%")

    adf = pd.DataFrame(acc_rows); adf.to_csv(os.path.join(HERE, "tf_accuracy.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame(recall_rows).to_csv(os.path.join(HERE, "uptrend_recall.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame(conf_rows).to_csv(os.path.join(HERE, "confusion_by_tf.csv"), index=False, encoding='utf-8-sig')

    # 판정: 어느 TF든 기준선 초과하면 사장님 직관 일부 성립
    valid_acc = adf[adf.get('acc4', pd.Series(dtype=float)).notna()] if 'acc4' in adf else pd.DataFrame()
    best = valid_acc.sort_values('acc4', ascending=False).iloc[0] if len(valid_acc) else None
    any_beats = (valid_acc['beats_baseline'] == 'YES').any() if len(valid_acc) else False
    up_any = pd.DataFrame(recall_rows)
    up_best = up_any.sort_values('uptrend_recall', ascending=False).iloc[0] if len(up_any) else None
    if best is not None:
        flag = (f"사장님직관 성립({best['tf']} acc {best['acc4']}%>기준선)" if any_beats
                else f"전TF 기준선 미달 — 장기MACD 판별 한계 확인(best {best['tf']} {best['acc4']}%)")
        verdict = (f"VERDICT Stg12 | 장기MACD 다중TF 판별 | "
                   f"best {best['tf']} acc {best['acc4']}%(기준선{best['baseline']}%) | "
                   f"상승recall 최고 {up_best['tf']} {up_best['uptrend_recall']}% (7h는 0%였음) | => {flag}")
    else:
        flag = "검증불가"; verdict = "VERDICT Stg12 | 검증불가"
    print("[verdict] " + verdict)
    pd.DataFrame([dict(sec=verdict), dict(sec=f"[TF별 정확도] {acc_rows}"), dict(sec=f"[상승/하락 recall] {recall_rows}")]).to_csv(
        os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
    with open(os.path.join(HERE, ".stg12_metric"), "w", encoding="utf-8") as f:
        f.write(f"best_tf={best['tf'] if best is not None else 'NA'}\nbest_acc={best['acc4'] if best is not None else 0}\n"
                f"baseline={best['baseline'] if best is not None else 0}\nany_beats={'YES' if any_beats else 'NO'}\n"
                f"up_recall_best_tf={up_best['tf'] if up_best is not None else 'NA'}\nup_recall_best={up_best['uptrend_recall'] if up_best is not None else 0}\n"
                f"n_tf={len(acc_rows)}\nhas_label_in_feats=False\nverdict_flag={flag}\n")
    print("[save] tf_accuracy/confusion_by_tf/uptrend_recall/summary.csv")


if __name__ == "__main__":
    main()
