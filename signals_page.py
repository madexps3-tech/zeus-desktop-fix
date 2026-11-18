"""Live signals page. The chart is the same market feed. A wait can be overridden."""

from __future__ import annotations

import json
import threading
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any

from aiohttp import web

from zeus3.contracts.market_data import Timeframe
from zeus3.v19.signals_engine import (
    CHARTS,
    FUTURES_ROOTS,
    PAIRS,
    POSITION_NAMES,
    _session_name,
    align_ladder,
    build_rows,
    liquidity,
    mark_taken,
    manage_decision,
    place_yen,
    range_dip,
    reaction,
    record,
    session_levels,
)

_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_LOCK = threading.Lock()
_ORDER_BUSY = threading.Event()
_LAST: dict[str, dict[str, Any]] = {}

LABELS = {
    "XAUUSD": "GOLD",
    "XAGUSD": "SILVER",
    "NAS100": "NASDAQ",
    "BTCUSD": "BITCOIN",
    "EURUSD": "EURO",
    "USDJPY": "USDJPY",
    "WTI": "OIL",
}

PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<title>ZEUS Signals</title>
<style>
:root{--bg:#071019;--panel:#0c1824;--line:#24384c;--text:#e7eef5;--muted:#8ea3b8;--good:#67d6a3;--bad:#ef7f88;--warn:#e9c66b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Arial,sans-serif}
header{display:flex;gap:10px;align-items:center;padding:10px 14px;border-bottom:1px solid var(--line);background:#08131c}
a{color:#9fb3c8;text-decoration:none;font-size:12px;font-weight:800}
h1{font-size:16px;margin:0;letter-spacing:.08em}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
button,select{background:#10202e;color:var(--text);border:1px solid #34506a;border-radius:6px;padding:7px 10px;font-weight:700}
button.on{border-color:var(--good);color:var(--good)}
main{display:grid;grid-template-columns:1fr 320px;gap:10px;padding:10px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px}
canvas{width:100%;height:520px;background:#050b11;border-radius:6px;cursor:crosshair}
table{width:100%;border-collapse:collapse;font:12px Consolas,monospace}
th{color:var(--muted);text-align:left;font-size:11px;padding:6px}
td{padding:6px;border-top:1px solid #1a2c3c}
tr.pick{outline:1px solid var(--warn)}
.good{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}.muted{color:var(--muted)}
.flow b{display:block;font-size:16px;margin:2px 0 10px}
.quotes{display:flex;gap:10px;align-items:stretch;margin:0 0 8px}
.qbox{border:1px solid #1e3344;border-radius:8px;padding:8px 16px;min-width:140px;background:#071018}
.qbox .k{font-size:11px;letter-spacing:.08em;color:#8ea3b8}
.qbox .v{font:700 30px Consolas,monospace;margin-top:2px}
.qbox.bid .v{color:#e9c66b}
.qbox.ask .v{color:#56a8ff}
.qbox.mid .v{color:#e7eef5;font-size:22px}
#status,#research,#alerts{font:12px Consolas,monospace;white-space:pre-wrap}
#alerts{max-height:88px;overflow:auto;margin:6px 0}
.pairq{padding:7px 0;border-top:1px solid #1a2c3c;cursor:pointer}
.pairq b{display:block;font-size:12px;letter-spacing:.04em}
.pairq .sub{display:block;color:var(--muted);font:11px Consolas,monospace}
</style></head><body>
<header>
  <a href="/v19/chart">CHART</a><a href="/v19/trade-desk">TRADE DESK</a><a href="/v19/shadow">SHADOW</a>
  <h1>SIGNALS</h1>
  <span class="muted" id="clock"></span>
</header>
<div class="row" style="padding:10px">
  <span id="pairs"></span>
  <span id="charts"></span>
  <button onclick="zoom(-20)">ZOOM IN</button>
  <button onclick="zoom(20)">ZOOM OUT</button>
  <button onclick="fit()">FIT</button>
  <button id="zones" onclick="toggleZones()">ZONES ON</button>
  <label>RISK % <input id="risk" value="2" style="width:72px" oninput="if(data)paint()"></label>
  <button id="manage" data-on="0" onclick="toggleManage()">MANAGE OFF</button>
  <span class="muted">A signal is a confirmed 1-minute candle. The stop must clear 10 times the spread. TRADE sends one market order to the logged-in MT5 account.</span>
</div>
<main>
  <section class="card">
    <div class="quotes">
      <div class="qbox mid"><div class="k" id="qsym">PAIR</div><div class="v" id="qpair">—</div></div>
      <div class="qbox bid"><div class="k">BID</div><div class="v" id="qbid">—</div></div>
      <div class="qbox ask"><div class="k">ASK</div><div class="v" id="qask">—</div></div>
      <div class="qbox mid"><div class="k">SPREAD</div><div class="v" id="qspread">—</div></div>
    </div>
    <canvas id="cv" width="1100" height="520"></canvas>
    <div id="status" class="muted"></div>
    <div class="muted">WATCHER</div>
    <div id="alerts" class="muted">Quiet until a new signal on one of the seven pairs.</div>
    <table id="grid"></table>
    <div id="research" class="muted" style="margin-top:8px"></div>
  </section>
  <aside>
    <section class="card">
      <div class="muted">SEVEN PAIRS</div>
      <div id="board"></div>
    </section>
    <section class="card flow" id="flow" style="margin-top:10px"></section>
    <section class="card" style="margin-top:10px">
      <div class="muted">THIS PAIR ON THE BROKER</div>
      <div id="positions"></div>
    </section>
  </aside>
</main>
<script>
const PAIRS=[["XAUUSD","GOLD"],["XAGUSD","SILVER"],["NAS100","NASDAQ"],["BTCUSD","BITCOIN"],["EURUSD","EURO"],["USDJPY","USDJPY"],["WTI","OIL"]];
const CHARTS=["M1","M5","M15","M30","H1","H4","D1"];
const LEVEL_COLOR={ASIA:"#7aa2d6",LONDON:"#e9c66b",NEW_YORK:"#67d6a3",YESTERDAY:"#c084fc",LATE:"#8ea3b8"};
let symbol=localStorage.getItem("sig_symbol")||"XAUUSD";
let chart=localStorage.getItem("sig_chart")||"M5";
let data=null, visible=80, pan=0, drag=null, cursor=null, selected=chart, pickedRow="INTRADAY";
let busy=false, timer=null, control=null, holdStatusUntil=0, loadId=0;
const saved={};
let showZones=localStorage.getItem("sig_zones")!=="0";
function $(id){return document.getElementById(id)}
function setStatus(text, holdMs){$("status").textContent=text; holdStatusUntil=Date.now()+(holdMs||0)}
function buttons(){
  $("pairs").innerHTML=PAIRS.map(p=>`<button class="${p[0]===symbol?"on":""}" onclick="setPair('${p[0]}')">${p[1]}</button>`).join("");
  $("charts").innerHTML=CHARTS.map(c=>`<button class="${c===chart?"on":""}" onclick="setChart('${c}')">${c}</button>`).join("");
}
function remember(j){ if(j&&j.symbol)saved[j.symbol+"|"+(j.chart||chart)]=j; }
function setPair(s){
  symbol=s; localStorage.setItem("sig_symbol",s); pan=0;
  const kept=saved[s+"|"+chart];
  if(kept){ data=kept; draw(); paint(); }
  load(true);
}
function setChart(c){
  chart=c; selected=c; localStorage.setItem("sig_chart",c); pan=0;
  const kept=saved[symbol+"|"+c];
  if(kept){ data=kept; draw(); paint(); }
  load(true);
}
function zoom(d){visible=Math.max(30,Math.min(240,visible+d));draw()}
function fit(){visible=Math.max(30,(data&&data.candles||[]).length||80);pan=0;draw()}
function toggleZones(){
  showZones=!showZones;
  localStorage.setItem("sig_zones", showZones?"1":"0");
  const button=$("zones");
  if(button){button.textContent=showZones?"ZONES ON":"ZONES OFF";button.className=showZones?"on":""}
  draw();
}
async function load(force){
  if(document.visibilityState==="hidden")return;
  if(busy && !force)return;
  const id=++loadId;
  const want=symbol, wantChart=chart;
  if(control)control.abort();
  control=new AbortController();
  busy=true;
  buttons();
  try{
    const r=await fetch("/api/v19/signals?symbol="+want+"&chart="+wantChart,{signal:control.signal});
    const j=await r.json();
    if(id!==loadId || want!==symbol || wantChart!==chart)return;
    if(!r.ok||!j.ok)throw Error(j.message||("HTTP "+r.status));
    data=j; remember(j); $("clock").textContent=j.server_time||"";
    const manage=$("manage");
    if(manage){
      manage.dataset.on=j.manage?"1":"0";
      manage.textContent=j.manage?"MANAGE ON":"MANAGE OFF";
    }
    draw(); paint(); consider(j);
  }catch(e){
    if(e.name!=="AbortError" && id===loadId)$("status").textContent="CHART ERROR · "+e.message;
  }finally{ if(id===loadId)busy=false }
}
async function toggleManage(){
  const button=$("manage");
  const on=button.dataset.on!=="1";
  button.disabled=true;
  try{
    const r=await fetch("/api/v19/signals/manage",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({on:on})});
    const j=await r.json();
    if(!r.ok||!j.ok)throw Error(j.message||"manage was not saved");
    button.dataset.on=j.on?"1":"0";
    button.textContent=j.on?"MANAGE ON":"MANAGE OFF";
    $("status").textContent=j.on?"MANAGE ON. The stop moves. Banking stays a button.":"MANAGE OFF. The ticket is left alone.";
  }catch(e){
    $("status").textContent="MANAGE NOT SAVED · "+e.message;
  }finally{ button.disabled=false; }
}
function windowRows(){
  const all=(data&&data.candles)||[];
  const count=Math.min(visible, all.length);
  const maxPan=Math.max(0, all.length-count);
  pan=Math.max(0, Math.min(pan, maxPan));
  const end=all.length-pan;
  return all.slice(Math.max(0,end-count), end);
}
function px(v){
  const n=Number(v);
  if(!isFinite(n))return "—";
  const a=Math.abs(n);
  const d=a>=100?2:a>=10?3:a>=1?5:5;
  return n.toFixed(d);
}
function paintQuote(){
  const q=(data&&data.quote)||{};
  const bid=Number(q.bid), ask=Number(q.ask);
  $("qsym").textContent=symbol+" · "+chart;
  $("qpair").textContent=symbol;
  $("qbid").textContent=px(bid);
  $("qask").textContent=px(ask);
  $("qspread").textContent=(isFinite(bid)&&isFinite(ask))?px(ask-bid):"—";
}
function draw(){
  const cv=$("cv"), width=Math.max(700,(cv.parentElement.clientWidth||1100)-8);
  cv.width=width; cv.height=520;
  const ctx=cv.getContext("2d"), rows=windowRows();
  const plotL=56, plotR=width-78, plotT=48, plotB=490;
  ctx.clearRect(0,0,cv.width,cv.height);
  ctx.fillStyle="#050b11"; ctx.fillRect(0,0,cv.width,cv.height);
  ctx.font="12px Consolas,monospace";
  if(!rows.length){ctx.fillStyle="#8ea3b8";ctx.fillText("No candles for "+symbol+" "+chart, 20, 40);return}
  let lo=Infinity, hi=-Infinity;
  rows.forEach(b=>{lo=Math.min(lo,b.low);hi=Math.max(hi,b.high)});
  const q=data.quote||{};
  if(q.bid!=null){lo=Math.min(lo,Number(q.bid));hi=Math.max(hi,Number(q.bid))}
  const span=Math.max(hi-lo, 0.00001);
  const row=(data.rows||[]).find(r=>r.chart===pickedRow&&r.entry!=null);
  if(row&&Math.abs(row.entry-((lo+hi)/2))<span*1.2){
    lo=Math.min(lo,row.stop,row.target,row.entry);hi=Math.max(hi,row.stop,row.target,row.entry)
  }
  const levels=(data.pools)||[];
  const pad=(hi-lo)*0.08||span*0.08; lo-=pad; hi+=pad;
  const y=p=>plotT+((hi-p)/(hi-lo))*(plotB-plotT);
  const step=(plotR-plotL)/Math.max(1,rows.length);
  const zoneButton=$("zones");
  if(zoneButton){zoneButton.textContent=showZones?"ZONES ON":"ZONES OFF";zoneButton.className=showZones?"on":""}
  if(showZones){
    const view=hi-lo;
    const bidNow=Number((data.quote||{}).bid);
    const bandFor=span=>Math.max(view*0.012, Math.min(view*0.04, Math.abs(span)*0.08));
    const paintZone=(price, height, name, color, x0)=>{
      const top=price+height/2, bot=price-height/2;
      if(top<lo||bot>hi) return;
      const yTop=y(Math.min(hi, top)), yBot=y(Math.max(lo, bot));
      const boxTop=Math.min(yTop,yBot), boxH=Math.max(3, Math.abs(yBot-yTop));
      ctx.fillStyle=color; ctx.globalAlpha=0.2;
      ctx.fillRect(x0, boxTop, Math.max(8, plotR-x0), boxH);
      ctx.globalAlpha=1; ctx.strokeStyle=color;
      ctx.strokeRect(x0, boxTop, Math.max(8, plotR-x0), boxH);
      ctx.fillStyle=color;
      ctx.fillText(name, x0+4, Math.max(plotT+11, boxTop-3));
    };
    levels.filter(level=>level.kind==="RANGE").forEach(level=>{
      const high=Number(level.high), lowP=Number(level.low);
      const color=LEVEL_COLOR[(level.name||"").split(" ")[0]]||"#8ea3b8";
      const band=bandFor(high-lowP);
      paintZone(high, band, level.name+" HIGH", color, plotL);
      paintZone(lowP, band, level.name+" LOW", color, plotL);
    });
    const swings=levels.filter(level=>level.kind==="HIGH"||level.kind==="LOW");
    swings.sort((a,b)=>Math.abs(Number(a.price)-bidNow)-Math.abs(Number(b.price)-bidNow));
    swings.slice(0,6).forEach(level=>{
      let x0=plotL;
      if(level.time){
        const stamp=Date.parse(level.time);
        if(isFinite(stamp)){
          let idx=0;
          for(let i=0;i<rows.length;i++){
            const barTime=Date.parse(rows[i].time);
            if(!isFinite(barTime)||barTime<stamp) idx=i;
            else {idx=i; break}
          }
          x0=plotL+idx*step;
        }
      }
      const span=Math.abs(Number(level.high)-Number(level.low));
      const color=level.kind==="LOW"?"#67d6a3":"#ef7f88";
      paintZone(Number(level.price), bandFor(span), level.name, color, x0);
    });
    ctx.globalAlpha=1;
  }
  const flowNow=data.flow||{};
  [["#f0c956", flowNow.poc, "POC"], ["#8ea3b8", flowNow.vah, "VALUE HIGH"], ["#8ea3b8", flowNow.val, "VALUE LOW"]].forEach(line=>{
    const price=Number(line[1]);
    if(!isFinite(price)||price<lo||price>hi) return;
    ctx.setLineDash([2,4]); ctx.strokeStyle=line[0]; ctx.beginPath(); ctx.moveTo(plotL,y(price)); ctx.lineTo(plotR,y(price)); ctx.stroke();
    ctx.setLineDash([]); ctx.fillStyle=line[0]; ctx.fillText(line[2]+" "+price, plotL+4, y(price)-4);
  });
  if(row){
    ctx.setLineDash([4,4]);
    [["#67d6a3",row.entry,"ENTRY"],["#ef7f88",row.stop,"STOP"],["#e9c66b",row.target,"TARGET "+row.r+"R"]].forEach(line=>{
      if(line[1]<lo||line[1]>hi)return;
      ctx.strokeStyle=line[0]; ctx.beginPath(); ctx.moveTo(plotL,y(line[1])); ctx.lineTo(plotR,y(line[1])); ctx.stroke();
      ctx.fillStyle=line[0]; ctx.fillText(line[2]+" "+line[1], plotR-170, y(line[1])-4);
    });
    ctx.setLineDash([]);
  }
  const ladder=(data.ladder&&data.ladder.shown)?data.ladder:{levels:[],icebergs:[]};
  ladder.levels.forEach(level=>{
    if(level.price<lo||level.price>hi)return;
    const yy=y(level.price);
    const bid=Number(level.bid_contracts)||0, ask=Number(level.ask_contracts)||0;
    ctx.fillStyle="#35597a"; ctx.fillRect(plotR+4, yy-1, Math.min(28, bid), 2);
    ctx.fillStyle="#7a3b46"; ctx.fillRect(plotR+34, yy-1, Math.min(28, ask), 2);
  });
  ladder.icebergs.forEach(item=>{
    if(item.price<lo||item.price>hi)return;
    ctx.fillStyle=item.side==="BUY"?"#67d6a3":"#ef7f88";
    ctx.fillText("ICE "+item.side+" "+item.price, plotL+4, y(item.price)+12);
  });
  rows.forEach((b,i)=>{
    const x=plotL+i*step+step*0.5, up=b.close>=b.open;
    ctx.strokeStyle=up?"#67d6a3":"#ef7f88"; ctx.fillStyle=ctx.strokeStyle;
    ctx.beginPath(); ctx.moveTo(x,y(b.high)); ctx.lineTo(x,y(b.low)); ctx.stroke();
    const top=y(Math.max(b.open,b.close)), bot=y(Math.min(b.open,b.close));
    ctx.fillRect(x-Math.max(2,step*0.28), top, Math.max(4,step*0.56), Math.max(1,bot-top));
    if(i%Math.ceil(rows.length/6)===0){
      ctx.fillStyle="#8ea3b8";
      ctx.fillText(String(b.time||"").slice(5,16).replace("T"," "), x-24, 512);
    }
  });
  ctx.fillStyle="#8ea3b8";
  for(let i=0;i<=4;i++){
    const price=hi-(hi-lo)*i/4;
    ctx.fillText(price.toFixed(price>100?2:5), plotR+4, y(price)+4);
  }
  const picked=(data.rows||[]).find(r=>r.chart===pickedRow)||{};
  const market=(data&&data.market)||picked.market||"";
  const feed=data.feed||{};
  ctx.fillStyle=feed.quote_stale?"#ef7f88":"#e7eef5";
  ctx.fillText((feed.quote_stale?"STALE":"LIVE "+(feed.quote_age??"—")+"s")+"   "+(feed.session||""), 12, 18);
  if(isFinite(Number(q.bid))&&Number(q.bid)>=lo&&Number(q.bid)<=hi){
    const yy=y(Number(q.bid));
    ctx.strokeStyle="#e9c66b"; ctx.lineWidth=2;
    ctx.beginPath(); ctx.moveTo(plotL,yy); ctx.lineTo(plotR,yy); ctx.stroke();
    ctx.lineWidth=1; ctx.fillStyle="#e9c66b"; ctx.fillText("BID "+px(q.bid), plotR-120, yy-6);
  }
  ctx.fillStyle="#e9c66b";
  ctx.fillText((market||"")+"   "+(picked.state||"")+"   "+(feed.session||(data.sessions||{}).current||"")+(feed.candles_stale?"   CANDLES OLD":""), 12, 36);
  if(cursor && cursor.x>=plotL && cursor.x<=plotR && cursor.y>=plotT && cursor.y<=plotB){
    const price=hi-((cursor.y-plotT)/(plotB-plotT))*(hi-lo);
    const index=Math.max(0, Math.min(rows.length-1, Math.floor((cursor.x-plotL)/step)));
    const bar=rows[index];
    ctx.strokeStyle="#9fb3c8"; ctx.setLineDash([3,3]);
    ctx.beginPath(); ctx.moveTo(plotL, cursor.y); ctx.lineTo(plotR, cursor.y); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cursor.x, plotT); ctx.lineTo(cursor.x, plotB); ctx.stroke();
    ctx.setLineDash([]);
    const label=px(price);
    ctx.fillStyle="#102033"; ctx.fillRect(plotR+2, cursor.y-9, 74, 18);
    ctx.fillStyle="#e9c66b"; ctx.fillText(label, plotR+6, cursor.y+4);
    if(bar){
      const when=String(bar.time||"").slice(5,16).replace("T"," ");
      const info=when+"   O "+px(bar.open)+"  H "+px(bar.high)+"  L "+px(bar.low)+"  C "+px(bar.close);
      ctx.fillStyle="#e7eef5"; ctx.fillText(info, plotL, plotB+16);
    }
  }
  paintQuote();
}
function researchLine(title, book){
  const bits=Object.keys(book||{}).map(chart=>{
    const x=book[chart];
    return chart+" "+(x.wins||0)+" wins, "+(x.losses||0)+" losses, "+(x.open||0)+" open, "+(x.be_wins||0)+" be-wins, "+(x.be_scratches||0)+" scratch";
  });
  return bits.length?title+" · "+bits.join(" · "):title+" · none yet";
}
function round2(n){return Math.round(n*100)/100}
function roundDist(n){
  const a=Math.abs(n);
  if(a>=50) return String(Math.round(n));
  if(a>=1) return String(round2(n));
  return String(Math.round(n*100000)/100000);
}
function moneyLine(row, account){
  if(!row||row.entry==null||row.stop==null) return row&&row.harvest||"—";
  const entry=Number(row.entry), stop=Number(row.risk_stop!=null?row.risk_stop:row.stop);
  const riskDist=Math.abs(entry-stop);
  const risk=Number($("risk").value);
  const acct=account||(data&&data.account)||{};
  const balance=Number(acct.equity||acct.balance);
  const targets=(row.targets&&row.targets.length)?row.targets:(row.target!=null?[row.target]:[]);
  if(!(riskDist>0)||!targets.length) return row.harvest||"—";
  return targets.map((price,i)=>{
    const reward=Math.abs(Number(price)-entry);
    const mult=round2(reward/riskDist);
    const pct=(isFinite(risk)&&risk>0)?round2(risk*mult):null;
    const cash=(pct!=null&&isFinite(balance)&&balance>0)?Math.round(balance*pct/100):null;
    const ratio=mult.toFixed(2)+"R";
    const cashText=cash==null?"":" $"+cash;
    return "T"+(i+1)+" "+ratio+cashText;
  }).join(" · ");
}
function seenBag(){
  try{return JSON.parse(sessionStorage.getItem("sig_seen_alerts")||"{}")}catch(e){return {}}
}
function remember(key){
  const bag=seenBag();
  bag[key]=Date.now();
  const keys=Object.keys(bag);
  if(keys.length>200) delete bag[keys[0]];
  sessionStorage.setItem("sig_seen_alerts", JSON.stringify(bag));
}
function speak(text){
  const box=$("alerts");
  const line=new Date().toISOString().slice(11,19)+" "+text;
  const prior=(box.textContent||"").split("\n").filter(Boolean);
  box.textContent=[line].concat(prior).slice(0,8).join("\n");
  if(window.Notification&&Notification.permission==="granted"){
    try{new Notification("ZEUS",{body:text})}catch(e){}
  }
}
let board={};
function boardLine(payload){
  const rows=(payload&&payload.rows)||[];
  const rank={INTRADAY:0,INTERDAY:1,SCALP:2,SWING:3,ICEBERG:4};
  const live=rows.filter(r=>rank[r.chart]!=null);
  const ranked=live.filter(r=>r.side&&r.entry!=null).sort((a,b)=>rank[a.chart]-rank[b.chart]);
  const hit=ranked.find(r=>r.tradeable)||ranked.find(r=>r.state!=="SHOWN");
  if(hit){
    const money=String(moneyLine(hit, payload.account)).split(" · ")[0];
    return {kind:"SIGNAL", side:hit.side, text:hit.chart+" "+hit.side+" "+px(hit.entry), sub:"stop "+px(hit.stop)+" · "+money};
  }
  const coming=live.find(r=>r.coming&&r.coming.side);
  if(coming) return {kind:"INCOMING", side:coming.coming.side, text:coming.chart+" "+coming.coming.side+" into "+px(coming.coming.zone), sub:"not a trade yet"};
  return {kind:"QUIET", text:"quiet", sub:""};
}
function paintBoard(){
  const box=$("board");
  if(!box) return;
  box.innerHTML=PAIRS.map(p=>{
    const item=board[p[0]]||{kind:"QUIET", text:"reading", sub:""};
    const tone=item.kind==="SIGNAL"?(item.side==="BUY"?"good":"bad"):(item.kind==="INCOMING"?"warn":"muted");
    return `<div class="pairq" onclick="setPair('${p[0]}')"><b class="${tone}">${p[1]} · ${item.text}</b>${item.sub?`<span class="sub">${item.sub}</span>`:""}</div>`;
  }).join("");
}
function consider(payload){
  if(!payload||!payload.ok) return;
  const name=payload.label||payload.symbol;
  const bag=seenBag();
  (payload.rows||[]).forEach(row=>{
    const coming=row.coming;
    if(coming&&coming.side){
      const same=(payload.rows||[]).some(other=>other.side===coming.side&&other.entry!=null&&Math.abs(Number(other.zone)-Number(coming.zone))<1e-6);
      const key="C|"+payload.symbol+"|"+row.chart+"|"+coming.side+"|"+coming.zone;
      if(!same&&!bag[key]){
        remember(key);
        speak(name+" "+row.chart+" "+coming.side+" coming into "+coming.zone+". Not a trade yet.");
      }
    }
    let announced=false;
    if(row.tradeable&&row.entry!=null){
      const key="R|"+payload.symbol+"|"+row.chart+"|"+row.side+"|"+row.entry+"|"+row.time;
      if(!bag[key]){
        remember(key);
        announced=true;
        speak(name+" "+row.chart+" "+row.side+" confirmed. Entry "+row.entry+" stop "+row.stop+" next "+((row.targets&&row.targets[0])||row.target)+". "+moneyLine(row, payload.account));
      }
    }
    if(row.guide&&!announced&&!(row.chart==="INTERDAY"&&!row.tradeable)){
      const key="G|"+payload.symbol+"|"+row.chart+"|"+row.guide;
      if(!bag[key]){
        remember(key);
        speak(name+" "+row.chart+" "+(row.side||"")+". "+row.guide);
      }
    }
  });
}
function paint(){
  if(data&&data.symbol){board[data.symbol]=boardLine(data);paintBoard()}
  const rows=data.rows||[];
  $("grid").innerHTML="<tr><th>ROW</th><th>STATE</th><th>SIDE</th><th>ENTRY</th><th>STOP</th><th>TARGET</th><th>HARVEST</th><th>REASON</th><th></th></tr>"+
    rows.map(r=>{
      const side=r.side?`<span class="${r.side==="BUY"?"good":"bad"}">${r.side}</span>`:"—";
      const targets=(r.targets&&r.targets.length)?r.targets.join(" · "):(r.target??"—");
      const harvest=moneyLine(r);
      const button=r.tradeable?`<button onclick="event.stopImmediatePropagation();trade('${r.chart}')">TRADE</button>`:"";
      return `<tr class="${r.chart===pickedRow?"pick":""}" onclick="pickedRow='${r.chart}';paint()"><td>${r.chart}</td><td>${r.state||"—"}</td><td>${side}</td><td>${r.entry??"—"}</td><td>${r.stop??"—"}</td><td>${targets}</td><td>${harvest}</td><td>${r.note||r.reason||"—"}</td><td>${button}</td></tr>`;
    }).join("");
  const f=data.flow||{}, ladder=data.ladder||{};
  $("flow").innerHTML=`<div class="muted">ORDER FLOW · THIS PAIR</div>
    <div>DELTA 5s</div><b>${f.delta_5s??"not in this book"}</b>
    <div>DELTA 60s</div><b>${f.delta_60s??"not in this book"}</b>
    <div>WHO IS HITTING</div><b class="${f.stepping==="BUYERS"?"good":(f.stepping==="SELLERS"?"bad":"")}">${f.stepping||"—"}</b>
    <div>VALUE HIGH</div><b>${f.vah??"not in the file"}</b>
    <div>POC</div><b>${f.poc??"not in the file"}</b>
    <div>VALUE LOW</div><b>${f.val??"not in the file"}</b>
    <div>ABSORPTION</div><b>${f.absorption?"YES":"no"}</b>
    <div>ICEBERG</div><b>${f.iceberg_price!=null?("YES · "+f.iceberg_side+" "+f.iceberg_price):(f.iceberg?"YES · no price":"no")}</b>
    <div>PULLED</div><b>${f.pulled?"YES · no price":"no"}</b>
    <div>SWEEP</div><b>${f.sweep_consumed?"YES · no price":"no"}</b>
    <div class="muted">${ladder.shown?"Ladder shifted by "+ladder.shift+". Not an entry.":(ladder.reason==="NO_LADDER"?"Ladder is not in the file yet.":"Ladder not drawn. "+(ladder.reason||""))}</div>
    <div class="muted">${f.note||""}</div>`;
  const pos=data.positions||[];
  $("positions").innerHTML=positionBox(pos);
  const research=data.research||{};
  const openBits=(research.open||[]).filter(x=>x.chart==="INTRADAY"||x.chart==="SWING"||x.chart==="ICEBERG"||x.chart==="INTERDAY"||x.chart==="SCALP").map(x=>x.chart+" "+x.side+" went "+(x.mfe??0)+" before turning");
  $("research").textContent=(openBits.length?("OPEN · "+openBits.join(" · ")):"No open signal on this pair.")+"\nTAKEN is an order this page sent. The win and loss counts stay in the log.";
  const row=(data.rows||[]).find(r=>r.chart===pickedRow);
  const news=data.news||{};
  const feed=data.feed||{};
  const newsLine=news.line||"NO CALENDAR";
  const market=data.market||(row&&row.market)||"";
  if(Date.now()>=holdStatusUntil) $("status").textContent=(market?market+" · ":"")+(feed.line?feed.line+"\n":"")+(row&&row.note?row.note:"")+(newsLine?"\n"+newsLine:"");
}
function isProtected(position){
  const sl=Number(position.stop_loss), entry=Number(position.price_open);
  if(!(sl>0)||!(entry>0)) return false;
  return position.side==="SELL"?sl<=entry:sl>=entry;
}
async function closeTicket(ticket){
  const r=await fetch("/api/v3-physical-execution/manage",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({owner_approved:true,fast_ack:true,ticket:ticket,action:"CLOSE",reason:"SIGNALS PAGE"})});
  const j=await r.json();
  if(!r.ok||!((j.management||{}).ok)) throw Error(((j.management||{}).reason)||j.message||"the close was rejected");
}
async function trade(chartName){
  const row=(data.rows||[]).find(r=>r.chart===chartName&&r.tradeable);
  if(!row){setStatus("NOT SENT · this row has no order. A stop that price has already passed stays on the row with no button.", 8000);return}
  const quote=(data&&data.quote)||{};
  const bid=Number(quote.bid), ask=Number(quote.ask);
  if(row.side==="SELL" && !(row.stop>ask && row.target<bid)){setStatus("NOT SENT · a sell stop must be above the live ask, and the target below the bid. Price has already gone through this one.", 12000);return}
  if(row.side==="BUY" && !(row.stop<bid && row.target>ask)){setStatus("NOT SENT · a buy stop must be below the live bid, and the target above the ask. Price has already gone through this one.", 12000);return}
  const risk=Number($("risk").value);
  if(!isFinite(risk)||risk<=0){setStatus("NOT SENT · set the risk percent", 8000);return}
  const opens=data.positions||[];
  const same=opens.filter(p=>p.side===row.side);
  const opposite=opens.filter(p=>p.side!==row.side);
  let msg="Send a MARKET "+row.side+" on "+symbol+"?\nStop "+row.stop+"\nTarget "+row.target+"\n"+row.note+"\nThis goes to the MT5 account that is logged in.";
  if(same.length) msg="A "+row.side+" is already open. Send another?\nStop "+row.stop+"\nTarget "+row.target+"\nThe open trade stays.";
  else if(opposite.length) msg="A "+opposite[0].side+" is still open. Send this "+row.side+" as well?\nStop "+row.stop+"\nTarget "+row.target+"\nThe open trade stays.";
  if(!confirm(msg))return;
  setStatus("SENDING...", 20000);
  const started=performance.now();
  try{
    await fetch("/api/v19/signals/priority",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({active:true})}).catch(()=>{});
    const r=await fetch("/api/v19/owner-order/submit",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({
      owner_approved:true,symbol:symbol,timeframe:row.chart==="SWING"?"H4":"M1",order_type:row.side==="BUY"?"MARKET_BUY":"MARKET_SELL",
      entry:null,stop:row.stop,targets:[row.target],requested_risk_pct:risk,horizon_lane:"INTRADAY",
      owner_note:"SIGNALS PAGE "+row.reason+" "+row.decision
    })});
    const j=await r.json();
    const ms=Math.round((j.timings_ms&&j.timings_ms.total)||(performance.now()-started));
    const ex=j.execution||j;
    const broker=ex.broker_result||{};
    const reason=((ex.blockers||j.blockers||[]).filter(Boolean).join(" · "))||broker.comment||ex.message||j.message||"the broker did not accept";
    if(!r.ok||j.ok===false||ex.submitted===false||j.submitted===false){
      const text="NOT SENT · "+reason+" · "+ms+" ms";
      setStatus(text, 20000);
      alert(text);
      return;
    }
    fetch("/api/v19/signals/taken",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({symbol:symbol,chart:chartName,side:row.side,reason:row.reason,entry:row.entry,stop:row.stop,target:row.target,r:row.r,time:row.time})}).catch(()=>{});
    const text="SENT · volume "+(ex.volume??"—")+" · "+(broker.comment||"check the MT5 Trade tab")+" · "+ms+" ms";
    setStatus(text, 20000);
    alert(text);
    load();
  }catch(e){const text="NOT SENT · "+e.message; setStatus(text, 20000); alert(text)}
  finally{
    fetch("/api/v19/signals/priority",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({active:false})}).catch(()=>{});
  }
}
function brokerLine(j){
  const m=j.management||{};
  const nested=(m.broker_result&&(m.broker_result.result||m.broker_result.broker_result))||{};
  return nested.comment||m.reason||j.message||"";
}
async function manage(ticket, action, entry, pct){
  const body={owner_approved:true,fast_ack:true,ticket:ticket,action:action,reason:"SIGNALS PAGE"};
  if(action==="BREAK_EVEN")body.stop_loss=entry;
  if(action==="PARTIAL")body.partial_pct=pct;
  if(action==="CLOSE"&&!confirm("Close ticket "+ticket+" at the market?"))return;
  if(action==="PARTIAL"&&!confirm("Close "+pct+"% of ticket "+ticket+"?"))return;
  const started=performance.now();
  try{
    await fetch("/api/v19/signals/priority",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({active:true})}).catch(()=>{});
    const r=await fetch("/api/v3-physical-execution/manage",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(body)});
    const j=await r.json();
    const ms=Math.round((j.timings_ms&&j.timings_ms.total)||j.management_server_ms||(performance.now()-started));
    const ok=r.ok&&j.ok!==false&&(j.management||{}).ok;
    const text=(ok?"BROKER OK":"BLOCKED")+" · "+brokerLine(j)+" · "+ms+" ms";
    setStatus(text, 20000);
    alert(text);
    load();
  }catch(e){const text="MANAGE ERROR · "+e.message; setStatus(text, 20000); alert(text)}
  finally{fetch("/api/v19/signals/priority",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({active:false})}).catch(()=>{})}
}
async function editStop(ticket){
  const price=Number(prompt("New stop price"));
  if(!isFinite(price)||price<=0)return;
  const started=performance.now();
  const body={owner_approved:true,fast_ack:true,ticket:ticket,action:"MODIFY_POSITION",stop_loss:price,reason:"SIGNALS PAGE EDIT SL"};
  await fetch("/api/v19/signals/priority",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({active:true})}).catch(()=>{});
  try{
    const r=await fetch("/api/v3-physical-execution/manage",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(body)});
    const j=await r.json();
    const ms=Math.round(j.management_server_ms||(performance.now()-started));
    const text=((r.ok&&j.ok!==false&&(j.management||{}).ok)?"STOP SENT":"BLOCKED")+" · "+brokerLine(j)+" · "+ms+" ms";
    setStatus(text, 20000);
    alert(text);
    load();
  }finally{fetch("/api/v19/signals/priority",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({active:false})}).catch(()=>{})}
}
async function editR(ticket, entry, stop, side){
  const multiple=Number(prompt("Target in R, for example 2"));
  if(!isFinite(multiple)||multiple<=0||!isFinite(entry)||!isFinite(stop)){$("status").textContent="NO R · the stop is missing";return}
  const risk=Math.abs(entry-stop);
  const price=side==="BUY"?entry+risk*multiple:entry-risk*multiple;
  const body={owner_approved:true,fast_ack:true,ticket:ticket,action:"MODIFY_POSITION",take_profits:[price],reason:"SIGNALS PAGE EDIT R"};
  const started=performance.now();
  await fetch("/api/v19/signals/priority",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({active:true})}).catch(()=>{});
  try{
    const r=await fetch("/api/v3-physical-execution/manage",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(body)});
    const j=await r.json();
    const ms=Math.round(j.management_server_ms||(performance.now()-started));
    const text=((r.ok&&j.ok!==false&&(j.management||{}).ok)?"TARGET SENT "+price:"BLOCKED")+" · "+brokerLine(j)+" · "+ms+" ms";
    setStatus(text, 20000);
    alert(text);
    load();
  }finally{fetch("/api/v19/signals/priority",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({active:false})}).catch(()=>{})}
}
const cv=$("cv");
cv.addEventListener("wheel",e=>{e.preventDefault();zoom(e.deltaY>0?15:-15)},{passive:false});
cv.addEventListener("pointerdown",e=>{drag=e.clientX});
cv.addEventListener("pointerup",()=>{drag=null});
cv.addEventListener("pointermove",e=>{
  const rect=cv.getBoundingClientRect();
  cursor={x:(e.clientX-rect.left)*(cv.width/rect.width), y:(e.clientY-rect.top)*(cv.height/rect.height)};
  if(drag!=null){const dx=e.clientX-drag;drag=e.clientX;pan+=dx<0?-2:2}
  draw();
});
cv.addEventListener("pointerleave",()=>{cursor=null;draw()});
document.addEventListener("visibilitychange",()=>{if(!document.hidden)load()});
window.addEventListener("pagehide",()=>{clearInterval(timer);if(control)control.abort()});
buttons();load();timer=setInterval(load,2000);
let fastBid=null,fastAsk=null,drawnAt=0;
async function fastQuote(){
  if(document.visibilityState==="hidden"||!data)return;
  try{
    const r=await fetch("/api/quote?symbol="+encodeURIComponent(symbol));
    const j=await r.json();
    if(!r.ok||!j.ok)return;
    const q=j.quote||{};
    const bid=Number(q.bid),ask=Number(q.ask);
    if(!isFinite(bid)||!isFinite(ask))return;
    if(bid===fastBid&&ask===fastAsk)return;
    fastBid=bid;fastAsk=ask;
    data.quote={bid:bid,ask:ask};
    data.spread=ask-bid;
    const rows=data.candles||[];
    if(rows.length){
      const last=rows[rows.length-1];
      const mid=(bid+ask)/2;
      last.close=mid;
      last.high=Math.max(Number(last.high),mid);
      last.low=Math.min(Number(last.low),mid);
    }
    if(data.feed){data.feed.quote_stale=false;data.feed.quote_age=0;}
    const now=performance.now();
    if(now-drawnAt>300){drawnAt=now;draw();}
  }catch(e){}
}
setInterval(fastQuote,250);
let watchAt=0, scanning=false;
async function watchOthers(){
  if(document.visibilityState==="hidden"||scanning) return;
  const pair=PAIRS[watchAt%PAIRS.length];
  watchAt++;
  if(pair[0]===symbol){
    if(data){ board[data.symbol]=boardLine(data); paintBoard(); consider(data); }
    return;
  }
  scanning=true;
  try{
    const r=await fetch("/api/v19/signals?symbol="+pair[0]+"&chart=M1&scan=1");
    const j=await r.json();
    if(r.ok&&j.ok&&j.symbol!==symbol){ board[j.symbol]=boardLine(j); paintBoard(); consider(j); }
  }catch(e){}
  finally{ scanning=false; }
}
setInterval(watchOthers, 12000);
function positionBox(list){
  return (list||[]).length?(list||[]).map(p=>`<div style="margin-top:8px"><b class="${p.side==="BUY"?"good":"bad"}">${p.side}</b> ${p.volume} @ ${p.price_open}<br>P/L ${p.profit} · SL ${p.stop_loss??"—"} · TP ${p.take_profit??"—"}<br>
    <button onclick="manage(${p.ticket},'CLOSE')">CLOSE</button>
    <button onclick="manage(${p.ticket},'BREAK_EVEN',${p.price_open})">BE</button>
    <button onclick="manage(${p.ticket},'PARTIAL',null,10)">10%</button>
    <button onclick="manage(${p.ticket},'PARTIAL',null,50)">50%</button>
    <button onclick="editStop(${p.ticket})">EDIT SL</button>
    <button onclick="editR(${p.ticket},${p.price_open},${p.stop_loss},'${p.side}')">EDIT R</button>
    ${p.manage_line?`<div class="muted">${p.manage_line}</div>`:""}</div>`).join(""):"<div class='muted'>No open broker position on this pair.</div>";
}
async function livePositions(){
  if(document.visibilityState==="hidden"||!symbol)return;
  try{
    const r=await fetch("/api/v19/signals/positions?symbol="+encodeURIComponent(symbol));
    const j=await r.json();
    if(!r.ok||!j.ok)return;
    if(data) data.positions=j.positions||[];
    const box=$("positions");
    if(box) box.innerHTML=positionBox(j.positions||[]);
  }catch(e){}
}
setInterval(livePositions, 500);
livePositions();
watchOthers();
if(window.Notification&&Notification.permission==="default") Notification.requestPermission().catch(()=>{});
</script></body></html>"""


def _bucket_seconds(chart: str) -> int:
    return {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}[chart]


def _live_candles(bars: list[dict[str, Any]], bid: float, chart: str) -> list[dict[str, Any]]:
    """Move the current candle with the quote. A closed bar alone looks like a picture."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    step = _bucket_seconds(chart)
    bucket = datetime.fromtimestamp(int(now.timestamp()) // step * step, tz=timezone.utc)
    if not bars:
        return [{"time": bucket.isoformat(), "open": bid, "high": bid, "low": bid, "close": bid}]
    last = dict(bars[-1])
    try:
        opened = datetime.fromisoformat(str(last["time"]).replace("Z", "+00:00"))
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=timezone.utc)
    except ValueError:
        opened = bucket
    if opened < bucket:
        return [*bars, {"time": bucket.isoformat(), "open": bid, "high": bid, "low": bid, "close": bid}]
    last["close"] = bid
    last["high"] = max(float(last["high"]), bid)
    last["low"] = min(float(last["low"]), bid)
    return [*bars[:-1], last]


