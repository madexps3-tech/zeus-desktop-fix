"""Live signals page. The chart is the same market feed. A wait can be overridden."""

from __future__ import annotations

from datetime import datetime, timezone
from time import monotonic
from typing import Any

from aiohttp import web

from zeus3.contracts.market_data import Timeframe
from zeus3.v19.signals_engine import CHARTS, PAIRS, build_rows, record

_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}

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
canvas{width:100%;height:460px;background:#050b11;border-radius:6px;cursor:grab}
table{width:100%;border-collapse:collapse;font:12px Consolas,monospace}
th{color:var(--muted);text-align:left;font-size:11px;padding:6px}
td{padding:6px;border-top:1px solid #1a2c3c}
tr.pick{outline:1px solid var(--warn)}
.good{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}.muted{color:var(--muted)}
.flow b{display:block;font-size:16px;margin:2px 0 10px}
#status{font:12px Consolas,monospace;min-height:32px}
</style></head><body>
<header>
  <a href="/v19/chart">CHART</a><a href="/v19/trade-desk">TRADE DESK</a><a href="/v19/shadow">SHADOW</a>
  <h1>SIGNALS</h1>
  <span class="muted" id="clock"></span>
</header>
<div class="row" style="padding:10px">
  <span id="pairs"></span>
  <span id="charts"></span>
  <button onclick="zoom(-30)">ZOOM IN</button>
  <button onclick="zoom(30)">ZOOM OUT</button>
  <button onclick="fit()">FIT</button>
  <label>RISK % <input id="risk" value="2" style="width:52px"></label>
  <span class="muted">One chart. The other six are rows. Nothing here is hidden because it says wait.</span>
</div>
<main>
  <section class="card">
    <canvas id="cv" width="1100" height="460"></canvas>
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
let symbol=localStorage.getItem("sig_symbol")||"XAUUSD";
let chart=localStorage.getItem("sig_chart")||"M5";
let data=null, visible=140, pan=0, drag=null, selected=chart, risk=2;
function $(id){return document.getElementById(id)}
function buttons(){
  $("pairs").innerHTML=PAIRS.map(p=>`<button class="${p[0]===symbol?"on":""}" onclick="setPair('${p[0]}')">${p[1]}</button>`).join("");
  $("charts").innerHTML=CHARTS.map(c=>`<button class="${c===chart?"on":""}" onclick="setChart('${c}')">${c}</button>`).join("");
}
function setPair(s){symbol=s;localStorage.setItem("sig_symbol",s);load()}
function setChart(c){chart=c;selected=c;localStorage.setItem("sig_chart",c);load()}
function zoom(d){visible=Math.max(20,Math.min(400,visible+d));draw()}
function fit(){visible=Math.max(20,(data&&data.candles||[]).length||140);pan=0;draw()}
async function load(){
  buttons();
  try{
    const r=await fetch("/api/v19/signals?symbol="+symbol+"&chart="+chart);
    const j=await r.json();
    if(!r.ok||!j.ok)throw Error(j.message||("HTTP "+r.status));
    data=j; $("clock").textContent=j.server_time||"";
    draw(); paint();
  }catch(e){$("status").textContent="CHART ERROR · "+e.message}
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
  const cv=$("cv"), ctx=cv.getContext("2d"), rows=windowRows();
  ctx.clearRect(0,0,cv.width,cv.height);
  ctx.fillStyle="#050b11"; ctx.fillRect(0,0,cv.width,cv.height);
  if(!rows.length){ctx.fillStyle="#8ea3b8";ctx.fillText("No candles for "+symbol+" "+chart, 20, 40);return}
  let lo=Infinity, hi=-Infinity;
  rows.forEach(b=>{lo=Math.min(lo,b.low);hi=Math.max(hi,b.high)});
  const row=(data.rows||[]).find(r=>r.chart===selected&&r.side);
  if(row){lo=Math.min(lo,row.stop,row.target,row.entry);hi=Math.max(hi,row.stop,row.target,row.entry)}
  const pad=(hi-lo)*0.08||1; lo-=pad; hi+=pad;
  const y=p=>20+((hi-p)/(hi-lo))*410;
  const step=1040/Math.max(1,rows.length);
  if(row){
    ctx.setLineDash([4,4]);
    [["#67d6a3",row.entry,"ENTRY"],["#ef7f88",row.stop,"STOP"],["#e9c66b",row.target,"TARGET "+row.r+"R"]].forEach(line=>{
      ctx.strokeStyle=line[0]; ctx.beginPath(); ctx.moveTo(10,y(line[1])); ctx.lineTo(1080,y(line[1])); ctx.stroke();
      ctx.fillStyle=line[0]; ctx.fillText(line[2]+" "+line[1], 820, y(line[1])-4);
    });
    ctx.setLineDash([]);
  }
  rows.forEach((b,i)=>{
    const x=20+i*step, up=b.close>=b.open;
    ctx.strokeStyle=up?"#67d6a3":"#ef7f88"; ctx.fillStyle=ctx.strokeStyle;
    ctx.beginPath(); ctx.moveTo(x,y(b.high)); ctx.lineTo(x,y(b.low)); ctx.stroke();
    const top=y(Math.max(b.open,b.close)), bot=y(Math.min(b.open,b.close));
    ctx.fillRect(x-Math.max(1,step*0.3), top, Math.max(2,step*0.6), Math.max(1,bot-top));
  });
  const q=data.quote||{};
  ctx.fillStyle="#e7eef5";
  ctx.fillText(symbol+"  "+chart+"   BID "+(q.bid??"—")+"   ASK "+(q.ask??"—")+"   SPREAD "+(data.spread??"—"), 16, 18);
}
function paint(){
  const rows=data.rows||[];
  $("grid").innerHTML="<tr><th>CHART</th><th>SIDE</th><th>ENTRY</th><th>STOP</th><th>TARGET</th><th>R</th><th>REASON</th><th>HIGHER</th><th>FLOW</th><th></th></tr>"+
    rows.map(r=>{
      const side=r.side?`<span class="${r.side==="BUY"?"good":"bad"}">${r.side}</span>`:"—";
      const flow=r.decision==="TAKE"?"good":(r.decision==="SKIP"?"bad":"warn");
      return `<tr class="${r.chart===selected?"pick":""}" onclick="selected='${r.chart}';draw();paint()"><td>${r.chart}</td><td>${side}</td><td>${r.entry??"—"}</td><td>${r.stop??"—"}</td><td>${r.target??"—"}</td><td>${r.r??"—"}</td><td>${r.reason}</td><td>${r.higher||"—"}</td><td class="${flow}">${r.decision||"—"}</td><td>${r.side?`<button onclick="event.stopImmediatePropagation();trade('${r.chart}')">TRADE</button>`:""}</td></tr>`;
    }).join("");
  const f=data.flow||{};
  $("flow").innerHTML=`<div class="muted">ORDER FLOW · LIVE BOOK</div>
    <div>DELTA</div><b>${f.delta??"not in this book"}</b>
    <div>ABSORPTION</div><b class="${f.absorption?"good":""}">${f.absorption?"YES":"no"}</b>
    <div>ICEBERG</div><b>${f.iceberg?"YES":"no"}</b>
    <div>PULLED</div><b class="${f.pulled?"bad":""}">${f.pulled?"YES":"no"}</b>
    <div>SWEEP CONSUMED</div><b>${f.sweep_consumed?"YES":"no"}</b>
    <div class="muted">${f.note||""}</div>`;
  const pos=data.positions||[];
  $("positions").innerHTML=pos.length?pos.map(p=>`<div style="margin-top:8px"><b class="${p.side==="BUY"?"good":"bad"}">${p.side}</b> ${p.volume} @ ${p.price_open}<br>P/L ${p.profit} · SL ${p.stop_loss??"—"} · TP ${p.take_profit??"—"}<br>
    <button onclick="manage(${p.ticket},'CLOSE_POSITION')">CLOSE</button>
    <button onclick="manage(${p.ticket},'STOP_TO_ENTRY',${p.price_open})">STOP TO ENTRY</button></div>`).join(""):"<div class='muted'>No open broker position on this pair.</div>";
  const research=data.research||{};
  const bits=Object.keys(research).map(k=>{const x=research[k];return k+" "+x.wins+" wins, "+x.losses+" losses, "+x.expired+" expired, "+x.open+" open"});
  $("research").textContent=bits.length?("RESEARCH LOG · "+bits.join(" · ")):("RESEARCH LOG · no scored signals yet");
  const row=(data.rows||[]).find(r=>r.chart===selected);
  $("status").textContent=row&&row.note?row.chart+" · "+row.note:"Click a row. TRADE sends a market order even if the row says wait. The account kill switch can still refuse it.";
}
async function trade(chartName){
  const row=(data.rows||[]).find(r=>r.chart===chartName&&r.side);
  if(!row)return;
  const msg="Send a MARKET "+row.side+" on "+symbol+"?\nStop "+row.stop+"\nTarget "+row.target+"\nThe signal says "+row.decision+".\nThis goes to the connected MT5 account. The kill switch can still block it.";
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
    $("status").textContent=ex.submitted===false?("NOT SENT · "+((ex.blockers||[]).join(" · ")||"the broker did not accept")):"SENT · check the position below";
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
cv.addEventListener("wheel",e=>{e.preventDefault();zoom(e.deltaY>0?20:-20)},{passive:false});
cv.addEventListener("pointerdown",e=>{drag=e.clientX});
cv.addEventListener("pointerup",()=>{drag=null});
cv.addEventListener("pointermove",e=>{if(drag==null)return;const dx=e.clientX-drag;drag=e.clientX;pan+=dx<0?-3:3;draw()});
buttons();load();setInterval(load,3000);
</script></body></html>"""


def _bars(host: Any, symbol: str, chart: str, fresh: bool) -> list[dict[str, Any]]:
    key = symbol + "|" + chart
    cached = _CACHE.get(key)
    if cached and not fresh and monotonic() - cached[0] < 20:
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


def _book(symbol: str) -> dict[str, Any]:
    try:
        from gold_shadow.mbo_book import read_mbo

        book = read_mbo(symbol)
    except Exception as exc:
        return {"fresh": False, "reason": str(exc)}
    try:
        from zeus3.v19.shadow_book_page import _sierra_flow

        _flow, _state, metrics = _sierra_flow(symbol)
        if metrics:
            book["absorption"] = bool(metrics.get("absorption"))
            book["delta"] = metrics.get("delta")
    except Exception:
        pass
    return book


def _positions(host: Any, symbol: str) -> list[dict[str, Any]]:
    try:
        truth = host.runtime.core.broker_truth.get(host.runtime.worker.profile_id)
    except Exception:
        return []
    found = []
    for row in getattr(truth, "positions", ()) or ():
        broker = str(getattr(row, "broker_symbol", "") or "").upper()
        if symbol not in broker and broker not in symbol:
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


async def signals_snapshot(host: Any, request: web.Request) -> web.Response:
    from datetime import datetime, timezone

    symbol = str(request.query.get("symbol") or "XAUUSD").upper()
    chart = str(request.query.get("chart") or "M5").upper()
    if symbol not in PAIRS or chart not in CHARTS:
        return web.json_response({"ok": False, "message": "unknown pair or chart"}, status=400)
    try:
        bars_by_chart = {name: _bars(host, symbol, name, name == chart) for name in CHARTS}
        quote = host.runtime.projection.market_data.quote(symbol)
    except Exception as exc:
        return web.json_response(
            {"ok": False, "message": f"{symbol} is not on this MetaTrader feed. {exc}"},
            status=503,
        )
    bid = float(quote.bid)
    ask = float(quote.ask)
    spread = round(ask - bid, 5)
    book = _book(symbol)
    rows = build_rows(symbol, bars_by_chart, book, spread)
    try:
        research = record(symbol, rows, bars_by_chart)
    except Exception:
        research = {}
    return web.json_response(
        {
            "ok": True,
            "symbol": symbol,
            "label": LABELS.get(symbol, symbol),
            "chart": chart,
            "candles": bars_by_chart.get(chart) or [],
            "quote": {"bid": bid, "ask": ask},
            "spread": spread,
            "rows": rows,
            "flow": {
                "fresh": bool(book.get("fresh")),
                "absorption": bool(book.get("absorption")),
                "iceberg": bool(book.get("iceberg_refresh")),
                "pulled": bool(book.get("size_pulled")),
                "sweep_consumed": bool(book.get("sweep_consumed")),
                "delta": book.get("delta"),
                "note": "The book is for the pair, not for one chart. " + str(book.get("reason") or ""),
            },
            "positions": _positions(host, symbol),
            "research": research,
            "server_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
    )
