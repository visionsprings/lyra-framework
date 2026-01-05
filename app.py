# app.py — Minimal Flask Web UI for Lyra Framework
from flask import Flask, render_template, request, jsonify
import json
import time
import portalocker
import threading
import os

app = Flask(__name__)
MESSAGE_PATH = "message.json"

# Ensure message.json exists
if not os.path.exists(MESSAGE_PATH):
    with open(MESSAGE_PATH, "w") as f:
        json.dump({"type": "", "content": ""}, f)

@app.route("/")
def index():
    return render_template("chat.html")

@app.route("/send", methods=["POST"])
def send():
    data = request.json
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"status": "error", "message": "Empty input"})

    try:
        with open(MESSAGE_PATH, "r+", encoding="utf-8") as f:
            portalocker.lock(f, portalocker.LOCK_EX)
            f.seek(0)
            f.truncate()
            json.dump({"type": "prompt", "content": message}, f)
            f.flush()
            portalocker.unlock(f)
        return jsonify({"status": "sent"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route("/receive")
def receive():
    try:
        with open(MESSAGE_PATH, "r", encoding="utf-8") as f:
            portalocker.lock(f, portalocker.LOCK_SH)
            data = json.load(f)
            portalocker.unlock(f)
            if data.get("type") == "reply":
                response = data["content"]
                # Reset file after reading
                with open(MESSAGE_PATH, "r+", encoding="utf-8") as f2:
                    portalocker.lock(f2, portalocker.LOCK_EX)
                    f2.seek(0)
                    f2.truncate()
                    json.dump({"type": "", "content": ""}, f2)
                    f2.flush()
                    portalocker.unlock(f2)
                return jsonify({"status": "reply", "content": response})
            return jsonify({"status": "waiting"})
    except Exception:
        return jsonify({"status": "error"})

# Run inference engine in background thread
def run_engine():
    from inference_engine import run_inference  # local import to avoid circular
    while True:
        try:
            with open(MESSAGE_PATH, "r", encoding="utf-8") as f:
                portalocker.lock(f, portalocker.LOCK_SH)
                data = json.load(f)
                portalocker.unlock(f)

                if data.get("type") == "prompt":
                    prompt = data["content"]
                    response = run_inference(prompt)

                    with open(MESSAGE_PATH, "r+", encoding="utf-8") as f2:
                        portalocker.lock(f2, portalocker.LOCK_EX)
                        f2.seek(0)
                        f2.truncate()
                        json.dump({"type": "reply", "content": response}, f2)
                        f2.flush()
                        portalocker.unlock(f2)
        except Exception as e:
            print(f"Engine loop error: {e}")
        time.sleep(1)

if __name__ == "__main__":
    # Start inference engine in background
    threading.Thread(target=run_engine, daemon=True).start()
    app.run(host="127.0.0.1", port=5000, debug=False)