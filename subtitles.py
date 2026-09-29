"""Live English speech -> Spanish subtitles over a background image.

    python3 subtitles.py --bg background.png     # then open the printed URL

ponytail: one process, no framework, no database. Audio in, text on a page.
Three moving parts, each an off-the-shelf program already on this Mac:
  whisper-stream (whisper.cpp)  hears English and prints utterances
  ollama                        translates each utterance to Spanish
  http.server                   shows them on a full-screen page
"""
import json, os, re, subprocess, sys, threading, urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8090
OLLAMA = "http://127.0.0.1:11434/api/generate"
MODEL = os.environ.get("SUBS_LLM", "qwen2.5:3b")
WHISPER_MODEL = os.environ.get("SUBS_ASR", "models/ggml-base.en.bin")
# -1 lets SDL choose. SDL often chooses a virtual device such as ZoomAudioDevice,
# which records silence forever and looks exactly like a broken program. Pass --mic N.
MIC = -1

# The page shows the tail of this. 40 is far more than three lines; the extra is
# scrollback the page never scrolls to, and it costs nothing.
lines = deque(maxlen=40)
lock = threading.Lock()
state = {"listening": False, "bg": None}

# whisper prints these when it hears noise but no speech. They would otherwise
# translate into real Spanish words and put nonsense on the screen.
NOISE = re.compile(r"^[\s\[\(]*(BLANK_AUDIO|INAUDIBLE|MUSIC|SOUND|NOISE|APPLAUSE|"
                   r"silence|music|applause|blank audio|start speaking|"
                   r"speaking in foreign language|foreign language|speech)[\s\]\)]*$", re.I)
# whisper-stream frames every utterance with its own markers. They are not speech, and
# they translate into Spanish nonsense on the screen if they are not dropped here.
MARKER = re.compile(r"^###|^\s*Transcription\s+\d|t0\s*=\s*\d+\s*ms")
# Whisper does not output nothing when it hears nothing. It outputs one of these.
# They are the stock phrases of its training data, and they arrive during every pause.
FILLER = {"okay", "ok", "thank you", "thanks", "thank you very much", "thanks for watching",
          "bye", "goodbye", "you", "yeah", "yes", "so", "uh", "um", "hmm", "mm-hmm", "right",
          "please subscribe", "see you next time", "the end", "i'm sorry"}


REFUSAL = re.compile(r"^(no puedo|no es posible|lo siento|parece ser|esta frase|"
                     r"i can|i'm sorry|sorry,|it seems|the text)", re.I)


def translate(text):
    """English -> Spanish through the local model. Returns None if it fails."""
    body = json.dumps({
        "model": MODEL,
        # Naming the target language inside the prompt, not only in the system field,
        # is what stops the drift. With the instruction in the system field alone this
        # model answered one test sentence in Latin, and got three others wrong.
        "prompt": f"Translate into Spanish (espanol):\n\n{text}\n\nSpanish:",
        "system": "You translate English subtitles into Spanish. Output only the Spanish translation.",
        "stream": False,
        "options": {"temperature": 0, "num_predict": 200},
    }).encode()
    try:
        req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.load(r)["response"].strip()
        out = out.strip('"').strip()
        # "orgulloso/a" is correct writing and wrong subtitling. Keep the first form.
        out = re.sub(r"\b(\w+?)o/a\b", r"\1o", out)
        if not out:
            return None
        # Given nonsense, the model explains why it cannot translate instead of
        # translating. That explanation is long, and it fills the screen.
        if REFUSAL.match(out) or len(out) > max(60, len(text) * 2.5):
            print(f"  dropped a non-translation: {out[:60]}", file=sys.stderr)
            return None
        return out
    except Exception as e:
        print(f"  translate failed: {e}", file=sys.stderr)
        return None


def clean(raw):
    """One line of whisper output -> speech, or None if there is no speech in it."""
    # whisper-stream draws with carriage returns and ANSI codes; strip both.
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", raw).replace("\r", " ")
    text = re.sub(r"\[[0-9:.]+ --> [0-9:.]+\]", " ", text)   # timestamps, if on
    text = re.sub(r"\s+", " ", text).strip()
    if not text or NOISE.match(text) or MARKER.search(text):
        return None
    if text.strip(" .,!?¡¿-").lower() in FILLER:
        return None
    # Whisper labels non-speech inside brackets, in words NOISE does not list:
    # "(dramatic music)", "[coughing]". Translated, they become Spanish on the screen —
    # "(musica dramatica)" reached it on 2026-09-18.
    if re.fullmatch(r"[\(\[].*[\)\]]", text):
        return None
    # A lone "." or "..." is whisper hearing a pause.
    return None if not re.search(r"[A-Za-z]", text) else text


def listen():
    """Run whisper-stream and translate every utterance it prints."""

    cmd = [
        "whisper-stream", "-m", WHISPER_MODEL, "-t", "6",
        "--step", "0",          # 0 = wait for a pause, then transcribe. One line per utterance.
        "--length", "8000",     # never hold more than 8 s before forcing a transcription
        "-vth", "0.6",          # voice-activity threshold
        "-mt", "64",            # the 32-token default truncates a long sentence
        "-kc",                  # keep context across a pause: the one configuration
                                # observed to transcribe a full passage correctly
        "-l", "en",
        "-c", str(MIC),
    ]
    print(f"  listening with: {' '.join(cmd)}")
    # Its own chatter, and the capture-device list, go to the log. Read it when
    # the page stays empty: the device list is the first thing to check.
    log = open("whisper.log", "w")
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=log,
                         text=True, errors="replace", bufsize=1)
    state["listening"] = True
    seen = deque(maxlen=4)
    for raw in p.stdout:
        text = clean(raw)
        # whisper-stream reprints its sliding window, so the same words arrive twice.
        # The invented filler alternates, so compare against the last few, not just one.
        if not text or text in seen:
            continue
        seen.append(text)
        print(f"  EN  {text}")
        es = translate(text)
        if es:
            with lock:
                # The English dedupe is not enough: "a few more questions" and "a few
                # more questions now" are different lines that translate to the same
                # Spanish, and the repeat is what the room sees.
                if es in list(lines)[-3:]:
                    continue
                print(f"  ES  {es}")
                lines.append(es)
    state["listening"] = False
    print("  whisper-stream stopped", file=sys.stderr)


