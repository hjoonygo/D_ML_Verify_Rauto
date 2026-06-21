# ==============================================================================
# 파일명: Optimizer_PautoV75.py
# 역할: Pauto V7.5 피보나치 SMC 맞춤형 하이퍼파라미터 최적화 모듈
# 특징: 1위 파라미터 자동 저장 및 Load & Play를 위한 메타데이터(학습기간) 각인 탑재
# ==============================================================================
import os
import sys
import json
import pandas as pd
import optuna
from optuna.samplers import TPESampler
from datetime import datetime
from Backtest_Engine_PautoV75 import Backtest_Engine_PautoV75

# [수정 완료]: 하드코딩된 경로 제거 및 현재 실행 파일 위치 동적 감지
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
if WORK_DIR not in sys.path:
    sys.path.insert(0, WORK_DIR)
os.chdir(WORK_DIR)

# 💡 최적화를 진행할 타겟 데이터 기간 (이 기간이 메타데이터로 GUI에 각인됩니다)
TARGET_START_DATE = "2026-01-01"
TARGET_END_DATE = "2026-01-31"
N_TRIALS = 30 # 최적화 시도 횟수

def objective(trial):
    # 새로운 피보나치 & SMC 맞춤형 최적화 변수 탐색
    leverage = trial.suggest_int('leverage', 1, 10)
    ml_threshold = trial.suggest_float('ml_threshold', 0.70, 0.90, step=0.05)
    fib_trigger_roe = trial.suggest_float('fib_trigger_roe', 10.0, 25.0, step=2.5) 
    fib_sl_roe = trial.suggest_float('fib_sl_roe', 3.0, 8.0, step=1.0) 
    fib_ext_pct = trial.suggest_float('fib_ext_pct', 0.500, 0.786, step=0.05) 

    engine = Backtest_Engine_PautoV75("Regime_Master_PautoV75", "Predict_ML_PautoV75", "Exec_Dynamic_TS_PautoV75", TARGET_START_DATE, TARGET_END_DATE)
    
    engine.params.update({
        'leverage': leverage,
        'ml_long_threshold': ml_threshold,
        'ml_short_threshold': 1.0 - ml_threshold,
        'fib_trigger_roe': fib_trigger_roe,
        'fib_sl_roe': fib_sl_roe,
        'fib_ext_pct': fib_ext_pct
    })
    
    engine._generate_reports = lambda: None 
    try: 
        engine.run_simulation()
    except Exception: 
        return -99999.0 
        
    return (engine.capital + engine.spot_wallet) - engine.initial_capital

def generate_monthly_report(engine, rank, params, realized_profit):
    lines = []
    lines.append(f"\n{'='*60}")
    lines.append(f"🏆 [ 순위: {rank}위 | 총 실현 순수익: ${round(realized_profit, 2)} ]")
    lines.append(f"⚙️ 파라미터: 레버리지 {params['leverage']}x | AI임계값 {params['ml_threshold']*100:.0f}%")
    lines.append(f"   피보나치: 발동 {params['fib_trigger_roe']:.1f}% | 하드손절 -{params['fib_sl_roe']:.1f}% | 락인비율 {params['fib_ext_pct']:.3f}")
    lines.append(f"{'='*60}")

    if not engine.trade_logs:
        lines.append("매매 기록이 없습니다 (조건이 너무 빡빡하여 진입 안함).\n")
        return lines

    df = pd.DataFrame(engine.trade_logs)
    df['Month'] = pd.to_datetime(df['청산시간']).dt.strftime('%Y-%m')
    months = sorted(df['Month'].unique())

    current_capital = engine.initial_capital
    current_spot = 0.0

    for idx, month in enumerate(months):
        m_df = df[df['Month'] == month]
        
        for _, row in m_df.iterrows():
            net = row['순수익금($)']
            current_capital += net
            if current_capital > engine.initial_capital:
                current_spot += (current_capital - engine.initial_capital)
                current_capital = engine.initial_capital
                
        unrealized_txt = ""
        if idx == len(months) - 1:
            upnl = 0.0
            if engine.position == "LONG":
                upnl = engine.position_size * ((engine.last_price - engine.entry_price) / engine.entry_price) - (engine.position_size * engine.fee_rate)
            elif engine.position == "SHORT":
                upnl = engine.position_size * ((engine.entry_price - engine.last_price) / engine.entry_price) - (engine.position_size * engine.fee_rate)
            unrealized_txt = f" | ⚠️ 최종 미실현수익: ${round(upnl, 2)}"

        lines.append(f"\n📅 [{month}월 결산] 선물계좌: ${round(current_capital,2)} | 현물격리: ${round(current_spot,2)}{unrealized_txt}")
        lines.append("-" * 60)

        def calc_stats(pos_df):
            trades = len(pos_df)
            profit = pos_df['순수익금($)'].sum() if trades > 0 else 0
            fees = pos_df['수수료($)'].sum() if trades > 0 else 0
            wins_df = pos_df[pos_df['순수익금($)'] > 0]
            loss_df = pos_df[pos_df['순수익금($)'] <= 0]
            win_rate = (len(wins_df) / trades * 100) if trades > 0 else 0
            avg_win = wins_df['순수익금($)'].mean() if len(wins_df) > 0 else 0
            avg_loss = loss_df['순수익금($)'].mean() if len(loss_df) > 0 else 0
            return trades, profit, fees, win_rate, avg_win, avg_loss

        l_tr, l_pr, l_fee, l_wr, l_aw, l_al = calc_stats(m_df[m_df['포지션'].str.contains('LONG')])
        lines.append(f" 🟢 [LONG] 수익: ${l_pr:,.2f} | 승률: {l_wr:.1f}% | 횟수: {l_tr}회 | 수수료: ${l_fee:,.2f}")
        lines.append(f"          ↳ 익절평균: ${l_aw:,.2f} | 손절평균: ${l_al:,.2f}")
        
        s_tr, s_pr, s_fee, s_wr, s_aw, s_al = calc_stats(m_df[m_df['포지션'].str.contains('SHORT')])
        lines.append(f" 🔴 [SHORT] 수익: ${s_pr:,.2f} | 승률: {s_wr:.1f}% | 횟수: {s_tr}회 | 수수료: ${s_fee:,.2f}")
        lines.append(f"          ↳ 익절평균: ${s_aw:,.2f} | 손절평균: ${s_al:,.2f}")

    return lines

