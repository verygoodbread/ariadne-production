#!/usr/bin/env python3
"""Ariadne backend — stdlib only.

Serves the repo root statically (Concierge bundle, Project Dashboard, and the
operator console are same-origin) and exposes a JSON API:

  POST  /api/projects                 create a project from a brief
  GET   /api/projects                 list projects (operator picker)
  GET   /api/projects/:id             derived project view
  PATCH /api/projects/:id             merge mutable state (mode/product/decisions)
  POST  /api/projects/:id/compose     operator narration -> AI-structured draft
  POST  /api/projects/:id/publish     write approved draft into the project
  GET   /api/projects/:id/events      SSE stream of project-updated events
  GET   /api/designs/:id              a design record (piece identity)

Run:  ANTHROPIC_API_KEY=... python3 serve.py   (port 8772)
"""

import json
import os
import queue
import sqlite3
import ssl
import threading
import time
import urllib.request
import urllib.error
import uuid
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "ariadne.db")
PORT = 8772


def load_env_file():
    """Pull KEY=VALUE pairs from a local .env into os.environ (won't override
    anything already set). Stdlib-only; no python-dotenv dependency."""
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if (len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"')):
                v = v[1:-1]
            os.environ.setdefault(k, v)


load_env_file()

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-sonnet-4-6"
ANTHROPIC_VERSION = "2023-06-01"


def _ssl_context():
    """macOS Python from python.org ships without a CA bundle; fall back to
    the system CA so urllib can do TLS to api.anthropic.com."""
    for path in (
        os.environ.get("SSL_CERT_FILE"),
        "/etc/ssl/cert.pem",                  # macOS
        "/etc/ssl/certs/ca-certificates.crt", # Debian/Ubuntu
        "/etc/pki/tls/certs/ca-bundle.crt",   # RHEL/Fedora
    ):
        if path and os.path.isfile(path):
            return ssl.create_default_context(cafile=path)
    return ssl.create_default_context()


SSL_CTX = _ssl_context()

# Serialises every read-modify-write of state_json + the per-project id counter.
WRITE_LOCK = threading.Lock()

# project_id -> set[queue.Queue]; guarded by SUB_LOCK.
SUBSCRIBERS = {}
SUB_LOCK = threading.Lock()

# ── Derivation: ported from the Concierge controller so figures stay consistent ─

QTY_LABELS = {
    "one": "Just one", "two": "Two", "few": "A few (3–5)",
    "5-20": "A handful (5–20)", "20-100": "A short run (20–100)",
    "100-500": "A run (100–500)", "500+": "A batch (500+)",
    "ask": "From the desk",
}
MATERIAL_LABELS = {
    "budget": "Budget tier", "mid": "Mid-market", "premium": "Premium",
    "bespoke": "Bespoke", "ask": "From the desk — premium",
}
TIMELINE_LABELS = {
    "flexible": "Flexible", "normal": "Normal", "tight": "Tight",
    "rush": "Rush", "emergency": "Emergency", "ask": "From the desk — normal",
}
AUDIENCE_LABELS = {"myself": "Myself", "customers": "My customers"}

MULT_QTY = {"one": 1.00, "two": 1.00, "few": 1.00, "5-20": 0.62,
            "20-100": 0.57, "100-500": 0.50, "500+": 0.40, "ask": 0.62}
MULT_MAT = {"budget": 0.35, "mid": 0.55, "premium": 1.00, "bespoke": 2.00, "ask": 1.00}
MULT_TIME = {"flexible": 0.55, "normal": 0.80, "tight": 1.00,
             "rush": 1.60, "emergency": 2.40, "ask": 1.00}
BASELINE_OF_RETAIL = 0.35
RETAIL_ANCHOR = 2400  # default brief (premium·tight·one ⇒ 1×) → $840

STAGE_NOTES = {
    "sourcing": "Suppliers shortlisted · sample maker contacted",
    "manufacturing": "Tooling, sampling, and the production run",
    "quality": "Sample review · tolerances & finish",
    "fulfillment": "Packed, insured, and to your door",
    "insights": "Post-launch reporting and reorder signals",
}
PATH_PERSONAL = ["sourcing", "quality", "fulfillment"]
PATH_BUSINESS = ["sourcing", "manufacturing", "quality", "fulfillment", "insights"]

# Shipped sample so the Design→Brief handoff is demoable out of the box.
SEED_DESIGNS = {
    "lamp-04": {
        "id": "lamp-04",
        "title": "Hanging lamp, no. 04",
        "subtitle": "Turned beech canopy · ceramic shade · 1.8m linen cord.",
        "eyebrow": "turned beech & ceramic",
        "file": "lamp_04.step",
        "view": "¾ front",
        "dimensions": [
            {"label": "height", "value": "188 mm"},
            {"label": "⌀", "value": "136"},
        ],
    }
}


def mult_from_qty(v):
    if not v:
        return None
    if isinstance(v, str) and v.startswith("custom:"):
        try:
            n = int(v[len("custom:"):])
        except ValueError:
            return None
        if n >= 1000:
            return 0.30
        if n >= 500:
            return 0.40
        if n >= 100:
            return 0.50
        if n >= 20:
            return 0.57
        if n >= 5:
            return 0.62
        return 1.00
    return MULT_QTY.get(v)


def qty_label(v):
    if isinstance(v, str) and v.startswith("custom:"):
        n = v[len("custom:"):]
        return f"{n} piece" if n == "1" else f"{n} pieces"
    return QTY_LABELS.get(v, v)


def normalize_mode(mode):
    return "atelier" if mode == "self" else "concierge"


def derive(brief, state):
    """Brief-derived read-model + mutable state. The piece comes from the
    design file captured at submit (falls back to the seeded sample)."""
    audience = brief.get("audience")
    material = brief.get("material") or "premium"
    timeline = brief.get("timeline") or "tight"
    quantity = brief.get("quantity")

    design = brief.get("design") or SEED_DESIGNS["lamp-04"]

    stage_ids = PATH_BUSINESS if audience == "customers" else PATH_PERSONAL
    stages = [
        {"order": i + 1, "id": sid, "label": sid.capitalize(),
         "note": STAGE_NOTES[sid], "state": "now" if i == 0 else "pending"}
        for i, sid in enumerate(stage_ids)
    ]

    q = mult_from_qty(quantity) or 1.0
    m = MULT_MAT.get(material, 1.0)
    t = MULT_TIME.get(timeline, 1.0)
    amount = round(RETAIL_ANCHOR * BASELINE_OF_RETAIL * q * m * t)

    mode = state.get("mode") or normalize_mode(brief.get("mode"))
    po = state.get("product", {})

    product = {
        "title": po.get("title", design.get("title", "Your piece")),
        "subtitle": po.get("subtitle", design.get("subtitle", "")),
        "eyebrow": po.get("eyebrow", design.get("eyebrow", "")),
        "file": design.get("file", ""),
        "view": design.get("view", ""),
        "dimensions": design.get("dimensions", []),
        "specs": {
            "material": po.get("material", MATERIAL_LABELS.get(material, material)),
            "quantity": po.get("quantity", qty_label(quantity)),
            "timeline": po.get("timeline", TIMELINE_LABELS.get(timeline, timeline)),
            "audience": po.get("audience", AUDIENCE_LABELS.get(audience, audience)),
        },
    }

    return {
        "mode": mode,
        "brief": brief,
        "notes": brief.get("notes", ""),
        "product": product,
        "stages": stages,
        "quote": {
            "amount": amount,
            "currency": "USD",
            "caption": "Indicative — premium·tight is the 1× baseline (~35% of retail).",
        },
        "status": "Brief received · in review",
        "decisions": state.get("decisions", []),
        "timeline": state.get("timeline", []),
        "journal": state.get("journal", []),
    }


# ── Storage ──────────────────────────────────────────────────────────────────

def db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db():
    conn = db()
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS projects (
                   id TEXT PRIMARY KEY, reference TEXT UNIQUE, created_at TEXT,
                   brief_json TEXT, state_json TEXT)"""
        )
        conn.execute("CREATE TABLE IF NOT EXISTS designs (id TEXT PRIMARY KEY, json TEXT)")
        for did, doc in SEED_DESIGNS.items():
            conn.execute("INSERT OR IGNORE INTO designs (id, json) VALUES (?,?)",
                         (did, json.dumps(doc)))
        conn.commit()
    finally:
        conn.close()


def get_design(did):
    conn = db()
    try:
        row = conn.execute("SELECT json FROM designs WHERE id=?", (did,)).fetchone()
    finally:
        conn.close()
    return json.loads(row["json"]) if row else None


def mint_reference(conn):
    n = conn.execute("SELECT COUNT(*) AS c FROM projects").fetchone()["c"]
    ref = f"A-{1827 + n}"
    while conn.execute("SELECT 1 FROM projects WHERE reference=?", (ref,)).fetchone():
        n += 1
        ref = f"A-{1827 + n}"
    return ref


REQUIRED_BRIEF = ("audience", "quantity", "material", "timeline")


def create_project(brief):
    if not isinstance(brief, dict) or any(not brief.get(k) for k in REQUIRED_BRIEF):
        raise ValueError("brief is missing required fields")
    with WRITE_LOCK:
        conn = db()
        try:
            pid = uuid.uuid4().hex[:8]
            ref = mint_reference(conn)
            conn.execute(
                "INSERT INTO projects (id, reference, created_at, brief_json, state_json)"
                " VALUES (?,?,?,?,?)",
                (pid, ref, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 json.dumps(brief), json.dumps({})),
            )
            conn.commit()
            return {"id": pid, "reference": ref}
        finally:
            conn.close()


def _row(pid):
    conn = db()
    try:
        return conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    finally:
        conn.close()


def get_project(pid):
    row = _row(pid)
    if not row:
        return None
    view = derive(json.loads(row["brief_json"]), json.loads(row["state_json"]))
    view.update({"id": row["id"], "reference": row["reference"],
                 "createdAt": row["created_at"]})
    return view


def list_projects():
    conn = db()
    try:
        rows = conn.execute(
            "SELECT id, reference, created_at, brief_json, state_json"
            " FROM projects ORDER BY created_at DESC"
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        brief = json.loads(r["brief_json"])
        state = json.loads(r["state_json"])
        design = brief.get("design") or SEED_DESIGNS["lamp-04"]
        out.append({
            "id": r["id"], "reference": r["reference"],
            "title": (state.get("product", {}).get("title")
                      or design.get("title", "Project")),
            "nickname": state.get("nickname", ""),
            "tags": state.get("tags", []),
            "mode": state.get("mode") or normalize_mode(brief.get("mode")),
            "createdAt": r["created_at"],
        })
    return out


def delete_project(pid):
    with WRITE_LOCK:
        conn = db()
        try:
            cur = conn.execute("DELETE FROM projects WHERE id=?", (pid,))
            conn.commit()
            deleted = cur.rowcount > 0
        finally:
            conn.close()
    if deleted:
        # Wake any open SSE subscribers so their next reload() returns 404.
        notify(pid)
        with SUB_LOCK:
            SUBSCRIBERS.pop(pid, None)
    return deleted


def _save_state(pid, mutate):
    """Run mutate(state) under the write lock and persist. Returns the
    derived project (or None if missing)."""
    with WRITE_LOCK:
        conn = db()
        try:
            row = conn.execute("SELECT state_json FROM projects WHERE id=?",
                                (pid,)).fetchone()
            if not row:
                return None
            state = json.loads(row["state_json"])
            mutate(state)
            conn.execute("UPDATE projects SET state_json=? WHERE id=?",
                         (json.dumps(state), pid))
            conn.commit()
        finally:
            conn.close()
    notify(pid)
    return get_project(pid)


def patch_project(pid, patch):
    if not isinstance(patch, dict):
        raise ValueError("patch must be an object")

    def mutate(state):
        for key, val in patch.items():
            # decisions/timeline/journal are lists keyed by item id; a patch
            # of {<id>: {fields}} updates matching items in place.
            if key in ("decisions", "timeline", "journal") and isinstance(val, dict):
                arr = state.setdefault(key, [])
                if isinstance(arr, list):
                    for item in arr:
                        upd = val.get(item.get("id"))
                        if isinstance(upd, dict):
                            item.update(upd)
                continue
            if isinstance(val, dict) and isinstance(state.get(key), dict):
                state[key].update(val)
            else:
                state[key] = val

    return _save_state(pid, mutate)


def publish(pid, draft):
    """Stamp server ids and upsert approved cards into the project."""
    if not isinstance(draft, dict):
        raise ValueError("publish body must be an object")

    today_short = datetime.now().strftime("%-d %b")
    today_when = datetime.now().strftime("today · %H:%M")
    placeholders = {"", "unknown", "tbd", "n/a", "none", "null"}

    def clean_date(v, fallback):
        if not isinstance(v, str) or v.strip().lower() in placeholders:
            return fallback
        return v

    def mutate(state):
        seq = state.setdefault("_ids", {"d": 0, "t": 0, "j": 0})
        for kind, prefix in (("decisions", "d"), ("timeline", "t"), ("journal", "j")):
            incoming = draft.get(kind) or []
            if not isinstance(incoming, list):
                continue
            arr = state.setdefault(kind, [])
            by_id = {x.get("id"): i for i, x in enumerate(arr) if x.get("id")}
            for item in incoming:
                if not isinstance(item, dict):
                    continue
                item = dict(item)
                if kind == "decisions":
                    item.setdefault("status", "open")
                    item.setdefault("chosen", None)
                    item["deadline"] = clean_date(item.get("deadline"), today_short)
                elif kind == "timeline":
                    item["date"] = clean_date(item.get("date"), today_short)
                elif kind == "journal":
                    item["when"] = clean_date(item.get("when"), today_when)
                iid = item.get("id")
                if iid and iid in by_id:
                    arr[by_id[iid]] = item
                else:
                    seq[prefix] += 1
                    item["id"] = f"{prefix}-{seq[prefix]}"
                    arr.append(item)

    return _save_state(pid, mutate)


# ── SSE ──────────────────────────────────────────────────────────────────────

def notify(pid):
    with SUB_LOCK:
        subs = list(SUBSCRIBERS.get(pid, ()))
    for qx in subs:
        try:
            qx.put_nowait("project-updated")
        except queue.Full:
            pass


# ── Anthropic compose (raw HTTP, stdlib) ─────────────────────────────────────

COMPOSE_TOOL = {
    "name": "emit_project_updates",
    "description": ("Convert the operator's plain-language note into structured "
                    "updates for the customer's project dashboard."),
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "stage": {"type": "string"},
                        "question": {"type": "string"},
                        "context": {"type": "string"},
                        "deadline": {"type": "string"},
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "value": {"type": "string"},
                                    "name": {"type": "string"},
                                    "meta": {"type": "string"},
                                },
                                "required": ["value", "name", "meta"],
                            },
                        },
                    },
                    "required": ["stage", "question", "context", "deadline", "options"],
                },
            },
            "timeline": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "date": {"type": "string"},
                        "title": {"type": "string"},
                        "why": {"type": "string"},
                        "status": {"type": "string", "enum": ["next", "now", "done"]},
                    },
                    "required": ["date", "title", "why", "status"],
                },
            },
            "journal": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "text": {"type": "string"},
                        "when": {"type": "string"},
                    },
                    "required": ["text", "when"],
                },
            },
        },
        "required": ["decisions", "timeline", "journal"],
    },
}

COMPOSE_SYSTEM = (
    "You are the operations desk for Ariadne, a made-to-order furniture studio. "
    "An operator describes, in plain language, what is happening on a customer's "
    "project. Convert that note into structured updates for the customer's "
    "dashboard using the emit_project_updates tool. Only include items the note "
    "actually supports — return empty arrays for anything not mentioned. "
    "Decisions are open questions the customer must answer (give 2–4 concrete "
    "options each). Timeline entries are milestones (status: next/now/done). "
    "Journal entries are short factual log lines. Keep copy concise and in the "
    "studio's calm, plain voice. Never invent prices or supplier names that are "
    "not in the note.\n\n"
    "DATES: The project context gives you today's date. Use it: 'today' or no "
    "date mentioned → use today's date (formatted like '20 May'). 'tomorrow' → "
    "the next calendar day. Relative phrases like 'next week' or 'in 3 days' → "
    "resolve to a concrete date. For journal 'when' fields, prefer 'today · "
    "HH:MM' style when you have a time, otherwise just the date. Never output "
    "'unknown', 'TBD', or an empty date — if you genuinely don't have one, use "
    "today's date."
)


def compose(pid, text):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None, "AI offline — set ANTHROPIC_API_KEY"
    proj = get_project(pid)
    if not proj:
        return None, "project not found"
    if not (text or "").strip():
        return None, "narration is empty"

    now = datetime.now()
    context = {
        "reference": proj["reference"],
        "piece": proj["product"]["title"],
        "stages": [s["label"] for s in proj["stages"]],
        "existing_decisions": [d.get("question") for d in proj["decisions"]],
        "today": now.strftime("%-d %B %Y"),           # e.g. "20 May 2026"
        "today_short": now.strftime("%-d %b"),         # e.g. "20 May"
        "now_time": now.strftime("today · %H:%M"),     # e.g. "today · 14:08"
    }
    body = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 2000,
        # tools + system are the stable, cacheable prefix; the volatile
        # per-project context + narration go in the user message.
        "system": [{"type": "text", "text": COMPOSE_SYSTEM,
                    "cache_control": {"type": "ephemeral"}}],
        "tools": [COMPOSE_TOOL],
        "tool_choice": {"type": "tool", "name": "emit_project_updates"},
        "messages": [{
            "role": "user",
            "content": (
                "Project context:\n" + json.dumps(context, ensure_ascii=False)
                + "\n\nOperator note:\n" + text.strip()
            ),
        }],
    }
    req = urllib.request.Request(
        ANTHROPIC_URL,
        data=json.dumps(body).encode(),
        headers={
            "content-type": "application/json",
            "x-api-key": key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        return None, f"Anthropic error {e.code}: {detail}"
    except Exception as e:  # noqa: BLE001
        return None, f"Anthropic request failed: {e}"

    for block in payload.get("content", []):
        if block.get("type") == "tool_use":
            return block.get("input", {}), None
    return None, "model returned no structured output"


# ── HTTP ─────────────────────────────────────────────────────────────────────

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, *a):
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}") if length else {}

    def _segments(self):
        path = urlparse(self.path).path
        return [s for s in path.split("/") if s], path

    def do_GET(self):
        segs, path = self._segments()
        if not path.startswith("/api/"):
            return super().do_GET()
        # /api/projects/:id/events — SSE, owns the socket from here on.
        if (len(segs) == 4 and segs[:2] == ["api", "projects"]
                and segs[3] == "events"):
            return self._sse(segs[2])
        return self._api("GET", segs)

    def do_POST(self):
        segs, path = self._segments()
        if path.startswith("/api/"):
            return self._api("POST", segs)
        self.send_error(405)

    def do_PATCH(self):
        segs, path = self._segments()
        if path.startswith("/api/"):
            return self._api("PATCH", segs)
        self.send_error(405)

    def do_DELETE(self):
        segs, path = self._segments()
        if path.startswith("/api/"):
            return self._api("DELETE", segs)
        self.send_error(405)

    def _api(self, method, segs):
        try:
            # segs == ["api", "projects", ...] | ["api", "designs", id]
            if segs[:2] == ["api", "designs"] and len(segs) == 3 and method == "GET":
                d = get_design(segs[2])
                return self._json(d) if d else self._json({"error": "not found"}, 404)

            if segs[:2] == ["api", "projects"]:
                if len(segs) == 2:
                    if method == "POST":
                        return self._json(create_project(self._body()), 201)
                    if method == "GET":
                        return self._json(list_projects())
                if len(segs) == 3:
                    pid = segs[2]
                    if method == "GET":
                        p = get_project(pid)
                        return self._json(p) if p else self._json({"error": "not found"}, 404)
                    if method == "PATCH":
                        p = patch_project(pid, self._body())
                        return self._json(p) if p else self._json({"error": "not found"}, 404)
                    if method == "DELETE":
                        ok = delete_project(pid)
                        return self._json({"deleted": pid}) if ok else self._json({"error": "not found"}, 404)
                if len(segs) == 4:
                    pid, sub = segs[2], segs[3]
                    if method == "POST" and sub == "compose":
                        draft, err = compose(pid, self._body().get("text", ""))
                        if err:
                            return self._json({"error": err}, 503)
                        return self._json(draft)
                    if method == "POST" and sub == "publish":
                        p = publish(pid, self._body())
                        return self._json(p) if p else self._json({"error": "not found"}, 404)

            return self._json({"error": "no such endpoint"}, 404)
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": f"server error: {e}"}, 500)

    def _sse(self, pid):
        if not get_project(pid):
            return self._json({"error": "not found"}, 404)
        q = queue.Queue(maxsize=64)
        with SUB_LOCK:
            SUBSCRIBERS.setdefault(pid, set()).add(q)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    evt = q.get(timeout=15)
                    self.wfile.write(f"event: {evt}\ndata: 1\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with SUB_LOCK:
                subs = SUBSCRIBERS.get(pid)
                if subs:
                    subs.discard(q)
                    if not subs:
                        SUBSCRIBERS.pop(pid, None)


if __name__ == "__main__":
    init_db()
    key_state = "set" if os.environ.get("ANTHROPIC_API_KEY") else "MISSING (compose disabled)"
    print(f"Ariadne backend on http://localhost:{PORT}  (root: {ROOT})")
    print(f"ANTHROPIC_API_KEY: {key_state}")
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
