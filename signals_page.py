"""Live signals page. The chart is the same market feed. A wait can be overridden."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from time import monotonic
from typing import Any

from aiohttp import web

from zeus3.contracts.market_data import Timeframe
from zeus3.v19.signals_engine import (
    CHARTS,
    FUTURES_ROOTS,
    PAIRS,
    POSITION_NAMES,
    align_ladder,
    build_rows,
    mark_taken,
    record,
    session_levels,
)

_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_LOCK = threading.Lock()
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
main{display:grid;grid-template-columns:1fr 300px;gap:10px;padding:10px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px}
canvas{width:100%;height:520px;background:#050b11;border-radius:6px;cursor:grab}
table{width:100%;border-collapse:collapse;font:12px Consolas,monospace}
th{color:var(--muted);text-align:left;font-size:11px;padding:6px}
td{padding:6px;border-top:1px solid #1a2c3c}
tr.pick{outline:1px solid var(--warn)}
.good{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}.muted{color:var(--muted)}
.flow b{display:block;font-size:16px;margin:2px 0 10px}
#status,#research{font:12px Consolas,monospace;white-space:pre-wrap}
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
  <label>RISK % <input id="risk" value="2" style="width:52px"></label>
  <span class="muted">One chart. POTENTIAL is not a trade. The book has no iceberg price yet.</span>
</div>
<main>
  <section class="card">
    <canvas id="cv" width="1100" height="520"></canvas>
    <div id="status" class="muted"></div>
    <table id="grid"></table>
    <div id="research" class="muted" style="margin-top:8px"></div>
  </section>
  <aside>
    <section class="card flow" id="flow"></section>
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
let data=null, visible=80, pan=0, drag=null, selected=chart;
let busy=false, timer=null, control=null;
function $(id){return document.getElementById(id)}
function buttons(){
  $("pairs").innerHTML=PAIRS.map(p=>`<button class="${p[0]===symbol?"on":""}" onclick="setPair('${p[0]}')">${p[1]}</button>`).join("");
  $("charts").innerHTML=CHARTS.map(c=>`<button class="${c===chart?"on":""}" onclick="setChart('${c}')">${c}</button>`).join("");
}
function setPair(s){symbol=s;localStorage.setItem("sig_symbol",s);load()}
function setChart(c){chart=c;selected=c;localStorage.setItem("sig_chart",c);load()}
function zoom(d){visible=Math.max(30,Math.min(240,visible+d));draw()}
function fit(){visible=Math.max(30,(data&&data.candles||[]).length||80);pan=0;draw()}
async function load(){
  if(busy||document.visibilityState==="hidden")return;
  busy=true;
  buttons();
  if(control)control.abort();
  control=new AbortController();
  try{
    const r=await fetch("/api/v19/signals?symbol="+symbol+"&chart="+chart,{signal:control.signal});
    const j=await r.json();
    if(!r.ok||!j.ok)throw Error(j.message||("HTTP "+r.status));
    data=j; $("clock").textContent=j.server_time||"";
    draw(); paint();
  }catch(e){
    if(e.name!=="AbortError")$("status").textContent="CHART ERROR · "+e.message;
  }finally{busy=false}
}
function windowRows(){
  const all=(data&&data.candles)||[];
  const count=Math.min(visible, all.length);
  const maxPan=Math.max(0, all.length-count);
  pan=Math.max(0, Math.min(pan, maxPan));
  const end=all.length-pan;
  return all.slice(Math.max(0,end-count), end);
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
  const span=Math.max(hi-lo, 0.00001);
  const row=(data.rows||[]).find(r=>r.chart===selected&&r.entry!=null);
  if(row){lo=Math.min(lo,row.stop,row.target,row.entry);hi=Math.max(hi,row.stop,row.target,row.entry)}
  const levels=((data.sessions||{}).levels)||[];
  levels.forEach(level=>{
    if(Math.abs(level.high-((lo+hi)/2))<span*1.6){lo=Math.min(lo,level.low);hi=Math.max(hi,level.high)}
  });
  const pad=(hi-lo)*0.08||span*0.08; lo-=pad; hi+=pad;
  const y=p=>plotT+((hi-p)/(hi-lo))*(plotB-plotT);
  const step=(plotR-plotL)/Math.max(1,rows.length);
  levels.forEach(level=>{
    const color=LEVEL_COLOR[level.name]||"#8ea3b8";
    [level.high, level.low].forEach((price,index)=>{
      if(price<lo||price>hi)return;
      ctx.strokeStyle=color; ctx.globalAlpha=0.85; ctx.setLineDash(level.name==="YESTERDAY"?[2,4]:[6,4]);
      ctx.beginPath(); ctx.moveTo(plotL,y(price)); ctx.lineTo(plotR,y(price)); ctx.stroke();
      ctx.setLineDash([]); ctx.globalAlpha=1; ctx.fillStyle=color;
      ctx.fillText(level.name+" "+(index?"LOW":"HIGH"), plotL+4, y(price)-3);
    });
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
  const picked=(data.rows||[]).find(r=>r.chart===selected)||{};
  const q=data.quote||{};
  ctx.fillStyle="#e7eef5";
  ctx.fillText(symbol+"  "+chart+"   BID "+(q.bid??"—")+"   ASK "+(q.ask??"—")+"   SPREAD "+(data.spread??"—"), 12, 18);
  ctx.fillStyle="#e9c66b";
  ctx.fillText((picked.state||"")+"   "+((data.sessions||{}).current||"")+"   "+(picked.reason==="POTENTIAL"?(picked.side==="BUY"?"POTENTIAL BUY":"POTENTIAL SELL"):""), 12, 36);
}
function researchLine(title, book){
  const bits=Object.keys(book||{}).map(chart=>{
    const x=book[chart];
    return chart+" "+(x.wins||0)+" wins, "+(x.losses||0)+" losses, "+(x.be_wins||0)+" be-wins, "+(x.be_scratches||0)+" scratch";
  });
  return bits.length?title+" · "+bits.join(" · "):title+" · none yet";
}
function paint(){
  const rows=data.rows||[];
  $("grid").innerHTML="<tr><th>CHART</th><th>STATE</th><th>SIDE</th><th>ENTRY</th><th>STOP</th><th>TARGET</th><th>R</th><th>REASON</th><th>HIGHER</th><th>BOOK</th><th></th></tr>"+
    rows.map(r=>{
      const side=r.side?`<span class="${r.side==="BUY"?"good":"bad"}">${r.reason==="POTENTIAL"?"POTENTIAL "+r.side:r.side}</span>`:"—";
      const flow=r.decision==="BUYERS STEPPING IN"?"good":(r.decision==="SELLERS STEPPING IN"||r.decision==="PULLED"?"bad":"warn");
      const button=r.tradeable?`<button onclick="event.stopImmediatePropagation();trade('${r.chart}')">TRADE</button>`:"";
      return `<tr class="${r.chart===selected?"pick":""}" onclick="selected='${r.chart}';draw();paint()"><td>${r.chart}</td><td>${r.state||"—"}</td><td>${side}</td><td>${r.entry??"—"}</td><td>${r.stop??"—"}</td><td>${r.target??"—"}</td><td>${r.r??"—"}</td><td>${r.reason}</td><td>${r.higher||"—"}</td><td class="${flow}">${r.decision||"—"}</td><td>${button}</td></tr>`;
    }).join("");
  const f=data.flow||{}, ladder=data.ladder||{};
  $("flow").innerHTML=`<div class="muted">ORDER FLOW · THIS PAIR</div>
    <div>DELTA 5s</div><b>${f.delta_5s??"not in this book"}</b>
    <div>DELTA 60s</div><b>${f.delta_60s??"not in this book"}</b>
    <div>WHO IS HITTING</div><b class="${f.stepping==="BUYERS"?"good":(f.stepping==="SELLERS"?"bad":"")}">${f.stepping||"—"}</b>
    <div>ABSORPTION</div><b>${f.absorption?"YES":"no"}</b>
    <div>ICEBERG</div><b>${f.iceberg?"YES · no price":"no"}</b>
    <div>PULLED</div><b>${f.pulled?"YES · no price":"no"}</b>
    <div>SWEEP</div><b>${f.sweep_consumed?"YES · no price":"no"}</b>
    <div class="muted">${ladder.shown?"Ladder shifted by "+ladder.shift+". Not an entry.":(ladder.reason==="NO_LADDER"?"Ladder is not in the file yet.":"Ladder not drawn. "+(ladder.reason||""))}</div>
    <div class="muted">${f.note||""}</div>`;
  const pos=data.positions||[];
  $("positions").innerHTML=pos.length?pos.map(p=>`<div style="margin-top:8px"><b class="${p.side==="BUY"?"good":"bad"}">${p.side}</b> ${p.volume} @ ${p.price_open}<br>P/L ${p.profit} · SL ${p.stop_loss??"—"} · TP ${p.take_profit??"—"}<br>
    <button onclick="manage(${p.ticket},'CLOSE_POSITION')">CLOSE</button>
    <button onclick="manage(${p.ticket},'STOP_TO_ENTRY',${p.price_open})">STOP TO ENTRY</button></div>`).join(""):"<div class='muted'>No open broker position on this pair.</div>";
  const research=data.research||{};
  $("research").textContent=researchLine("TAKEN", research.taken)+"\n"+researchLine("IF TAKEN", research.if_taken)+"\nThe old log was set aside. TAKEN is only an order this page sent. IF TAKEN was never sent.";
  const row=(data.rows||[]).find(r=>r.chart===selected);
  $("status").textContent=row&&row.note?row.chart+" · "+row.note:"Click a row. TRADE sends a market order. POTENTIAL cannot be sent. The kill switch can still refuse a trade.";
}
async function trade(chartName){
  const row=(data.rows||[]).find(r=>r.chart===chartName&&r.tradeable);
  if(!row)return;
  const open=(data.positions||[]).find(p=>p.side&&p.side!==row.side);
  if(open){$("status").textContent="NOT SENT · this pair already has a "+open.side+". Close it first.";return}
  const msg="Send a MARKET "+row.side+" on "+symbol+"?\nStop "+row.stop+"\nTarget "+row.target+"\nThe book says "+row.decision+".\nThis goes to the connected MT5 account.";
  if(!confirm(msg))return;
  const risk=Number($("risk").value);
  if(!isFinite(risk)||risk<=0){$("status").textContent="NOT SENT · set the risk percent";return}
  $("status").textContent="SENDING...";
  try{
    const r=await fetch("/api/v19/owner-order/submit",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({
      owner_approved:true,symbol:symbol,timeframe:chartName,order_type:row.side==="BUY"?"MARKET_BUY":"MARKET_SELL",
      entry:null,stop:row.stop,targets:[row.target],requested_risk_pct:risk,horizon_lane:"INTRADAY",
      owner_note:"SIGNALS PAGE "+row.reason+" "+row.decision
    })});
    const j=await r.json();
    if(!r.ok||j.ok===false)throw Error(j.message||"rejected");
    const ex=j.execution||j;
    if(ex.submitted===false){$("status").textContent="NOT SENT · "+((ex.blockers||[]).join(" · ")||"the broker did not accept");return}
    await fetch("/api/v19/signals/taken",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({symbol:symbol,chart:chartName,side:row.side,reason:row.reason,entry:row.entry,stop:row.stop,target:row.target,r:row.r,time:row.time})});
    $("status").textContent="SENT · check the position below";
    load();
  }catch(e){$("status").textContent="NOT SENT · "+e.message}
}
async function manage(ticket, action, entry){
  const body={owner_approved:true,ticket:ticket,action:action==="STOP_TO_ENTRY"?"MODIFY_POSITION":action,reason:"SIGNALS PAGE"};
  if(action==="STOP_TO_ENTRY")body.stop_loss=entry;
  if(action==="CLOSE_POSITION"&&!confirm("Close ticket "+ticket+" at the market?"))return;
  try{
    const r=await fetch("/api/v3-physical-execution/manage",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(body)});
    const j=await r.json();
    $("status").textContent=((j.management||{}).ok?"BROKER OK":"BLOCKED")+" · "+((j.management||{}).reason||j.message||"");
    load();
  }catch(e){$("status").textContent="MANAGE ERROR · "+e.message}
}
const cv=$("cv");
cv.addEventListener("wheel",e=>{e.preventDefault();zoom(e.deltaY>0?15:-15)},{passive:false});
cv.addEventListener("pointerdown",e=>{drag=e.clientX});
cv.addEventListener("pointerup",()=>{drag=null});
cv.addEventListener("pointermove",e=>{if(drag==null)return;const dx=e.clientX-drag;drag=e.clientX;pan+=dx<0?-2:2;draw()});
document.addEventListener("visibilitychange",()=>{if(!document.hidden)load()});
window.addEventListener("pagehide",()=>{clearInterval(timer);if(control)control.abort()});
buttons();load();timer=setInterval(load,3000);
</script></body></html>"""


