# app.py — Lyra Framework Web UI + Orchestrator
from flask import Flask, render_template, request, jsonify
import json
import time
import portalocker
import threading
import os
import logging
import subprocess
import requests
from db import get_db
from utils import extract_from_text


app = Flask(__name__)
MESSAGE_PATH = "message.json"

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Ensure message.json exists
if not os.path.exists(MESSAGE_PATH):
    with open(MESSAGE_PATH, "w", encoding="utf-8") as f:
        json.dump({"type": "", "content": ""}, f, indent=2)


# === Emotion analysis helper ===
def get_emotion_vector(text: str) -> str:
    try:
        resp = requests.post("http://127.0.0.1:8000/analyze", json={"text": text}, timeout=5)
        if resp.status_code == 200:
            return json.dumps(resp.json().get("emotions", {}))
    except Exception as e:
        logging.warning(f"Emotion analysis failed: {e}")
    return json.dumps({})


# === Auto-start emotion server ===
def start_emotion_server():
    try:
        requests.get("http://127.0.0.1:8000/docs", timeout=3)
        logging.info("Emotion server already running")
    except:
        logging.info("Launching emotion analysis server...")
        try:
            subprocess.Popen([
                "python", "-m", "uvicorn",
                "distilbert_emotion_server:app",
                "--host", "127.0.0.1",
                "--port", "8000"
            ], cwd=os.path.dirname(os.path.abspath(__file__)))
            # Wait for it to start
            for _ in range(15):
                time.sleep(1)
                try:
                    requests.get("http://127.0.0.1:8000/docs", timeout=1)
                    logging.info("Emotion server ready")
                    return
                except:
                    pass
            logging.warning("Emotion server did not start within timeout")
        except Exception as e:
            logging.error(f"Failed to launch emotion server: {e}")


# === Launch separate Inference Engine process ===
def start_inference_engine():
    """Auto-start inference_engine.py if not already running."""
    already_running = False
    try:
        with open(MESSAGE_PATH, "r", encoding="utf-8") as f:
            portalocker.lock(f, portalocker.LOCK_EX | portalocker.LOCK_NB)
            portalocker.unlock(f)
    except portalocker.exceptions.LockException:
        already_running = True
    except Exception:
        pass  # File might not exist yet, but we'll create it

    if already_running:
        logging.info("Inference engine already running")
        return

    logging.info("Launching dedicated inference engine (inference_engine.py)...")
    try:
        subprocess.Popen(
            ["python", "inference_engine.py"],
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        time.sleep(3)  # Give it time to initialize
        logging.info("Inference engine launched")
    except Exception as e:
        logging.error(f"Failed to launch inference engine: {e}")


# === Routes ===
@app.route("/")
def index():
    return render_template("chat.html")


@app.route("/send", methods=["POST"])
def send():
    data = request.json or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"status": "error", "message": "Empty message"})

    try:
        # Save user message and capture its ID
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO messages (role, content) VALUES (?, ?)", ("user", message))
            user_msg_id = cursor.lastrowid
            emotions = get_emotion_vector(message)
            cursor.execute("UPDATE messages SET emotions = ? WHERE id = ?", (emotions, user_msg_id))
            conn.commit()

        # Send prompt with user_msg_id
        prompt_data = {
            "type": "prompt",
            "content": message,
            "user_msg_id": user_msg_id
        }
        with open(MESSAGE_PATH, "r+", encoding="utf-8") as f:
            portalocker.lock(f, portalocker.LOCK_EX)
            f.seek(0)
            f.truncate()
            json.dump(prompt_data, f, indent=2)
            f.flush()
            portalocker.unlock(f)

        logging.info(f"User message saved (id: {user_msg_id})")
        return jsonify({"status": "sent"})
    except Exception as e:
        logging.error(f"Send error: {e}")
        return jsonify({"status": "error"})


