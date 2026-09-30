# Transcriby

Someone speaks English into the MacBook. Live Spanish subtitles appear across the top of the
screen, over whatever you are presenting. Everything runs on this Mac. No account, no internet,
no cloud service.

## One phone controls the whole talk

`show.py` is the way to run a real event. One command starts everything.

```sh
python3 show.py
```

**The subtitles are drawn by this Mac, on one of its own displays.** There is no page to open
for them, and there is no browser in the chain. `--screen 1` starts them on the second display;
the phone can move them later, while the speaker talks.

Two addresses are printed, and both are for *other* devices:

| Address | Who opens it |
|---|---|
| `http://<this Mac>:8100/` | The organizer's phone. Every control is here |
| `http://<this Mac>:8000/` | The speaker's iPad. The countdown, nothing else |

All three devices must be on the same Wi-Fi.

From that one page the organizer can:

- **Move the slides.** Back and forward, on this Mac, in Keynote, PowerPoint, a PDF or a
  full-screen Canva link. See the permission below.
- **Run the timer.** Start, pause, restart, a duration, one minute more or less, and the
  WRAP IT UP message on the speaker's screen.
- **Turn the subtitles on and off**, and change the colour, the size, the height, the number
  of lines and **which display they are on**, while the speaker talks.
- **See what the room reads.** The last four lines, each with its age in seconds. That
  number is how you judge whether the subtitles are late.

It starts only what is not already running, so you can start `timer.py` yourself first and
`show.py` will use it. `--no-timer` leaves the timer out. `--no-overlay` draws nothing on this
Mac and serves the subtitles as a web page instead, which suits a rehearsal.

### The slides need one permission

The arrow keys go to whichever app is in front. macOS blocks that until you allow it:
**System Settings > Privacy & Security > Accessibility**, then add the terminal you start
`show.py` from. The phone says so if the permission is missing; it does not fail silently.

### It has no password, and that matters more than it did

The timer alone was a countdown on a local network. This page moves your slides. Anybody on
the same Wi-Fi who opens the address gets the same buttons you have.

So put the Mac, the phone and the iPad on **your own phone hotspot** at a public venue. The
alternative is a password, and a password on a stage is a thing to mistype in the dark.

### What it does not do yet

It cannot change the whisper model during a talk. That model is chosen when `subtitles.py`
starts, and changing it means about two seconds with no subtitles. Start it with
`SUBS_ASR=...` if the room needs the bigger model.

## Two ways to show it

**Over your slides (use this one).** A borderless window floats above everything, including a
full-screen Canva link, Keynote or PowerPoint, on whichever display you choose. The mouse passes
straight through it, so you present exactly as you normally would.

```sh
.venv/bin/python overlay.py --screen 1
```

`--screen` picks the display. `--list` prints them:

```sh
.venv/bin/python overlay.py --list
  [0] 1512x982   Built-in Retina Display
  [1] 1920x1080  DW275
```

It starts `subtitles.py` itself if it is not already running.

| Option | What it does |
|---|---|
| `--screen N` | Which display. `0` is the built-in one |
| `--color white` | White text. Use it over dark slides; black is the default |
| `--size N` | Font size in points. Leave it out and it fits the screen |
| `--y 0.5` | Where the newest sentence sits, as a fraction from the top. `0.5` is the middle of the screen |
| `--history N` | How many sentences stay on screen. Lower it if the older text reaches your logos |

The text is black and centred, with nothing behind it.

**The newest sentence is always in the middle of the screen.** When the next one arrives it takes
that place, and the sentence before it moves up to make room. The eye returns to the same spot
every time, and the room can finish the previous sentence while the new one appears.

**The older sentences stream upwards.** They stack above the newest one and keep rising as more
arrive, until they run off the top of the screen. Nothing is dropped early: the block uses all the
room between the newest sentence and the top edge, and sheds the oldest line only when it runs out.

That stack reaches the top of the slide, so it can meet a header or a logo. `--history 3` keeps the
flow but holds it lower. `--history 2` is the newest sentence and the one before it, nothing more.

**Set `--y` against your own deck.** Every slide puts its title somewhere else. Put a real slide on
the screen, then move the number until the text sits in a clear band.

At `0.5` there is half a screen above the text, so a long pair of sentences always fits. Lower the
number to move the whole thing up the slide.

**As a web page.** Useful for a rehearsal, or when you want the background image in the same
window. It needs a browser you control on the presenting screen, so it does not suit a Canva link.

## Run it

```sh
python3 subtitles.py --bg background.png
```

Then open `http://127.0.0.1:8090/` and press `Ctrl-Cmd-F` for full screen.

Use `127.0.0.1`, not `localhost`. The server listens on IPv4 only, and a browser resolves
`localhost` to IPv6 first.

If the browser cannot open it while `curl http://127.0.0.1:8090/` works, the browser has lost its
macOS local-network permission. Check **System Settings > Privacy & Security > Local Network**.
That happened once on this Mac, to Chrome, and it is not a fault in this program.

`Ctrl-C` stops it.

## What it needs installed

`subtitles.py` needs nothing: Python standard library only.

`overlay.py` needs PyObjC, which is in `.venv`. It is already installed. To rebuild it:

```sh
python3 -m venv .venv.nosync && .venv.nosync/bin/pip install pyobjc-framework-Cocoa
```

It does not need Xcode. The Xcode licence on this Mac is not accepted, which blocks
`/usr/bin/python3` and `swiftc`, so neither was used.

### The countdown is a second repository

`show.py` starts `timer.py` from a sibling folder named `stage-timer`. Clone it next to this one:

```sh
git clone https://github.com/KenobiNakamoto/stage-timer.git
```

