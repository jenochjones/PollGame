from flask import Flask, render_template, request, jsonify, redirect, url_for, Response
import csv
import io
import json
import socket
import time
import uuid
from datetime import datetime
from pathlib import Path

app = Flask(__name__)
app.config["SECRET_KEY"] = "replace-this-secret-key-for-production"

QUESTION_SECONDS = 10
QUESTION_FILE = Path(__file__).with_name("questions.json")

def load_questions():
    with QUESTION_FILE.open("r", encoding="utf-8") as f:
        questions = json.load(f)
    cleaned = []
    for item in questions:
        question = str(item.get("question", "")).strip()
        options = [str(x).strip() for x in item.get("options", []) if str(x).strip()]
        if question and len(options) >= 2:
            cleaned.append({"question": question, "options": options})
    if not cleaned:
        raise RuntimeError("questions.json must contain at least one question with at least two options.")
    return cleaned

QUESTIONS = load_questions()

game = {
    "status": "lobby",          # lobby, question, results, finished
    "players": {},             # player_id: {name, email, joined_at}
    "current_question": -1,
    "question_started_at": None,
    "answers": {},             # question_index as str -> player_id -> answer dict
    "history": []
}

def get_local_ip():
    """Best-effort local IP so phones on the same Wi-Fi can join."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"

def answered_count():
    qkey = str(game["current_question"])
    return len(game["answers"].get(qkey, {}))

def total_players():
    return len(game["players"])

def seconds_left():
    if game["status"] != "question" or game["question_started_at"] is None:
        return 0
    elapsed = time.time() - game["question_started_at"]
    return max(0, int(round(QUESTION_SECONDS - elapsed)))

def finalize_question_if_needed(force=False):
    if game["status"] != "question":
        return
    elapsed = time.time() - game["question_started_at"]
    everyone_answered = total_players() > 0 and answered_count() >= total_players()
    if force or elapsed >= QUESTION_SECONDS or everyone_answered:
        game["status"] = "results"

def current_results():
    if game["current_question"] < 0:
        return []
    options = QUESTIONS[game["current_question"]]["options"]
    counts = {option: 0 for option in options}
    qkey = str(game["current_question"])
    for answer in game["answers"].get(qkey, {}).values():
        label = answer.get("answer")
        if label in counts:
            counts[label] += 1
    return [{"option": option, "count": counts[option]} for option in options]

def public_state(player_id=None):
    finalize_question_if_needed()
    current_question = None
    player_answer = None
    if game["current_question"] >= 0:
        current_question = {
            "index": game["current_question"],
            "number": game["current_question"] + 1,
            "total": len(QUESTIONS),
            "question": QUESTIONS[game["current_question"]]["question"],
            "options": QUESTIONS[game["current_question"]]["options"]
        }
        if player_id:
            qkey = str(game["current_question"])
            player_answer = game["answers"].get(qkey, {}).get(player_id, {}).get("answer")
    return {
        "status": game["status"],
        "players": list(game["players"].values()),
        "player_count": total_players(),
        "answered_count": answered_count() if game["status"] in ["question", "results"] else 0,
        "seconds_left": seconds_left(),
        "current_question": current_question,
        "results": current_results() if game["status"] in ["results", "finished"] else [],
        "player_answer": player_answer,
        "join_url": f"http://{get_local_ip()}:5000/join",
        "can_download": game["status"] == "finished"
    }

@app.route("/")
def host():
    return render_template("host.html", join_url=f"http://{get_local_ip()}:5000/join")

@app.route("/join")
def join_page():
    return render_template("join.html")

@app.route("/player/<player_id>")
def player_page(player_id):
    if player_id not in game["players"]:
        return redirect(url_for("join_page"))
    return render_template("player.html", player_id=player_id, player=game["players"][player_id])

@app.route("/api/state")
def api_state():
    player_id = request.args.get("player_id")
    return jsonify(public_state(player_id))

@app.route("/api/join", methods=["POST"])
def api_join():
    data = request.get_json(force=True)
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip()
    if not name or not email or "@" not in email:
        return jsonify({"ok": False, "error": "Please enter a name and valid email."}), 400
    if game["status"] != "lobby":
        return jsonify({"ok": False, "error": "The game has already started. Please wait for the next round."}), 400
    player_id = uuid.uuid4().hex
    game["players"][player_id] = {
        "id": player_id,
        "name": name,
        "email": email,
        "joined_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"
    }
    return jsonify({"ok": True, "player_id": player_id, "redirect": url_for("player_page", player_id=player_id)})

@app.route("/api/start", methods=["POST"])
def api_start():
    if total_players() == 0:
        return jsonify({"ok": False, "error": "At least one player must join before starting."}), 400
    game["status"] = "question"
    game["current_question"] = 0
    game["question_started_at"] = time.time()
    game["answers"].setdefault("0", {})
    return jsonify({"ok": True, "state": public_state()})

@app.route("/api/answer", methods=["POST"])
def api_answer():
    finalize_question_if_needed()
    if game["status"] != "question":
        return jsonify({"ok": False, "error": "This question is no longer accepting answers."}), 400
    data = request.get_json(force=True)
    player_id = str(data.get("player_id", ""))
    answer = str(data.get("answer", ""))
    if player_id not in game["players"]:
        return jsonify({"ok": False, "error": "Unknown player."}), 400
    options = QUESTIONS[game["current_question"]]["options"]
    if answer not in options:
        return jsonify({"ok": False, "error": "Invalid answer."}), 400
    qkey = str(game["current_question"])
    game["answers"].setdefault(qkey, {})[player_id] = {
        "player_id": player_id,
        "answer": answer,
        "answered_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"
    }
    finalize_question_if_needed()
    return jsonify({"ok": True, "state": public_state(player_id)})

@app.route("/api/next", methods=["POST"])
def api_next():
    if game["status"] not in ["results", "question"]:
        return jsonify({"ok": False, "error": "No active question to advance."}), 400
    finalize_question_if_needed(force=True)
    next_index = game["current_question"] + 1
    if next_index >= len(QUESTIONS):
        game["status"] = "finished"
        return jsonify({"ok": True, "state": public_state()})
    game["current_question"] = next_index
    game["question_started_at"] = time.time()
    game["answers"].setdefault(str(next_index), {})
    game["status"] = "question"
    return jsonify({"ok": True, "state": public_state()})

@app.route("/api/reset", methods=["POST"])
def api_reset():
    game["status"] = "lobby"
    game["players"] = {}
    game["current_question"] = -1
    game["question_started_at"] = None
    game["answers"] = {}
    game["history"] = []
    return jsonify({"ok": True})

@app.route("/download_results")
def download_results():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["question_number", "question", "player_name", "email", "answer", "answered_at"])
    for q_index, q in enumerate(QUESTIONS):
        qkey = str(q_index)
        for player_id, player in game["players"].items():
            answer_record = game["answers"].get(qkey, {}).get(player_id, {})
            writer.writerow([
                q_index + 1,
                q["question"],
                player["name"],
                player["email"],
                answer_record.get("answer", ""),
                answer_record.get("answered_at", "")
            ])
    csv_data = output.getvalue()
    filename = f"poll_game_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
