import os
import threading
import uuid
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory
from dotenv import load_dotenv

load_dotenv()

# Import pipeline modules (these must exist in your project)
import rag_pipeline      # must expose answer_query(query: str) -> str
import text_to_speech    # must expose synthesize_speech(text: str, speaker="...", outfile="...") -> outfile or None
import speech_to_text    # must expose start_stt(), stop_stt(), get_latest_transcript()

# Flask app
app = Flask(__name__, static_folder="static", template_folder="templates")

# Directory to store generated audio
AUDIO_DIR = Path("generated_audio")
AUDIO_DIR.mkdir(exist_ok=True)

# In-memory flag so only one STT thread runs
stt_lock = threading.Lock()
stt_running = False

@app.route("/")
def index():
    return render_template("index.html")

# ----------------------------
# Query → RAG → TTS
# ----------------------------
@app.route("/api/query", methods=["POST"])
def api_query():
    data = request.json or {}
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"success": False, "error": "Missing 'query'"}), 400

    try:
        # 1) Ask RAG
        response_text = rag_pipeline.answer_query(query)
    except Exception as e:
        return jsonify({"success": False, "error": f"RAG error: {e}"}), 500

    # 2) Synthesize audio
    out_filename = AUDIO_DIR / f"reply_{uuid.uuid4().hex}.mp3"
    audio_file = text_to_speech.synthesize_speech(
        response_text,
        speaker="Grove",
        outfile=str(out_filename)
    )

    audio_url = f"/audio/{out_filename.name}" if audio_file else None

    return jsonify({"success": True, "text": response_text, "audio_url": audio_url})

# ----------------------------
# Serve audio files
# ----------------------------
@app.route("/audio/<path:filename>")
def serve_audio(filename):
    return send_from_directory(AUDIO_DIR, filename)

# ----------------------------
# STT controls
# ----------------------------
@app.route("/api/stt/start", methods=["POST"])
def stt_start():
    global stt_running
    with stt_lock:
        if stt_running:
            return jsonify({"success": False, "status": "already_running"})
        try:
            speech_to_text.start_stt()
            stt_running = True
            return jsonify({"success": True, "status": "started"})
        except Exception as e:
            stt_running = False
            return jsonify({"success": False, "status": "error", "error": str(e)}), 500

@app.route("/api/stt/stop", methods=["POST"])
def stt_stop():
    global stt_running
    with stt_lock:
        if not stt_running:
            return jsonify({"success": False, "status": "not_running"})
        try:
            speech_to_text.stop_stt()
            stt_running = False
            return jsonify({"success": True, "status": "stopped"})
        except Exception as e:
            stt_running = False
            return jsonify({"success": False, "status": "error", "error": str(e)}), 500

@app.route("/api/stt/latest", methods=["GET"])
def stt_latest():
    try:
        text = speech_to_text.get_latest_transcript()
        return jsonify({"success": True, "transcript": text})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ----------------------------
# Run server
# ----------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8501))
    debug_mode = os.getenv("DEBUG", "False").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
