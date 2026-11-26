"""Start the phone page from the signals page. Run once, on the PC, before ZEUS opens."""
from pathlib import Path

page = Path("src") / "zeus3" / "v19" / "signals_page.py"
if not page.exists():
    print("Could not find the signals page.", flush=True)
    raise SystemExit(1)
text = page.read_text(encoding="utf-8")
if "start_watch" in text:
    print("Phone watch is already wired.", flush=True)
elif "_AUTO_THREAD.start()" not in text:
    print("Could not find the auto start.", flush=True)
    raise SystemExit(1)
else:
    nl = "\r\n" if "\r\n" in text else "\n"
    text = text.replace(
        "_AUTO_THREAD.start()",
        "_AUTO_THREAD.start()" + nl
        + "    try:" + nl
        + "        from zeus3.v19.watch_page import start_watch" + nl
        + "        start_watch(host)" + nl
        + "    except Exception:" + nl
        + "        pass",
        1,
    )
    page.write_text(text, encoding="utf-8")
    print("Phone watch starts with the page.", flush=True)

LAYOUT = r'''PHONE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ZEUS</title>
<style>
:root{--bg:#071019;--panel:#0c1824;--line:#24384c;--text:#e7eef5;--muted:#8ea3b8;--good:#67d6a3;--bad:#ef7f88;--warn:#e9c66b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Arial,sans-serif}
main{padding:16px 14px 72px}h1{font-size:18px;letter-spacing:.16em;margin:0 0 12px}
form{display:flex;flex-direction:column;gap:10px}input,button{font:16px Arial;padding:12px;border-radius:8px}
input{background:#08131c;color:var(--text);border:1px solid var(--line)}
button{background:#17324a;color:var(--text);border:1px solid #3d6f93}
.msg{color:var(--warn);min-height:1.2em}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px;margin:0 0 10px}
.card b{display:block;font-size:16px}.sub{color:var(--muted);font-size:14px;margin-top:4px}
.good{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}
.mark{position:fixed;left:0;right:0;bottom:0;padding:10px 14px;background:#08131c;border-top:1px solid var(--line);color:var(--warn);font-weight:700}
.note{color:var(--muted);font-size:13px}
</style></head><body>
<main id="app"></main>
<div class="mark" id="mark"></div>
<script>
const app=document.getElementById("app");
const mark=document.getElementById("mark");
function esc(v){
  return String(v==null?"":v).replace(/&/g,"&"+"amp;").replace(/</g,"&"+"lt;").replace(/>/g,"&"+"gt;");
}
function loginBox(message){
  mark.textContent="";
  app.innerHTML="<h1>ZEUS</h1><p class='note'>Watch only. Place the order in MT5.</p><form id='in'><input name='name' placeholder='Name' autocapitalize='off'><input name='password' type='password' placeholder='Password'><button>Sign in</button></form><p class='msg'>"+esc(message||"")+"</p>";
  document.getElementById("in").onsubmit=async function(event){
    event.preventDefault();
    const body={name:this.name.value,password:this.password.value};
    const response=await fetch("/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    const data=await response.json();
    if(!response.ok){loginBox(data.message||"Sign in failed.");return;}
    paint();
  };
}
function card(row){
  const tone=row.kind==="LATE"?"warn":(row.kind==="SIGNAL"?(row.side==="BUY"?"good":"bad"):(row.side?"warn":""));
  const targets=(row.targets||[]).join(" \u00b7 ");
  const bits=[];
  if(row.side) bits.push(row.chart+" "+row.side);
  if(row.entry!=null) bits.push("entry "+row.entry);
  if(row.stop!=null) bits.push("stop "+row.stop);
  if(targets) bits.push("target "+targets);
  return "<div class='card'><b class='"+tone+"'>"+esc(row.label)+" \u00b7 "+esc(bits[0]||row.kind||"quiet")+"</b><div class='sub'>"+esc(bits.slice(1).join(" \u00b7 "))+"</div><div class='sub'>"+esc(row.reason||"")+"</div></div>";
}
let timer=0;
async function paint(){
  const response=await fetch("/board");
  const data=await response.json().catch(()=>({}));
  if(!response.ok){
    if(timer){clearInterval(timer);timer=0;}
    loginBox(data.message||"");
    return;
  }
  mark.textContent=data.name;
  app.innerHTML="<h1>ZEUS</h1>"+(data.rows||[]).map(card).join("")+"<p class='note'>No order is sent from this page.</p>";
  if(!timer) timer=setInterval(paint,4000);
}
paint();
</script></body></html>"""

DESK_LOGIN = """<!doctype html><html><head><meta charset="utf-8"><title>ZEUS phone</title>
<style>body{background:#071019;color:#e7eef5;font-family:Arial;padding:24px}input,button{font:16px Arial;padding:10px;margin:6px 0;display:block}.warn{color:#e9c66b}</style>
</head><body><h1>Phone names</h1><p>This password is in WATCH_OWNER.txt on this PC.</p>
<form method="post"><input type="hidden" name="action" value="enter"><input name="password" type="password" placeholder="Owner password"><button>Open</button></form>
<p class="warn"><!--MSG--></p></body></html>"""

DESK = """<!doctype html><html><head><meta charset="utf-8"><title>ZEUS phone</title>
<style>body{background:#071019;color:#e7eef5;font-family:Arial;padding:24px}input,button{font:16px Arial;padding:8px;margin:4px}form{margin:8px 0}a{color:#9fb3c8}</style>
</head><body><h1>Phone names</h1>
<p>Blocking a name cuts off the phone that is open. The others stay on. This page does not send an order.</p>
<form method="post"><input name="name" placeholder="Name"><input name="password" placeholder="Password"><input type="hidden" name="action" value="add"><button>Add</button></form>
<!--USERS-->
</body></html>"""
'''

watch = Path("src") / "zeus3" / "v19" / "watch_page.py"
if not watch.exists():
    print("Could not find the phone page.", flush=True)
    raise SystemExit(1)
body = watch.read_text(encoding="utf-8")
if "PHONE = " not in body:
    watch.write_text(body.rstrip() + "\n\n" + LAYOUT, encoding="utf-8")
    print("Phone page layout added.", flush=True)
