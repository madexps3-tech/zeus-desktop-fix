"""A watch-only page for a phone. It cannot send an order."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import threading
from pathlib import Path
from typing import Any

from aiohttp import web

PORT = 8790
USERS = Path("watch_users.json")
OWNER = Path("WATCH_OWNER.txt")
_LOCK = threading.Lock()
_SESSIONS: dict[str, str] = {}
_TOKENS: dict[str, str] = {}
_DESK: dict[str, str] = {}
_CACHE: dict[str, dict[str, Any]] = {}
_STARTED = False
_HOST: Any = None

RANK = ("INTRADAY", "INTERDAY", "RESPONSIVE", "SCALP", "SWING", "ICEBERG")
PAIRS = ("XAUUSD", "XAGUSD", "NAS100", "BTCUSD", "EURUSD", "USDJPY", "WTI", "NG-C", "GER40")
LABELS = {
    "XAUUSD": "GOLD", "XAGUSD": "SILVER", "NAS100": "NASDAQ", "BTCUSD": "BITCOIN",
    "EURUSD": "EURO", "USDJPY": "USDJPY", "WTI": "OIL", "NG-C": "GAS", "GER40": "DAX",
}


def _hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000).hex()


def _load() -> dict[str, Any]:
    try:
        state = json.loads(USERS.read_text(encoding="utf-8")) if USERS.exists() else {}
    except (OSError, json.JSONDecodeError):
        state = {}
    if not isinstance(state, dict):
        state = {}
    users = state.get("users")
    state["users"] = users if isinstance(users, dict) else {}
    return state


def _save(state: dict[str, Any]) -> None:
    USERS.write_text(json.dumps(state), encoding="utf-8")


def _owner_password() -> str:
    if OWNER.exists():
        for line in OWNER.read_text(encoding="utf-8").splitlines():
            if line.startswith("Password: "):
                found = line.split("Password: ", 1)[1].strip()
                if found:
                    return found
    password = secrets.token_urlsafe(9)
    OWNER.write_text(
        "\n".join((
            "This file stays on the PC. Do not send it to a phone.",
            "Open http://127.0.0.1:8790/desk on this PC to add a name or block one.",
            "The phone opens http://127.0.0.1:8790/ on this network, or the Tailscale address for port 8790.",
            "Point Tailscale at port 8790, not 8783. Port 8783 can send an order.",
            f"Password: {password}",
            "",
        )),
        encoding="utf-8",
    )
    return password


def _check_owner(password: str) -> bool:
    return hmac.compare_digest(password, _owner_password())


def _user(name: str) -> dict[str, Any] | None:
    row = _load()["users"].get(name)
    return row if isinstance(row, dict) else None


def add_user(name: str, password: str) -> str:
    clean = "".join(ch for ch in name.strip().lower() if ch.isalnum())
    if len(clean) < 2 or len(clean) > 20:
        return "Use 2 to 20 letters or numbers."
    if len(password) < 6:
        return "The password needs at least 6 characters."
    salt = secrets.token_bytes(16)
    state = _load()
    state["users"][clean] = {"salt": salt.hex(), "hash": _hash(password, salt), "blocked": False}
    _save(state)
    return ""


def set_blocked(name: str, blocked: bool) -> str:
    clean = name.strip().lower()
    state = _load()
    row = state["users"].get(clean)
    if not isinstance(row, dict):
        return "That name is not there."
    row["blocked"] = bool(blocked)
    _save(state)
    with _LOCK:
        token = _SESSIONS.pop(clean, None)
        if token:
            _TOKENS.pop(token, None)
    return ""


def _login(name: str, password: str) -> tuple[str, str]:
    clean = name.strip().lower()
    row = _user(clean)
    if row is None:
        return "", "That name is not on this PC."
    if row.get("blocked"):
        return "", "This login is blocked."
    try:
        salt = bytes.fromhex(str(row.get("salt") or ""))
        expected = str(row.get("hash") or "")
    except ValueError:
        return "", "That name is not on this PC."
    if not hmac.compare_digest(_hash(password, salt), expected):
        return "", "That password is wrong."
    token = secrets.token_urlsafe(24)
    with _LOCK:
        old = _SESSIONS.get(clean)
        if old:
            _TOKENS.pop(old, None)
        _SESSIONS[clean] = token
        _TOKENS[token] = clean
    return token, ""


def _name_for(token: str) -> tuple[str, str]:
    with _LOCK:
        name = _TOKENS.get(token) or ""
    if not name:
        return "", "Sign in again. This login was opened somewhere else, or it was blocked."
    row = _user(name)
    if row is None or row.get("blocked"):
        with _LOCK:
            _TOKENS.pop(token, None)
            if _SESSIONS.get(name) == token:
                _SESSIONS.pop(name, None)
        return "", "This login is blocked."
    return name, ""


def _detail(row: dict[str, Any], late: bool) -> dict[str, Any]:
    targets = [price for price in (row.get("targets") or []) if price is not None]
    if not targets and row.get("target") is not None:
        targets = [row.get("target")]
    return {
        "chart": row.get("chart") or "",
        "side": row.get("side") or "",
        "entry": row.get("entry"),
        "stop": row.get("stop"),
        "targets": targets[:4],
        "reason": str(row.get("note") or row.get("reason") or ""),
        "state": "LATE" if late else str(row.get("state") or ""),
    }


def _summarize(payload: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in (payload.get("rows") or []) if isinstance(row, dict)]
    live = [row for row in rows if str(row.get("chart") or "") in RANK]
    ranked = [row for row in live if row.get("side") and row.get("entry") is not None]
    ranked.sort(key=lambda row: RANK.index(str(row.get("chart"))))
    hit = next((row for row in ranked if row.get("button") or row.get("tradeable")), None)
    if hit is not None:
        late = bool(hit.get("late") or hit.get("missed") or str(hit.get("state") or "") == "LATE")
        item = _detail(hit, late)
        item["kind"] = "LATE" if late else "SIGNAL"
        return item
    push = next((row for row in live if row.get("push") and row.get("side") and row.get("entry") is not None), None)
    if push is not None:
        item = _detail(push, False)
        item["kind"] = "PUSH"
        item["reason"] = "High risk. Not a trade. " + item["reason"]
        return item
    sweep = next((row for row in rows if row.get("chart") == "SWEEP" and row.get("side") and row.get("entry") is not None), None)
    if sweep is not None:
        item = _detail(sweep, False)
        item["kind"] = "SWEEP"
        item["reason"] = "Not a trade. " + item["reason"]
        return item
    coming = next((row for row in live if isinstance(row.get("coming"), dict) and row["coming"].get("side")), None)
    if coming is not None:
        zone = coming["coming"]
        return {
            "kind": "INCOMING",
            "chart": coming.get("chart") or "",
            "side": zone.get("side") or "",
            "entry": zone.get("zone"),
            "stop": None,
            "targets": [],
            "reason": str(zone.get("text") or "Not a trade yet."),
            "state": "COMING",
        }
    if ranked:
        shown = ranked[0]
        late = bool(shown.get("late") or shown.get("missed") or str(shown.get("state") or "") == "LATE")
        item = _detail(shown, late)
        item["kind"] = "LATE" if late else "SHOWN"
        return item
    return {"kind": "QUIET", "chart": "", "side": "", "entry": None, "stop": None, "targets": [], "reason": "Quiet.", "state": ""}


def _board_rows() -> list[dict[str, Any]]:
    rows = []
    for symbol in PAIRS:
        item = dict(_CACHE.get(symbol) or {"kind": "QUIET", "reason": "Reading.", "side": "", "entry": None, "stop": None, "targets": []})
        item["symbol"] = symbol
        item["label"] = LABELS.get(symbol, symbol)
        rows.append(item)
    return rows


def _scan(host: Any) -> None:
    from zeus3.v19.signals_page import PAIRS as page_pairs, _LOCK as page_lock, _payload

    for symbol in page_pairs:
        locked = page_lock.acquire(timeout=8)
        if not locked:
            continue
        try:
            payload = _payload(symbol, "M1", host, True)
        except Exception:
            payload = None
        finally:
            page_lock.release()
        if isinstance(payload, dict) and payload.get("rows") is not None:
            _CACHE[symbol] = _summarize(payload)


def _cookie(header: str, name: str) -> str:
    for part in str(header or "").split(";"):
        piece = part.strip()
        if piece.startswith(name + "="):
            return piece.split("=", 1)[1]
    return ""


async def watch_page(_request: web.Request) -> web.Response:
    return web.Response(text=PHONE, content_type="text/html")


async def watch_login(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = str(body.get("name") or "")
    password = str(body.get("password") or "")
    token, message = _login(name, password)
    if not token:
        return web.json_response({"ok": False, "message": message}, status=401)
    response = web.json_response({"ok": True, "name": name.strip().lower()})
    response.set_cookie("zeus_watch", token, httponly=True, samesite="Lax", path="/")
    return response


async def watch_logout(request: web.Request) -> web.Response:
    token = _cookie(request.headers.get("Cookie", ""), "zeus_watch")
    with _LOCK:
        name = _TOKENS.pop(token, None)
        if name and _SESSIONS.get(name) == token:
            _SESSIONS.pop(name, None)
    response = web.json_response({"ok": True})
    response.del_cookie("zeus_watch", path="/")
    return response


async def watch_board(request: web.Request) -> web.Response:
    token = _cookie(request.headers.get("Cookie", ""), "zeus_watch")
    if not token:
        return web.json_response({"ok": False, "message": ""}, status=401)
    name, message = _name_for(token)
    if not name:
        return web.json_response({"ok": False, "message": message}, status=401)
    return web.json_response({"ok": True, "name": name, "rows": _board_rows()})


def _desk_open(request: web.Request) -> bool:
    token = _cookie(request.headers.get("Cookie", ""), "zeus_desk")
    with _LOCK:
        return bool(token) and _DESK.get(token) == "owner"


async def desk_page(request: web.Request) -> web.Response:
    if not _desk_open(request):
        return web.Response(text=DESK_LOGIN, content_type="text/html")
    users = _load()["users"]
    lines = []
    for name in sorted(users):
        row = users[name]
        state = "blocked" if isinstance(row, dict) and row.get("blocked") else "on"
        action = "unblock" if state == "blocked" else "block"
        label = "Turn on" if state == "blocked" else "Block"
        lines.append(
            f"<form method='post'><b>{_esc(name)}</b> <span>{state}</span> "
            f"<input type='hidden' name='name' value='{_esc(name)}'><input type='hidden' name='action' value='{action}'>"
            f"<button>{label}</button></form>"
        )
    body = DESK.replace("<!--USERS-->", "".join(lines) or "<p>No names yet.</p>")
    return web.Response(text=body, content_type="text/html")


async def desk_post(request: web.Request) -> web.Response:
    form = await request.post()
    action = str(form.get("action") or "")
    if action == "enter":
        if not _check_owner(str(form.get("password") or "")):
            return web.Response(text=DESK_LOGIN.replace("<!--MSG-->", "That password is wrong."), content_type="text/html", status=401)
        token = secrets.token_urlsafe(24)
        with _LOCK:
            _DESK.clear()
            _DESK[token] = "owner"
        response = web.HTTPFound("/desk")
        response.set_cookie("zeus_desk", token, httponly=True, samesite="Strict", path="/")
        return response
    if not _desk_open(request):
        return web.HTTPFound("/desk")
    name = str(form.get("name") or "")
    if action == "add":
        message = add_user(name, str(form.get("password") or ""))
    elif action == "block":
        message = set_blocked(name, True)
    elif action == "unblock":
        message = set_blocked(name, False)
    else:
        message = "Unknown action."
    if message:
        return web.Response(text=f"<p>{_esc(message)}</p><p><a href='/desk'>Back</a></p>", content_type="text/html", status=400)
    return web.HTTPFound("/desk")


def _esc(value: str) -> str:
    text = str(value)
    return text.replace("&", "&" + "amp;").replace("<", "&" + "lt;").replace(">", "&" + "gt;").replace('"', "&" + "quot;")


def _loop(host: Any) -> None:
    while True:
        with _LOCK:
            someone = bool(_TOKENS)
        if someone and host is not None:
            try:
                _scan(host)
            except Exception:
                pass
        threading.Event().wait(12)


def start_watch(host: Any) -> None:
    """One local page on port 8790. It has no order route."""
    global _STARTED, _HOST
    _HOST = host
    if _STARTED:
        return
    _STARTED = True
    _owner_password()
    threading.Thread(target=_loop, args=(host,), name="zeus-watch-scan", daemon=True).start()

    def serve() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        app = web.Application()
        app.router.add_get("/", watch_page)
        app.router.add_post("/login", watch_login)
        app.router.add_post("/logout", watch_logout)
        app.router.add_get("/board", watch_board)
        app.router.add_get("/desk", desk_page)
        app.router.add_post("/desk", desk_post)
        runner = web.AppRunner(app)
        loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, "127.0.0.1", PORT)
        loop.run_until_complete(site.start())
        print(f"Phone watch is on http://127.0.0.1:{PORT}/  The owner password is in {OWNER.resolve()}", flush=True)
        loop.run_forever()

    threading.Thread(target=serve, name="zeus-watch", daemon=True).start()
