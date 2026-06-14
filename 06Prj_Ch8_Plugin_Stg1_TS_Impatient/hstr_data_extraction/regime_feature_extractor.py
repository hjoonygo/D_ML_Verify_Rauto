# -*- coding: utf-8 -*-
# [파일명] regime_feature_extractor.py
# 코드길이: 약 300줄, 내부버전명: regime_v1, 로직 축약/생략 없이 전체 출력
#
# [목적] 36개월 1분봉(Merged_Data.csv)에 '장세 관련 연속 수치(feature)' + '참고용 SMC 사후라벨'을
#        Lookahead 없이 4H 기준으로 붙인다. 장세를 4칸으로 못 박지 않고 수치로 기록 → 나중에 ML이 칸을 결정.
#
# [핵심 분리 — 미래참조 방지의 뼈대]
#   (A) 라벨(label_smc_*): 사후(미래 봐도 됨). ML이 '맞출 정답지'. 스윙 확정지연을 보정 안 함(사후라 OK).
#   (B) feature(feat_*)  : 실시간(그 시점 과거만). 봇이 실제 보는 값. 스윙은 swing_length 만큼 '지연 확정'을
#                          반영해 shift. EMA/ADX/ATR은 인과적(과거만)이라 그대로 사용.
#   → 4H값을 1분봉에 ffill할 때 shift(1) 안전판으로 '확정된 직전 4H봉'만 보게 한다.
#
# [함수 In/Out]
#   compute_adx(df, n)               : 4H OHLC -> ADX Series
#   compute_continuous_metrics(d4)   : 4H OHLC -> EMA/ADX/ATR/BB 연속수치 컬럼 추가된 d4
#   smc_structure(d4, swing_len)     : 4H OHLC -> (구조상태 라벨, 연속 구조수치) DataFrame
#   label_regime(struct, atr_ratio)  : 구조+변동성 -> 4장세 참고라벨(사후)
#   build(df_1m, swing_lens)         : 전체 파이프라인 -> (1분봉+feature/label) df, 분포리포트 dict
#
# [사용] 하위 기록폴더에서 실행, 데이터는 상위 D:\ML\Verify\Merged_Data.csv 자동탐색.
#        python regime_feature_extractor.py
# ==============================================================================
import os, sys
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, pandas as pd
from smartmoneyconcepts import smc

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
SWING_LENS = [5, 8, 12]          # 4H 스윙 민감도 후보 (사용자 승인)
TF = '4h'
ATR_RATIO_DIV = 1.0              # 횡보 변동/죽음 가르는 참고 분기 (ML이 나중에 재결정 → 라벨은 참고용)

def find_data_file():
    names = ["Merged_data.csv","merged_data.csv","Merged_Data.csv"]
    for d in [WORK_DIR, os.path.dirname(WORK_DIR), r"D:\ML\Verify"]:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p): return p
    raise FileNotFoundError("Merged_data.csv 를 상위 D:\\ML\\Verify 에 두세요.")

def compute_adx(df, n=14):
    h,l,c = df['high'],df['low'],df['close']
    pdm = h.diff(); mdm = l.diff()
    pdm = pdm.where((pdm>0)&(pdm>mdm.abs()),0.0)
    mdm = (-mdm).where((mdm<0)&((-mdm)>pdm),0.0)
    tr = pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/n,adjust=False).mean()
    pdi = 100*(pdm.ewm(alpha=1/n,adjust=False).mean()/atr)
    mdi = 100*(mdm.ewm(alpha=1/n,adjust=False).mean()/atr)
    dx = (abs(pdi-mdi)/(pdi+mdi).replace(0,np.nan))*100
    return dx.ewm(alpha=1/n,adjust=False).mean()

def compute_continuous_metrics(d4):
    """인과적(과거만) 연속 수치 — feature로 안전."""
    d=d4.copy()
    for s in (20,50,100): d[f'ema_{s}']=d['close'].ewm(span=s,adjust=False).mean()
    d['ema20_slope']=d['ema_20'].pct_change(3)          # 3봉(=12h) 기울기
    d['ema_fan']=(d['ema_20']-d['ema_100'])/d['close']  # 정배열 강도(+상승/-하락)
    d['adx']=compute_adx(d,14)
    d['adx_chg']=d['adx'].diff(3)
    tr=pd.concat([d['high']-d['low'],(d['high']-d['close'].shift()).abs(),(d['low']-d['close'].shift()).abs()],axis=1).max(axis=1)
    d['atr']=tr.ewm(alpha=1/14,adjust=False).mean()
    d['norm_atr']=d['atr']/d['close']*100
    d['avg_norm_atr']=d['norm_atr'].rolling(60).mean()
    d['atr_ratio']=d['norm_atr']/d['avg_norm_atr']      # >1 변동확대 / <1 압축
    mid=d['close'].rolling(20).mean(); sd=d['close'].rolling(20).std()
    d['bb_width']=(2*sd)/mid
    d['bb_width_pct']=d['bb_width'].rolling(100).rank(pct=True)
    return d