Put the two folders side by side, so that `stage-timer` is the sibling of this folder. Without it
everything else still works and the timer controls stay at `--:--`. `--no-timer` leaves the timer
out on purpose.

## The three parts

Each part is a program that was already on this Mac. This file only joins them together.

| Part | Program | What it does |
|---|---|---|
| Hearing | `whisper-stream` (whisper.cpp) | Waits for a pause, then prints the English it heard |
| Translating | `ollama` running `qwen2.5:3b` | Turns that English into Spanish |
| Showing | `http.server` (Python) | Puts the Spanish on a full-screen page |

Expect about two to three seconds between the end of a sentence and the Spanish on screen. The
delay is mostly the pause detection. A subtitle appears when a sentence finishes, not word by
word, because a half-heard sentence translates badly.

## The background

Give it any image:

```sh
python3 subtitles.py --bg deck.png
```

With no `--bg`, it uses a file named `background.*` in this folder. With no such file, the page
stays black and shows only the subtitles.

**From Canva:** export the slide as PNG and point `--bg` at it.

**From a PDF:** convert the first page, then use the PNG.

```sh
sips -s format png deck.pdf --out background.png
```

The image is centred and fits the screen without cropping. Black fills anything left over.

## What is proven, and what you must check yourself

Proven on 2026-09-16:

- Whisper transcribed a clean 12-second English passage word for word.
- The translator returned correct Spanish for every test sentence.
- One live microphone run put correct Spanish subtitles on the screen from speech in the room.

Proven on 2026-09-17, for `show.py`:

- One command started the subtitles, the overlay and the control page, and used the timer
  that was already running instead of starting a second one.
- Every button's command was tested against the running server: the timer, the three
  colours, the size, the height, the line count, on and off, and the slide key.
- The overlay took a new colour, size and height from the server while it ran, and it kept
  them when the server missed a poll.

Proven on 2026-09-18:

- One command draws the subtitles on this Mac with no page to open, and prints two addresses.
- The phone moved the subtitles between the built-in display and an external one, twice each
  way, and the fit size changed with the display (66 pt to 84 pt).
- Colour and height changed while it ran.

**Not proven for `show.py`: the page in a real phone browser.** Its JavaScript parses, and
every command behind it answers, but nobody has tapped the buttons on a phone yet. Do that
once before you rely on it.

**Not proven: the accuracy from a real speaker, in a real room, through your microphone.** Test
that before the talk, with the microphone you will use, from where the speaker will stand.

Do not test it by playing audio from the MacBook speakers into the MacBook microphone. That loop
fails for a reason that has nothing to do with this program: macOS cancels its own output, and
whisper reads what is left as nonsense. It wasted time here. Speak into the microphone instead.

## Pick the microphone

This is the one that wastes your time. Open the log after you start it:

```sh
cat whisper.log
```

It lists the capture devices it found. If the chosen one is a virtual device — `ZoomAudioDevice`
is the usual one — it records silence and the page never fills. Nothing reports an error. Choose
the real microphone by its number:

```sh
python3 subtitles.py --bg background.png --mic 2
```

## When it invents sentences

Whisper does not print nothing when it hears nothing. It prints a stock phrase from its training
data: "Okay.", "Thank you.", "Thanks for watching!". Those arrive during every pause. `FILLER` in
`subtitles.py` drops the common ones before they are translated.

If a phrase still repeats across a long silence, add it to `FILLER`, and try `-nf` in the
`whisper-stream` command. That flag turns off the temperature fallback, which is what makes
whisper loop.

A quieter room and a closer microphone fix more than any flag.

## Any browser, and full screen

The page is plain HTML, CSS and JavaScript. There is no framework and no build step. It works in
Safari, Chrome, Comet, Arc, Edge and Firefox. Comet is built on Chromium, so it behaves as Chrome
does.

For full screen, use the browser's own command. Nothing in the page is needed for it.

| Browser | Full screen |
|---|---|
| Safari | `Ctrl-Cmd-F` |
| Chrome, Comet, Arc, Edge | `Ctrl-Cmd-F`, or `F11` |
| Firefox | `Ctrl-Cmd-F` |

Open the page with `127.0.0.1`, not `localhost`. The server listens on IPv4 only.

## Check the text is readable

The subtitles are **black, on nothing**. The band behind them is fully transparent, so the text
sits directly on your artwork.

**That puts the readability on your background.** Keep the top third of the image light and plain.
Black text on a dark photograph cannot be read, and there is no shading behind it to help.

Look at the screen from the back of the room before you start. If the text is small, the room is
large: raise `font-size` in the `#subs` rule inside `subtitles.py`.

The newest line is solid black. The lines above it are lighter, so the eye goes to the new text.

The dot in the corner is green while it is listening and red when it has stopped.

## Models

| File | Size | Where it came from |
|---|---|---|
| `models/ggml-base.en.bin` | 142 MB | whisper.cpp models on Hugging Face |
| `qwen2.5:3b` | 1.9 GB | `ollama pull qwen2.5:3b` |

`base.en` is the small, fast English model. If the room is noisy or the speaker has a strong
accent, `ggml-small.en.bin` hears better and still keeps up:

```sh
curl -L -o models/ggml-small.en.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin
SUBS_ASR=models/ggml-small.en.bin python3 subtitles.py --bg background.png
```

`SUBS_LLM` changes the translation model the same way.

Both models stay on this Mac. No audio and no text leaves it.

## Check it still works

```sh
python3 subtitles.py --check
```

It tests the line cleaner, which is the part that decides whether noise reaches the screen.

## What it does not do

No slide control, no speaker names, no recording, no transcript file, no second language, no
word-by-word subtitles. One image, one language pair, one screen.

To change slides during a talk, export the deck as images and add arrow keys. That is a small
change, and nothing here needs it until a talk actually has slides.