@app.route("/receive")
def receive():
    try:
        with open(MESSAGE_PATH, "r", encoding="utf-8") as f:
            portalocker.lock(f, portalocker.LOCK_SH)
            data = json.load(f)
            portalocker.unlock(f)

        if data.get("type") == "reply":
            raw_response = data.get("content", "").strip()
            user_msg_id = data.get("user_msg_id")

            if not raw_response:
                return jsonify({"status": "waiting"})

            # === Three explicit extractions ===
            content = extract_from_text(raw_response, "response")
            if not content or len(content.strip()) < 3:
                logging.warning("[Receive] Response extraction failed — falling back to raw text.")
                content = raw_response.strip()[:2000]

            logging.info(f"[Receive] Extracted RESPONSE: {content[:150]}{'...' if len(content) > 150 else ''}")

            actions = extract_from_text(raw_response, "actions") or "none"
            logging.info(f"[Receive] Extracted ACTIONS: {actions}")

            internal_dialogue = extract_from_text(raw_response, "internal_dialogue") or "I listen quietly."
            logging.info(f"[Receive] Extracted INTERNAL_DIALOGUE: {internal_dialogue}")

            # === Save structured reply ===
            try:
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO messages 
                        (role, content, actions, internal_dialogue, reply_to) 
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        ("assistant", content, actions, internal_dialogue, user_msg_id)
                    )
                    emotions_json = get_emotion_vector(content)
                    cursor.execute(
                        "UPDATE messages SET emotions = ? WHERE rowid = last_insert_rowid()",
                        (emotions_json,)
                    )
                    conn.commit()
                logging.info(f"Assistant structured reply saved (reply_to: {user_msg_id})")
            except Exception as db_e:
                logging.error(f"Failed to save structured reply: {db_e}")

            # === Reset message.json ===
            with open(MESSAGE_PATH, "r+", encoding="utf-8") as f:
                portalocker.lock(f, portalocker.LOCK_EX)
                f.seek(0)
                f.truncate()
                json.dump({"type": "", "content": ""}, f, indent=2)
                f.flush()
                portalocker.unlock(f)

            return jsonify({
                "status": "reply",
                "content": content,
                "actions": actions
            })

        return jsonify({"status": "waiting"})

    except Exception as e:
        logging.error(f"Receive error: {e}")
        return jsonify({"status": "error"})


@app.route("/fetch-history")
def fetch_history():
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT role, content, actions FROM messages ORDER BY id DESC LIMIT 10")
            rows = cursor.fetchall()
            history = [
                {"role": row["role"], "content": row["content"], "actions": row["actions"]}
                for row in reversed(rows)
            ]
        return jsonify(history)
    except Exception as e:
        logging.error(f"History error: {e}")
        return jsonify([])


@app.route("/db-manager")
def db_manager():
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row["name"] for row in cursor.fetchall()]

            data = {}
            for table in tables:
                cursor.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT 100")
                rows = cursor.fetchall()
                if rows:
                    columns = rows[0].keys()
                    row_list = [dict(zip(columns, row)) for row in rows]
                    data[table] = {"columns": list(columns), "rows": row_list}
                else:
                    data[table] = {"columns": [], "rows": []}

        return render_template("db_manager.html", tables=data)
    except Exception as e:
        logging.error(f"DB Manager error: {e}")
        return f"<pre>DB Manager Error: {e}</pre>", 500


@app.route("/db-delete", methods=["POST"])
def db_delete():
    table = request.form.get("table")
    row_id = request.form.get("id")
    if not table or not row_id:
        return "Missing params", 400
    try:
        with get_db() as conn:
            conn.execute(f"DELETE FROM {table} WHERE rowid = ?", (row_id,))
            conn.commit()
        return "<script>alert('Row deleted'); window.location='/db-manager';</script>"
    except Exception as e:
        logging.error(f"Delete failed: {e}")
        return f"<pre>Delete failed: {e}</pre>", 500


# === Startup ===
if __name__ == "__main__":
    # Start supporting services
    threading.Thread(target=start_emotion_server, daemon=True).start()
    time.sleep(4)

    # Start dedicated inference engine
    start_inference_engine()
    time.sleep(3)  # Allow model loading

    logging.info("Lyra Framework running — http://127.0.0.1:5001")
    app.run(host="127.0.0.1", port=5001, debug=False)