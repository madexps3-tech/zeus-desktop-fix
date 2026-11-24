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
    place_value,
    place_marks,
    stack_line,
    range_dip,
    reaction,
    record,
    session_levels,
    settle_rows,
    _band,
    _closed,
    _time,
    _wait,
)

_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_LOCK = threading.Lock()
_ORDER_BUSY = threading.Event()
_LAST: dict[str, dict[str, Any]] = {}
_VIEW: dict[str, dict[str, Any]] = {}

LABELS = {
    "XAUUSD": "GOLD",
    "XAGUSD": "SILVER",
    "NAS100": "NASDAQ",
    "BTCUSD": "BITCOIN",
    "EURUSD": "EURO",
    "USDJPY": "USDJPY",
    "WTI": "OIL",
    "NG-C": "GAS",
    "GER40": "DAX",
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
.good{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}.late{color:#ff5a5a;font-weight:700}.muted{color:var(--muted)}
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
  <a href="/v19/chart">CHART</a><a href="/v19/trade-desk">TRADE DESK</a><a href="/v19/auto">AUTO</a><a href="/v19/shadow">SHADOW</a>
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
  <label>RISK $ <input id="cash" value="" placeholder="opt" style="width:72px" oninput="if(data)paint()"></label>
  <button id="manage" data-on="0" onclick="toggleManage()">MANAGE OFF</button>
  <button id="ice" data-on="0" onclick="toggleIce()">ICE AUTO OFF</button>
  <span class="muted">MARKET sends now. LIMIT rests at the row price. ICE AUTO sends a gold, oil, or Nasdaq iceberg as a limit.</span>
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
    <div id="alerts" class="muted">Quiet until a new signal on one of the nine pairs.</div>
    <table id="grid"></table>
    <div id="research" class="muted" style="margin-top:8px"></div>
  </section>
  <aside>
    <section class="card">
      <div class="muted">NINE PAIRS</div>
      <div id="board"></div>
    </section>
    <section class="card flow" id="flow" style="margin-top:10px"></section>
    <section class="card" style="margin-top:10px">
      <div class="muted">THIS PAIR ON THE BROKER</div>
      <div id="bookrisk" style="margin:6px 0 8px"></div>
      <div id="positions"></div>
    </section>
  </aside>
</main>
<script>
const PAIRS=[["XAUUSD","GOLD"],["XAGUSD","SILVER"],["NAS100","NASDAQ"],["BTCUSD","BITCOIN"],["EURUSD","EURO"],["USDJPY","USDJPY"],["WTI","OIL"],["NG-C","GAS"],["GER40","DAX"]];
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
  symbol=s; localStorage.setItem("sig_symbol",s); pan=0; fastBid=null; fastAsk=null;
  const kept=saved[s+"|"+chart];
  if(kept && kept.symbol===s && (kept.candles||[]).length){ data=kept; }
  else { data={symbol:s,chart:chart,candles:[],rows:[],quote:{},flow:{},positions:[],pools:[],broker:s,news:{}}; }
  buttons(); draw(); paint();
  load(true, true);
}
function setChart(c){
  chart=c; selected=c; localStorage.setItem("sig_chart",c); pan=0;
  const kept=saved[symbol+"|"+c];
  if(kept && (kept.candles||[]).length){ data=kept; }
  else {
    data={symbol:symbol,chart:c,candles:[],rows:(data&&data.rows)||[],quote:(data&&data.quote)||{},flow:(data&&data.flow)||{},positions:(data&&data.positions)||[],pools:(data&&data.pools)||[],broker:(data&&data.broker)||symbol,news:(data&&data.news)||{}};
  }
  buttons(); draw(); paint();
  load(true, true);
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
async function load(force, view){
  if(document.visibilityState==="hidden")return;
  if(busy && !force)return;
  const id=++loadId;
  const want=symbol, wantChart=chart;
  if(control)control.abort();
  control=new AbortController();
  busy=true;
  buttons();
  try{
    const r=await fetch("/api/v19/signals?symbol="+want+"&chart="+wantChart+(view?"&view=1":""),{signal:control.signal});
    const j=await r.json();
    if(id!==loadId || want!==symbol || wantChart!==chart)return;
    if(j.chart && j.chart!==wantChart)return;
    if(!r.ok||!j.ok)throw Error(j.message||("HTTP "+r.status));
    data=j; remember(j); $("clock").textContent=j.server_time||"";
    const manage=$("manage");
    if(manage){
      manage.dataset.on=j.manage?"1":"0";
      manage.textContent=j.manage?"MANAGE ON":"MANAGE OFF";
    }
    const ice=$("ice");
    if(ice){
      ice.dataset.on=j.ice_auto?"1":"0";
      ice.textContent=j.ice_auto?"ICE AUTO ON":"ICE AUTO OFF";
    }
    draw(); paint(); consider(j);
  }catch(e){
    if(e.name!=="AbortError" && id===loadId){
      $("status").textContent="CHART ERROR · "+e.message;
      if(!data||data.symbol!==want){
        data={symbol:want,candles:[],rows:[],quote:{},flow:{},positions:[],pools:[],broker:want};
        draw(); paint();
      }
    }
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
  }finally{button.disabled=false}
}
async function toggleIce(){
  const button=$("ice");
  const on=button.dataset.on!=="1";
  button.disabled=true;
  try{
    const r=await fetch("/api/v19/signals/ice",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({on:on})});
    const j=await r.json();
    if(!r.ok||!j.ok)throw Error(j.message||"iceberg auto was not saved");
    button.dataset.on=j.on?"1":"0";
    button.textContent=j.on?"ICE AUTO ON":"ICE AUTO OFF";
    $("status").textContent=j.on?"ICE AUTO ON. A refilled gold, oil, or Nasdaq iceberg is sent as a limit.":"ICE AUTO OFF. An iceberg needs the LIMIT button.";
  }catch(e){
    $("status").textContent="ICE AUTO NOT SAVED · "+e.message;
  }finally{button.disabled=false}
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
  const plotL=56, plotR=width-78, plotT=78, plotB=490;
  ctx.clearRect(0,0,cv.width,cv.height);
  ctx.fillStyle="#050b11"; ctx.fillRect(0,0,cv.width,cv.height);
  ctx.font="12px Consolas,monospace";
  paintQuote();
  if(!rows.length){ctx.fillStyle="#8ea3b8";ctx.fillText("No candles for "+symbol+" "+chart, 20, 40);return}
  let lo=Infinity, hi=-Infinity;
  const priceOf=v=>{const n=Number(v); return isFinite(n)&&n>0?n:null};
  rows.forEach(b=>{const low=priceOf(b.low), high=priceOf(b.high); if(low!=null)lo=Math.min(lo,low); if(high!=null)hi=Math.max(hi,high)});
  const q=data.quote||{};
  const bidPx=priceOf(q.bid);
  if(bidPx!=null){lo=Math.min(lo,bidPx);hi=Math.max(hi,bidPx)}
  const span=Math.max(hi-lo, 0.00001);
  const row=(data.rows||[]).find(r=>r.chart===pickedRow&&r.entry!=null);
  if(row&&isFinite(lo)&&Math.abs(Number(row.entry)-((lo+hi)/2))<span*1.2){
    [row.stop,row.target,row.entry].forEach(v=>{const n=priceOf(v); if(n!=null){lo=Math.min(lo,n);hi=Math.max(hi,n)}});
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
  const magnetHigh=Number(flowNow.unfinished_high), magnetLow=Number(flowNow.unfinished_low);
  ctx.save();
  ctx.lineWidth=3;
  ctx.font="700 14px Arial,sans-serif";
  [[magnetHigh,"UNFINISHED HIGH"],[magnetLow,"UNFINISHED LOW"]].forEach(line=>{
    const price=line[0];
    if(!isFinite(price)||price<lo||price>hi) return;
    ctx.setLineDash([8,4]); ctx.strokeStyle="#f4e8ff"; ctx.beginPath(); ctx.moveTo(plotL,y(price)); ctx.lineTo(plotR,y(price)); ctx.stroke();
    ctx.setLineDash([]); ctx.fillStyle="#ffe38a"; ctx.fillText(line[1]+" "+price, plotL+4, y(price)+14);
  });
  ctx.restore();
  if(row){
    ctx.setLineDash([4,4]);
    [["#67d6a3",row.entry,"ENTRY"],["#ef7f88",row.stop,"STOP"],["#e9c66b",row.target,row.r==null?"TARGET":"TARGET "+row.r+"R"]].forEach(line=>{
      const price=priceOf(line[1]);
      if(price==null||price<lo||price>hi)return;
      ctx.strokeStyle=line[0]; ctx.beginPath(); ctx.moveTo(plotL,y(price)); ctx.lineTo(plotR,y(price)); ctx.stroke();
      ctx.fillStyle=line[0]; ctx.fillText(line[2]+" "+price, plotR-170, y(price)-4);
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
      ctx.fillText(localWhen(b.time), x-24, 512);
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
  ctx.fillStyle="#8ea3b8";
  ctx.fillText(marketClocks(new Date()), 12, 52);
  const news=data.news||{};
  const left=Number(news.seconds);
  if((news.impact==="HIGH"||news.impact==="HOLIDAY"||news.holiday)&&isFinite(left)&&left>=0&&left<=7200){
    const mins=Math.max(0, Math.round(left/60));
    const holiday=news.holiday?("HOLIDAY "+news.holiday+"   "):"";
    ctx.fillStyle="#ef7f88";
    ctx.fillText(holiday+(news.name||"NEWS")+" "+(news.impact||"")+" in "+mins+"m", 12, 64);
  }
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
      const when=localWhen(bar.time);
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
function orderRisk(){
  const box=$("cash");
  const typed=box?String(box.value||"").trim():"";
  const acct=(data&&data.account)||{};
  const equity=Number(acct.equity||acct.balance);
  if(typed!==""){
    const cash=Number(typed);
    if(!isFinite(cash)||cash<=0) return {error:"NOT SENT · the dollar risk has to be above 0."};
    if(!(equity>0)) return {error:"NOT SENT · the account balance is not on the page, so a dollar risk cannot be sized."};
    return {pct:cash/equity*100, label:"$"+cash};
  }
  const risk=Number($("risk").value);
  if(!isFinite(risk)||risk<=0) return {error:"NOT SENT · set the risk percent, or a dollar amount."};
  return {pct:risk, label:risk+"%"};
}
function moneyLine(row, account){
  if(row&&row.push) return row.harvest||"—";
  if(!row||row.entry==null||row.stop==null) return row&&row.harvest||"—";
  const entry=Number(row.entry), stop=Number(row.risk_stop!=null?row.risk_stop:row.stop);
  const riskDist=Math.abs(entry-stop);
  const plan=orderRisk();
  const risk=plan.error?NaN:plan.pct;
  const acct=account||(data&&data.account)||{};
  const balance=Number(acct.equity||acct.balance);
  const targets=(row.targets&&row.targets.length)?row.targets:(row.target!=null?[row.target]:[]);
  if(!(riskDist>0)||!targets.length) return row.harvest||"—";
  return targets.map((price,i)=>{
    const reward=Math.abs(Number(price)-entry);
    const mult=round2(reward/riskDist);
    const pct=(isFinite(risk)&&risk>0)?round2(risk*mult):null;
    const cash=(pct!=null&&isFinite(balance)&&balance>0)?Math.round(balance*pct/100):null;
    const ratio=mult.toFixed(2)+"R to "+price;
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
function zoneParts(date, timeZone){
  const parts=new Intl.DateTimeFormat("en-US",{timeZone:timeZone,hourCycle:"h23",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",weekday:"short"}).formatToParts(date);
  const out={};
  parts.forEach(part=>{if(part.type!=="literal") out[part.type]=part.value});
  return out;
}
function atLocal(timeZone, hour, minute, base){
  let guess=new Date(base.getTime());
  for(let i=0;i<3;i++){
    const parts=zoneParts(guess, timeZone);
    const desired=Date.UTC(+parts.year, +parts.month-1, +parts.day, hour, minute);
    const actual=Date.UTC(+parts.year, +parts.month-1, +parts.day, +parts.hour, +parts.minute);
    const next=new Date(guess.getTime()+(desired-actual));
    if(next.getTime()===guess.getTime()) return next;
    guess=next;
  }
  return guess;
}
function nzClock(date){
  const parts=zoneParts(date, "Pacific/Auckland");
  return parts.hour+":"+parts.minute;
}
function marketClocks(now){
  const sessions=[
    ["Asia","Asia/Tokyo",9,0,18,0],
    ["London","Europe/London",8,0,17,0],
    ["New York","America/New_York",8,0,17,0],
    ["US stocks","America/New_York",9,30,16,0]
  ];
  const parts=sessions.map(row=>{
    let open=atLocal(row[1], row[2], row[3], now);
    let close=atLocal(row[1], row[4], row[5], now);
    if(now>=close){
      const next=new Date(now.getTime()+24*60*60*1000);
      open=atLocal(row[1], row[2], row[3], next);
      close=atLocal(row[1], row[4], row[5], next);
    }
    const on=now>=open&&now<close;
    return row[0]+(on?" open till "+nzClock(close):" opens "+nzClock(open));
  });
  const hour=now.getHours()+now.getMinutes()/60;
  let pace="Slow";
  if(hour>=21||hour<6) pace="Moving";
  if(hour>=3.5&&hour<6) pace="Fast";
  return pace+" · "+parts.join(" · ");
}
function localStamp(){
  const d=new Date();
  const p=n=>String(n).padStart(2,"0");
  return p(d.getHours())+":"+p(d.getMinutes())+":"+p(d.getSeconds());
}
function localWhen(value){
  const raw=String(value||"");
  if(!raw) return "";
  const iso=raw.includes("T")?raw:raw.replace(" ","T");
  const zoned=/Z|[+-]\d\d:?\d\d$/.test(iso);
  const d=new Date(zoned?iso:iso+"Z");
  if(isNaN(d.getTime())) return raw.slice(5,16).replace("T"," ");
  const p=n=>String(n).padStart(2,"0");
  return p(d.getMonth()+1)+"-"+p(d.getDate())+" "+p(d.getHours())+":"+p(d.getMinutes());
}
function speak(text){
  const box=$("alerts");
  const line=localStamp()+" "+text;
  const prior=(box.textContent||"").split("\n").filter(Boolean);
  box.textContent=[line].concat(prior).slice(0,8).join("\n");
  if(window.Notification&&Notification.permission==="granted"){
    try{new Notification("ZEUS",{body:text})}catch(e){}
  }
}
let board={};
function boardLine(payload){
  const rows=(payload&&payload.rows)||[];
  const rank={INTRADAY:0,INTERDAY:1,RESPONSIVE:2,SCALP:3,SWING:4,ICEBERG:5};
  const live=rows.filter(r=>rank[r.chart]!=null);
  const ranked=live.filter(r=>r.side&&r.entry!=null).sort((a,b)=>rank[a.chart]-rank[b.chart]);
  const hit=ranked.find(r=>r.tradeable);
  if(hit){
    const money=String(moneyLine(hit, payload.account)).split(" · ")[0];
    return {kind:"SIGNAL", side:hit.side, text:hit.chart+" "+hit.side+" "+px(hit.entry), sub:"stop "+px(hit.stop)+" · "+money};
  }
  const push=live.find(r=>r.push&&r.side&&r.entry!=null);
  if(push){
    const tp=(push.targets&&push.targets.length)?push.targets[0]:push.target;
    const mult=push.r!=null?push.r+"R · ":"";
    return {kind:"PUSH", side:push.side, text:"PUSH "+push.side+" "+px(push.entry), sub:"high risk · stop "+px(push.stop)+" · TP "+px(tp)+" "+mult+"not a trade"};
  }
  const coming=live.find(r=>r.coming&&r.coming.side);
  if(coming){
    const tps=coming.coming.tps?coming.coming.tps+" · ":"";
    return {kind:"INCOMING", side:coming.coming.side, text:coming.chart+" "+coming.coming.side+" into "+px(coming.coming.zone), sub:tps+"not a trade yet"};
  }
  return {kind:"QUIET", text:"quiet", sub:""};
}
function paintBoard(){
  const box=$("board");
  if(!box) return;
  box.innerHTML=PAIRS.map(p=>{
    const item=board[p[0]]||{kind:"QUIET", text:"reading", sub:""};
    const tone=item.kind==="SIGNAL"?(item.side==="BUY"?"good":"bad"):(item.kind==="INCOMING"||item.kind==="PUSH"?"warn":"muted");
    return `<div class="pairq" onclick="setPair('${p[0]}')"><b class="${tone}">${p[1]} · ${item.text}</b>${item.sub?`<span class="sub">${item.sub}</span>`:""}</div>`;
  }).join("");
}
function consider(payload){
  if(!payload||!payload.ok) return;
  const name=payload.label||payload.symbol;
  const bag=seenBag();
  const news=payload.news||{};
  if(news.warn){
    const key="N|"+(news.holiday||news.name)+"|"+news.impact;
    if(!bag[key]){
      remember(key);
      const mins=Math.max(0, Math.round(Number(news.seconds||0)/60));
      const what=news.holiday?("Bank holiday "+news.holiday+". "):"";
      speak(what+(news.name||"News")+" "+(news.impact||"")+" in "+mins+" minutes.");
    }
  }
  (payload.rows||[]).forEach(row=>{
    const coming=row.coming;
    if(coming&&coming.side){
      const same=(payload.rows||[]).some(other=>other.side===coming.side&&other.entry!=null&&Math.abs(Number(other.zone)-Number(coming.zone))<1e-6);
      const key="C|"+payload.symbol+"|"+row.chart+"|"+coming.side+"|"+coming.zone;
      if(!same&&!bag[key]){
        remember(key);
        speak(name+" "+row.chart+" "+coming.side+" coming into "+coming.zone+". Not a trade yet."+(coming.tps?" "+coming.tps+".":""));
      }
    }
    if(row.push&&row.side&&row.entry!=null){
      const key="P|"+payload.symbol+"|"+row.side+"|"+row.entry+"|"+row.stop+"|"+row.time;
      if(!bag[key]){
        remember(key);
        speak(name+" intraday push "+row.side+". High risk. Entry "+row.entry+" stop "+row.stop+" "+(row.harvest||"")+". Not a trade.");
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
      const late=!!(r.late||r.state==="LATE");
      const tone=late?"late":(r.push&&!r.tradeable?"warn":(r.side==="BUY"?"good":"bad"));
      const side=r.side?`<span class="${tone}">${r.side}</span>`:"—";
      const stateCell=late?`<span class="late">${r.state||"LATE"}</span>`:(r.state||"—");
      const targets=(r.targets&&r.targets.length)?r.targets.join(" · "):(r.target??"—");
      const harvest=moneyLine(r);
      const limitOk=["ICEBERG","SCALP","INTRADAY","SWING","RESPONSIVE"].includes(r.chart);
      const button=r.tradeable?`<button onclick="event.stopImmediatePropagation();trade('${r.chart}','MARKET')">MARKET</button>${limitOk?`<button onclick="event.stopImmediatePropagation();trade('${r.chart}','LIMIT')">LIMIT</button>`:""}`:"";
      const noteCell=late?`<span class="late">${r.note||"Entry is late. Not an order."}</span>`:(r.note||r.reason||"—");
      return `<tr class="${r.chart===pickedRow?"pick":""}" onclick="pickedRow='${r.chart}';paint()"><td>${r.chart}</td><td>${stateCell}</td><td>${side}</td><td>${r.entry??"—"}</td><td>${r.stop??"—"}</td><td>${targets}</td><td>${harvest}</td><td>${noteCell}</td><td>${button}</td></tr>`;
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
  const openBits=(research.open||[]).filter(x=>x.chart==="INTRADAY"||x.chart==="SWING"||x.chart==="ICEBERG"||x.chart==="INTERDAY"||x.chart==="SCALP"||x.chart==="RESPONSIVE").map(x=>x.chart+" "+x.side+" went "+(x.mfe??0)+" before turning");
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
async function postManage(body){
  const r=await fetch("/api/v19/signals/ticket",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(body)});
  if(r.status===404) throw Error("Zeus is still on the old close. Close Zeus, then run the desktop file.");
  return r;
}
async function closeTicket(ticket){
  const r=await postManage({owner_approved:true,fast_ack:true,ticket:ticket,action:"CLOSE",reason:"SIGNALS PAGE"});
  const j=await r.json();
  if(!r.ok||!((j.management||{}).ok)) throw Error(((j.management||{}).reason)||j.message||"the close was rejected");
}
async function trade(chartName, mode){
  const row=(data.rows||[]).find(r=>r.chart===chartName&&r.tradeable);
  if(!row){setStatus("NOT SENT · this row has no order. A stop that price has already passed stays on the row with no button.", 8000);return}
  const limit=mode==="LIMIT";
  const quote=(data&&data.quote)||{};
  const bid=Number(quote.bid), ask=Number(quote.ask);
  if(row.side==="SELL" && !(row.stop>ask && row.target<bid)){setStatus("NOT SENT · a sell stop must be above the live ask, and the target below the bid.", 12000); return}
  if(row.side==="BUY" && !(row.stop<bid && row.target>ask)){setStatus("NOT SENT · a buy stop must be below the live bid, and the target above the ask.", 12000); return}
  const plan=orderRisk();
  if(plan.error){setStatus(plan.error, 8000);return}
  setStatus("SENDING...", 20000);
  const started=performance.now();
  try{
    await fetch("/api/v19/signals/priority",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({active:true})}).catch(()=>{});
    const r=await fetch("/api/v19/owner-order/submit",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({
      owner_approved:true,symbol:(data&&data.broker)||symbol,timeframe:row.chart==="SWING"?"H4":"M1",
      order_type:limit?(row.side==="BUY"?"BUY_LIMIT":"SELL_LIMIT"):(row.side==="BUY"?"MARKET_BUY":"MARKET_SELL"),
      entry:limit?row.entry:null,stop:row.stop,targets:[row.target],requested_risk_pct:plan.pct,horizon_lane:"INTRADAY",
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
      return;
    }
    fetch("/api/v19/signals/taken",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({symbol:symbol,chart:chartName,side:row.side,reason:row.reason,entry:row.entry,stop:row.stop,target:row.target,r:row.r,time:row.time})}).catch(()=>{});
    const text="SENT · volume "+(ex.volume??"—")+" · "+(broker.comment||"check the MT5 Trade tab")+" · "+ms+" ms";
    setStatus(text, 20000);
    load();
  }catch(e){setStatus("NOT SENT · "+e.message, 20000)}
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
  manageNote="Sending "+action+"...";
  showManageNote();
  setStatus(manageNote, 20000);
  const started=performance.now();
  try{
    await fetch("/api/v19/signals/priority",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({active:true})}).catch(()=>{});
    const r=await postManage(body);
    const j=await r.json();
    const ms=Math.round((j.timings_ms&&j.timings_ms.total)||j.management_server_ms||(performance.now()-started));
    const ok=r.ok&&j.ok!==false&&(j.management||{}).ok;
    const text=(ok?"BROKER OK":"BLOCKED")+" · "+brokerLine(j)+" · "+ms+" ms";
    manageNote=text;
    showManageNote();
    positionHtml="";
    setStatus(text, 20000);
    load();
  }catch(e){const text="MANAGE ERROR · "+e.message; manageNote=text; showManageNote(); positionHtml=""; setStatus(text, 20000)}
  finally{fetch("/api/v19/signals/priority",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({active:false})}).catch(()=>{})}
}
async function editStop(ticket){
  const price=Number(prompt("New stop price"));
  if(!isFinite(price)||price<=0)return;
  const started=performance.now();
  const body={owner_approved:true,fast_ack:true,ticket:ticket,action:"MODIFY_POSITION",stop_loss:price,reason:"SIGNALS PAGE EDIT SL"};
  await fetch("/api/v19/signals/priority",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({active:true})}).catch(()=>{});
  try{
    const r=await postManage(body);
    const j=await r.json();
    const ms=Math.round(j.management_server_ms||(performance.now()-started));
    const text=((r.ok&&j.ok!==false&&(j.management||{}).ok)?"STOP SENT":"BLOCKED")+" · "+brokerLine(j)+" · "+ms+" ms";
    setStatus(text, 20000);
    load();
  }catch(e){setStatus("MANAGE ERROR · "+e.message, 20000)}
  finally{fetch("/api/v19/signals/priority",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({active:false})}).catch(()=>{})}
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
    const r=await postManage(body);
    const j=await r.json();
    const ms=Math.round(j.management_server_ms||(performance.now()-started));
    const text=((r.ok&&j.ok!==false&&(j.management||{}).ok)?"TARGET SENT "+price:"BLOCKED")+" · "+brokerLine(j)+" · "+ms+" ms";
    setStatus(text, 20000);
    load();
  }catch(e){setStatus("MANAGE ERROR · "+e.message, 20000)}
  finally{fetch("/api/v19/signals/priority",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({active:false})}).catch(()=>{})}
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
  if(document.visibilityState==="hidden"||!data||data.symbol!==symbol)return;
  try{
    const r=await fetch("/api/quote?symbol="+encodeURIComponent(symbol));
    const j=await r.json();
    if(!r.ok||!j.ok)return;
    const q=j.quote||{};
    const bid=Number(q.bid),ask=Number(q.ask);
    if(!isFinite(bid)||!isFinite(ask))return;
    const rows=data.candles||[];
    if(rows.length){
      const lastClose=Number(rows[rows.length-1].close);
      if(isFinite(lastClose)&&lastClose>0&&Math.abs(bid-lastClose)/lastClose>0.5)return;
    }
    if(bid===fastBid&&ask===fastAsk)return;
    fastBid=bid;fastAsk=ask;
    data.quote={bid:bid,ask:ask};
    data.spread=ask-bid;
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
let positionHtml="", manageNote="";
function showManageNote(){
  const box=$("positions");
  if(!box)return;
  let note=document.getElementById("manageNote");
  if(!note){note=document.createElement("div"); note.id="manageNote"; note.className="warn"; box.appendChild(note);}
  note.textContent=manageNote;
}
function positionBox(list){
  const rows=(list||[]).map(p=>`<div style="margin-top:8px"><b class="${p.side==="BUY"?"good":"bad"}">${p.side}</b> ${p.volume} @ ${p.price_open}<br>P/L ${p.profit} · SL ${p.stop_loss??"—"} · TP ${p.take_profit??"—"}<br>
    <button type="button" onclick="manage(${p.ticket},'CLOSE')">CLOSE</button>
    <button type="button" onclick="manage(${p.ticket},'BREAK_EVEN',${p.price_open})">BE</button>
    <button type="button" onclick="manage(${p.ticket},'PARTIAL',null,10)">10%</button>
    <button type="button" onclick="manage(${p.ticket},'PARTIAL',null,50)">50%</button>
    <button type="button" onclick="editStop(${p.ticket})">EDIT SL</button>
    <button type="button" onclick="editR(${p.ticket},${p.price_open},${p.stop_loss},'${p.side}')">EDIT R</button>
    ${p.manage_line?`<div class="muted">${p.manage_line}</div>`:""}</div>`).join("");
  const note=manageNote?`<div class="warn">${manageNote}</div>`:"";
  return rows?rows+note:"<div class='muted'>No open broker position on this pair.</div>"+note;
}
const lotValue={};
function bookCash(n){
  if(!isFinite(n)) return "—";
  const sign=n<0?"-":"";
  const abs=Math.abs(n);
  return sign+"$"+(abs>=10?Math.round(abs).toLocaleString():abs.toFixed(2));
}
function bookPct(n, equity){
  if(!(equity>0)||!isFinite(n)) return "";
  return " · "+(n/equity*100).toFixed(1)+"%";
}
function paintBook(list){
  const box=$("bookrisk");
  if(!box) return;
  const rows=list||[];
  if(!rows.length){box.textContent="No open lots on this pair."; return;}
  const q=(data&&data.quote)||{};
  const bid=Number(q.bid), ask=Number(q.ask);
  const acct=(data&&data.account)||{};
  const equity=Number(acct.equity||acct.balance);
  let risk=0, potential=0, locked=0, naked=0, unpriced=0, covered=0;
  rows.forEach(p=>{
    const entry=Number(p.price_open), stop=Number(p.stop_loss)||0, tp=Number(p.take_profit)||0, profit=Number(p.profit);
    const mark=p.side==="SELL"?ask:bid;
    const move=p.side==="SELL"?entry-mark:mark-entry;
    if(isFinite(profit)&&isFinite(move)&&Math.abs(move)>Math.max(Math.abs(entry)*1e-6, 1e-6)){
      const seen=profit/move;
      if(seen>0) lotValue[p.ticket]=seen;
    }
    const per=lotValue[p.ticket];
    if(!(per>0)){unpriced++; return;}
    const buy=p.side!=="SELL";
    if(!(stop>0)){naked++; return;}
    if(buy?stop>=entry:stop<=entry){
      covered++;
      const held=(buy?stop-entry:entry-stop)*per;
      if(held>0) locked+=held;
    }else risk+=(buy?entry-stop:stop-entry)*per;
    if(tp>0&&isFinite(mark)){
      const room=buy?tp-mark:mark-tp;
      if(room>0) potential+=room*per;
    }
  });
  box.innerHTML="Open risk "+bookCash(risk)+bookPct(risk, equity)+" of the account<br>Potential "+bookCash(potential)+bookPct(potential, equity)+" if the targets are hit"
    +(covered?"<br>"+covered+" lot"+(covered>1?"s are":" is")+" at the entry or better. That risk is off."+(locked>0?" Locked "+bookCash(locked)+".":""):"")
    +(naked?"<br>"+naked+" lot"+(naked>1?"s have":" has")+" no stop. Those dollars are not counted.":"")
    +(unpriced?"<br>The price is still on the fill, so the dollars are not in yet.":"");
}
async function livePositions(){
  if(document.visibilityState==="hidden"||!symbol)return;
  try{
    const r=await fetch("/api/v19/signals/positions?symbol="+encodeURIComponent(symbol));
    const j=await r.json();
    if(!r.ok||!j.ok)return;
    if(data) data.positions=j.positions||[];
    paintBook(j.positions||[]);
    const box=$("positions");
    if(!box||box.matches(":hover"))return;
    const next=positionBox(j.positions||[]);
    if(next===positionHtml)return;
    positionHtml=next;
    box.innerHTML=next;
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
_PRICE = {
    "XAUUSD": (500.0, 20000.0),
    "XAGUSD": (5.0, 200.0),
    "NAS100": (3000.0, 80000.0),
    "BTCUSD": (1000.0, 1000000.0),
    "EURUSD": (0.5, 2.5),
    "USDJPY": (50.0, 300.0),
    "WTI": (20.0, 200.0),
    "NG-C": (0.5, 20.0),
    "GER40": (4000.0, 40000.0),
}
# The cash name is first. A future is last. StarTrader adds +. Vantage raw adds .r.
_TRY = {
    "XAUUSD": ("XAUUSD+", "XAUUSD", "XAUUSD.r", "XAUUSD.a", "GOLD+", "GOLD"),
    "XAGUSD": ("XAGUSD+", "XAGUSD", "XAGUSD.r", "SILVER+", "SILVER"),
    "NAS100": ("NAS100+", "NAS100", "NAS100.r", "US100+", "US100", "USTEC+", "USTEC", "USTECH", "NAS100ft+"),
    "BTCUSD": ("BTCUSD", "BTCUSD+", "BTCUSD.r"),
    "EURUSD": ("EURUSD+", "EURUSD", "EURUSD.r"),
    "USDJPY": ("USDJPY+", "USDJPY", "USDJPY.r"),
    "WTI": ("USOUSD+", "USOUSD", "USOIL+", "USOIL", "WTI+", "WTI", "CL-OIL"),
    "NG-C": ("NG-C", "NG-C+", "NATGAS+", "NATGAS", "NGAS+", "NGAS"),
    "GER40": ("GER40+", "GER40", "GER40.r", "DE40+", "DE40", "DAX40", "GER40ft+"),
}
_ROOTS = {
    "XAUUSD": ("XAUUSD", "GOLD"),
    "XAGUSD": ("XAGUSD", "SILVER"),
    "NAS100": ("NAS100", "USTEC", "USTECH", "US100", "NDX100"),
    "BTCUSD": ("BTCUSD",),
    "EURUSD": ("EURUSD",),
    "USDJPY": ("USDJPY",),
    "WTI": ("USOUSD", "USOIL", "WTIUSD", "XTIUSD", "WTI", "CLOIL"),
    "NG-C": ("NGC", "NATGAS", "NGAS", "XNGUSD"),
    "GER40": ("GER40", "GER30", "DE40", "DAX40", "GDAXI", "DAX"),
}
_TAIL = {"", "R", "M", "C", "I", "P", "E", "FT", "FUT", "FUTURE", "CASH", "PRO", "RAW", "ECN", "SB"}


def _flat_name(name: str) -> str:
    return str(name).upper().replace(".", "").replace("+", "").replace("-", "").replace("_", "").replace(" ", "")


def _in_band(symbol: str, bid: float) -> bool:
    low, high = _PRICE.get(symbol, (0.0, 0.0))
    return low < float(bid) < high


def _root_match(symbol: str, flat: str) -> bool:
    if symbol == "WTI" and any(skip in flat for skip in _OIL_SKIP):
        return False
    if symbol == "NG-C" and any(skip in flat for skip in ("XAG", "XAU", "SILVER", "GOLD", "BRENT", "UKOIL")):
        return False
    for root in _ROOTS.get(symbol, ()):
        if not flat.startswith(root):
            continue
        if flat[len(root):] in _TAIL:
            return True
    return False


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


def _broker_feed(host: Any, symbol: str, chart: str, scan: bool) -> tuple[Any, dict[str, list[dict[str, Any]]], str] | None:
    """Use the broker's own spelling. The cash name wins. The price has to be that market."""
    worker = _worker(host)
    if worker is None:
        return None
    found: list[tuple[int, str, Any]] = []

    def consider(name: str, got: Any) -> None:
        bid = float(getattr(got, "bid", 0) or 0)
        if not _in_band(symbol, bid):
            return
        flat = _flat_name(name)
        cash = 0 if ("FT" in flat or "FUT" in flat) else 1
        found.append((cash, str(name), got))

    for name in _TRY.get(symbol, ()):
        try:
            consider(name, worker.quote(name))
        except Exception:
            continue
        if found and found[-1][0] == 1:
            break
    if not found:
        try:
            catalog = tuple(worker.symbol_catalog())
        except Exception:
            catalog = ()
        for name in catalog:
            if not _root_match(symbol, _flat_name(name)):
                continue
            try:
                consider(str(name), worker.quote(str(name)))
            except Exception:
                continue
    if not found:
        return None
    found.sort(key=lambda item: item[0], reverse=True)
    _rank, chosen, quote = found[0]
    bars_by_chart: dict[str, list[dict[str, Any]]] = {}
    names = ("M1", "M15", "H1", "H4", "D1") if scan else CHARTS
    for name in names:
        try:
            bars_by_chart[name] = _candles_from_rows(worker.bars(chosen, Timeframe(name), count=160 if scan else 400))
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
    """The pair on screen can wait for one missing chart. A scan has to see the charts a trade is built from."""
    found: dict[str, list[dict[str, Any]]] = {}
    if scan:
        for name in ("M1", "M15", "H1", "H4", "D1"):
            found[name] = _bars(host, symbol, name, 90.0, 160)
        for name in CHARTS:
            found.setdefault(name, _CACHE.get(symbol + "|" + name, (0.0, []))[1])
        return found
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
        for name in missing:
            try:
                found[name] = _bars(host, symbol, name, 90.0, 120)
            except Exception:
                found[name] = []
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


def _ladder_levels(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """The study writes bid and ask as ladder p/b/a. Older files used levels."""
    rows = raw.get("ladder")
    if not isinstance(rows, list) or not rows:
        rows = raw.get("levels") or []
    levels = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        price = item.get("price", item.get("p"))
        if isinstance(price, bool) or not isinstance(price, (int, float)) or float(price) <= 0:
            continue
        levels.append({
            "price": float(price),
            "bid_contracts": item.get("bid_contracts", item.get("b")),
            "ask_contracts": item.get("ask_contracts", item.get("a")),
        })
    return levels


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
            "levels": _ladder_levels(raw),
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
        stack = raw.get("stack")
        if isinstance(stack, dict) and stack.get("price") is not None:
            book["stack"] = {
                "price": float(stack["price"]),
                "side": str(stack.get("side") or ""),
            }
        for name in ("unfinished_high", "unfinished_low"):
            value = raw.get(name)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) > 0:
                book[name] = float(value)
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
    return _root_match(symbol, _flat_name(broker))


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
    """Move the stop when manage is on. The close warning is sent either way."""
    if not positions:
        return
    managing = manage_enabled()
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
        if match is None or nearest is None:
            continue
        close = nearest <= max(abs(entry) * 0.002, 1e-6)
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
        saved = {
            "symbol": symbol,
            "line": "",
            "risk": previous.get("risk"),
            "dip": previous.get("dip"),
            "sent": previous.get("sent"),
            "told": previous.get("told") or "",
            "magnet": previous.get("magnet"),
            "tp": previous.get("tp"),
        }
        magnet = None
        magnet_open = False
        ahead = book.get("unfinished_high") if side == "BUY" else book.get("unfinished_low")
        if isinstance(ahead, (int, float)) and not isinstance(ahead, bool):
            magnet = float(ahead)
            magnet_open = True
            saved["magnet"] = magnet
        elif isinstance(previous.get("magnet"), (int, float)) and not isinstance(previous.get("magnet"), bool):
            magnet = float(previous["magnet"])
            magnet_open = False
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
            symbol=symbol,
            magnet=magnet,
            magnet_open=magnet_open,
        )
        saved["line"] = decision.get("line") or ""
        saved["risk"] = decision.get("risk")
        saved["dip"] = decision.get("dip")
        armed = False
        try:
            cfg = _auto_load()
            armed = bool(cfg.get("armed")) and symbol in (cfg.get("symbols") or [])
        except Exception:
            armed = False
        acting = (managing or armed) and close
        if acting and decision.get("bank"):
            try:
                _ticket_by_volume(host, int(pos["ticket"]), "CLOSE", None, None, ())
            except Exception:
                pass
            else:
                _announce_manage(symbol, str(saved["line"] or "Bank."), int(pos["ticket"]), entry)
                saved["told"] = saved["line"]
        else:
            new_stop = decision.get("stop")
            if acting and isinstance(new_stop, (int, float)) and not isinstance(new_stop, bool) and saved.get("sent") != float(new_stop):
                try:
                    _ticket_by_volume(host, int(pos["ticket"]), "MODIFY_POSITION", None, float(new_stop), ())
                except Exception:
                    new_stop = None
                else:
                    saved["sent"] = float(new_stop)
                    pos["stop_loss"] = float(new_stop)
                    _announce_manage(symbol, f"Stop moved to {round(float(new_stop), 5)}.", int(pos["ticket"]), entry)
            nxt = decision.get("take_profit")
            if acting and isinstance(nxt, (int, float)) and not isinstance(nxt, bool) and saved.get("tp") != float(nxt):
                try:
                    _ticket_by_volume(host, int(pos["ticket"]), "MODIFY_POSITION", None, None, (float(nxt),))
                except Exception:
                    nxt = None
                else:
                    saved["tp"] = float(nxt)
                    _announce_manage(symbol, str(saved["line"]), int(pos["ticket"]), entry)
                    saved["told"] = saved["line"]
        warn = str(saved["line"] or "")
        if warn and warn != saved["told"] and (acting or ("is being traded" in warn) or warn.startswith("90%")):
            _announce_manage(symbol, warn, int(pos["ticket"]), entry)
            saved["told"] = warn
        trades[key] = saved
        if saved["line"] and close:
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
        extra = ""
        if holiday:
            extra = " · " + str(holiday.get("name") or "HOLIDAY")
        return {"line": "NO NEWS ON THE CALENDAR" + extra}
    seconds = float(nxt.get("seconds_from_now") or 0)
    minutes = int(abs(seconds) // 60)
    clock = f"{minutes // 60}h {minutes % 60}m" if minutes >= 60 else f"{minutes}m"
    when = "ago" if seconds < 0 else "in"
    impact = str(nxt.get("impact") or "UNKNOWN").upper()
    name = str(nxt.get("name") or "event")
    today = []
    for row in upcoming:
        if float(row.get("seconds_from_now") or 0) > 24 * 3600:
            break
        today.append(str(row.get("name") or "event") + " " + str(row.get("impact") or "UNKNOWN"))
    line = f"NEXT {name} {impact} {when} {clock}"
    holiday_name = str(holiday.get("name") or "HOLIDAY") if holiday else ""
    if holiday:
        line = "CLOSED · " + holiday_name + " · " + line
    if today:
        line += " · TODAY " + " · ".join(today[:4])
    if snap.get("state") not in {"LIVE_SCHEDULE", "CACHED_SCHEDULE"}:
        line = "NO CALENDAR · " + line
    holiday_seconds = float(holiday.get("seconds_from_now") or 0) if holiday else None
    warn = (impact in {"HIGH", "HOLIDAY"} and 0 <= seconds <= 1800) or (
        holiday_seconds is not None and 0 <= holiday_seconds <= 1800
    )
    return {
        "line": line,
        "state": snap.get("state"),
        "name": name,
        "impact": impact,
        "seconds": seconds,
        "holiday": holiday_name,
        "warn": warn,
    }


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


def _drop_left(symbol: str, rows: list[dict[str, Any]], bid: float, ask: float, positions: list[dict[str, Any]]) -> None:
    """An entry price the market has left is not a current order, unless that side is already open."""
    band = _band(symbol)
    for index, row in enumerate(rows):
        if not row.get("side") or row.get("entry") is None:
            continue
        side = str(row.get("side"))
        if any(str(position.get("side")) == side for position in positions):
            continue
        live = bid if side == "BUY" else ask
        try:
            away = abs(float(live) - float(row["entry"]))
        except (TypeError, ValueError):
            continue
        if away <= band:
            continue
        rows[index] = _wait(str(row.get("chart") or ""), "Price has left that entry. Not a trade.", str(row.get("market") or ""))


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
    broker = symbol
    bid_now = float(getattr(quote, "bid", 0) or 0) if quote is not None else 0.0
    if not _in_band(symbol, bid_now):
        direct = _broker_feed(host, symbol, chart, scan)
        if direct is None:
            label = LABELS.get(symbol, symbol)
            raise RuntimeError(f"{label} is not on this MetaTrader feed. Show it in Market Watch. The page name is {symbol}.")
        quote, bars_by_chart, broker = direct
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
    else:
        place_value(book, symbol, bid, ask)
    place_marks(book, symbol, bid, ask)
    levels = session_levels(bars_by_chart.get("M15") or bars_by_chart.get("M5") or [])
    pools = liquidity(levels, bars_by_chart)
    rows = build_rows(symbol, bars_by_chart, book, spread, levels, bid, ask)
    for row in rows:
        if not row.get("tradeable"):
            continue
        note = stack_line(symbol, str(row.get("side") or ""), book.get("stack") if isinstance(book.get("stack"), dict) else None)
        if note:
            row["note"] = (str(row.get("note") or "") + " " + note).strip()
    positions = _positions(host, symbol)
    minute = _closed(bars_by_chart.get("M1") or [])
    latest = _time(minute[-1]) if minute else ""
    settle_rows(symbol, rows, positions, bid, ask, spread, book, latest)
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
        shots = {"M1": compact("M1"), "M5": compact("M5"), "M15": compact("M15"), "H1": compact("H1"), "H4": compact("H4")}
    return {
        "ok": True,
        "symbol": symbol,
        "broker": broker,
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
            "unfinished_high": book.get("unfinished_high"),
            "unfinished_low": book.get("unfinished_low"),
            "stepping": stepping,
            "note": str(book.get("reason") or ""),
        },
        "positions": positions,
        "manage": manage_enabled(),
        "ice_auto": ice_enabled(),
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


def ice_enabled() -> bool:
    try:
        from zeus3.v19.telegram_alert import ice_enabled as saved
        return bool(saved())
    except Exception:
        return False


def set_ice(on: bool) -> None:
    from zeus3.v19.telegram_alert import set_ice as save
    save(bool(on))


async def signals_ice(host: Any, request: web.Request) -> web.Response:
    """Iceberg auto. Off until this is on. It sends a resting limit, not a market chase."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict) or "on" not in payload:
        return web.json_response({"ok": True, "on": ice_enabled()})
    set_ice(bool(payload.get("on")))
    return web.json_response({"ok": True, "on": ice_enabled()})


async def signals_positions(host: Any, request: web.Request) -> web.Response:
    """Profit from the broker snapshot already in memory. No chart rebuild."""
    symbol = str(request.query.get("symbol") or "").upper()
    if symbol not in PAIRS:
        return web.json_response({"ok": False, "message": "unknown pair"}, status=400)
    return web.json_response({"ok": True, "positions": _positions(host, symbol)})


def _quick_view(symbol: str, chart: str) -> dict[str, Any] | None:
    """Candles already read for this chart. The click does not wait for another full rebuild."""
    base = _VIEW.get(symbol)
    if not isinstance(base, dict):
        return None
    cached = _CACHE.get(symbol + "|" + chart)
    candles = cached[1] if cached and cached[1] else None
    if not candles:
        last = _LAST.get(symbol + "|" + chart)
        candles = last.get("candles") if isinstance(last, dict) else None
    if not candles:
        return None
    quick = dict(base)
    quick["candles"] = candles
    quick["chart"] = chart
    quick["ok"] = True
    return quick


async def signals_snapshot(host: Any, request: web.Request) -> web.Response:
    _auto_ensure(host)
    symbol = str(request.query.get("symbol") or "XAUUSD").upper()
    chart = str(request.query.get("chart") or "M5").upper()
    scan = str(request.query.get("scan") or "") == "1"
    view = str(request.query.get("view") or "") == "1"
    if symbol not in PAIRS or chart not in CHARTS:
        return web.json_response({"ok": False, "message": "unknown pair or chart"}, status=400)
    quick = _quick_view(symbol, chart) if view and not scan else None
    if quick is not None:
        return web.json_response(quick)
    if view and not scan and isinstance(_VIEW.get(symbol), dict):
        locked = _LOCK.acquire(timeout=2)
        if locked:
            try:
                try:
                    await asyncio.to_thread(_bars, host, symbol, chart, 25.0, 200)
                except Exception:
                    pass
            finally:
                _LOCK.release()
            quick = _quick_view(symbol, chart)
            if quick is not None:
                return web.json_response(quick)
    if _ORDER_BUSY.is_set():
        cached = _LAST.get(symbol + "|" + chart)
        if cached and cached.get("candles"):
            return web.json_response(cached)
    if scan:
        locked = _LOCK.acquire(blocking=False)
    else:
        locked = _LOCK.acquire(timeout=4)
    if not locked:
        cached = _LAST.get(symbol + "|" + chart)
        if cached and cached.get("candles"):
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
    if not scan and payload.get("candles"):
        _LAST[symbol + "|" + chart] = payload
        _VIEW[symbol] = payload
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

_AUTO_HOST: Any = None
_AUTO_THREAD: threading.Thread | None = None
_AUTO_GUARD = threading.Lock()


def _auto_file() -> Any:
    from pathlib import Path

    return Path("zeus_auto.json")


def _auto_default() -> dict[str, Any]:
    return {
        "armed": False,
        "symbols": [],
        "unit": "usd",
        "risk": 200.0,
        "max_risk": 400.0,
        "compound": False,
        "base_balance": None,
        "sent": {},
        "log": [],
    }


def _auto_load() -> dict[str, Any]:
    cfg = _auto_default()
    try:
        found = json.loads(_auto_file().read_text(encoding="utf-8"))
    except Exception:
        return cfg
    if isinstance(found, dict):
        cfg.update(found)
    cfg["armed"] = bool(cfg.get("armed"))
    cfg["compound"] = bool(cfg.get("compound"))
    cfg["symbols"] = [name for name in (cfg.get("symbols") or []) if name in PAIRS]
    cfg["unit"] = "pct" if str(cfg.get("unit")) == "pct" else "usd"
    cfg["sent"] = cfg.get("sent") if isinstance(cfg.get("sent"), dict) else {}
    cfg["log"] = list(cfg.get("log") or [])[-40:]
    return cfg


def _auto_store(cfg: dict[str, Any]) -> None:
    cfg["log"] = list(cfg.get("log") or [])[-40:]
    _auto_file().write_text(json.dumps(cfg), encoding="utf-8")


def _auto_say(cfg: dict[str, Any], line: str) -> None:
    previous = list(cfg.get("log") or [])
    if previous and previous[-1].endswith("  " + line):
        return
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    previous.append(stamp + "  " + line)
    cfg["log"] = previous[-40:]


def _auto_ensure(host: Any) -> None:
    global _AUTO_HOST, _AUTO_THREAD
    _AUTO_HOST = host
    with _AUTO_GUARD:
        if _AUTO_THREAD is not None and _AUTO_THREAD.is_alive():
            return
        _AUTO_THREAD = threading.Thread(target=_auto_loop, name="zeus-auto", daemon=True)
        _AUTO_THREAD.start()


def _auto_money(cfg: dict[str, Any], account: dict[str, Any]) -> tuple[float, float, float]:
    balance = float(account.get("balance") or 0)
    equity = float(account.get("equity") or balance or 0)
    base = float(cfg.get("base_balance") or balance or 0)
    pot = equity if cfg.get("compound") else (base or balance)
    risk = float(cfg.get("risk") or 0)
    cap = float(cfg.get("max_risk") or 0)
    if str(cfg.get("unit")) == "pct":
        return pot * risk / 100.0, pot * cap / 100.0, pot
    return risk, cap, pot


def _auto_positions(host: Any) -> list[dict[str, Any]]:
    found = []
    for symbol in PAIRS:
        for row in _positions(host, symbol):
            row["symbol"] = symbol
            row["protected"] = _broker_protected(row)
            found.append(row)
    return found


def _auto_hit(side: str, target: float, bid: float, ask: float) -> bool:
    if side == "BUY":
        return bid >= target
    if side == "SELL":
        return ask <= target
    return False


def _auto_choose(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in rows:
        if not row.get("tradeable"):
            continue
        if str(row.get("state") or "") in {"LATE", "OPEN"} or row.get("late"):
            continue
        if str(row.get("reason") or "") in {"POTENTIAL", "OPEN"}:
            continue
        if str(row.get("side") or "") not in {"BUY", "SELL"}:
            continue
        try:
            if float(row.get("stop") or 0) <= 0 or float(row.get("target") or row.get("targets", [0])[0] or 0) <= 0:
                continue
        except (TypeError, ValueError, IndexError):
            continue
        return row
    return None


def _auto_pass(host: Any, cfg: dict[str, Any]) -> None:
    account = _account(host)
    if not account.get("balance"):
        _auto_say(cfg, "No broker balance yet.")
        return
    risk_usd, cap_usd, pot = _auto_money(cfg, account)
    if risk_usd <= 0 or cap_usd <= 0:
        _auto_say(cfg, "Risk or the max is not set.")
        return
    if risk_usd > cap_usd:
        _auto_say(cfg, "One trade is larger than the max. Nothing sent.")
        return
    positions = _auto_positions(host)
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in positions:
        by_symbol.setdefault(str(row.get("symbol")), []).append(row)
    sent = cfg.setdefault("sent", {})
    for symbol in list(by_symbol):
        try:
            _payload(symbol, "M1", host, scan=True)
        except Exception as exc:
            _auto_say(cfg, symbol + " was not managed. " + str(exc))
    positions = _auto_positions(host)
    open_risk = 0.0
    for row in positions:
        if row.get("protected"):
            continue
        remembered = sent.get(str(row.get("symbol"))) if isinstance(sent.get(str(row.get("symbol"))), dict) else {}
        open_risk += float(remembered.get("risk_usd") or risk_usd)
    chosen_symbols = [name for name in cfg.get("symbols") or [] if name in PAIRS]
    if not chosen_symbols:
        _auto_say(cfg, "Auto is on. No symbol is selected.")
        return
    said = len(cfg.get("log") or [])
    placed = False
    for symbol in chosen_symbols:
        if by_symbol.get(symbol):
            continue
        if open_risk + risk_usd > cap_usd + 0.01:
            _auto_say(cfg, symbol + " waits. Open risk is already " + format(open_risk, ".0f") + " of " + format(cap_usd, ".0f") + ".")
            continue
        try:
            payload = _payload(symbol, "M1", host, scan=True)
        except Exception as exc:
            _auto_say(cfg, symbol + " could not be read. " + str(exc))
            continue
        feed = payload.get("feed") or {}
        if feed.get("market") != "OPEN":
            _auto_say(cfg, symbol + " feed is " + str(feed.get("market") or "not open") + ".")
            continue
        row = _auto_choose(list(payload.get("rows") or []))
        if row is None:
            continue
        target = float((row.get("targets") or [row.get("target")])[0])
        mark = symbol + "|" + str(row.get("chart")) + "|" + str(row.get("side")) + "|" + format(float(row.get("entry") or 0), ".5f")
        previous = sent.get(symbol) if isinstance(sent.get(symbol), dict) else {}
        if previous.get("mark") == mark:
            continue
        balance = float(account.get("balance") or 0)
        pct = (risk_usd / balance) * 100.0 if balance else None
        try:
            result = host.runtime.execute_owner_order_clean(
                symbol=symbol,
                timeframe=Timeframe.M1,
                order_type="MARKET_BUY" if row.get("side") == "BUY" else "MARKET_SELL",
                requested_entry=None,
                stop=float(row.get("stop")),
                targets=(target,),
                target_specs=(),
                requested_risk_pct=pct,
                horizon_lane="INTRADAY",
                owner_note="ZEUS AUTO " + str(row.get("chart") or ""),
            )
        except Exception as exc:
            _auto_say(cfg, symbol + " was not sent. " + str(exc))
            continue
        blockers = []
        if isinstance(result, dict):
            blockers = [str(item) for item in (result.get("blockers") or []) if item]
        if blockers:
            _auto_say(cfg, symbol + " blocked. " + " · ".join(blockers))
            continue
        sent[symbol] = {"mark": mark, "side": row.get("side"), "target": target, "risk_usd": risk_usd}
        open_risk += risk_usd
        placed = True
        _auto_say(cfg, "SENT " + symbol + " " + str(row.get("chart")) + " " + str(row.get("side")) + " risk " + format(risk_usd, ".0f"))
        break
    if not placed and len(cfg.get("log") or []) == said:
        _auto_say(cfg, "Looking. Nothing new to send.")


def _auto_loop() -> None:
    import time

    while True:
        host = _AUTO_HOST
        cfg = _auto_load()
        if host is not None and cfg.get("armed"):
            with _AUTO_GUARD:
                fresh = _auto_load()
                if fresh.get("armed"):
                    try:
                        _auto_pass(host, fresh)
                    except Exception as exc:
                        _auto_say(fresh, "Auto stopped this pass. " + str(exc))
                    _auto_store(fresh)
        time.sleep(20)


def _auto_view(host: Any) -> dict[str, Any]:
    cfg = _auto_load()
    account = _account(host) if host is not None else {}
    risk_usd, cap_usd, pot = _auto_money(cfg, account) if account else (0.0, 0.0, 0.0)
    positions = _auto_positions(host) if host is not None else []
    return {
        "ok": True,
        "armed": cfg["armed"],
        "symbols": cfg["symbols"],
        "pairs": [{"symbol": name, "label": LABELS.get(name, name)} for name in PAIRS],
        "unit": cfg["unit"],
        "risk": cfg["risk"],
        "max_risk": cfg["max_risk"],
        "compound": cfg["compound"],
        "base_balance": cfg.get("base_balance"),
        "account": account,
        "risk_usd": risk_usd,
        "max_usd": cap_usd,
        "pot": pot,
        "positions": positions,
        "log": list(cfg.get("log") or [])[-12:],
    }


def render_auto_page() -> str:
    return r"""<!doctype html><html><head><meta charset="utf-8"><title>ZEUS Auto</title>
<style>
:root{--bg:#071019;--panel:#0c1824;--line:#24384c;--text:#e7eef5;--muted:#8ea3b8;--good:#67d6a3;--bad:#ef7f88}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Arial,sans-serif}
header{display:flex;gap:14px;align-items:center;padding:12px 16px;border-bottom:1px solid var(--line)}
a{color:#9fb3c8;text-decoration:none;font-size:12px;font-weight:800}
h1{font-size:16px;margin:0;letter-spacing:.08em}
main{display:grid;grid-template-columns:340px 1fr;gap:12px;padding:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px;margin-bottom:12px}
label{display:block;color:var(--muted);font-size:12px;margin:10px 0 4px}
input,select,button{background:#10202e;color:var(--text);border:1px solid #34506a;border-radius:6px;padding:8px 10px;font-weight:700}
button.on{border-color:var(--good);color:var(--good)}
.pair{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-top:1px solid #1a2c3c}
.muted{color:var(--muted)} .good{color:var(--good)} .bad{color:var(--bad)}
#log{font:12px Consolas,monospace;white-space:pre-wrap}
table{width:100%;border-collapse:collapse;font:12px Consolas,monospace}
td{padding:6px;border-top:1px solid #1a2c3c}
</style></head><body>
<header>
  <a href="/v19/signals">SIGNALS</a><a href="/v19/chart">CHART</a><a href="/v19/trade-desk">TRADE DESK</a>
  <h1>AUTO</h1><span class="muted" id="arm">OFF</span>
</header>
<main>
  <section>
    <div class="card">
      <button id="armbtn" onclick="arm()">AUTO OFF</button>
      <p class="muted">Off does nothing. On sends a confirmed row for a ticked symbol, including a push whose next swing is at least 2R. A yellow push under 2R is not sent. CLOSE on the signals page still closes it.</p>
      <label>BROKER ON METATRADER</label>
      <select id="broker" onchange="useBroker(this.value)"><option value="">The account that is logged in</option></select>
      <div class="muted" id="brokerline"></div>
      <label>SYMBOLS</label>
      <div id="pairs"></div>
      <label>RISK PER TRADE</label>
      <input id="risk" value="200">
      <label>MAX OPEN RISK</label>
      <input id="max" value="400">
      <label>UNIT</label>
      <select id="unit"><option value="usd">Dollars</option><option value="pct">Percent of the account</option></select>
      <label><input id="compound" type="checkbox"> Compound. A percent uses the account now. Off uses the balance from when you saved.</label>
      <button onclick="save()">SAVE</button>
      <div class="muted" id="money"></div>
    </div>
  </section>
  <section>
    <div class="card">
      <div class="muted">OPEN</div>
      <table id="open"></table>
    </div>
    <div class="card">
      <div class="muted">WHAT AUTO DID</div>
      <div id="log">Quiet.</div>
    </div>
  </section>
</main>
<script>
let state=null;
function money(n){return n==null?"—":Number(n).toLocaleString(undefined,{maximumFractionDigits:0})}
async function refresh(){
  const r=await fetch("/api/v19/auto");
  state=await r.json();
  document.getElementById("arm").textContent=state.armed?"ON":"OFF";
  document.getElementById("arm").className=state.armed?"good":"muted";
  const btn=document.getElementById("armbtn");
  btn.textContent=state.armed?"AUTO ON":"AUTO OFF";
  btn.className=state.armed?"on":"";
  if(!document.getElementById("pairs").childElementCount){
    document.getElementById("pairs").innerHTML=(state.pairs||[]).map(p=>`<div class="pair"><b>${p.label}</b><input type="checkbox" data-symbol="${p.symbol}" ${state.symbols.includes(p.symbol)?"checked":""}></div>`).join("");
    document.getElementById("risk").value=state.risk;
    document.getElementById("max").value=state.max_risk;
    document.getElementById("unit").value=state.unit;
    document.getElementById("compound").checked=!!state.compound;
  }
  const acct=state.account||{};
  document.getElementById("money").textContent="Balance "+money(acct.balance)+" · equity "+money(acct.equity)+" · one trade "+money(state.risk_usd)+" · max open "+money(state.max_usd);
  const rows=state.positions||[];
  document.getElementById("open").innerHTML=rows.length?rows.map(p=>`<tr><td>${p.symbol}</td><td>${p.side}</td><td>${p.volume}</td><td>${p.protected?"AT ENTRY":"OPEN RISK"}</td><td>${money(p.profit)}</td></tr>`).join(""):"<tr><td class='muted'>No open position on these pairs.</td></tr>";
  document.getElementById("log").textContent=(state.log||[]).join("\n")||"Quiet.";
}
async function save(armed){
  const symbols=[...document.querySelectorAll("[data-symbol]:checked")].map(x=>x.dataset.symbol);
  const body={
    armed: armed==null?!!(state&&state.armed):armed,
    symbols,
    risk: Number(document.getElementById("risk").value),
    max_risk: Number(document.getElementById("max").value),
    unit: document.getElementById("unit").value,
    compound: document.getElementById("compound").checked
  };
  const r=await fetch("/api/v19/auto",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(body)});
  state=await r.json();
  document.getElementById("pairs").innerHTML="";
  await refresh();
}
function arm(){save(!(state&&state.armed))}
async function brokers(){
  try{
    const r=await fetch("/api/v19/system/terminal-identities");
    const j=await r.json();
    const box=document.getElementById("broker");
    (j.terminal_identities||[]).forEach(row=>{
      const o=document.createElement("option");
      o.value=row.terminal_path||"";
      o.textContent=(row.company||row.server||"MetaTrader")+" · "+(row.login||"")+(row.current_runtime?" · IN USE":"");
      if(row.current_runtime) o.selected=true;
      box.appendChild(o);
    });
    const acct=j.account||{};
    document.getElementById("brokerline").textContent=acct.login?(acct.company||acct.server||"")+" "+acct.login:"No terminal answered.";
  }catch(e){
    document.getElementById("brokerline").textContent="The broker list did not load.";
  }
}
async function useBroker(path){
  if(!path) return;
  const r=await fetch("/api/v19/system/switch-account",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({owner_approved:true,terminal_path:path})});
  const j=await r.json();
  document.getElementById("brokerline").textContent=j.ok===false?(j.message||"The switch was refused"):"That account is now the one Zeus uses.";
}
brokers();
refresh();
setInterval(refresh, 3000);
</script></body></html>"""


async def auto_state(host: Any, request: web.Request) -> web.Response:
    _auto_ensure(host)
    return web.json_response(_auto_view(host))


async def auto_save(host: Any, request: web.Request) -> web.Response:
    _auto_ensure(host)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "message": "bad json"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"ok": False, "message": "bad json"}, status=400)
    with _AUTO_GUARD:
        cfg = _auto_load()
        cfg["armed"] = bool(body.get("armed"))
        cfg["symbols"] = [str(name).upper() for name in (body.get("symbols") or []) if str(name).upper() in PAIRS]
        cfg["unit"] = "pct" if str(body.get("unit")) == "pct" else "usd"
        try:
            cfg["risk"] = float(body.get("risk") or 0)
            cfg["max_risk"] = float(body.get("max_risk") or 0)
        except (TypeError, ValueError):
            return web.json_response({"ok": False, "message": "risk must be a number"}, status=400)
        cfg["compound"] = bool(body.get("compound"))
        if not cfg["compound"]:
            account = _account(host)
            if account.get("balance"):
                cfg["base_balance"] = float(account["balance"])
        _auto_say(cfg, "Saved. Auto is " + ("on." if cfg["armed"] else "off."))
        _auto_store(cfg)
    return web.json_response(_auto_view(host))


def _floor_volume(value: float, step: float) -> float:
    from decimal import Decimal, ROUND_DOWN

    if step <= 0:
        raise ValueError("broker volume step must be positive")
    steps = (Decimal(str(value)) / Decimal(str(step))).to_integral_value(rounding=ROUND_DOWN)
    return float(steps * Decimal(str(step)))


def _ticket_by_volume(host: Any, ticket: int, action: str, partial: Any, stop: Any, targets: Any) -> dict[str, Any]:
    """A manage click is volume. It never looks up a risk percent."""
    bridge = host.runtime._ensure_physical_execution_bridge(require_acceptance_armed=False)
    native = bridge.worker._ensure_native()
    mt5 = native.mt5
    rows = mt5.positions_get(ticket=int(ticket)) or ()
    if not rows:
        raise ValueError("ticket is not open")
    row = rows[0]
    symbol = str(row.symbol)
    volume = float(row.volume or 0)
    entry = float(row.price_open or 0)
    current_sl = float(getattr(row, "sl", 0) or 0)
    current_tp = float(getattr(row, "tp", 0) or 0)
    buy_code = int(getattr(mt5, "POSITION_TYPE_BUY", 0))
    side = "BUY" if int(getattr(row, "type", buy_code)) == buy_code else "SELL"
    magic = int(getattr(row, "magic", 0) or 0)
    name = str(action or "").upper()
    if name == "CLOSE":
        result = native.close_position(int(ticket), symbol=symbol, side=side, volume=volume, magic=magic, comment="ZEUS-CLOSE")
    elif name == "PARTIAL":
        pct = float(partial)
        if pct <= 0 or pct >= 100:
            raise ValueError("a partial is a percent of the open volume, not a risk percent")
        limits = native.volume_limits(symbol)
        close_volume = _floor_volume(volume * pct / 100.0, float(limits.step))
        if close_volume < float(limits.minimum):
            raise ValueError("partial is below the broker minimum volume")
        remainder = volume - close_volume
        if remainder > 1e-12 and remainder < float(limits.minimum) - 1e-12:
            raise ValueError("partial would leave a remainder below the broker minimum")
        result = native.close_position(int(ticket), symbol=symbol, side=side, volume=close_volume, magic=magic, comment="ZEUS-PART")
    elif name in {"BREAK_EVEN", "BE"}:
        result = native.modify_position(int(ticket), stop_loss=entry, take_profit=current_tp or None)
    elif name == "MODIFY_POSITION":
        new_sl = current_sl or None if stop in {None, ""} else float(stop)
        new_tp = current_tp or None
        if targets:
            new_tp = float(list(targets)[0])
        result = native.modify_position(int(ticket), stop_loss=new_sl, take_profit=new_tp)
    else:
        raise ValueError("unknown manage action")
    ok = bool(getattr(result, "success", False))
    retcode = getattr(result, "retcode", None)
    if retcode in {10008, 10009, 10010}:
        ok = True
    comment = str(getattr(result, "comment", "") or "")
    if not comment and not ok:
        comment = f"retcode {retcode}" if retcode is not None else "the broker did not accept"
    return {
        "management": {
            "ok": ok,
            "reason": comment,
            "broker_result": {"comment": comment, "retcode": getattr(result, "retcode", None)},
        },
        "broker_writes": 1 if ok else 0,
    }


async def signals_ticket(host: Any, request: web.Request) -> web.Response:
    """Close, partial, break-even, and edits. A partial is volume. Manage can be off."""
    started = monotonic()
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict) or body.get("owner_approved") is not True:
        return web.json_response({"ok": False, "message": "explicit owner approval is required", "management": {"ok": False, "reason": "explicit owner approval is required"}}, status=400)
    try:
        ticket = int(body.get("ticket"))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "message": "ticket is required", "management": {"ok": False, "reason": "ticket is required"}}, status=400)
    action = str(body.get("action") or "")
    partial = body.get("partial_pct")
    stop = body.get("stop_loss")
    targets = tuple(body.get("take_profits") or ())

    def run() -> dict[str, Any]:
        return _ticket_by_volume(host, ticket, action, partial, stop, targets)

    try:
        payload = await asyncio.to_thread(run)
    except Exception as exc:
        return web.json_response(
            {"ok": False, "message": f"{type(exc).__name__}: {exc}", "management": {"ok": False, "reason": str(exc)}},
            status=400,
        )
    return web.json_response({
        "ok": bool((payload.get("management") or {}).get("ok", True)),
        **payload,
        "management_server_ms": round((monotonic() - started) * 1000.0, 2),
    })


