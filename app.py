from flask import Flask, request, render_template, redirect, url_for
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI
import os, json, time, requests

app = Flask(__name__)

BASE_URL = "https://suppositionless-nonbiological-roman.ngrok-free.dev"
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SETTINGS_FILE = "settings.json"

def load_settings():
    with open(SETTINGS_FILE, "r") as f:
        return json.load(f)

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)

conversation_memory = {}

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    settings = load_settings()
    if request.method == "POST":
        settings["greeting"] = request.form.get("greeting", settings["greeting"])
        settings["system_prompt"] = request.form.get("system_prompt", settings["system_prompt"])
        settings["voice_gender"] = request.form.get(
            "voice_gender", settings.get("voice_gender", "male")
        )
        # ElevenLabs settings
        settings["use_elevenlabs"] = True if request.form.get("use_elevenlabs") == "true" else False
        settings["elevenlabs_api_key"] = request.form.get("elevenlabs_api_key", settings.get("elevenlabs_api_key", ""))
        settings["eleven_voice_id"] = request.form.get("eleven_voice_id", settings.get("eleven_voice_id", ""))
        save_settings(settings)
        return redirect(url_for("dashboard"))
    return render_template("dashboard.html", settings=settings)

@app.route("/", methods=["GET", "POST"])
def root():
    return "Server running"

@app.route("/voice", methods=["POST"])
def voice():
    response = VoiceResponse()
    settings = load_settings()
    gather = Gather(
        input="speech",
        action=f"{BASE_URL}/process",
        method="POST",
        timeout=5,
        speechTimeout="auto"
    )
    gather.say(settings["greeting"])
    response.append(gather)
    return str(response)

@app.route("/process", methods=["POST"])
def process():
    user_speech = request.form.get("SpeechResult", "").strip()
    call_sid = request.form.get("CallSid")
    settings = load_settings()
    response = VoiceResponse()
    if not user_speech:
        response.say("Sorry, I didn’t catch that. Could you please repeat?")
        response.redirect(f"{BASE_URL}/voice", method="POST")
        return str(response)
    if call_sid not in conversation_memory:
        conversation_memory[call_sid] = []
    conversation_memory[call_sid].append({"role": "user", "content": user_speech})
    ai_reply = generate_ai_reply(conversation_memory[call_sid])
    conversation_memory[call_sid].append({"role": "assistant", "content": ai_reply})
    # If ElevenLabs is enabled, synthesize audio and play it; otherwise use Twilio TTS
    if settings.get("use_elevenlabs") and settings.get("elevenlabs_api_key"):
        try:
            filename = tts_elevenlabs(ai_reply, settings, call_sid)
            response.play(f"{BASE_URL}/static/tts/{filename}")
        except Exception as e:
            print("ElevenLabs TTS error:", e)
            response.say("Sorry, voice synthesis failed; playing default voice.")
            response.say(ai_reply)
    else:
        response.say(ai_reply)
    gather = Gather(
        input="speech",
        action=f"{BASE_URL}/process",
        method="POST",
        timeout=5,
        speechTimeout="auto"
    )
    response.append(gather)
    return str(response)

def generate_ai_reply(history):
    settings = load_settings()
    messages = [{"role": "system", "content": settings["system_prompt"]}] + history
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.3
    )
    return completion.choices[0].message.content


def tts_elevenlabs(text, settings, call_sid=None):
    """Synthesize `text` via ElevenLabs and save an MP3 into static/tts/, returning filename."""
    api_key = settings.get("elevenlabs_api_key")
    voice_id = settings.get("eleven_voice_id") or ""
    if not api_key or not voice_id:
        raise RuntimeError("ElevenLabs API key or voice_id not configured")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{onwK4e9ZLuTAKqWW03F9}"
    headers = {
        "xi-api-key": api_key,
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }
    payload = {"text": text}

    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"ElevenLabs TTS failed: {resp.status_code} {resp.text}")

    # ensure static dir exists
    out_dir = os.path.join("static", "tts")
    os.makedirs(out_dir, exist_ok=True)
    stamp = int(time.time())
    safe_id = call_sid or "anon"
    filename = f"tts_{safe_id}_{stamp}.mp3"
    out_path = os.path.join(out_dir, filename)
    with open(out_path, "wb") as f:
        f.write(resp.content)
    return filename

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
