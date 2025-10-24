# text_to_speech.py
import os
import requests
from dotenv import load_dotenv
load_dotenv()
RIME_AUTH_TOKEN = os.getenv("RIME_AUTH_TOKEN")

def synthesize_speech(text: str, speaker: str = "Grove", outfile: str = "audio_output.mp3"):
    url = "https://users.rime.ai/v1/rime-tts"
    payload = {
        "speaker": speaker,
        "text": text,
        "modelId": "mist",
        "lang": "eng",
        "samplingRate": 22050,
        "speedAlpha": 1.0,
        "reduceLatency": False,
        "pauseBetweenBrackets": False,
        "phonemizeBetweenBrackets": False
    }
    headers = {
        "Accept": "audio/mp3",
        "Authorization": f"Bearer {RIME_AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, stream=True, timeout=60)
        if resp.status_code == 200:
            with open(outfile, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
            return outfile
        else:
            print("TTS error:", resp.status_code, resp.text)
            return None
    except Exception as e:
        print("TTS request failed:", e)
        return None