if __name__ == "__main__":
    print("="*60)
    print("🚀 Pauto V7.5 ML 피보나치 하이퍼파라미터 최적화(Optuna) 시작")
    print("="*60)
    
    sampler = TPESampler(seed=42)
    study = optuna.create_study(direction='maximize', sampler=sampler)
    study.optimize(objective, n_trials=N_TRIALS, n_jobs=1)
    
    best_trials = sorted(study.trials, key=lambda t: t.value, reverse=True)[:5]
    best_trial = best_trials[0] 
    
    # 🌟 [메타데이터 각인 기능] JSON 파일에 훈련 기간과 갱신 일자 기록
    best_params_export = {
        'leverage': best_trial.params['leverage'],
        'ml_long_threshold': best_trial.params['ml_threshold'],
        'ml_short_threshold': round(1.0 - best_trial.params['ml_threshold'], 2),
        'fib_trigger_roe': best_trial.params['fib_trigger_roe'],
        'fib_sl_roe': best_trial.params['fib_sl_roe'],
        'fib_ext_pct': best_trial.params['fib_ext_pct'],
        
        # GUI의 Load & Play 전광판을 위한 데이터 출처 각인
        'optimized_period': f"{TARGET_START_DATE} ~ {TARGET_END_DATE}",
        'updated_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    param_file_path = os.path.join(WORK_DIR, "Pauto_Best_Params.json")
    with open(param_file_path, "w", encoding="utf-8") as f:
        json.dump(best_params_export, f, indent=4)
        
    print("\n" + "="*60)
    print(f"🎉 [성공] 1위 황금 세팅값 및 데이터 메타정보가 자동 저장되었습니다!")
    print(f"   경로: {param_file_path}")
    print("="*60)

    final_report = []
    final_report.append("============================================================")
    final_report.append("🏆 Pauto V7.5 피보나치 최적화 결과 (Top 5 랭킹)")
    final_report.append("============================================================")
    
    print("\n[AI] 최적화 완료! Top 5 조합에 대한 상세 분석 리포트를 생성합니다...\n")
    
    for rank, trial in enumerate(best_trials, 1):
        engine = Backtest_Engine_PautoV75("Regime_Master_PautoV75", "Predict_ML_PautoV75", "Exec_Dynamic_TS_PautoV75", TARGET_START_DATE, TARGET_END_DATE)
        engine.params.update({
            'leverage': trial.params['leverage'],
            'ml_long_threshold': trial.params['ml_threshold'],
            'ml_short_threshold': 1.0 - trial.params['ml_threshold'],
            'fib_trigger_roe': trial.params['fib_trigger_roe'],
            'fib_sl_roe': trial.params['fib_sl_roe'],
            'fib_ext_pct': trial.params['fib_ext_pct']
        })
        engine._generate_reports = lambda: None 
        engine.run_simulation()
        
        report_lines = generate_monthly_report(engine, rank, trial.params, trial.value)
        
        for line in report_lines:
            print(line)
            final_report.append(line)
            
    report_path = os.path.join(WORK_DIR, "Pauto_Opt_Top5_Report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(final_report))