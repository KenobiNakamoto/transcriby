"""Subtitles drawn on top of every other window, on the screen you choose.

    .venv.nosync/bin/python overlay.py --screen 1

Use this when the slides are not in a browser you control — a Canva link, Keynote,
anything presenting full screen. The overlay floats above it, including above a full
screen app on its own Space, and the mouse passes straight through.

ponytail: this is a second window onto the same state, not a second program. It reads
`/lines` from subtitles.py exactly as the web page does. The web page still works.
"""
import argparse, json, subprocess, sys, threading, time, urllib.request

from AppKit import (NSApplication, NSApplicationActivationPolicyAccessory, NSBackingStoreBuffered,
                    NSColor, NSFont, NSMakeRect, NSScreen, NSTextField, NSTimer, NSWindow,
                    NSWindowCollectionBehaviorCanJoinAllSpaces,
                    NSWindowCollectionBehaviorFullScreenAuxiliary,
                    NSWindowCollectionBehaviorStationary, NSWindowStyleMaskBorderless,
                    NSTextAlignmentCenter)

SERVER = "http://127.0.0.1:8090"
# Above every ordinary window, and above a full screen app. 1000 is the screen-saver
# level; NSStatusWindowLevel (25) is not enough to clear a full screen presentation.
OVERLAY_LEVEL = 1000
MAX_HISTORY = 8    # the most the server is ever asked for

# What the flags set, until a server says otherwise.
latest = [{}]

COLORS = {"black": NSColor.blackColor, "white": NSColor.whiteColor,
          "yellow": NSColor.yellowColor}


def poll(server, flags):
    """Read the server in the background, so drawing never waits on the network."""
    while True:
        # Start from what is on the screen now, not from the flags: one missed poll must
        # not throw the talk back to the opening colour and size.
        cfg = dict(latest[0] or flags)
        try:
            with urllib.request.urlopen(f"{server}/lines", timeout=4) as r:
                d = json.load(r)
            cfg["text"] = "\n".join(d["lines"][-MAX_HISTORY:])
            # show.py serves the same shape plus the live look. subtitles.py serves only
            # the lines, so anything missing keeps the value the flags gave it.
            for k in ("visible", "color", "size", "y", "history", "screen"):
                if k in d:
                    cfg[k] = d[k]
        except Exception:
            cfg["text"] = ""
        latest[0] = cfg
        time.sleep(0.4)


