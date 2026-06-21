# [파일명] trendstack_regime.py
# 코드길이: 약 90줄 / 내부버전: trendstack_regime_v1 (regime_feature_extractor 추출) / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 업트렌드 숏컷용 feat_struct_8(실시간 SMC 구조라벨) 생성. regime_feature_extractor.py
#        (업로드 원본, 내부버전 regime_v1)에서 compute_adx·compute_continuous_metrics·smc_structure·
#        label_regime를 '한 글자도 안 바꾸고' 추출(원본 L42-114).
# [핵심] feat_struct = 4H SMC 스윙(HH+HL=uptrend/LH+LL=downtrend/그외 range) → shift(swing_len) 지연확정(실시간安). 3상태.
#        label_smc(4상태)는 사후 정답지(룩어헤드) — 라이브 사용 금지. 봇은 feat_struct만 쓴다.
# [의존] smartmoneyconcepts (pip install smartmoneyconcepts)
# [In] 4H OHLC DataFrame + swing_len(8) [Out] (struct_post, feat_struct) Series
# ── 함수 ── compute_adx · compute_continuous_metrics · smc_structure(원본1:1) · label_regime · feat_struct_of(헬퍼)
# ── 상수 ── SWING_LENS=[5,8,12], TF='4h', ATR_RATIO_DIV=1.0 (원본값)
# ─────────────────────────────────────────────────────────────────────────
import numpy as np, pandas as pd
from smartmoneyconcepts import smc

SWING_LENS = [5, 8, 12]
TF = '4h'
ATR_RATIO_DIV = 1.0


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


def feat_struct_of(df4h, swing_len=8):
    # 4H OHLC → (struct_post, feat_struct). feat=post.shift(swing_len)=실시간안전.
    post, feat = None, None
    res = smc_structure(df4h, swing_len)
    post = res[f'struct_post_{swing_len}']
    feat = res[f'feat_struct_{swing_len}']
    return post, feat