PAGE = """<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Transcriby</title>
<style>
 html,body{margin:0;height:100%;background:#000;overflow:hidden;
   font-family:-apple-system,Helvetica Neue,sans-serif}
 #bg{position:fixed;inset:0;width:100%;height:100%;object-fit:contain;background:#000}
 /* The band is fully transparent: black text straight onto the artwork, nothing
    behind it. Choose a background whose top third is light, or the text will not
    be readable — there is no scrim to rescue it. */
 #band{position:fixed;top:0;left:0;right:0;padding:3vh 5vw 6vh;background:none}
 #subs{height:3.9em;overflow:hidden;line-height:1.3;
   font-size:clamp(22px,3.5vw,68px);font-weight:600;color:#000;text-wrap:balance}
 #subs p{margin:0 0 .15em}
 #subs p:not(:last-child){opacity:.55}
 #dot{position:fixed;bottom:2.2vh;right:2.2vw;width:1.5vh;height:1.5vh;border-radius:50%;
   background:#2ecc40;box-shadow:0 0 12px #2ecc40;opacity:.55}
 body.off #dot{background:#ff4136;box-shadow:0 0 12px #ff4136}
</style>
<img id=bg alt="">
<div id=band><div id=subs></div></div>
<div id=dot></div>
<script>
var subs = document.getElementById('subs'), bg = document.getElementById('bg'), last = '';
fetch('/bg').then(function(r){ if (r.ok) bg.src = '/bg?' + Date.now(); });
function tick(){
  fetch('/lines').then(function(r){ return r.json(); }).then(function(d){
    document.body.className = d.listening ? '' : 'off';
    var key = d.lines.join('|');
    if (key !== last){
      last = key;
      subs.textContent = '';
      d.lines.forEach(function(t){
        var p = document.createElement('p');
        p.textContent = t;
        subs.appendChild(p);
      });
      // Always show the newest text, whatever it wrapped to.
      subs.scrollTop = subs.scrollHeight;
    }
  }).catch(function(){});
}
setInterval(tick, 400); tick();
</script>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path in ("/", "/display"):
            return self.send(200, PAGE.encode(), "text/html; charset=utf-8")
        if path == "/lines":
            with lock:
                tail = list(lines)[-6:]
            body = json.dumps({"lines": tail, "listening": state["listening"]}).encode()
            return self.send(200, body, "application/json")
        if path == "/bg":
            bg = state["bg"]
            if not bg or not os.path.isfile(bg):
                return self.send(404, b"no background", "text/plain")
            ext = os.path.splitext(bg)[1].lower()
            ctype = {".png": "image/png", ".webp": "image/webp",
                     ".gif": "image/gif", ".svg": "image/svg+xml"}.get(ext, "image/jpeg")
            with open(bg, "rb") as f:
                return self.send(200, f.read(), ctype)
        self.send(404, b"not found", "text/plain")


def check():
    assert clean("[BLANK_AUDIO]") is None
    assert clean("   ...  ") is None
    assert clean("\x1b[2K\rHello there, everyone.") == "Hello there, everyone."
    assert clean("[00:00:01.000 --> 00:00:03.000]  Good morning.") == "Good morning."
    assert clean("Bitcoin is money.") == "Bitcoin is money."
    # whisper-stream's own framing, which must never reach the screen
    assert clean("### Transcription 4 START | t0 = 15108 ms | t1 = 23108 ms") is None
    assert clean("### Transcription 3 END") is None
    assert clean("[Start speaking]") is None
    # invented out of silence, in every form whisper writes it
    assert clean("Okay.") is None
    assert clean(" Thank you. ") is None
    assert clean("Thanks for watching!") is None
    assert clean("Okay, so the supply is fixed.") == "Okay, so the supply is fixed."
    assert clean("(speaking in foreign language)") is None
    assert clean("(dramatic music)") is None
    assert clean("[coughing]") is None
    assert clean("(Music)") is None
    assert clean("Bitcoin (the network) is money.") == "Bitcoin (the network) is money."
    # the model explaining itself instead of translating
    assert REFUSAL.match("No puedo traducir esa frase porque parece ser un fragmento")
    assert not REFUSAL.match("Nadie puede imprimir mas de veintiun millones.")
    assert re.sub(r"\b(\w+?)o/a\b", r"\1o", "Estoy orgulloso/a de ti") == "Estoy orgulloso de ti"
    print("checks pass")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check(); sys.exit()
    if "--mic" in sys.argv:
        globals()["MIC"] = int(sys.argv[sys.argv.index("--mic") + 1])
    if "--bg" in sys.argv:
        state["bg"] = sys.argv[sys.argv.index("--bg") + 1]
    else:
        for name in sorted(os.listdir(".")):
            if name.lower().startswith("background."):
                state["bg"] = name
                break
    print(f"  background: {state['bg'] or 'none — page stays black'}")
    threading.Thread(target=listen, daemon=True).start()
    print(f"  screen  ->  http://127.0.0.1:{PORT}/")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
