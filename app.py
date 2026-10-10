"""WeatherPanel - e-paper style weather station.

Usage:
    python app.py --city "Berlin"                 # live window, refreshes every 15 min
    python app.py --lat -23.55 --lon -46.63 --name "Sao Paulo"
    python app.py --city Lisbon --once panel.png  # render one frame to a file and exit
    python app.py --demo                          # offline synthetic data

Keys in the window: R refresh now, S save PNG, F fullscreen, Q/Esc quit.
"""
from __future__ import annotations

import argparse
import datetime as dt
import queue
import sys
import threading
import tkinter as tk
import traceback

from PIL import Image, ImageOps, ImageTk

import render
import weather

PAPER_RGB = (228, 228, 221)
INK_RGB = (36, 36, 40)
BEZEL = "#e9e7e1"
BEZEL_EDGE = "#c9c6bd"


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="E-paper style weather panel (data: Open-Meteo)")
    p.add_argument("--city", default="Berlin", help="city name to geocode (default: Berlin)")
    p.add_argument("--lat", type=float, help="latitude (use with --lon instead of --city)")
    p.add_argument("--lon", type=float, help="longitude")
    p.add_argument("--name", help="display name when using --lat/--lon")
    p.add_argument("--units", choices=["metric", "imperial"], default="metric")
    p.add_argument("--refresh", type=float, default=15, help="refresh interval in minutes (default 15)")
    p.add_argument("--once", metavar="PNG", help="render a single frame to this file and exit")
    p.add_argument("--bw", action="store_true", help="with --once: save as pure 1-bit image for e-paper hardware")
    p.add_argument("--demo", action="store_true", help="use synthetic data (no network)")
    p.add_argument("--no-flash", action="store_true", help="disable the e-paper refresh flash animation")
    return p.parse_args(argv)


class Source:
    """Resolves the location once, then fetches and renders frames."""

    def __init__(self, args):
        self.args = args
        self.loc = None
        self.last = None

    def location(self):
        if self.loc is None:
            a = self.args
            if a.lat is not None and a.lon is not None:
                self.loc = weather.Location(a.name or f"{a.lat:.2f}, {a.lon:.2f}", a.lat, a.lon)
            elif a.demo:
                self.loc = weather.Location(a.city if a.city != "Berlin" else "Demo City", 52.52, 13.41, "DE")
            else:
                self.loc = weather.geocode(a.city)
        return self.loc

    def frame(self) -> Image.Image:
        try:
            loc = self.location()
            wx = weather.demo(loc, self.args.units) if self.args.demo else weather.fetch(loc, self.args.units)
            if not self.args.demo:
                try:
                    wx.radar = weather.fetch_radar(loc.lat, loc.lon)
                except Exception as e:  # radar is a bonus; keep the forecast if it fails
                    print(f"radar: {e}", file=sys.stderr)
            self.last = wx
            return render.render(wx)
        except Exception as e:  # network down, bad city, API error...
            traceback.print_exc()
            if self.last is not None:
                return render.render(self.last, status=f"! update failed {dt.datetime.now():%H:%M}")
            return render.render_message("No weather data", f"{type(e).__name__}: {e}\nRetrying automatically.")


def tint(img: Image.Image) -> Image.Image:
    """Map pure ink/paper to the grey-on-grey look of a real e-paper panel."""
    l = img.convert("L")
    bands = [l.point([i + (p - i) * v // 255 for v in range(256)]) for i, p in zip(INK_RGB, PAPER_RGB)]
    return Image.merge("RGB", bands)


class Viewer:
    def __init__(self, source: Source, refresh_min: float, flash: bool):
        self.source = source
        self.refresh_s = max(1.0, refresh_min * 60)
        self.flash = flash
        self.frames: queue.Queue[Image.Image] = queue.Queue()
        self.wake = threading.Event()
        self.current = None

        self.root = tk.Tk()
        self.root.title("WeatherPanel")
        self.root.configure(bg=BEZEL)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.scale = min(1.0, (sw - 120) / render.W, (sh - 160) / render.H)
        size = (int(render.W * self.scale), int(render.H * self.scale))

        frame = tk.Frame(self.root, bg=BEZEL, highlightbackground=BEZEL_EDGE, highlightthickness=2)
        frame.pack(padx=18, pady=18, expand=True)
        self.label = tk.Label(frame, bg=BEZEL, bd=0, width=size[0], height=size[1])
        self.label.pack(padx=26, pady=26)
        self._show(render.render_message("Loading...", "Fetching weather from Open-Meteo"))

        for key in ("r", "R"):
            self.root.bind(key, lambda e: self.wake.set())
        for key in ("s", "S"):
            self.root.bind(key, lambda e: self.save())
        for key in ("f", "F", "<F11>"):
            self.root.bind(key, lambda e: self.root.attributes("-fullscreen", not self.root.attributes("-fullscreen")))
        for key in ("q", "Q", "<Escape>"):
            self.root.bind(key, lambda e: self.root.destroy())

        threading.Thread(target=self._worker, daemon=True).start()
        self.root.after(200, self._poll)

    def _worker(self):
        while True:
            self.frames.put(self.source.frame())
            self.wake.wait(self.refresh_s)
            self.wake.clear()

    def _poll(self):
        try:
            img = self.frames.get_nowait()
        except queue.Empty:
            pass
        else:
            if self.flash and self.current is not None:
                self._flash(img)
            else:
                self._show(img)
        self.root.after(200, self._poll)

    def _flash(self, img):
        """Imitate a full e-paper refresh: inverted, black, white, then the new image."""
        black = Image.new("L", img.size, 0)
        white = Image.new("L", img.size, 255)
        steps = [ImageOps.invert(self.current), black, white, img]
        for k, frame in enumerate(steps):
            self.root.after(110 * k, lambda f=frame: self._show(f, keep=f is img))

    def _show(self, img, keep=True):
        if keep:
            self.current = img
        shown = tint(img)
        if self.scale < 1:
            shown = shown.resize((int(img.width * self.scale), int(img.height * self.scale)), Image.LANCZOS)
        self.photo = ImageTk.PhotoImage(shown)
        self.label.configure(image=self.photo, width=shown.width, height=shown.height)

    def save(self):
        if self.current is not None:
            name = f"weatherpanel_{dt.datetime.now():%Y%m%d_%H%M%S}.png"
            self.current.save(name)
            print(f"saved {name}")

    def run(self):
        self.root.mainloop()


def main(argv=None):
    args = parse_args(argv)
    source = Source(args)
    if args.once:
        img = source.frame()
        (render.to_1bit(img) if args.bw else img).save(args.once)
        print(f"saved {args.once}")
        return 0
    Viewer(source, args.refresh, flash=not args.no_flash).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