def server_is_up(server):
    try:
        urllib.request.urlopen(f"{server}/lines", timeout=2).read()
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screen", type=int, default=0, help="which display, 0 is the built-in one")
    ap.add_argument("--list", action="store_true", help="print the displays and stop")
    ap.add_argument("--size", type=int, default=0, help="font size in points, 0 fits the screen")
    # Black was asked for, and it is right on a light slide. On a dark one nothing can
    # be read, and there is no shading behind the text to help. So the colour is a flag.
    ap.add_argument("--color", choices=["black", "white"], default="black",
                    help="text colour. Use white over dark slides")
    # Every deck puts its title somewhere else, so the height is a number you set,
    # not one this program can guess.
    # How far back the stream reaches. The room above the newest sentence is the hard
    # limit; this is how much of that room to use before the text meets the artwork.
    ap.add_argument("--history", type=int, default=MAX_HISTORY,
                    help="how many sentences to keep on screen. Lower it if the older "
                         "text reaches your logos")
    ap.add_argument("--server", default=SERVER,
                    help="where the lines come from. show.py serves the same feed plus "
                         "the settings its phone page changes")
    ap.add_argument("--y", type=float, default=0.5,
                    help="where the newest sentence sits, as a fraction from the top. "
                         "0.5 is the middle of the screen")
    args = ap.parse_args()

    screens = NSScreen.screens()
    if args.list:
        for i, s in enumerate(screens):
            f = s.frame()
            print(f"  [{i}] {int(f.size.width)}x{int(f.size.height)}  {s.localizedName()}")
        return
    if not 0 <= args.screen < len(screens):
        sys.exit(f"No screen {args.screen}. There are {len(screens)}. Use --list.")

    if not server_is_up(args.server):
        if args.server != SERVER:
            sys.exit(f"  nothing answers at {args.server}. Start show.py first.")
        print("  subtitles.py was not running. Starting it.")
        subprocess.Popen([sys.executable, "subtitles.py"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(30):
            if server_is_up(args.server):
                break
            time.sleep(1)
        else:
            sys.exit("  subtitles.py did not answer. Start it yourself and read its output.")

    # Every measurement below belongs to one display, and the phone can change which one
    # during a talk, so they are recomputed together rather than fixed at start.
    # Cocoa measures from the bottom of the screen, so a fraction from the top is 1 - y.
    # The newest sentence is centred on that line, and older text stacks above it.
    geo = {}

    def use_screen(i):
        scr = NSScreen.screens()[i]
        f = scr.frame()
        margin = int(f.size.width * 0.04)
        geo.update(i=i, name=scr.localizedName(), f=f, margin=margin,
                   width=f.size.width - margin * 2,
                   # The fit size is a fraction of the width, so it moves with the screen.
                   auto_pt=max(20, int(f.size.width / 34 * 1.5)),
                   top=f.origin.y + f.size.height - int(f.size.height * 0.02))

    use_screen(args.screen)
    pt = args.size or geo["auto_pt"]
    rect = NSMakeRect(geo["f"].origin.x + geo["margin"],
                      geo["f"].origin.y + geo["f"].size.height * (1 - args.y),
                      geo["width"], 10)

    app = NSApplication.sharedApplication()
    # Accessory: no icon in the Dock, and it never takes focus from the slides.
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        rect, NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False)
    win.setOpaque_(False)
    win.setBackgroundColor_(NSColor.clearColor())
    win.setLevel_(OVERLAY_LEVEL)
    win.setIgnoresMouseEvents_(True)          # clicks go to the slides underneath
    win.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces
                               | NSWindowCollectionBehaviorFullScreenAuxiliary
                               | NSWindowCollectionBehaviorStationary)
    win.setHasShadow_(False)

    label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, rect.size.width, rect.size.height))
    label.setBezeled_(False)
    label.setDrawsBackground_(False)          # nothing behind the text, as asked
    label.setEditable_(False)
    label.setSelectable_(False)
    label.setFont_(NSFont.boldSystemFontOfSize_(pt))
    label.setTextColor_(NSColor.blackColor() if args.color == "black" else NSColor.whiteColor())
    label.setAlignment_(NSTextAlignmentCenter)
    label.cell().setWraps_(True)
    label.cell().setScrollable_(False)
    win.contentView().addSubview_(label)
    win.orderFrontRegardless()

    flags = {"text": "", "visible": True, "color": args.color, "size": args.size,
             "y": args.y, "history": args.history, "screen": args.screen}
    latest[0] = dict(flags)
    threading.Thread(target=poll, args=(args.server, flags), daemon=True).start()

    shown = [None]
    applied = {}

    def height_of(s):
        label.setStringValue_(s)
        return label.cell().cellSizeForBounds_(NSMakeRect(0, 0, geo["width"], 10000)).height

    def draw(cfg):
        key = (cfg["text"], cfg["visible"], cfg["color"], cfg["size"], cfg["y"],
               cfg["history"], cfg["screen"])
        if key == shown[0]:
            return
        shown[0] = key
        # A display can be unplugged mid-talk, so the index is checked against the live list.
        if cfg["screen"] != geo["i"]:
            live = len(NSScreen.screens())
            if 0 <= cfg["screen"] < live:
                use_screen(cfg["screen"])
                applied.pop("pt", None)      # the fit size belonged to the old screen
            elif applied.get("nomove") != cfg["screen"]:
                applied["nomove"] = cfg["screen"]
                print(f"  cannot move to display {cfg['screen']}: this program sees "
                      f"{live}", file=sys.stderr, flush=True)
        # The look can change mid-talk, from the phone. Apply only what moved: setting the
        # font on every tick re-lays out the text and makes it flicker.
        want_pt = cfg["size"] or geo["auto_pt"]
        if want_pt != applied.get("pt"):
            label.setFont_(NSFont.boldSystemFontOfSize_(want_pt))
            applied["pt"] = want_pt
        if cfg["color"] != applied.get("color"):
            label.setTextColor_(COLORS.get(cfg["color"], NSColor.blackColor)())
            applied["color"] = cfg["color"]
        centre_y = geo["f"].origin.y + geo["f"].size.height * (1 - cfg["y"])
        look = (want_pt, cfg["color"], cfg["y"], cfg["history"], cfg["visible"], geo["i"])
        if look != applied.get("look"):
            applied["look"] = look
            # Printed only when it changes. During a talk this line is the proof that the
            # phone reached the screen, and afterwards it is the record of what was used.
            print(f"  look: [{geo['i']}] {geo['name']}, {want_pt} pt, {cfg['color']}, "
                  f"y={cfg['y']}, {cfg['history']} lines, "
                  f"{'on' if cfg['visible'] else 'off'}", flush=True)
        lines = [l for l in cfg["text"].split("\n") if l][-cfg["history"]:]
        if not lines or not cfg["visible"]:
            label.setStringValue_("")
            return
        # The newest sentence straddles centre_y. Everything else sits above it, so the
        # eye returns to the same place for every new sentence.
        base = centre_y - height_of(lines[-1]) / 2
        room = geo["top"] - base
        # A sentence wraps to one line or to two, so the pair does not always fit. Drop
        # the older sentence only when it truly does not, never the newest.
        while len(lines) > 1 and height_of("\n".join(lines)) > room:
            lines.pop(0)
        h = max(1.0, height_of("\n".join(lines)))
        win.setFrame_display_(
            NSMakeRect(geo["f"].origin.x + geo["margin"], base, geo["width"], h), True)
        label.setFrame_(NSMakeRect(0, 0, geo["width"], h))

    def tick(_timer):
        # Cocoa swallows a raise inside a timer: the subtitles would freeze with nothing
        # printed, which is the worst way to fail in front of a room. Say it instead.
        try:
            draw(latest[0])
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            if msg != applied.get("err"):
                applied["err"] = msg
                print(f"  overlay error: {msg}", file=sys.stderr, flush=True)

    NSTimer.scheduledTimerWithTimeInterval_repeats_block_(0.3, True, tick)
    print(f"  overlay on screen [{geo['i']}] {geo['name']}, {pt} pt", flush=True)
    print("  Ctrl-C here stops it.", flush=True)
    app.run()


if __name__ == "__main__":
    main()
