import os,sys,numpy as np,pandas as pd,collections
sys.path.insert(0, os.path.join(os.getcwd(),"bots"))
from bot_trendstack_impatient_king import TrendStackImpatientKingBot
from bot_trendstack_impatient import TrendStackImpatientBot
import trendstack_signal_engine as E, trendstack_regime as RG
import rauto_paper_engine as PE
from rauto_contract import MarketBar, Signal, Action, Side
DATA=r"D:\ML\Verify\Merged_Data.csv"
df=pd.read_csv(DATA,usecols=lambda c:c in('timestamp','open','high','low','close','volume','oi_zscore_24h'))
df['timestamp']=pd.to_datetime(df['timestamp'],utc=True).dt.tz_convert(None)
# feat(4H) for 장세 분해
ohlc=df.set_index('timestamp')[['open','high','low','close']]
df4=E.resample_tf(ohlc,240)
try: _,featser=RG.feat_struct_of(df4,8); featser.index=df4.index
except Exception: featser=pd.Series("range",index=df4.index)
rows=list(df.itertuples(index=False))
LEV=22.0;SLIP=0.0005
def feed(bot):
    bot.on_init({}); cur=None; n=0
    for r in rows:
        oz=r.oi_zscore_24h; oz=float(oz) if oz==oz else float('nan')
        sig=bot.on_bar(MarketBar(ts=r.timestamp,o=r.open,h=r.high,l=r.low,c=r.close,v=r.volume,aux={'oi_zscore':oz}))
        if sig is not None and sig.action==Action.ENTER: cur=sig.size_pct
        if len(bot._trades)>n: bot._trades[-1]['size']=cur if cur else 7.0864; n=len(bot._trades)
    for t in bot._trades:
        t['feat']=str(featser.asof(pd.Timestamp(t['entry_t']))) if len(featser) else 'range'
        t['Rs']=t["R"]-(SLIP if 'sl' in t['reason'] else 0.0)   # 손절=시장가 슬리피지
    return bot._trades
def acct(trd):
    acc=PE.PaperAccount(10000.0); ps=[]
    for t in trd:
        b0=acc.bal
        acc.open(Signal(Action.ENTER,side=Side(int(t['side'])),size_pct=t.get('size',7.0864),leverage=LEV),ts=None,price=100.0)
        acc.resolve_replay(R=t['Rs'],mae=min(0.0,t['Rs']),fund=t.get('fund',0.0)); ps.append(acc.bal/b0-1)
    return acc,np.array(ps)
def pf(trd): R=np.array([t['Rs'] for t in trd]);g=R[R>0].sum();b=-R[R<0].sum();return g/b if b>0 else 99
out={}
for nm,Bot in [("imp",TrendStackImpatientBot),("king",TrendStackImpatientKingBot)]:
    trd=feed(Bot()); a,ps=acct(trd)
    for t,p in zip(trd,ps): t['p']=p
    out[nm]=(trd,a)
    wr=np.mean([1 if t['Rs']>0 else 0 for t in trd])*100; rc=collections.Counter(t['reason'] for t in trd)
    print(f"{nm:5}: 거래{len(trd)} 승률{wr:.0f}% PF{pf(trd):.2f} | ${a.bal:,.0f}({a.metrics()[0]:+.0f}%) MDD{a.metrics()[1]:.1f}% | {dict(rc)}")
# 분해
def brk(trd,key,vals):
    D=pd.DataFrame(trd)
    for v in vals:
        g=D[D[key]==v]
        if len(g): print(f"    {str(v):<10}: {len(g):>3}건 기여{g['p'].sum()*100:+.0f}%")
for nm in("imp","king"):
    trd=out[nm][0]; print(f"\n[{nm}] 롱숏:");brk(trd,'side',[1,-1]);print(f"[{nm}] 장세:");brk(trd,'feat',['downtrend','range','uptrend']);print(f"[{nm}] 연도:");brk(trd,'year',[2023,2024,2025,2026])
