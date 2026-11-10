from pathlib import Path
import sys

root = Path(sys.argv[1].strip().strip('"').rstrip("\\/"))
page = root / "src" / "zeus3" / "v19" / "shadow_book_page.py"
web = root / "src" / "zeus3" / "v19" / "web.py"
text = page.read_text(encoding="utf-8")
start = text.find("\ndef render")
if start < 0:
    raise SystemExit("Shadow page has no render function")
text = text[:start] + r'''

def render():
    body = """
<div id="book" class="card span12"><div class="mono">Scoring the shadow book. You can open another tab while this runs.</div></div>
<script>
function esc(v){return String(v==null?'':v).replace(/[&<>]/g,function(c){return {'&':'&','<':'<','>':'>'}[c]})}
function rows(items){
  if(!items||!items.length) return "<div class='mono muted'>No rows.</div>";
  return "<table class='mono'><tr><th>STRATEGY</th><th>ACTION</th><th>REASON</th><th>ENTRY</th><th>STOP</th><th>TARGET</th></tr>"+items.map(function(row){var action=String(row.action||'WAIT');var color=action==='BUY'||action==='SELL'?'good':'muted';return '<tr><td>'+esc(row.strategy_id)+'</td><td class="'+color+'">'+esc(action)+'</td><td>'+esc(row.reason)+'</td><td>'+esc(row.entry)+'</td><td>'+esc(row.stop)+'</td><td>'+esc(row.target)+'</td></tr>'}).join('')+"</table>"
}
function paint(data){
  var account=data.account||{}, html='';
  if(account.connected){
    var pos=(account.open_positions||[]).map(function(p){return '<div>'+esc(p.ticket)+' '+esc(p.symbol)+' '+esc(p.side)+' '+esc(p.lots)+' pnl '+esc(p.profit)+'</div>'}).join('')||"<div class='muted'>No open positions.</div>";
    html+="<section class='card span6'><div class='label'>FLOATING P&L</div><div class='big'>"+esc(account.floating_pnl)+"</div><div class='mono'>Balance "+esc(account.balance)+" Equity "+esc(account.equity)+"</div></section>";
    html+="<section class='card span6'><div class='label'>OPEN TRADES</div><div class='mono'>"+pos+"</div></section>";
  } else html+="<section class='card span12'><div class='label'>BROKER</div><div class='mono warn'>"+esc(account.reason||'NOT CONNECTED')+"</div></section>";
  var virtual=data.virtual||{};
  var lines="<div class='mono'>Start 10000 equity "+esc(virtual.equity)+" closed "+esc(virtual.closed_pnl)+" floating "+esc(virtual.floating_pnl)+" orders are not sent</div>";
  (data.scores||[]).forEach(function(score){var mbo=score.mbo; if(!mbo) return; lines+="<div class='mono'>"+esc(score.symbol)+" "+esc(mbo.root)+" "+esc(mbo.reason)+" sweep "+(mbo.sweep_consumed?1:0)+" iceberg "+(mbo.iceberg_refresh?1:0)+" pulled "+(mbo.size_pulled?1:0)+"</div>"});
  var potentials=(data.scores||[]).reduce(function(all,score){return all.concat(score.potentials||[])},[]);
  if(!potentials.length) lines+="<div class='mono muted'>No Gold, Nasdaq, or oil setup right now.</div>";
  else lines+="<table class='mono'><tr><th></th><th>MARKET</th><th>STRATEGY</th><th>ACTION</th><th>REASON</th><th>LOTS</th><th>ENTRY</th><th>STOP</th><th>TARGET</th></tr>"+potentials.map(function(row){return '<tr><td>'+(row.taken?'SHADOW':'POTENTIAL')+'</td><td>'+esc(row.symbol)+'</td><td>'+esc(row.strategy_id)+'</td><td>'+esc(row.action)+'</td><td>'+esc(row.reason)+'</td><td>'+esc(row.lots)+'</td><td>'+esc(row.entry)+'</td><td>'+esc(row.stop)+'</td><td>'+esc(row.target)+'</td></tr>'}).join('')+"</table>";
  html+="<section class='card span12'><div class='label'>VIRTUAL 10K MBO ON GC NQ CL</div>"+lines+"</section>";
  (data.scores||[]).forEach(function(score){
    if(score.rows&&score.rows.length===0&&score.reason){html+="<section class='card span12'><div class='label'>"+esc(score.symbol)+"</div><div class='mono warn'>"+esc(score.reason)+"</div></section>"; return}
    html+="<section class='card span12'><div class='label'>"+esc(score.symbol)+" OFFICIAL broker "+esc(score.clock)+" "+esc(score.sierra_state)+"</div>"+rows(score.official)+"</section>";
    html+="<section class='card span12'><div class='label'>"+esc(score.symbol)+" STRUCTURE PREVIEW not a trade</div>"+rows(score.structure_preview)+"</section>";
  });
  document.getElementById('book').outerHTML=html;
}
fetch('/api/v19/shadow-book').then(function(r){return r.json()}).then(paint).catch(function(e){document.getElementById('book').innerHTML="<div class='mono bad'>"+esc(e)+"</div>"});
</script>
"""
    return page(title="ZEUS Shadow Book", active="SHADOW", body=body, footer="Four shadow strategies. They score. They do not send orders.")
'''
page.write_text(text, encoding="utf-8")
code = web.read_text(encoding="utf-8")
old = "        payload = snapshot()\n"
new = "        payload = await asyncio.get_running_loop().run_in_executor(None, snapshot)\n"
if old in code and "run_in_executor(None, snapshot)" not in code:
    code = code.replace(old, new, 1)
    web.write_text(code, encoding="utf-8")
print("SHADOW_UNLOCKED")