_OIL_SKIP = ("BRENT", "UKOIL", "XBRUSD", "UKOUSD")
_OIL_HINT = ("USOIL", "USOUSD", "XTIUSD", "WTICOUSD", "WTIUSD", "SPOTCRUDE", "CRUDE", "WTI", "XTI")


def _worker(host: Any) -> Any:
    return getattr(getattr(host, "runtime", None), "worker", None)


def _candles_from_rows(rows: Any) -> list[dict[str, Any]]:
    found = []
    for row in rows or ():
        data = row if isinstance(row, dict) else {}
        raw_time = data.get("time")
        if isinstance(raw_time, (int, float)) and not isinstance(raw_time, bool):
            stamp = datetime.fromtimestamp(int(raw_time), timezone.utc).isoformat()
        else:
            stamp = str(raw_time or "")
        try:
            found.append({
                "time": stamp,
                "open": float(data["open"]),
                "high": float(data["high"]),
                "low": float(data["low"]),
                "close": float(data["close"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return found


def _oil_feed(host: Any, chart: str, scan: bool) -> tuple[Any, dict[str, list[dict[str, Any]]], str] | None:
    """The feed has no symbol named WTI. Use the broker's crude name, and only if the price is oil."""
    worker = _worker(host)
    if worker is None:
        return None
    try:
        names = tuple(worker.symbol_catalog())
    except Exception:
        return None
    chosen = None
    quote = None
    for name in names:
        flat = str(name).upper().replace(".", "").replace("+", "").replace("-", "").replace(" ", "")
        if any(skip in flat for skip in _OIL_SKIP):
            continue
        if not any(hint in flat for hint in _OIL_HINT):
            continue
        try:
            got = worker.quote(str(name))
        except Exception:
            continue
        bid = float(getattr(got, "bid", 0) or 0)
        if 20 <= bid <= 200:
            chosen = str(name)
            quote = got
            break
    if quote is None or chosen is None:
        return None
    bars_by_chart: dict[str, list[dict[str, Any]]] = {}
    for name in CHARTS:
        if scan and name != "M1":
            bars_by_chart[name] = []
            continue
        try:
            bars_by_chart[name] = _candles_from_rows(worker.bars(chosen, Timeframe(name), count=120 if scan else 400))
        except Exception:
            bars_by_chart[name] = []
    return quote, bars_by_chart, chosen


def _bars(host: Any, symbol: str, chart: str, max_age: float, count: int = 160) -> list[dict[str, Any]]:
    key = symbol + "|" + chart
    cached = _CACHE.get(key)
    if _ORDER_BUSY.is_set():
        return cached[1] if cached else []
    if cached and monotonic() - cached[0] < max_age:
        return cached[1]
    rows = host.runtime.projection.market_data.bars(symbol, Timeframe(chart), count=count)
    found = [
        {
            "time": row.open_time_utc.isoformat(),
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
        }
        for row in rows
    ]
    _CACHE[key] = (monotonic(), found)
    return found


_FILLED: dict[str, float] = {}


def _chart_bars(host: Any, symbol: str, chart: str, scan: bool) -> dict[str, list[dict[str, Any]]]:
    """One MetaTrader history on a click. The other timeframes stay cached, and only one missing one is filled."""
    found: dict[str, list[dict[str, Any]]] = {}
    missing: list[str] = []
    for name in CHARTS:
        key = symbol + "|" + name
        cached = _CACHE.get(key)
        fresh = cached is not None and monotonic() - cached[0] < (25.0 if name == chart else 90.0)
        if fresh:
            found[name] = cached[1]
        elif name == chart and not scan:
            found[name] = _bars(host, symbol, name, 25.0, 200)
        else:
            found[name] = cached[1] if cached else []
            if not cached:
                missing.append(name)
    if missing and not _ORDER_BUSY.is_set():
        name = missing[0]
        found[name] = _bars(host, symbol, name, 90.0, 80 if scan else 120)
    return found


def _read_raw(symbol: str) -> dict[str, Any] | None:
    from gold_shadow.mbo_book import _roots

    newest = None
    for root in FUTURES_ROOTS.get(symbol, ()):
        for folder in _roots():
            path = folder / f"zeus_mbo_{root}.json"
            if not path.is_file():
                continue
            if newest is None or path.stat().st_mtime > newest.stat().st_mtime:
                newest = path
    if newest is None:
        return None
    try:
        payload = json.loads(newest.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    payload["_age"] = datetime.now(timezone.utc).timestamp() - newest.stat().st_mtime
    return payload


def _book(symbol: str) -> dict[str, Any]:
    try:
        from gold_shadow.mbo_book import read_mbo

        book = read_mbo(symbol)
    except Exception as exc:
        book = {"fresh": False, "reason": str(exc)}
    raw = _read_raw(symbol)
    if raw is not None:
        age = float(raw.get("_age") or 999)
        book.update({
            "fresh": age <= 20,
            "reason": "MBO_LIVE" if age <= 20 else "MBO_STALE",
            "sweep_consumed": bool(raw.get("sweep_consumed")),
            "iceberg_refresh": bool(raw.get("iceberg_refresh")),
            "size_pulled": bool(raw.get("size_pulled")),
            "levels": raw.get("levels") or [],
            "icebergs": raw.get("icebergs") or [],
            "futures_bid": raw.get("bid"),
            "futures_ask": raw.get("ask"),
            "last": raw.get("last"),
        })
        for name in ("poc", "vah", "val"):
            value = raw.get(name)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) > 0:
                book[name] = float(value)
        for name in ("delta_5s", "delta_60s"):
            value = raw.get(name)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                book[name] = float(value)
        ice = raw.get("iceberg")
        if isinstance(ice, dict) and ice.get("price") is not None:
            book["iceberg"] = {
                "price": float(ice["price"]),
                "side": str(ice.get("side") or ""),
                "bid_size": float(ice.get("bid_size") or 0),
                "ask_size": float(ice.get("ask_size") or 0),
                "refills": int(ice.get("refills") or 0),
                "time": ice.get("time"),
            }
        else:
            book["iceberg"] = None
        other = raw.get("other")
        if isinstance(other, dict) and other.get("price") is not None:
            book["other"] = {
                "price": float(other["price"]),
                "side": str(other.get("side") or ""),
                "refills": int(other.get("refills") or 0),
                "time": other.get("time"),
            }
        else:
            book["other"] = None
    try:
        from zeus3.v19.shadow_book_page import _sierra_flow

        _flow, _state, metrics = _sierra_flow(symbol)
        if metrics:
            book["absorption"] = bool(metrics.get("absorption"))
            for name in ("delta_5s", "delta_60s"):
                value = metrics.get(name)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    book[name] = value
    except Exception:
        pass
    return book


def _same_pair(symbol: str, broker: str) -> bool:
    broker = broker.upper().replace(".", "").replace("+", "").replace("-", "")
    if symbol in broker or broker in symbol:
        return True
    return any(name in broker for name in POSITION_NAMES.get(symbol, ()))


def _positions(host: Any, symbol: str) -> list[dict[str, Any]]:
    try:
        truth = host.runtime.core.broker_truth.get(host.runtime.worker.profile_id)
    except Exception:
        return []
    found = []
    for row in getattr(truth, "positions", ()) or ():
        broker = str(getattr(row, "broker_symbol", "") or "")
        if not _same_pair(symbol, broker):
            continue
        side = "BUY" if int(getattr(row, "type_code", 1)) == 0 else "SELL"
        found.append(
            {
                "ticket": int(getattr(row, "ticket", 0) or 0),
                "side": side,
                "volume": float(getattr(row, "volume", 0.0) or 0.0),
                "price_open": getattr(row, "price_open", None),
                "stop_loss": getattr(row, "stop_loss", None),
                "take_profit": getattr(row, "take_profit", None),
                "profit": getattr(row, "profit", None),
            }
        )
    _attach_manage(found)
    return found


def _manage_path() -> Path:
    return Path.cwd() / "manage.txt"


def _manage_state_path() -> Path:
    return Path.cwd() / "manage_state.json"


def manage_enabled() -> bool:
    path = _manage_path()
    if not path.is_file():
        return False
    return path.read_text(encoding="utf-8").strip().lower() == "on"


def set_manage(on: bool) -> None:
    _manage_path().write_text("on\n" if on else "off\n", encoding="utf-8")


def _load_manage_state() -> dict[str, Any]:
    path = _manage_state_path()
    if not path.is_file():
        return {"trades": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"trades": {}}
    if not isinstance(payload, dict):
        return {"trades": {}}
    payload.setdefault("trades", {})
    return payload


def _save_manage_state(state: dict[str, Any]) -> None:
    _manage_state_path().write_text(json.dumps(state), encoding="utf-8")


def _attach_manage(positions: list[dict[str, Any]]) -> None:
    if not manage_enabled():
        return
    trades = _load_manage_state().get("trades") or {}
    for row in positions:
        saved = trades.get(str(row.get("ticket"))) or {}
        if saved.get("line"):
            row["manage_line"] = saved["line"]


def _announce_manage(symbol: str, text: str, ticket: int, entry: float) -> None:
    try:
        from zeus3.v19.telegram_alert import announce_manage
    except Exception:
        return
    try:
        announce_manage(symbol, text, ticket, entry)
    except Exception:
        return


def _run_manage(
    host: Any,
    symbol: str,
    rows: list[dict[str, Any]],
    positions: list[dict[str, Any]],
    bars_by_chart: dict[str, list[dict[str, Any]]],
    book: dict[str, Any],
    bid: float,
    ask: float,
) -> None:
    """Move the stop when manage is on. Never close the trade from here."""
    if not manage_enabled() or not positions:
        return
    state = _load_manage_state()
    trades = state.setdefault("trades", {})
    changed = False
    for pos in positions:
        side = str(pos.get("side") or "")
        try:
            entry = float(pos.get("price_open"))
        except (TypeError, ValueError):
            continue
        match = None
        nearest = None
        for row in rows:
            if str(row.get("side") or "") != side or row.get("entry") is None:
                continue
            try:
                gap = abs(float(row["entry"]) - entry)
            except (TypeError, ValueError):
                continue
            if nearest is None or gap < nearest:
                nearest = gap
                match = row
        if match is None or nearest is None or nearest > max(abs(entry) * 0.002, 1e-6):
            continue
        targets = [price for price in (match.get("targets") or []) if price is not None]
        if not targets and match.get("target") is not None:
            targets = [match.get("target")]
        chart = str(match.get("chart") or "")
        bars = bars_by_chart.get("H1" if chart in {"SWING", "INTERDAY"} else "M15") or []
        key = str(pos.get("ticket"))
        previous = trades.get(key) if isinstance(trades.get(key), dict) else {}
        dip = previous.get("dip")
        if not isinstance(dip, (int, float)) or isinstance(dip, bool) or float(dip) <= 0:
            dip = range_dip(bars)
        risk = previous.get("risk")
        if isinstance(risk, bool) or not isinstance(risk, (int, float)):
            risk = None
        decision = manage_decision(
            side=side,
            entry=entry,
            stop=pos.get("stop_loss"),
            risk=None if risk is None else float(risk),
            bid=bid,
            ask=ask,
            targets=targets,
            dip=None if dip is None else float(dip),
            book=book,
            volume=float(pos.get("volume") or 0),
        )
        saved = {
            "symbol": symbol,
            "line": decision.get("line") or "",
            "risk": decision.get("risk"),
            "dip": decision.get("dip"),
            "sent": previous.get("sent"),
            "told": previous.get("told") or "",
        }
        new_stop = decision.get("stop")
        if isinstance(new_stop, (int, float)) and not isinstance(new_stop, bool):
            if saved.get("sent") != float(new_stop):
                try:
                    host.runtime.manage_physical_trade(
                        ticket=int(pos["ticket"]),
                        action="MODIFY_POSITION",
                        stop_loss=float(new_stop),
                        reason="ZEUS MANAGE",
                    )
                except Exception:
                    new_stop = None
                else:
                    saved["sent"] = float(new_stop)
                    pos["stop_loss"] = float(new_stop)
                    _announce_manage(symbol, f"Stop moved to {round(float(new_stop), 5)}.", int(pos["ticket"]), entry)
        if saved["line"] and saved["line"] != saved["told"]:
            _announce_manage(symbol, str(saved["line"]), int(pos["ticket"]), entry)
            saved["told"] = saved["line"]
        trades[key] = saved
        if saved["line"]:
            pos["manage_line"] = saved["line"]
        if saved != previous:
            changed = True
    if changed:
        _save_manage_state(state)


def render_signals_page() -> str:
    return PAGE


_NEWS: Any = None
_TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}


def _feed(quote: Any, candle_time: str, chart: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    tick = getattr(quote, "broker_timestamp_utc", None) or getattr(quote, "received_at_utc", None) or now
    if getattr(tick, "tzinfo", None) is None:
        tick = tick.replace(tzinfo=timezone.utc)
    quote_age = max(0, int((now - tick).total_seconds()))
    candle = None
    if candle_time:
        try:
            candle = datetime.fromisoformat(str(candle_time).replace("Z", "+00:00"))
            if candle.tzinfo is None:
                candle = candle.replace(tzinfo=timezone.utc)
        except ValueError:
            candle = None
    candle_age = max(0, int((now - candle).total_seconds())) if candle else None
    limit = _TF_SECONDS.get(chart, 60) * 3
    candles_stale = candle_age is None or candle_age > limit
    health = str(getattr(getattr(quote, "health", ""), "value", getattr(quote, "health", "")) or "")
    quote_stale = quote_age > 60 or health in {"STALE", "DISCONNECTED", "ERROR"}
    session = _session_name(now if candles_stale else (candle or now))
    if health in {"DISCONNECTED", "ERROR"}:
        market = "NO FEED"
    elif quote_stale:
        market = "STALE"
    else:
        market = "OPEN"
    return {
        "quote_age": quote_age,
        "candle_age": candle_age,
        "quote_stale": quote_stale,
        "candles_stale": candles_stale,
        "session": session,
        "market": market,
        "line": f"FEED {market} · quote {quote_age}s ago · candle {candle_age if candle_age is not None else '—'}s ago · {session}",
    }


def _news(symbol: str) -> dict[str, Any]:
    global _NEWS
    try:
        from zeus3.chart.news_risk import NewsRiskService

        if _NEWS is None:
            _NEWS = NewsRiskService(background=True)
        snap = _NEWS.snapshot(symbol)
    except Exception:
        return {"line": "NO CALENDAR"}
    if snap.get("state") == "UNAVAILABLE":
        return {"line": "NO CALENDAR"}
    upcoming = list(snap.get("upcoming_events") or [])
    holiday = next((row for row in upcoming if str(row.get("impact") or "").upper() == "HOLIDAY"), None)
    nxt = upcoming[0] if upcoming else snap.get("nearest_event")
    if not nxt:
        return {"line": "NO NEWS ON THE CALENDAR" + (" · " + str(holiday.get("name") or "HOLIDAY") if holiday else "")}
    seconds = float(nxt.get("seconds_from_now") or 0)
    minutes = int(abs(seconds) // 60)
    clock = f"{minutes // 60}h {minutes % 60}m" if minutes >= 60 else f"{minutes}m"
    when = "ago" if seconds < 0 else "in"
    today = []
    for row in upcoming:
        if float(row.get("seconds_from_now") or 0) > 24 * 3600:
            break
        today.append(str(row.get("name") or "event") + " " + str(row.get("impact") or "UNKNOWN"))
    line = f"NEXT {nxt.get('name') or 'event'} {nxt.get('impact') or 'UNKNOWN'} {when} {clock}"
    if holiday:
        line = "CLOSED · " + str(holiday.get("name") or "HOLIDAY") + " · " + line
    if today:
        line += " · TODAY " + " · ".join(today[:4])
    if snap.get("state") not in {"LIVE_SCHEDULE", "CACHED_SCHEDULE"}:
        line = "NO CALENDAR · " + line
    return {"line": line, "state": snap.get("state")}


def _account(host: Any) -> dict[str, Any]:
    """The logged-in MT5 balance. The risk box turns that into a target amount."""
    try:
        truth = host.runtime.core.broker_truth.get(host.runtime.worker.profile_id)
    except Exception:
        return {}
    account = getattr(truth, "account", None)
    if account is None:
        return {}
    balance = getattr(account, "balance", None)
    equity = getattr(account, "equity", None)
    return {
        "balance": None if balance is None else float(balance),
        "equity": None if equity is None else float(equity),
    }


def _broker_protected(position: dict[str, Any]) -> bool:
    try:
        stop = float(position.get("stop_loss") or 0)
        entry = float(position.get("price_open") or 0)
    except (TypeError, ValueError):
        return False
    if stop <= 0 or entry <= 0:
        return False
    if str(position.get("side")) == "SELL":
        return stop <= entry
    return stop >= entry


def _broker_protection(rows: list[dict[str, Any]], positions: list[dict[str, Any]]) -> None:
    """The broker stop, not the signal note, decides whether closing the open trade loses."""
    by_name = {row.get("chart"): row for row in rows}
    inter = by_name.get("INTERDAY") or {}
    held_side = str(inter.get("closes") or "")
    if held_side not in {"BUY", "SELL"}:
        return
    matched = [row for row in positions if str(row.get("side")) == held_side]
    if not matched:
        return
    protected = all(_broker_protected(row) for row in matched)
    close = (
        f"Get ready to close the open {held_side}. The stop is at the entry, so closing it is not a loss."
        if protected
        else f"Get ready to close the open {held_side}. The stop is not at the entry, so closing it can still lose."
    )
    detail = str(inter.get("signal_note") or "")
    inter["note"] = f"{close} {detail}".strip()


def _payload(symbol: str, chart: str, host: Any, scan: bool = False) -> dict[str, Any]:
    core = host.runtime.projection.market_data
    try:
        from zeus3.market_data.subscriptions import SubscriptionPriority

        host.runtime.market_runtime.add_quote_watch(
            symbol,
            priority=SubscriptionPriority.ACTIVE_CHART,
            minimum_interval_seconds=0.05,
            task_id=f"ACTIVE_CHART_QUOTE:{symbol}",
        )
    except Exception:
        pass
    quote = None
    if not scan:
        try:
            quote = core.refresh_quote(symbol)
        except Exception:
            try:
                quote = core.quote(symbol)
            except Exception:
                quote = None
    else:
        try:
            quote = core.quote(symbol)
        except Exception:
            quote = None
    direct = None
    bid_now = float(getattr(quote, "bid", 0) or 0) if quote is not None else 0.0
    if symbol == "WTI" and not (20 <= bid_now <= 200):
        direct = _oil_feed(host, chart, scan)
        if direct is None:
            raise RuntimeError("quote is not cached: WTI")
        quote, bars_by_chart, _broker = direct
    elif quote is None:
        raise RuntimeError(f"quote is not cached: {symbol}")
    if direct is None:
        bars_by_chart = _chart_bars(host, symbol, chart, scan)
    bid = float(quote.bid)
    ask = float(quote.ask)
    mid = (bid + ask) / 2
    for name in CHARTS:
        bars_by_chart[name] = _live_candles(bars_by_chart.get(name) or [], mid, name)
    spread = round(ask - bid, 5)
    book = _book(symbol)
    if symbol == "USDJPY":
        place_yen(book, bid, ask)
    levels = session_levels(bars_by_chart.get("M15") or bars_by_chart.get("M5") or [])
    pools = liquidity(levels, bars_by_chart)
    rows = build_rows(symbol, bars_by_chart, book, spread, levels, bid, ask)
    positions = _positions(host, symbol)
    _broker_protection(rows, positions)
    _run_manage(host, symbol, rows, positions, bars_by_chart, book, bid, ask)
    if scan or monotonic() - _FILLED.get(symbol, 0.0) < 15.0:
        research = {"taken": {}, "if_taken": {}}
    else:
        try:
            research = record(symbol, rows, bars_by_chart)
        except Exception:
            research = {"taken": {}, "if_taken": {}}
        else:
            _FILLED[symbol] = monotonic()
    delta = book.get("delta_5s")
    stepping = "BUYERS" if isinstance(delta, (int, float)) and not isinstance(delta, bool) and delta > 0 else (
        "SELLERS" if isinstance(delta, (int, float)) and not isinstance(delta, bool) and delta < 0 else "QUIET"
    )
    shots: dict[str, list[dict[str, float]]] = {}
    if any(isinstance(row, dict) and row.get("tradeable") for row in rows):
        def compact(name: str) -> list[dict[str, float]]:
            found = []
            for bar in (bars_by_chart.get(name) or [])[-70:]:
                if not isinstance(bar, dict):
                    continue
                try:
                    found.append({"o": float(bar["open"]), "h": float(bar["high"]), "l": float(bar["low"]), "c": float(bar["close"])})
                except (KeyError, TypeError, ValueError):
                    continue
            return found
        shots = {"M5": compact("M5"), "M15": compact("M15"), "H1": compact("H1")}
    return {
        "ok": True,
        "symbol": symbol,
        "label": LABELS.get(symbol, symbol),
        "chart": chart,
        "candles": [] if scan else (bars_by_chart.get(chart) or []),
        "quote": {"bid": bid, "ask": ask},
        "spread": spread,
        "sessions": levels,
        "pools": pools,
        "reaction": reaction(bars_by_chart.get(chart) or [], pools),
        "rows": rows,
        "shots": shots,
        "market": (rows[0].get("market") if rows else "RANGE"),
        "ladder": align_ladder(symbol, book, bid, ask),
        "flow": {
            "fresh": bool(book.get("fresh")),
            "absorption": bool(book.get("absorption")),
            "iceberg": bool(book.get("iceberg_refresh")),
            "iceberg_price": (book.get("iceberg") or {}).get("price") if isinstance(book.get("iceberg"), dict) else None,
            "iceberg_side": (book.get("iceberg") or {}).get("side") if isinstance(book.get("iceberg"), dict) else None,
            "pulled": bool(book.get("size_pulled")),
            "sweep_consumed": bool(book.get("sweep_consumed")),
            "delta_5s": book.get("delta_5s"),
            "delta_60s": book.get("delta_60s"),
            "poc": book.get("poc"),
            "vah": book.get("vah"),
            "val": book.get("val"),
            "stepping": stepping,
            "note": str(book.get("reason") or ""),
        },
        "positions": positions,
        "manage": manage_enabled(),
        "account": _account(host),
        "research": research,
        "feed": _feed(quote, ((bars_by_chart.get(chart) or [None])[-1] or {}).get("time", ""), chart),
        "news": _news(symbol),
        "server_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }


async def signals_manage(host: Any, request: web.Request) -> web.Response:
    """The stop-management switch. Off leaves the ticket alone."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict) or "on" not in payload:
        return web.json_response({"ok": True, "on": manage_enabled()})
    set_manage(bool(payload.get("on")))
    return web.json_response({"ok": True, "on": manage_enabled()})


async def signals_positions(host: Any, request: web.Request) -> web.Response:
    """Profit from the broker snapshot already in memory. No chart rebuild."""
    symbol = str(request.query.get("symbol") or "").upper()
    if symbol not in PAIRS:
        return web.json_response({"ok": False, "message": "unknown pair"}, status=400)
    return web.json_response({"ok": True, "positions": _positions(host, symbol)})


async def signals_snapshot(host: Any, request: web.Request) -> web.Response:
    symbol = str(request.query.get("symbol") or "XAUUSD").upper()
    chart = str(request.query.get("chart") or "M5").upper()
    scan = str(request.query.get("scan") or "") == "1"
    if symbol not in PAIRS or chart not in CHARTS:
        return web.json_response({"ok": False, "message": "unknown pair or chart"}, status=400)
    if _ORDER_BUSY.is_set():
        cached = _LAST.get(symbol)
        if cached:
            return web.json_response(cached)
    if scan:
        locked = _LOCK.acquire(blocking=False)
    else:
        locked = _LOCK.acquire(timeout=4)
    if not locked:
        cached = _LAST.get(symbol)
        if cached:
            return web.json_response(cached)
        return web.json_response({"ok": False, "message": "Still reading MetaTrader."}, status=503)
    try:
        payload = await asyncio.to_thread(_payload, symbol, chart, host, scan)
    except Exception as exc:
        return web.json_response(
            {"ok": False, "message": f"{symbol} is not on this MetaTrader feed. {exc}"},
            status=503,
        )
    finally:
        _LOCK.release()
    _LAST[symbol] = payload
    try:
        from zeus3.v19.telegram_alert import announce, start

        start(host)
        announce(payload)
    except Exception:
        pass
    return web.json_response(payload)


async def signals_priority(host: Any, request: web.Request) -> web.Response:
    """Hold chart reads while an order is on its way to the broker."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    if bool((body or {}).get("active")):
        _ORDER_BUSY.set()
    else:
        _ORDER_BUSY.clear()
    return web.json_response({"ok": True})


async def signals_taken(host: Any, request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "message": "bad json"}, status=400)
    try:
        research = mark_taken(body if isinstance(body, dict) else {})
    except ValueError as exc:
        return web.json_response({"ok": False, "message": str(exc)}, status=400)
    return web.json_response({"ok": True, "research": research})
