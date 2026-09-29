"""One phone controls the whole talk: the timer, the slides and the subtitles.

    python3 show.py --screen 1      # then open the printed phone URL

ponytail: this program owns almost nothing. The three programs that do the work already
exist, so this one starts them, forwards the phone's taps, and holds the only state that
had no home: how the subtitles look, and when each line arrived.

  timer.py      (../stage-timer)  the countdown, and the speaker's display
  subtitles.py  (here)            hearing and translating
  overlay.py    (here)            the subtitles on the presentation screen

It never repeats their logic. The timer's own pages stay its own, on its own port.
"""
import argparse, json, os, re, signal, socket, subprocess, sys, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8100
SUBS = "http://127.0.0.1:8090"      # subtitles.py
TIMER = "http://127.0.0.1:8000"     # timer.py
HERE = os.path.dirname(os.path.abspath(__file__))
TIMER_DIR = os.path.join(os.path.dirname(HERE), "stage-timer")

COLORS = ("black", "white", "yellow")
# What the overlay reads every poll. The flags still set the opening values; the phone
# moves them during the talk. Placement stays a choice, never a guess.
subs = {"visible": True, "color": "black", "size": 0, "y": 0.5, "history": 8, "screen": 0}
displays = []            # display names, asked of overlay.py once at start

# [text, arrived_ms] newest last. subtitles.py serves only a window of its own deque and
# no times, so arrival is stamped here. That is what makes "is it late?" answerable.
seen = []
seen_lock = threading.Lock()
listening = [False]
now_ms = lambda: int(time.time() * 1000)


def merge(incoming, stamp):
    """Fold a fresh window of lines into `seen`, without repeating what is already there."""
    with seen_lock:
        old = [t for t, _ in seen]
        keep = 0
        # The window slides, so its first items are usually the last items already held.
        # Find the longest such overlap; everything after it is genuinely new.
        for i in range(min(len(old), len(incoming)), 0, -1):
            if old[-i:] == incoming[:i]:
                keep = i
                break
        for t in incoming[keep:]:
            seen.append([t, stamp])
        del seen[:-40]


def watch():
    """Read subtitles.py in the background and stamp every new line."""
    while True:
        try:
            with urllib.request.urlopen(f"{SUBS}/lines", timeout=4) as r:
                d = json.load(r)
            listening[0] = bool(d.get("listening"))
            merge([t for t in d.get("lines", []) if t], now_ms())
        except Exception:
            listening[0] = False
        time.sleep(0.4)


def timer_state():
    try:
        with urllib.request.urlopen(f"{TIMER}/state", timeout=2) as r:
            return json.load(r)
    except Exception:
        return {"ms": None, "running": False, "wrap": False, "warn": 120000, "danger": 30000}


def timer_cmd(action, value):
    body = json.dumps({"action": action, "value": value}).encode()
    req = urllib.request.Request(f"{TIMER}/cmd", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=4) as r:
        return json.load(r)


def slide(action):
    """Move the deck by pressing the arrow key the presenting app already listens for.

    One path on purpose: arrow keys work for Keynote, PowerPoint, a PDF and a Canva link
    in a browser. Keynote and PowerPoint also take direct AppleScript, which needs no
    permission, but it is a second path for two of the five things Kenobi presents from.
    """
    code = 124 if action == "next" else 123          # right arrow / left arrow
    p = subprocess.run(["osascript", "-e",
                        f'tell application "System Events" to key code {code}'],
                       capture_output=True, text=True)
    if p.returncode == 0:
        return {"ok": True}
    err = (p.stderr or "").strip()
    # The one failure worth naming, because it is a setting and not a fault.
    if "1002" in err or "not allowed" in err:
        return {"error": "macOS blocks the key press. Add this terminal to System "
                         "Settings > Privacy & Security > Accessibility, then try again."}
    return {"error": err[:200] or "osascript failed"}