def smc_structure(d4, swing_len):
    """SMC 스윙으로 HH/HL/LH/LL → 구조상태. (A)라벨용 사후 + (B)feature용 지연확정 둘 다 반환."""
    shl = smc.swing_highs_lows(d4[['open','high','low','close']], swing_length=swing_len)
    hl = shl['HighLow'].values; lv = shl['Level'].values
    n=len(d4)
    struct_post = np.array(['none']*n, dtype=object)  # 사후 구조
    cont_break = np.zeros(n)                          # 직전 동종스윙 대비 갱신폭(연속수치)
    last_high=last_low=None; prev_high=prev_low=None
    state='range'
    high_is=None; low_is=None  # 'HH'/'LH', 'HL'/'LL'
    for i in range(n):
        if not np.isnan(hl[i]):
            if hl[i]==1:   # 스윙 고점
                prev_high=last_high; last_high=lv[i]
                if prev_high is not None:
                    high_is='HH' if last_high>prev_high else 'LH'
                    cont_break[i]=(last_high-prev_high)/prev_high
            else:          # 스윙 저점
                prev_low=last_low; last_low=lv[i]
                if prev_low is not None:
                    low_is='HL' if last_low>prev_low else 'LL'
                    cont_break[i]=(last_low-prev_low)/prev_low
            if high_is=='HH' and low_is=='HL': state='uptrend'
            elif high_is=='LH' and low_is=='LL': state='downtrend'
            else: state='range'
        struct_post[i]=state
    cont_break=pd.Series(cont_break,index=d4.index).replace(0,np.nan).ffill().fillna(0)
    post=pd.Series(struct_post,index=d4.index)
    # (B) feature: 스윙은 swing_len 뒤에야 확정 → 그만큼 지연
    feat=post.shift(swing_len).fillna('range')
    cont_feat=cont_break.shift(swing_len).fillna(0)
    return pd.DataFrame({f'struct_post_{swing_len}':post, f'feat_struct_{swing_len}':feat,
                         f'feat_break_{swing_len}':cont_feat}, index=d4.index)

def label_regime(struct, atr_ratio):
    """사후 참고라벨: 구조 + 변동성 → 4장세 (ML이 나중에 재결정하므로 '참고'."""
    out=[]
    for s,a in zip(struct, atr_ratio):
        if s=='uptrend': out.append('uptrend')
        elif s=='downtrend': out.append('downtrend')
        else: out.append('volatile_range' if (a>=ATR_RATIO_DIV) else 'dead_range')
    return out

def build(df_1m, swing_lens=SWING_LENS):
    ohlc={'open':'first','high':'max','low':'min','close':'last','volume':'sum'}
    d4=df_1m.resample(TF,label='right',closed='right').agg(ohlc).dropna()
    d4.columns=[c.lower() for c in d4.columns]
    d4=compute_continuous_metrics(d4)
    reports={}
    for sl in swing_lens:
        st=smc_structure(d4,sl)
        d4=pd.concat([d4,st],axis=1)
        d4[f'label_smc_{sl}']=label_regime(d4[f'struct_post_{sl}'].values, d4['atr_ratio'].fillna(1).values)
        vc=d4[f'label_smc_{sl}'].value_counts(normalize=True)
        # 전환 횟수 + 평균 지속(4H봉)
        lab=d4[f'label_smc_{sl}']; switches=(lab!=lab.shift()).sum()
        reports[sl]={'분포%':(vc*100).round(1).to_dict(),'전환수':int(switches),
                     '평균지속_4H봉':round(len(d4)/max(switches,1),1)}
    # 4H → 1분봉 매핑: shift(1) 안전판(확정된 직전 4H봉만)
    feat_cols=[c for c in d4.columns if c not in ('open','high','low','close','volume')]
    d4_safe=d4[feat_cols].shift(1)
    out=df_1m.join(d4_safe, how='left'); out[feat_cols]=out[feat_cols].ffill()
    return out, reports, d4

if __name__=="__main__":
    print("="*64); print("[장세 수치/라벨 추출 — regime_v1]"); print("="*64)
    path=find_data_file(); print(f"[데이터] 읽음: {path}")
    df=pd.read_csv(path, parse_dates=['timestamp']).set_index('timestamp').sort_index()
    df=df[['open','high','low','close','volume']] if 'volume' in df.columns else df[['open','high','low','close']]
    if 'volume' not in df.columns: df['volume']=0.0
    print(f"[데이터] {df.index.min()} ~ {df.index.max()} | {len(df):,}행")
    out, reports, d4 = build(df)
    print(f"\n[4H봉] {len(d4)}개 | 1분봉 출력 {len(out):,}행, 컬럼 {len(out.columns)}개")
    print("\n[스윙길이별 4장세 참고분포 — 사람이 보기에 말 되는지 검수]")
    for sl,r in reports.items():
        print(f"  swing_len={sl:2d}: {r['분포%']}  전환 {r['전환수']}회, 평균지속 {r['평균지속_4H봉']}봉(≈{r['평균지속_4H봉']*4/24:.1f}일)")
    outp=os.path.join(WORK_DIR,"Merged_Data_with_Regime_Features.csv")
    out.to_csv(outp); print(f"\n[저장] {outp}")
    print("[완료] feature(feat_*)=실시간안전, label(label_smc_*)=사후정답지(ML용)")
