"""
[파일명] analyze_pauto_v76.py
코드길이: 약 200줄, 내부버전 v7.6
목적: PautoV75 v7.6 시뮬 결과 csv 분석 — 총수익률/롱숏별/RR비/maxDD/강제청산
사용법: python analyze_pauto_v76.py <Pauto_TradeLog_YYMMDD_HHMMSS.csv>

In: TradeLog csv (Backtest_Engine_PautoV75.py가 출력)
Out: 콘솔 상세 보고서 + analysis_report.txt 파일
"""
import sys
import os
import pandas as pd
import numpy as np

INITIAL_CAPITAL = 10000.0
FEE_RATE_NOMINAL = 0.0004  # taker 4bp

def analyze(log_path: str):
    if not os.path.exists(log_path):
        print(f"[ERROR] 파일 없음: {log_path}")
        sys.exit(1)

    df = pd.read_csv(log_path, encoding='utf-8-sig')
    df['진입시간'] = pd.to_datetime(df['진입시간'])
    df['청산시간'] = pd.to_datetime(df['청산시간'])

    n_rows = len(df)
    print(f"\n{'='*78}")
    print(f"Pauto v7.6 시뮬 결과 분석 보고서")
    print(f"{'='*78}")
    print(f"로그 파일: {log_path}")
    print(f"전체 행수: {n_rows}")

    # === 1) 거래 페어 분해 (50% 익절 + 나머지 50% = 1거래) ===
    df['side'] = df['포지션'].apply(lambda x: 'LONG' if 'LONG' in x else 'SHORT')
    df['is_reduce'] = df['포지션'].str.contains('50% 익절')
    df['is_remaining'] = df['포지션'].str.contains('나머지 50%')
    df['is_full'] = df['포지션'].str.contains('전량')

    # 거래 페어 그룹화: 같은 진입시간 + side = 1 거래
    pairs = df.groupby(['진입시간', 'side']).agg(
        n_rows=('순수익금($)', 'count'),
        net_sum=('순수익금($)', 'sum'),
        fee_sum=('수수료($)', 'sum'),
        entry_price=('진입가', 'first'),
        exit_price_first=('청산가', 'first'),
        exit_price_last=('청산가', 'last'),
        exit_time=('청산시간', 'max'),
        leverage=('레버리지', 'first'),
        size_first=('진입수량($)', 'first'),
    ).reset_index()
    n_trades = len(pairs)
    print(f"거래 페어수: {n_trades}")
    print(f"매매 기간: {pairs['진입시간'].min()} ~ {pairs['exit_time'].max()}")

    # === 2) 자본 곡선 + maxDD ===
    # 시간순 정렬
    df_sorted = df.sort_values('청산시간').reset_index(drop=True)
    capital_series = INITIAL_CAPITAL + df_sorted['순수익금($)'].cumsum()
    peak_series = capital_series.cummax()
    dd_series = (capital_series - peak_series) / peak_series * 100  # % DD
    max_dd_pct = dd_series.min()
    max_dd_idx = dd_series.idxmin()
    max_dd_capital = capital_series.iloc[max_dd_idx]
    final_capital = capital_series.iloc[-1]
    total_return_pct = (final_capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

    print(f"\n{'='*78}")
    print(f"[자본 곡선]")
    print(f"{'='*78}")
    print(f"  시작 자본: ${INITIAL_CAPITAL:,.2f}")
    print(f"  종료 자본: ${final_capital:,.2f}")
    print(f"  총 수익률: {total_return_pct:+.2f}%")
    print(f"  Peak 자본: ${peak_series.max():,.2f}")
    print(f"  Max DD: {max_dd_pct:.2f}% (시점 거래 #{max_dd_idx+1}, 자본 ${max_dd_capital:,.2f})")
    print(f"  강제청산 감지: {'예 (자본 0 도달)' if final_capital <= 0.01 else '없음'}")

    # === 3) Long vs Short 분리 통계 ===
    def side_stats(side):
        sub = pairs[pairs['side'] == side]
        if len(sub) == 0:
            return None
        n = len(sub)
        wins = sub[sub['net_sum'] > 0]
        losses = sub[sub['net_sum'] <= 0]
        wr = len(wins) / n * 100
        net = sub['net_sum'].sum()
        mean_win = wins['net_sum'].mean() if len(wins) > 0 else 0
        mean_loss = losses['net_sum'].mean() if len(losses) > 0 else 0
        # RR비 (절댓값)
        rr = abs(mean_win / mean_loss) if mean_loss != 0 else float('inf')
        # PF
        gross_win = wins['net_sum'].sum() if len(wins) > 0 else 0
        gross_loss = abs(losses['net_sum'].sum()) if len(losses) > 0 else 1e-9
        pf = gross_win / gross_loss if gross_loss > 0 else float('inf')
        fee = sub['fee_sum'].sum()
        return {
            'n': n, 'wins': len(wins), 'losses': len(losses), 'wr': wr,
            'net': net, 'mean_win': mean_win, 'mean_loss': mean_loss,
            'rr': rr, 'pf': pf, 'fee': fee,
        }

    print(f"\n{'='*78}")
    print(f"[Long/Short 분리 통계]")
    print(f"{'='*78}")
    for side in ['LONG', 'SHORT']:
        s = side_stats(side)
        if s is None:
            print(f"\n  [{side}] 거래 0건")
            continue
        print(f"\n  [{side}] {s['n']}거래 (Win {s['wins']} / Loss {s['losses']})")
        print(f"    승률: {s['wr']:.2f}%")
        print(f"    순수익: ${s['net']:+,.2f}")
        print(f"    평균 win: ${s['mean_win']:+,.2f}")
        print(f"    평균 loss: ${s['mean_loss']:+,.2f}")
        print(f"    RR비 (|mean_win/mean_loss|): {s['rr']:.3f}")
        print(f"    Profit Factor: {s['pf']:.3f}")
        print(f"    수수료 합계: ${s['fee']:,.2f}")

    # === 4) 청산사유별 분포 ===
    print(f"\n{'='*78}")
    print(f"[청산사유 분포]")
    print(f"{'='*78}")
    df['청산유형'] = df['청산사유(Exec)'].apply(lambda x: 
        'SMC_1차' if 'SMC 1차' in str(x) else
        'SMC_OB이탈' if 'SMC OB' in str(x) else
        'Fibonacci락인' if 'Fibonacci' in str(x) else
        '초기손절' if '초기 하드' in str(x) else
        '기타'
    )
    for reason, cnt in df['청산유형'].value_counts().items():
        pct = cnt / n_rows * 100
        sub = df[df['청산유형'] == reason]
        avg_pnl = sub['순수익금($)'].mean()
        print(f"  {reason:20s}: {cnt:4d}회 ({pct:5.1f}%), 평균 PnL ${avg_pnl:+,.2f}")

    # === 5) 알파 판단 ===
    print(f"\n{'='*78}")
    print(f"[알파 판단]")
    print(f"{'='*78}")
    days = (pairs['exit_time'].max() - pairs['진입시간'].min()).total_seconds() / 86400
    months = days / 30
    monthly_return = total_return_pct / months if months > 0 else 0
    print(f"  분석 기간: {days:.0f}일 ({months:.1f}개월)")
    print(f"  월평균 수익률: {monthly_return:+.2f}%/월")
    print(f"  사용자 목표 (월 8% 진입단계): {'★ 달성' if monthly_return >= 8 else '✗ 미달성'}")
    print(f"  사용자 최종 목표 (월 15%): {'★ 달성' if monthly_return >= 15 else '✗ 미달성'}")
    if max_dd_pct < -50:
        print(f"  ⚠ Max DD {max_dd_pct:.1f}% — 사용자 트라우마 임계 초과")

    # === 6) 텍스트 파일 저장 ===
    out_path = log_path.replace('.csv', '_analysis.txt')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(f"Pauto v7.6 분석 보고서\n")
        f.write(f"입력: {log_path}\n")
        f.write(f"\n총 수익률: {total_return_pct:+.2f}%\n")
        f.write(f"종료 자본: ${final_capital:,.2f}\n")
        f.write(f"Max DD: {max_dd_pct:.2f}%\n")
        f.write(f"거래수: {n_trades}\n")
        f.write(f"기간: {days:.0f}일 ({months:.1f}개월)\n")
        f.write(f"월수익률: {monthly_return:+.2f}%\n")
        for side in ['LONG', 'SHORT']:
            s = side_stats(side)
            if s is None:
                f.write(f"\n[{side}] 거래 0건\n")
                continue
            f.write(f"\n[{side}] {s['n']}거래, WR {s['wr']:.1f}%, 순수익 ${s['net']:+,.2f}, RR {s['rr']:.2f}, PF {s['pf']:.2f}\n")
    print(f"\n[저장] {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # 기본 파일명 패턴 자동 검색
        candidates = sorted([f for f in os.listdir('.') if f.startswith('Pauto_TradeLog_') and f.endswith('.csv')])
        if candidates:
            print(f"인자 없음 — 자동 탐색: {candidates[-1]}")
            analyze(candidates[-1])
        else:
            print("사용법: python analyze_pauto_v76.py <Pauto_TradeLog_YYMMDD_HHMMSS.csv>")
            sys.exit(1)
    else:
        analyze(sys.argv[1])
