#!/usr/bin/env python3
"""Ariadne backend — stdlib only.

Serves the repo root statically (so the Concierge bundle and the Project
Dashboard are same-origin) and exposes a tiny JSON API that turns a submitted
concierge brief into a persisted project. Everything the dashboard shows is
*derived* from the brief; only the two-way mutable bits live in the DB.

Run:  python3 serve.py   (port 8772)
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "ariadne.db")
PORT = 8772

# ── Derivation: ported verbatim from the Concierge controller so the numbers
#    stay consistent with what the brief form already shows the user. ──────────

QTY_LABELS = {
    "one": "Just one", "two": "Two", "few": "A few (3–5)",
    "5-20": "A handful (5–20)",
    "20-100": "A short run (20–100)",
    "100-500": "A run (100–500)",
    "500+": "A batch (500+)",
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

MULT_QTY = {
    "one": 1.00, "two": 1.00, "few": 1.00,
    "5-20": 0.62, "20-100": 0.57, "100-500": 0.50, "500+": 0.40, "ask": 0.62,
}
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
    # Concierge uses 'self' for the hands-on tier; the dashboard calls it 'atelier'.
    return "atelier" if mode == "self" else "concierge"


def derive(brief, state):
    """Build the full dashboard view: brief-derived fields + mutable state."""
    audience = brief.get("audience")
    material = brief.get("material") or "premium"
    timeline = brief.get("timeline") or "tight"
    quantity = brief.get("quantity")

    stage_ids = PATH_BUSINESS if audience == "customers" else PATH_PERSONAL
    stages = [
        {
            "order": i + 1,
            "id": sid,
            "label": sid.capitalize(),
            "note": STAGE_NOTES[sid],
            "state": "now" if i == 0 else "pending",
        }
        for i, sid in enumerate(stage_ids)
    ]

    q = mult_from_qty(quantity) or 1.0
    m = MULT_MAT.get(material, 1.0)
    t = MULT_TIME.get(timeline, 1.0)
    amount = round(RETAIL_ANCHOR * BASELINE_OF_RETAIL * q * m * t)

    mode = state.get("mode") or normalize_mode(brief.get("mode"))
    product_overrides = state.get("product", {})

    product = {
        "title": product_overrides.get("title", "Hanging lamp, no. 04"),
        "subtitle": product_overrides.get(
            "subtitle", "Turned beech canopy · ceramic shade · 1.8m linen cord."
        ),
        "specs": {
            "material": product_overrides.get("material", MATERIAL_LABELS.get(material, material)),
            "quantity": product_overrides.get("quantity", qty_label(quantity)),
            "timeline": product_overrides.get("timeline", TIMELINE_LABELS.get(timeline, timeline)),
            "audience": product_overrides.get("audience", AUDIENCE_LABELS.get(audience, audience)),
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
        # Fully brief-derived: a fresh project has no narrative yet. These are
        # populated only by two-way writes from the dashboard.
        "decisions": state.get("decisions", []),
        "timeline": state.get("timeline", []),
        "journal": state.get("journal", []),
    }


# ── Storage ──────────────────────────────────────────────────────────────────

def db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS projects (
               id          TEXT PRIMARY KEY,
               reference   TEXT UNIQUE,
               created_at  TEXT,
               brief_json  TEXT,
               state_json  TEXT
           )"""
    )
    return conn


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


def get_project(pid):
    conn = db()
    try:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    brief = json.loads(row["brief_json"])
    state = json.loads(row["state_json"])
    view = derive(brief, state)
    view.update({
        "id": row["id"],
        "reference": row["reference"],
        "createdAt": row["created_at"],
    })
    return view


def patch_project(pid, patch):
    """Shallow-merge the patch into state_json (mode / product / decisions …)."""
    if not isinstance(patch, dict):
        raise ValueError("patch must be an object")
    conn = db()
    try:
        row = conn.execute("SELECT state_json FROM projects WHERE id=?", (pid,)).fetchone()
        if not row:
            return None
        state = json.loads(row["state_json"])
        for key, val in patch.items():
            if isinstance(val, dict) and isinstance(state.get(key), dict):
                state[key].update(val)
            else:
                state[key] = val
        conn.execute("UPDATE projects SET state_json=? WHERE id=?",
                     (json.dumps(state), pid))
        conn.commit()
    finally:
        conn.close()
    return get_project(pid)


# ── HTTP ─────────────────────────────────────────────────────────────────────

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        return json.loads(raw or b"{}")

    def _api_path(self):
        return urlparse(self.path).path

    def do_GET(self):
        path = self._api_path()
        if path.startswith("/api/"):
            return self._handle_api("GET", path)
        return super().do_GET()

    def do_POST(self):
        path = self._api_path()
        if path.startswith("/api/"):
            return self._handle_api("POST", path)
        self.send_error(405)

    def do_PATCH(self):
        path = self._api_path()
        if path.startswith("/api/"):
            return self._handle_api("PATCH", path)
        self.send_error(405)

    def _handle_api(self, method, path):
        try:
            if method == "POST" and path == "/api/projects":
                return self._send_json(create_project(self._read_json()), 201)

            if path.startswith("/api/projects/"):
                pid = path[len("/api/projects/"):].strip("/")
                if not pid:
                    return self._send_json({"error": "missing id"}, 400)
                if method == "GET":
                    proj = get_project(pid)
                    return self._send_json(proj) if proj else \
                        self._send_json({"error": "not found"}, 404)
                if method == "PATCH":
                    proj = patch_project(pid, self._read_json())
                    return self._send_json(proj) if proj else \
                        self._send_json({"error": "not found"}, 404)

            return self._send_json({"error": "no such endpoint"}, 404)
        except ValueError as e:
            return self._send_json({"error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001 — surface anything else as 500 JSON
            return self._send_json({"error": f"server error: {e}"}, 500)


if __name__ == "__main__":
    db().close()  # ensure schema exists before first request
    print(f"Ariadne backend on http://localhost:{PORT}  (root: {ROOT})")
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
