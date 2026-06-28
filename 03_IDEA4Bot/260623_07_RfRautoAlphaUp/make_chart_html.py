# -*- coding: utf-8 -*-
# [make_chart_html.py] 백테 거래 → Rauto 스마트폰차트 스타일 standalone HTML (+ Pine 복사box). 크롬서 바로 열림.
#   build_html(d1m, T, expo, out, pine_text) = 재사용 함수(bt_report가 호출, 크롬 자동오픈).
#   ★제 데이터 그대로라 항상 정렬(TradingView 심볼/시간대/무기한 불필요). 분할 개별체결=흰십자·롱청/숏분홍·+파랑/-빨강.
import os, sys, json
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd
import trendstack_signal_engine as TS
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "rauto_trades_chart.html")


def _ms(t): return int(pd.Timestamp(t, tz="UTC").value // 10**6)


def build_html(d1m, T, expo, out=OUT, ctf=240, pine_text="", cap=10000.0, title="Rauto 백테 체결"):
    g = TS.resample_tf(d1m[["open", "high", "low", "close"]], ctf)
    tms = (g.index.tz_localize("UTC").astype("int64") // 10**6).tolist()
    px = [[int(t), float(a), float(b), float(c), float(d)] for t, a, b, c, d in
          zip(tms, g.open, g.high, g.low, g.close)]
    trd = []
    for r in T.sort_values("et").itertuples():
        fills = r.fills if isinstance(r.fills, list) else [(r.et, r.entry)]
        trd.append(dict(et=_ms(getattr(r, "et_fill", r.et)), xt=_ms(getattr(r, "xt_fill", r.xt)), ep=float(r.entry), xp=float(r.exit),
                        side=("L" if r.side == 1 else "S"), pnl=round(float(r.R) * 100, 2),
                        qt=round((cap * expo) / float(r.entry), 3),
                        f=[[_ms(t), float(p)] for t, p in fills]))
    H = '''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title><style>
html,body{margin:0;background:#0b0e13;color:#e6edf3;font-family:sans-serif}
#hd{padding:7px 10px;font-size:13px;border-bottom:1px solid #27303a}
.k{color:#8b98a5}.bl{color:#3b82f6}.pk{color:#ff3d8b}
#wrap{position:relative;width:100vw;height:62vh}#cv{width:100%;height:100%;display:block;cursor:crosshair}
#tf{padding:5px 10px;font-size:12px;color:#8b98a5}#tf b{cursor:pointer;color:#7fb6ee;margin-right:8px}
#pbox{padding:6px 10px}#pbox textarea{width:100%;height:18vh;background:#0c0f14;color:#9aa6b2;border:1px solid #27303a;border-radius:6px;font:11px monospace;white-space:pre}
#pbox button{background:#13311f;color:#5fd3a0;border:1px solid #1d9e75;border-radius:6px;padding:6px 12px;font-size:12px;cursor:pointer;margin-bottom:4px}
</style></head><body>
<div id="hd">__TITLE__ · <span class="k">롱</span> <b class="bl">●청색</b> <span class="k">숏</span> <b class="pk">●분홍</b> · 흰십자=분할 개별체결 · <b class="bl">+수익</b>/<b class="pk">−손실</b> <span class="k" id="info"></span></div>
<div id="wrap"><canvas id="cv"></canvas></div>
<div id="tf">TF: <b onclick="setTF(60)">1h</b><b onclick="setTF(240)">4h</b><b onclick="setTF(480)">8h</b><b onclick="setTF(1440)">1D</b> · 드래그=과거 · 더블탭=최신</div>
<div id="pbox"><button onclick="cp()">📋 Pine 스크립트 복사 (TradingView BTCUSDT.P·UTC·4h에 붙여넣기)</button>
<textarea id="pine" readonly></textarea></div>
<script>
var PX=__PX__, TRD=__TRD__, PINE=__PINE__;
document.getElementById('pine').value=PINE;
function cp(){var t=document.getElementById('pine');t.select();document.execCommand('copy');}
var CTF=240,CHOFF=0,CHN=120;
function agg(px,m){if(!px.length)return[];var o=[],c=null,sp=m*60000;for(var j=0;j<px.length;j++){var d=px[j],b=Math.floor(d[0]/sp)*sp;if(!c||c.t!==b){c={t:b,o:d[1],h:d[2],l:d[3],c:d[4]};o.push(c);}else{c.h=Math.max(c.h,d[2]);c.l=Math.min(c.l,d[3]);c.c=d[4];}}return o;}
function p2(v){return(v<10?'0':'')+v;}function dl(ms){var d=new Date(ms);return(d.getUTCFullYear()%100)+'/'+p2(d.getUTCMonth()+1)+'/'+p2(d.getUTCDate());}
function setTF(m){CTF=m;CHOFF=0;draw();}
function draw(){var cv=document.getElementById('cv'),w=document.getElementById('wrap');var cw=w.clientWidth,ch=w.clientHeight;cv.width=cw;cv.height=ch;var g=cv.getContext('2d');g.clearRect(0,0,cw,ch);
 var all=agg(PX,CTF),SP=CTF*60000,N=Math.min(CHN,all.length),mo=Math.max(0,all.length-N);if(CHOFF<0)CHOFF=0;if(CHOFF>mo)CHOFF=mo;
 var end=all.length-CHOFF,vis=all.slice(end-N,end),T0=vis[0].t,T1=vis[vis.length-1].t+SP,padR=54,padB=22,padT=8,padL=4,n=vis.length,CW=(cw-padR-padL)/n;
 var lo=1e18,hi=-1e18;vis.forEach(function(d){lo=Math.min(lo,d.l);hi=Math.max(hi,d.h);});var rng=(hi-lo)||1;
 function py(v){return padT+(hi-v)/rng*(ch-padB-padT);}function pxi(i){return padL+(i+0.5)*CW;}function pxt(t){return padL+((t-T0)/SP)*CW;}
 g.strokeStyle='#1b212a';g.fillStyle='#6b7480';g.font='10px sans-serif';g.textAlign='left';
 for(var q=0;q<=3;q++){var y=padT+q*((ch-padB-padT)/3);g.beginPath();g.moveTo(padL,y);g.lineTo(cw-padR,y);g.stroke();g.fillText((hi-rng*q/3).toFixed(0),cw-padR+4,y+3);}
 g.textAlign='center';for(var t=0;t<=3;t++){var ix=Math.round(t*(n-1)/3);g.fillText(dl(vis[ix].t),Math.min(Math.max(pxi(ix),24),cw-padR-24),ch-padB+13);}
 var bw=Math.max(1.5,CW*0.6);
 vis.forEach(function(d,i){var u=d.c>=d.o;g.strokeStyle=u?'#26a69a':'#ef5350';g.fillStyle=u?'#26a69a':'#ef5350';g.beginPath();g.moveTo(pxi(i),py(d.h));g.lineTo(pxi(i),py(d.l));g.stroke();var yb=py(Math.max(d.o,d.c)),hb=Math.max(1,Math.abs(py(d.o)-py(d.c)));g.fillRect(pxi(i)-bw/2,yb,bw,hb);});
 function near(t){var b=0,bs=1e18;for(var z=0;z<vis.length;z++){var dt=Math.abs(vis[z].t+SP/2-t);if(dt<bs){bs=dt;b=z;}}return b;}
 function cl(p,c){return Math.max(c.l,Math.min(c.h,p));}
 var sh=0;TRD.filter(function(tr){return tr.xt>=T0&&tr.et<T1;}).forEach(function(tr){sh++;var ie=near(tr.et),ix=near(tr.xt);if(ix<ie)ix=ie;var ce=vis[ie],cx=vis[ix];
  var Xe=pxi(ie),Xx=pxi(ix),Ye=py(cl(tr.ep,ce)),Yx=py(cl(tr.xp,cx)),col=tr.side==='S'?'#ff3d8b':'#3b82f6';
  g.strokeStyle=col;g.lineWidth=0.8;g.setLineDash([]);g.beginPath();g.moveTo(Xe,Ye);g.lineTo(Xx,Ye);g.stroke();
  g.strokeStyle='#fff';g.lineWidth=1;g.setLineDash([4,3]);g.beginPath();g.moveTo(Xx,Ye);g.lineTo(Xx,Yx);g.stroke();g.setLineDash([]);
  var hl=Math.max(5,CW*0.3+3);
  (tr.f||[]).forEach(function(fp){var fb=near(fp[0]),fc=vis[fb];if(!fc)return;var fx=pxi(fb),fy=py(cl(fp[1],fc));g.strokeStyle='#fff';g.lineWidth=0.5;g.beginPath();g.moveTo(fx-hl,fy);g.lineTo(fx+hl,fy);g.moveTo(fx,fy-hl);g.lineTo(fx,fy+hl);g.stroke();});
  g.strokeStyle='#fff';g.lineWidth=0.5;g.beginPath();g.moveTo(Xx-hl,Yx);g.lineTo(Xx+hl,Yx);g.moveTo(Xx,Yx-hl);g.lineTo(Xx,Yx+hl);g.stroke();
  g.font='bold 8px sans-serif';g.textAlign='left';g.fillStyle=col;g.fillText((tr.side==='S'?'S':'L')+tr.ep.toFixed(0)+'@'+tr.qt,Xe+2,Ye+11);
  if(tr.pnl!=null){g.textAlign='right';g.fillStyle=tr.pnl<0?'#ef5350':'#3b82f6';g.fillText((tr.pnl>0?'+':'')+tr.pnl+'%',Xx,Math.min(Ye,Yx)-4);}});
 document.getElementById('info').textContent=' · '+sh+'거래 · '+dl(T0)+'~'+dl(T1);cv._m={CW:CW};}
(function(){var cv=document.getElementById('cv'),D=null;function gx(e){return e.touches?e.touches[0].clientX:e.clientX;}
 function dn(e){D={x:gx(e),o:CHOFF};}function up(){D=null;}function mv(e){if(!D||!cv._m)return;var r=cv.getBoundingClientRect(),s=cv.width/r.width;CHOFF=D.o+Math.round((gx(e)-D.x)*s/cv._m.CW);draw();e.preventDefault&&e.preventDefault();}
 cv.addEventListener('mousedown',dn);window.addEventListener('mouseup',up);cv.addEventListener('mousemove',mv);
 cv.addEventListener('touchstart',dn);window.addEventListener('touchend',up);cv.addEventListener('touchmove',mv,{passive:false});
 var lt=0;cv.addEventListener('click',function(){var t=Date.now();if(t-lt<300){CHOFF=0;draw();}lt=t;});
 window.addEventListener('resize',draw);draw();})();
</script></body></html>'''
    H = (H.replace("__TITLE__", title).replace("__PX__", json.dumps(px))
         .replace("__TRD__", json.dumps(trd, ensure_ascii=False)).replace("__PINE__", json.dumps(pine_text, ensure_ascii=False)))
    open(out, "w", encoding="utf-8").write(H)
    return out


def main():
    from fib_replay_1m import load_1m, load_funding
    import bt_full as B, make_pine as MP, json as J
    bp = J.load(open(os.path.join(HERE, "best_params_full.json")))
    d1m = load_1m(); fund = load_funding()
    T = B.gen_trades(d1m, fund, bp["sig_tf"], bp["pivot_tf"], bp["N"], (bp["fib1"], bp["fib2"], bp["fib3"]),
                     bp["init_atr_mult"], er_gate=bp["er_gate"], capture_fills=True)
    expo = bp["size_pct"] / 100.0 * bp["lev"]
    MP.build_pine(T, expo)
    out = build_html(d1m, T, expo, pine_text=open(MP.OUT, encoding="utf-8").read())
    print(f"[저장] {out}")


if __name__ == "__main__":
    main()