def _bars(host: Any, symbol: str, chart: str, max_age: float) -> list[dict[str, Any]]:
    key = symbol + "|" + chart
    cached = _CACHE.get(key)
    if cached and monotonic() - cached[0] < max_age:
        return cached[1]
    rows = host.runtime.projection.market_data.bars(symbol, Timeframe(chart), count=400)
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
        })
    try:
        from zeus3.v19.shadow_book_page import _sierra_flow

        _flow, _state, metrics = _sierra_flow(symbol)
        if metrics:
            book["absorption"] = bool(metrics.get("absorption"))
            book["delta_5s"] = metrics.get("delta_5s")
            book["delta_60s"] = metrics.get("delta_60s")
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
        side = "BUY" if int(getattr(row, "type_code", 1) or 1) == 0 else "SELL"
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
    return found


def render_signals_page() -> str:
    return PAGE


def _payload(symbol: str, chart: str, host: Any) -> dict[str, Any]:
    bars_by_chart = {name: _bars(host, symbol, name, 5 if name == chart else 45) for name in CHARTS}
    quote = host.runtime.projection.market_data.quote(symbol)
    bid = float(quote.bid)
    ask = float(quote.ask)
    spread = round(ask - bid, 5)
    book = _book(symbol)
    levels = session_levels(bars_by_chart.get("M15") or bars_by_chart.get("M5") or [])
    rows = build_rows(symbol, bars_by_chart, book, spread, levels)
    try:
        research = record(symbol, rows, bars_by_chart)
    except Exception:
        research = {"taken": {}, "if_taken": {}}
    delta = book.get("delta_5s")
    stepping = "BUYERS" if isinstance(delta, (int, float)) and not isinstance(delta, bool) and delta > 0 else (
        "SELLERS" if isinstance(delta, (int, float)) and not isinstance(delta, bool) and delta < 0 else "QUIET"
    )
    return {
        "ok": True,
        "symbol": symbol,
        "label": LABELS.get(symbol, symbol),
        "chart": chart,
        "candles": bars_by_chart.get(chart) or [],
        "quote": {"bid": bid, "ask": ask},
        "spread": spread,
        "sessions": levels,
        "rows": rows,
        "ladder": align_ladder(symbol, book, bid, ask),
        "flow": {
            "fresh": bool(book.get("fresh")),
            "absorption": bool(book.get("absorption")),
            "iceberg": bool(book.get("iceberg_refresh")),
            "pulled": bool(book.get("size_pulled")),
            "sweep_consumed": bool(book.get("sweep_consumed")),
            "delta_5s": book.get("delta_5s"),
            "delta_60s": book.get("delta_60s"),
            "stepping": stepping,
            "note": str(book.get("reason") or ""),
        },
        "positions": _positions(host, symbol),
        "research": research,
        "server_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }


async def signals_snapshot(host: Any, request: web.Request) -> web.Response:
    symbol = str(request.query.get("symbol") or "XAUUSD").upper()
    chart = str(request.query.get("chart") or "M5").upper()
    if symbol not in PAIRS or chart not in CHARTS:
        return web.json_response({"ok": False, "message": "unknown pair or chart"}, status=400)
    if not _LOCK.acquire(blocking=False):
        cached = _LAST.get(symbol)
        if cached:
            return web.json_response(cached)
        return web.json_response({"ok": False, "message": "Still reading MetaTrader."}, status=503)
    try:
        payload = _payload(symbol, chart, host)
    except Exception as exc:
        return web.json_response(
            {"ok": False, "message": f"{symbol} is not on this MetaTrader feed. {exc}"},
            status=503,
        )
    finally:
        _LOCK.release()
    _LAST[symbol] = payload
    return web.json_response(payload)


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