def list_displays():
    """Ask the overlay what displays this Mac has. It already prints them for --list."""
    venv = os.path.join(HERE, ".venv", "bin", "python")
    if not os.path.isfile(venv):
        return []
    try:
        out = subprocess.run([venv, "overlay.py", "--list"], cwd=HERE,
                             capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return []
    return [m.group(1).strip() for m in
            (re.match(r"\s*\[\d+\]\s+\S+\s+(.*)", l) for l in out.splitlines()) if m]


def set_sub(action, value):
    if action == "visible":
        subs["visible"] = bool(value)
    elif action == "color":
        if value not in COLORS:
            return {"error": "unknown colour"}
        subs["color"] = value
    elif action == "size":
        # 0 means fit the screen, which is what the overlay does with no --size.
        subs["size"] = 0 if value == 0 else min(300, max(20, int(value)))
    elif action == "y":
        subs["y"] = round(min(0.95, max(0.05, float(value))), 2)
    elif action == "history":
        subs["history"] = min(8, max(1, int(value)))
    elif action == "screen":
        # Which display the subtitles are drawn on. The overlay checks the index again,
        # because a display can be unplugged between this tap and the next draw.
        # Before the list is known, allow a few; after it, never past the last display.
        limit = len(displays) - 1 if displays else 3
        subs["screen"] = min(max(0, int(value)), limit)
    else:
        return {"error": "unknown action"}
    return dict(subs)


def sub_state():
    stamp = now_ms()
    with seen_lock:
        tail = [{"t": t, "age": round((stamp - ts) / 1000, 1)} for t, ts in seen[-4:]]
    return dict(subs, listening=listening[0], lines=tail)


PAGE = """<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name=apple-mobile-web-app-capable content=yes>
<title>Transcriby control</title><style>
:root{color-scheme:dark}
body{margin:0;padding:16px;background:#010101;color:#f0e8d5;
 padding-bottom:calc(16px + env(safe-area-inset-bottom));
 -webkit-user-select:none;user-select:none;
 font:600 17px/1.3 ui-sans-serif,-apple-system,Helvetica,sans-serif}
#t{font-size:15vw;text-align:center;font-variant-numeric:tabular-nums;margin:4px 0 12px}
#t.over{color:#e01b24}
h2{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#8c8274;margin:18px 0 8px}
.g{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:10px}
.g2{grid-template-columns:repeat(2,1fr)}
button{font:inherit;padding:18px 0;border:0;border-radius:12px;background:#1c1a17;color:#f0e8d5;
 -webkit-tap-highlight-color:transparent}
button:active{background:#2b2b2b}
button.on{background:#f7931a;color:#010101}
.go{background:#f7931a;color:#010101}
.wide{grid-column:span 3}
.slide{padding:30px 0;font-size:24px}
#err{background:#e01b24;color:#fff;border-radius:10px;padding:10px;margin:8px 0;display:none}
#feed{background:#12110f;border-radius:12px;padding:10px 12px;min-height:72px}
#feed div{margin:0 0 6px;font-weight:500}
#feed span{color:#8c8274;font-size:13px;margin-left:6px}
#feed div:last-child{color:#fff;font-weight:700}
#dot{display:inline-block;width:10px;height:10px;border-radius:50%;background:#2ecc40;
 margin-right:8px;vertical-align:middle}
#dot.off{background:#e01b24}
</style>

<div id=t>--:--</div>
<div id=err></div>

<h2>Slides</h2>
<div class="g g2">
 <button class=slide onclick="cmd('slide','prev')">&#9664;</button>
 <button class=slide onclick="cmd('slide','next')">&#9654;</button>
</div>

<h2>Timer</h2>
<div class=g>
 <button class=go onclick="cmd('timer','start')">Start</button>
 <button onclick="cmd('timer','pause')">Pause</button>
 <button onclick="cmd('timer','restart')">Restart</button>
</div>
<div class=g id=presets></div>
<div class="g g2">
 <button onclick="cmd('timer','adjust',-60000)">&minus; 1 min</button>
 <button onclick="cmd('timer','adjust',60000)">+ 1 min</button>
</div>
<div class=g><button class=wide id=wrapbtn>WRAP IT UP</button></div>

<h2>Subtitles</h2>
<div class=g>
 <button id=onoff class=wide></button>
</div>
<div class=g>
 <button id=cblack onclick="cmd('subs','color','black')">Black</button>
 <button id=cwhite onclick="cmd('subs','color','white')">White</button>
 <button id=cyellow onclick="cmd('subs','color','yellow')">Yellow</button>
</div>
<div class=g>
 <button onclick="bump('size',-8)">A &minus;</button>
 <button onclick="cmd('subs','size',0)">Auto</button>
 <button onclick="bump('size',8)">A +</button>
</div>
<div class=g>
 <button onclick="bump('y',-0.05)">Higher</button>
 <button id=ypos></button>
 <button onclick="bump('y',0.05)">Lower</button>
</div>
<div class=g>
 <button onclick="bump('history',-1)">Fewer lines</button>
 <button id=hcount></button>
 <button onclick="bump('history',1)">More lines</button>
</div>

<h2>Which display</h2>
<div class=g id=screens></div>

<h2><span id=dot></span>What the room reads</h2>
<div id=feed></div>

<script>
var el = document.getElementById('t'), err = document.getElementById('err');
var wrapBtn = document.getElementById('wrapbtn'), onoff = document.getElementById('onoff');
var feed = document.getElementById('feed'), dot = document.getElementById('dot');
var ypos = document.getElementById('ypos'), hcount = document.getElementById('hcount');
var screens = document.getElementById('screens');
var pad = function(n){ return String(n).padStart(2, '0'); };
var now = {};
// Built as real elements, not as an HTML string: an inline onclick inside a JavaScript
// string needs escaped quotes, and that is the trap that has broken these pages before.
[1, 5, 10, 15, 20, 30].forEach(function(m){
  var b = document.createElement('button');
  b.textContent = m + ' min';
  b.onclick = function(){ cmd('timer', 'set', m * 60000); };
  document.getElementById('presets').appendChild(b);
});

function show(e){
  err.style.display = e ? 'block' : 'none';
  err.textContent = e || '';
}

function cmd(target, action, value){
  return fetch('cmd', {method: 'POST', body: JSON.stringify(
      {target: target, action: action, value: value === undefined ? 0 : value})})
    .then(function(r){ return r.json(); })
    .then(function(d){ show(d.error); tick(); })
    .catch(function(){ show('the Mac did not answer'); });
}

// The stepper reads the value the server last reported, so two taps never fight.
function bump(key, by){
  var v = now.subs ? now.subs[key] : 0;
  if (key === 'size' && !v) v = 48;              // Auto has no number; start from a real one
  cmd('subs', key, key === 'y' ? Math.round((v + by) * 100) / 100 : v + by);
}

wrapBtn.onclick = function(){ cmd('timer', 'wrap', now.timer && now.timer.wrap ? 0 : 1); };
onoff.onclick = function(){ cmd('subs', 'visible', now.subs && now.subs.visible ? 0 : 1); };

function tick(){
  fetch('state', {cache: 'no-store'}).then(function(r){ return r.json(); }).then(function(d){
    now = d;
    var ms = d.timer.ms;
    if (ms === null){ el.textContent = '--:--'; el.className = ''; }
    else {
      var over = ms < 0, a = Math.abs(ms);
      el.textContent = (over ? '-' : '') + pad(Math.floor(a / 60000)) + ':' + pad(Math.floor(a / 1000) % 60);
      el.className = over ? 'over' : '';
    }
    wrapBtn.className = d.timer.wrap ? 'wide on' : 'wide';
    wrapBtn.textContent = d.timer.wrap ? 'Hide message' : 'WRAP IT UP';
    onoff.className = d.subs.visible ? 'wide on' : 'wide';
    onoff.textContent = d.subs.visible ? 'Subtitles are ON' : 'Subtitles are OFF';
    ['black', 'white', 'yellow'].forEach(function(c){
      document.getElementById('c' + c).className = d.subs.color === c ? 'on' : '';
    });
    // The displays never change while the Mac runs, so they are drawn once.
    if (!screens.children.length && d.displays.length){
      d.displays.forEach(function(name, i){
        var b = document.createElement('button');
        b.textContent = i === 0 ? 'Main' : name.split(' ')[0];
        b.onclick = function(){ cmd('subs', 'screen', i); };
        screens.appendChild(b);
      });
    }
    for (var i = 0; i < screens.children.length; i++)
      screens.children[i].className = d.subs.screen === i ? 'on' : '';
    ypos.textContent = Math.round(d.subs.y * 100) + '%';
    hcount.textContent = d.subs.history + ' lines';
    dot.className = d.subs.listening ? '' : 'off';
    feed.innerHTML = d.subs.lines.map(function(l){
      return '<div>' + l.t.replace(/[<>&]/g, ' ') + '<span>' + l.age + 's</span></div>';
    }).join('') || '<div style="color:#8c8274">nothing heard yet</div>';
  }).catch(function(){ show('the Mac did not answer'); });
}
tick(); setInterval(tick, 500);
</script>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path in ("/", "/c"):
            return self.send(200, PAGE, "text/html; charset=utf-8")
        if path == "/state":
            return self.send(200, json.dumps({"timer": timer_state(), "subs": sub_state(),
                                              "displays": displays}), "application/json")
        if path == "/lines":
            # What overlay.py polls: the same shape subtitles.py serves, plus the
            # settings, so the overlay keeps one poll and one origin.
            with seen_lock:
                tail = [t for t, _ in seen][-subs["history"]:]
            return self.send(200, json.dumps(dict(subs, lines=tail, listening=listening[0])),
                             "application/json")
        self.send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path.split("?")[0].rstrip("/") != "/cmd":
            return self.send(404, b"not found", "text/plain")
        try:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"] or 0)) or "{}")
        except ValueError:
            return self.send(400, b'{"error":"bad json"}', "application/json")
        target, action, value = body.get("target"), body.get("action"), body.get("value", 0)
        try:
            if target == "timer":
                if action not in ("start", "pause", "restart", "set", "adjust", "wrap"):
                    out = {"error": "unknown timer action"}
                elif not isinstance(value, int) or abs(value) > 24 * 3600_000:
                    out = {"error": "bad value"}
                else:
                    out = timer_cmd(action, value)
            elif target == "subs":
                out = set_sub(action, value)
            elif target == "slide":
                out = slide("next" if action == "next" else "prev")
            else:
                out = {"error": "unknown target"}
        except Exception as e:
            out = {"error": f"{target} did not answer: {e}"[:200]}
        self.send(200, json.dumps(out), "application/json")


def up(url, timeout=1.5):
    try:
        urllib.request.urlopen(url, timeout=timeout).read()
        return True
    except Exception:
        return False


def spawn(cmd, cwd):
    # Its own process group, so stopping it also stops ITS children. subtitles.py runs
    # whisper-stream, and a whisper-stream left behind holds the microphone.
    return subprocess.Popen(cmd, cwd=cwd, start_new_session=True)


def start_children(args):
    """Start only what is not already running, and only what was asked for."""
    kids = []
    if not up(f"{SUBS}/lines"):
        cmd = [sys.executable, "subtitles.py"]
        if args.mic is not None:
            cmd += ["--mic", str(args.mic)]
        if args.bg:
            cmd += ["--bg", args.bg]
        print("  starting subtitles.py")
        kids.append(spawn(cmd, HERE))
    if not args.no_timer and not up(f"{TIMER}/state"):
        timer = os.path.join(TIMER_DIR, "timer.py")
        if os.path.isfile(timer):
            print("  starting timer.py")
            kids.append(spawn([sys.executable, timer], TIMER_DIR))
        else:
            print(f"  no timer at {timer} — the timer controls will stay at --:--")
    if not args.no_overlay:
        venv = os.path.join(HERE, ".venv", "bin", "python")
        if not os.path.isfile(venv):
            print("  no .venv — see the README. Skipping the overlay.")
        else:
            print(f"  starting overlay.py on screen {args.screen}")
            kids.append(spawn([venv, "overlay.py", "--screen", str(args.screen),
                               "--server", f"http://127.0.0.1:{PORT}"], HERE))
    return kids


def check():
    # The window slides, so the merge is the one piece of arithmetic that can drop or
    # repeat a line without anyone noticing until a talk.
    seen.clear()
    merge(["one", "two"], 100)
    assert [t for t, _ in seen] == ["one", "two"]
    merge(["one", "two", "three"], 200)                  # window grew by one
    assert [t for t, _ in seen] == ["one", "two", "three"]
    assert seen[-1][1] == 200 and seen[0][1] == 100      # only the new line is stamped now
    merge(["two", "three", "four"], 300)                 # window slid forward
    assert [t for t, _ in seen] == ["one", "two", "three", "four"]
    merge(["two", "three", "four"], 400)                 # nothing new
    assert [t for t, _ in seen] == ["one", "two", "three", "four"]
    seen.clear()
    merge(["a"] * 3, 10)                                 # a genuine repeat is kept as three
    assert [t for t, _ in seen] == ["a", "a", "a"]
    # Settings are clamped, because a phone can send anything.
    assert set_sub("y", 9)["y"] == 0.95 and set_sub("y", -3)["y"] == 0.05
    assert set_sub("size", 5)["size"] == 20 and set_sub("size", 0)["size"] == 0
    assert set_sub("history", 99)["history"] == 8 and set_sub("history", 0)["history"] == 1
    displays[:] = ["Built-in", "Projector"]
    assert set_sub("screen", 1)["screen"] == 1          # the second display
    assert set_sub("screen", 7)["screen"] == 1          # never past the last one
    assert set_sub("screen", -2)["screen"] == 0
    displays[:] = ["Built-in"]
    assert set_sub("screen", 3)["screen"] == 0          # one display means one choice
    displays[:] = []
    assert "error" in set_sub("color", "chartreuse") and set_sub("color", "white")["color"] == "white"
    assert "error" in set_sub("font", 1)
    set_sub("visible", 0); assert subs["visible"] is False
    set_sub("visible", 1); assert subs["visible"] is True
    print("checks pass")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--screen", type=int, default=0,
                    help="which display the subtitles are drawn on. 0 is the built-in one. "
                         "The phone can move them later")
    ap.add_argument("--no-overlay", action="store_true",
                    help="do not draw on this Mac. Only for a rehearsal in a browser")
    ap.add_argument("--mic", type=int, help="capture device for whisper. Read whisper.log")
    ap.add_argument("--bg", help="background image for the subtitle web page")
    ap.add_argument("--no-timer", action="store_true", help="do not start timer.py")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    # Piped to a file or a log, Python holds these prints back. The addresses are the first
    # thing anybody needs, so they must appear as they are printed.
    sys.stdout.reconfigure(line_buffering=True)
    if args.check:
        check(); sys.exit()

    # Claim the port BEFORE starting anything. A second copy of show.py used to start three
    # programs, fail to bind, and leave them running with no control page.
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    except OSError as e:
        sys.exit(f"  cannot listen on {PORT}: {e}\n"
                 f"  show.py may already be running. Stop it first.")

    subs["screen"] = args.screen
    displays[:] = list_displays()
    kids = start_children(args)
    # `pkill -f show.py` must stop the whole show, not orphan three programs. Turning the
    # signal into a normal exit is what lets the cleanup below run.
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
    threading.Thread(target=watch, daemon=True).start()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("1.1.1.1", 80))
    ip = s.getsockname()[0]
    s.close()
    here = displays[args.screen] if args.screen < len(displays) else f"display {args.screen}"
    print(f"\n  Phone (control)   ->  http://{ip}:{PORT}/")
    print(f"  Speaker (timer)   ->  http://{ip}:8000/")
    if args.no_overlay:
        print(f"  Subtitles         ->  a browser, at http://{ip}:8090/")
    else:
        print(f"  Subtitles         ->  drawn on this Mac, on {here}")
    print("\n  Ctrl-C stops everything it started.\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for k in kids:
            try:
                os.killpg(os.getpgid(k.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
