# speech_to_text.py
import os
import threading
import json
import time
import wave
from urllib.parse import urlencode
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
import pyaudio
import websocket

ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
CONNECTION_PARAMS = {"sample_rate":16000, "format_turns": True}
API_ENDPOINT = f"wss://streaming.assemblyai.com/v3/ws?{urlencode(CONNECTION_PARAMS)}"

FRAMES_PER_BUFFER = 800
SAMPLE_RATE = CONNECTION_PARAMS["sample_rate"]
CHANNELS = 1
FORMAT = pyaudio.paInt16

# state
_audio = None
_stream = None
_ws = None
_thread = None
_stop_event = threading.Event()
_recorded_frames = []
_recording_lock = threading.Lock()
_latest_file = Path("latest_transcript.txt")

def _write_latest(text: str):
    try:
        _latest_file.write_text(text, encoding="utf-8")
    except Exception:
        pass

def _on_open(ws):
    def _stream_audio():
        global _stream
        while not _stop_event.is_set():
            try:
                data = _stream.read(FRAMES_PER_BUFFER, exception_on_overflow=False)
                with _recording_lock:
                    _recorded_frames.append(data)
                ws.send(data, websocket.ABNF.OPCODE_BINARY)
            except Exception:
                break
    t = threading.Thread(target=_stream_audio, daemon=True)
    t.start()

def _on_message(ws, message):
    try:
        data = json.loads(message)
        ttype = data.get("type")
        if ttype == "Turn":
            transcript = data.get("transcript","")
            formatted = data.get("turn_is_formatted", False)
            if formatted:
                # final turn; write to latest_transcript.txt
                _write_latest(transcript)
        # ignore others
    except Exception:
        pass

def _on_error(ws, err):
    _stop_event.set()

def _on_close(ws, code, msg):
    _stop_event.set()
    # save wav
    if _recorded_frames:
        try:
            fname = f"stt_record_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
            with wave.open(fname, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                with _recording_lock:
                    wf.writeframes(b"".join(_recorded_frames))
        except Exception:
            pass

def start_stt():
    """Start STT in background. returns immediately."""
    global _audio, _stream, _ws, _thread, _stop_event
    if _thread and _thread.is_alive():
        return
    _stop_event.clear()
    _audio = pyaudio.PyAudio()
    try:
        _stream = _audio.open(input=True, frames_per_buffer=FRAMES_PER_BUFFER, channels=CHANNELS, format=FORMAT, rate=SAMPLE_RATE)
    except Exception as e:
        _audio.terminate()
        raise RuntimeError(f"Could not open microphone: {e}")

    _ws = websocket.WebSocketApp(
        API_ENDPOINT,
        header={"Authorization": ASSEMBLYAI_API_KEY},
        on_open=_on_open,
        on_message=_on_message,
        on_error=_on_error,
        on_close=_on_close,
    )

    def _run_ws():
        try:
            _ws.run_forever()
        except Exception:
            pass

    _thread = threading.Thread(target=_run_ws, daemon=True)
    _thread.start()
    # background thread will stream audio; return immediately

def stop_stt():
    """Stop STT gracefully."""
    global _ws, _stop_event, _stream, _audio
    _stop_event.set()
    try:
        if _ws:
            _ws.send(json.dumps({"type":"Terminate"}))
            time.sleep(1.0)
            _ws.close()
    except Exception:
        pass
    try:
        if _stream:
            if _stream.is_active():
                _stream.stop_stream()
            _stream.close()
    except Exception:
        pass
    try:
        if _audio:
            _audio.terminate()
    except Exception:
        pass

def get_latest_transcript():
    try:
        if _latest_file.exists():
            return _latest_file.read_text(encoding="utf-8")
    except Exception:
        return ""
    return ""
