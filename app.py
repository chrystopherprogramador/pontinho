"""
🃏 Pontinho Vegas — Backend Flask + SQLite
Dev:   python app.py            (auto-reload de templates ligado)
Prod:  waitress-serve --listen=0.0.0.0:5000 app:app
Docker: docker build -t pontinho . ; docker run -p 5000:5000 -v pontinho_data:/app/data pontinho
"""
import json
import os
import sqlite3
from collections import Counter
from datetime import datetime
from flask import (
    Flask, g, jsonify, render_template, request, send_file, send_from_directory
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("PONTINHO_DB", os.path.join(BASE_DIR, "pontinho.db"))

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.jinja_env.auto_reload = True


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _column_exists(con, table, col):
    return any(r[1] == col for r in con.execute(f"PRAGMA table_info({table})").fetchall())


def _table_exists(con, table):
    return con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def init_db():
    con = sqlite3.connect(DB_PATH)
    # Migração: se players antigo existe sem 'room', recria preservando dados
    if _table_exists(con, "players") and not _column_exists(con, "players", "room"):
        con.executescript("""
            ALTER TABLE players RENAME TO players_old;
        """)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS players (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            room          TEXT    NOT NULL DEFAULT 'global' COLLATE NOCASE,
            name          TEXT    NOT NULL COLLATE NOCASE,
            wins          INTEGER NOT NULL DEFAULT 0,
            games_played  INTEGER NOT NULL DEFAULT 0,
            round_wins    INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(room, name)
        );
        CREATE TABLE IF NOT EXISTS matches (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            room           TEXT    NOT NULL DEFAULT 'global' COLLATE NOCASE,
            winner_name    TEXT    NOT NULL,
            players_json   TEXT    NOT NULL,
            rounds         INTEGER NOT NULL DEFAULT 0,
            rounds_json    TEXT,
            settings_json  TEXT,
            suspicious     INTEGER NOT NULL DEFAULT 0,
            played_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_players_room ON players(room);
        CREATE INDEX IF NOT EXISTS idx_matches_room ON matches(room);
    """)
    if _table_exists(con, "players_old"):
        con.executescript("""
            INSERT INTO players (name, wins, games_played, round_wins, created_at)
                SELECT name, wins, games_played, COALESCE(round_wins,0), created_at
                FROM players_old;
            DROP TABLE players_old;
        """)
    # Colunas adicionais em matches (compat com DB antigo)
    for col, ddl in (
        ("rounds_json", "ALTER TABLE matches ADD COLUMN rounds_json TEXT"),
        ("settings_json", "ALTER TABLE matches ADD COLUMN settings_json TEXT"),
        ("room", "ALTER TABLE matches ADD COLUMN room TEXT NOT NULL DEFAULT 'global' COLLATE NOCASE"),
        ("suspicious", "ALTER TABLE matches ADD COLUMN suspicious INTEGER NOT NULL DEFAULT 0"),
    ):
        if _table_exists(con, "matches") and not _column_exists(con, "matches", col):
            try:
                con.execute(ddl)
            except sqlite3.OperationalError:
                pass
    con.commit()
    con.close()


def _room():
    raw = (
        request.args.get("sala")
        or request.args.get("room")
        or (request.get_json(silent=True) or {}).get("room")
        or "global"
    )
    raw = str(raw).strip().lower()
    safe = "".join(ch for ch in raw if ch.isalnum() or ch in "-_")
    return (safe[:32] or "global")


@app.after_request
def add_cache_headers(resp):
    if resp.mimetype == "text/html":
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "icon.svg", mimetype="image/svg+xml")


@app.route("/sw.js")
def sw():
    return send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")


@app.route("/manifest.webmanifest")
def manifest():
    return send_from_directory(
        app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json"
    )


@app.get("/api/ranking")
def api_ranking():
    room = _room()
    db = get_db()
    rows = db.execute(
        """
        SELECT name, wins, games_played, round_wins
        FROM players WHERE room = ?
        ORDER BY wins DESC, round_wins DESC, games_played ASC, name ASC
        LIMIT 100
        """,
        (room,),
    ).fetchall()
    return jsonify({"room": room, "ranking": [dict(r) for r in rows]})


@app.get("/api/players")
def api_players():
    room = _room()
    db = get_db()
    rows = db.execute(
        "SELECT name FROM players WHERE room = ? ORDER BY name COLLATE NOCASE",
        (room,),
    ).fetchall()
    return jsonify([r["name"] for r in rows])


@app.get("/api/stats/<name>")
def api_stats(name):
    room = _room()
    db = get_db()
    p = db.execute(
        "SELECT * FROM players WHERE room=? AND name=? COLLATE NOCASE", (room, name)
    ).fetchone()
    if not p:
        return jsonify({"error": "Jogador não encontrado nesta sala."}), 404

    matches = db.execute(
        """
        SELECT id, winner_name, players_json, rounds, played_at
        FROM matches WHERE room = ? ORDER BY played_at DESC
        """,
        (room,),
    ).fetchall()

    history, games, wins, total_rounds = [], 0, 0, 0
    for m in matches:
        try:
            pls = json.loads(m["players_json"])
        except Exception:
            pls = []
        if not any(pl.lower() == name.lower() for pl in pls):
            continue
        games += 1
        total_rounds += int(m["rounds"] or 0)
        won = (m["winner_name"] or "").lower() == name.lower()
        if won:
            wins += 1
        history.append({
            "id": m["id"], "winner": m["winner_name"],
            "players": pls, "rounds": m["rounds"],
            "played_at": m["played_at"], "won": won,
        })

    return jsonify({
        "name": p["name"], "room": room,
        "wins": p["wins"], "round_wins": p["round_wins"],
        "games_played": p["games_played"],
        "win_rate": round((wins / games) * 100, 1) if games else 0.0,
        "avg_rounds_per_game": round(total_rounds / games, 1) if games else 0,
        "history": history[:30],
    })


@app.get("/api/matches")
def api_matches():
    room = _room()
    db = get_db()
    rows = db.execute(
        """
        SELECT id, winner_name, players_json, rounds, played_at, suspicious
        FROM matches WHERE room = ?
        ORDER BY played_at DESC LIMIT 50
        """,
        (room,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["players"] = json.loads(d.pop("players_json"))
        except Exception:
            d["players"] = []
        out.append(d)
    return jsonify(out)


@app.post("/api/match")
def api_save_match():
    data = request.get_json(silent=True) or {}
    winner = (data.get("winner") or "").strip()
    all_players = [p.strip() for p in (data.get("players") or []) if p and p.strip()]
    round_wins = data.get("round_wins") or {}
    rounds = int(data.get("rounds") or 0)
    rounds_detail = data.get("rounds_detail")
    settings = data.get("settings") or {}
    room = _room()

    if not winner or not all_players:
        return jsonify({"error": "Dados inválidos."}), 400
    if not any(winner.lower() == p.lower() for p in all_players):
        return jsonify({"error": "Vencedor não está na mesa."}), 400

    # Anti-cheat leve: confere totais informados vs limite
    suspicious = 0
    if isinstance(rounds_detail, list) and rounds_detail:
        totals = Counter()
        for entry in rounds_detail:
            if not isinstance(entry, dict):
                continue
            if entry.get("type") == "round":
                for nm, v in (entry.get("entries") or {}).items():
                    try:
                        totals[nm] += int(v)
                    except (TypeError, ValueError):
                        suspicious = 1
            elif entry.get("type") == "reentry":
                nm = entry.get("player")
                try:
                    totals[nm] = int(entry.get("score_after", totals.get(nm, 0)))
                except (TypeError, ValueError):
                    suspicious = 1
        try:
            if totals.get(winner, 0) >= int(settings.get("limit", 101)):
                suspicious = 1
        except Exception:
            suspicious = 1

    db = get_db()
    for nm in all_players:
        db.execute(
            """
            INSERT INTO players (room, name, games_played) VALUES (?, ?, 1)
            ON CONFLICT(room, name) DO UPDATE SET games_played = games_played + 1
            """,
            (room, nm),
        )
    db.execute(
        "UPDATE players SET wins = wins + 1 WHERE room=? AND name=? COLLATE NOCASE",
        (room, winner),
    )
    for nm, count in (round_wins or {}).items():
        try:
            c = int(count)
        except (TypeError, ValueError):
            c = 0
        if c <= 0:
            continue
        db.execute(
            "UPDATE players SET round_wins = round_wins + ? WHERE room=? AND name=? COLLATE NOCASE",
            (c, room, str(nm).strip()),
        )
    db.execute(
        """
        INSERT INTO matches (room, winner_name, players_json, rounds, rounds_json, settings_json, suspicious)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            room, winner,
            json.dumps(all_players, ensure_ascii=False),
            rounds,
            json.dumps(rounds_detail, ensure_ascii=False) if rounds_detail else None,
            json.dumps(settings, ensure_ascii=False) if settings else None,
            suspicious,
        ),
    )
    db.commit()
    return jsonify({"ok": True, "suspicious": bool(suspicious), "room": room})


@app.get("/api/export")
def api_export():
    if not os.path.exists(DB_PATH):
        return jsonify({"error": "Sem DB ainda."}), 404
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return send_file(
        DB_PATH, mimetype="application/x-sqlite3",
        as_attachment=True, download_name=f"pontinho-{stamp}.db",
    )


@app.get("/api/rooms")
def api_rooms():
    db = get_db()
    rows = db.execute(
        "SELECT room, COUNT(*) AS players FROM players GROUP BY room ORDER BY players DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
