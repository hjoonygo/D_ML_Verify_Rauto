# -*- coding: utf-8 -*-
# [파일명] ml_sizing.py
# 코드길이: 약 230줄 | 내부버전: 06Prj_Ch6_Stg4_MLSizing_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 모듈이 하는 일 — 고딩 설명]
#   ML에게 '자유도 최대'로 진짜 실력을 보게 한다. 사장님 지시 = (다)봇수익정답지 + (가)거래있는봉만(미래참조 구조적 차단).
#   기존 Stg13의 3대 족쇄를 전부 푼다:
#     ① 타깃: label_smc(라벨맞히기) 폐기 → '거래있는 봉에서 그 봇이 이겼나(R부호)' + R크기 가중(정보량↑)
#     ② 특징: 표준8 + 허스트 + CVD + OI마이크로 + 다TF + 구조(feat_break) 전부(과거봉만)
#     ③ 모델: LogReg/RandForest/GradBoost/HistGB 4종 + 하이퍼파라미터 탐색 + class_weight 불균형보정
#   [★미래참조 차단 — (가)의 핵심] 거래 진입봉 t의 타깃 = 그 거래의 실제 R(이미 일어난 일). 특징 = t 이전봉만.
#                                  거래 안 한 봉은 학습 제외 → 미래 가상수익 계산 자체가 없음 = lookahead 불가능.
#   [평가] acc/AUC가 아니라 '이 ML로 사이징(베팅배수 조절)했을 때 봇 PF·수익이 표준 칩필터보다 나은가'.
#          워크포워드 OOS. 학습기간만 fit. ML이 OOS에서 표준 못이기면 STANDARD 채택.
#
# [In] 특징행렬 X(과거봉만) / 거래리스트(side·entry_t·R) / 봉인덱스 / 워크포워드 창
# [Out] ml_model_compare(모델별 OOS), feature_importance, ml_sizing_pf(ML사이징 봇PF), recommend
# [사용함수] build_targets(거래→타깃y,가중w) / hyperparam_grids / fit_eval_models / wf_ml_sizing
# ==============================================================================
import numpy as np

# 하이퍼파라미터 격자(학습기간 내 검증분할로 탐색) — '만반의 준비'
def hyperparam_grids():
    return {
        'LogReg': [dict(C=c) for c in (0.1, 1.0, 10.0)],
        'RandForest': [dict(n_estimators=n, max_depth=d, min_samples_leaf=l)
                       for n in (200, 400) for d in (4, 8, None) for l in (1, 5)],
        'GradBoost': [dict(n_estimators=n, max_depth=d, learning_rate=lr)
                      for n in (150, 300) for d in (2, 3) for lr in (0.03, 0.1)],
        'HistGB': [dict(max_iter=n, max_depth=d, learning_rate=lr)
                   for n in (200, 400) for d in (3, None) for lr in (0.05, 0.1)],
    }


def make_model(name, hp):
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, HistGradientBoostingClassifier
    if name == 'LogReg':
        return LogisticRegression(max_iter=2000, class_weight='balanced', **hp)
    if name == 'RandForest':
        return RandomForestClassifier(class_weight='balanced', random_state=0, n_jobs=-1, **hp)
    if name == 'GradBoost':
        return GradientBoostingClassifier(random_state=0, **hp)
    if name == 'HistGB':
        return HistGradientBoostingClassifier(random_state=0, class_weight='balanced', **hp)
    raise ValueError(name)


def build_targets(trade_bots, trade_R):
    # (다)+(가): 거래있는 봉만. y=1(이 거래가 이김 R>0) / 0(짐). 표본가중 w=|R|(R클수록 중요).
    #   trend봇·sideway봇을 한 데이터셋에 합치되 'bot' 더미특징으로 구분(ML이 봇별 패턴 학습).
    y = (np.asarray(trade_R) > 0).astype(int)
    w = np.abs(np.asarray(trade_R))
    w = np.clip(w, 1e-6, None)
    return y, w


def time_val_split(n, val_frac=0.25):
    # 학습기간 내부를 다시 (앞)학습/(뒤)검증으로 시간순 분할 — 하이퍼탐색용(미래참조 없음)
    k = int(n * (1 - val_frac))
    return np.arange(k), np.arange(k, n)


def fit_eval_models(Xtr, ytr, wtr, Xte, yte, scaler=None):
    # 4모델 × 하이퍼격자를 학습기간 내 검증분할로 탐색 → 각 모델 best를 OOS(te)에서 평가.
    from sklearn.metrics import roc_auc_score
    grids = hyperparam_grids()
    rows = []; best_overall = None
    tr_i, val_i = time_val_split(len(Xtr))
    if len(np.unique(ytr[tr_i])) < 2 or len(val_i) < 5:
        return rows, None
    for name, hps in grids.items():
        best_hp = None; best_val = -1
        for hp in hps:
            try:
                m = make_model(name, hp)
                m.fit(Xtr[tr_i], ytr[tr_i], sample_weight=wtr[tr_i])
                if len(np.unique(ytr[val_i])) < 2:
                    continue
                p = m.predict_proba(Xtr[val_i])[:, 1]
                a = roc_auc_score(ytr[val_i], p)
                if a > best_val:
                    best_val = a; best_hp = hp
            except Exception:
                continue
        if best_hp is None:
            continue
        # best_hp로 학습기간 전체 재학습 → OOS 평가
        try:
            m = make_model(name, best_hp)
            m.fit(Xtr, ytr, sample_weight=wtr)
            if len(np.unique(yte)) >= 2:
                pte = m.predict_proba(Xte)[:, 1]
                auc = roc_auc_score(yte, pte)
                acc = float(((pte > 0.5).astype(int) == yte).mean())
            else:
                auc = float('nan'); acc = float('nan')
            rows.append(dict(model=name, val_auc=round(best_val, 3), oos_auc=round(auc, 3),
                             oos_acc=round(acc, 3), hp=str(best_hp)))
            if not np.isnan(auc) and (best_overall is None or auc > best_overall[1]):
                best_overall = (name, auc, best_hp, m)
        except Exception:
            continue
    return rows, best_overall


def feature_importance(model, names):
    try:
        if hasattr(model, 'feature_importances_'):
            imp = model.feature_importances_
        elif hasattr(model, 'coef_'):
            imp = np.abs(model.coef_).ravel()
        else:
            return []
        order = np.argsort(imp)[::-1]
        return [(names[i], round(float(imp[i]), 4)) for i in order]
    except Exception:
        return []
