"""
Spotify Replacement – Dear PyGui version

Single window. Rounded corners, native drag + snap + resize.

Rounding:
  - SetWindowRgn on the DPG viewport itself (works on Win10 + Win11)
  - DWM rounding also requested on Win11 for anti-aliased edges
Border:
  - DWM's rectangular 1px border is disabled (DWMWA_COLOR_NONE)
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import datetime
import json
import os
import subprocess
import sys
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import dearpygui.dearpygui as dpg
import requests
import yaml
from PIL import Image, ImageDraw, ImageChops

warnings.filterwarnings("ignore", category=DeprecationWarning)

LOG = os.path.join(os.path.expanduser("~"), ".spotify_replacement", "app.log")
os.makedirs(os.path.dirname(LOG), exist_ok=True)
sys.stderr = open(LOG, "a", buffering=1, encoding="utf-8")
sys.stdout = sys.stderr


APP_DIR = os.path.join(os.path.expanduser("~"), ".spotify_replacement")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
TOKEN_CACHE_PATH = os.path.join(APP_DIR, ".spotify_token_cache")
COVER_CACHE_DIR = os.path.join(APP_DIR, "covers")
GO_LIBRESPOT_API = "http://127.0.0.1:3678"

os.makedirs(APP_DIR, exist_ok=True)
os.makedirs(COVER_CACHE_DIR, exist_ok=True)

ACCENT = (0, 120, 212, 255)
ACCENT_LIGHT = (64, 156, 255, 255)
BG_DARK = (10, 13, 20, 255)
BG_PANEL = (18, 22, 32, 255)
BG_CARD = (24, 29, 42, 255)
TEXT_DIM = (150, 158, 172, 255)
TEXT_BRIGHT = (235, 238, 245, 255)

WINDOW_TITLE = "Pyify"
CORNER_RADIUS = 15


FONT_CANDIDATES = [
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]
FONT_SIZE = 17

if sys.platform == "win32":
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    user32.FindWindowW.restype = ctypes.c_void_p

    user32.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.GetParent.argtypes = [ctypes.c_void_p]
    user32.GetParent.restype = ctypes.c_void_p
    user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    user32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]

    kernel32.GetCurrentProcessId.argtypes = []
    kernel32.GetCurrentProcessId.restype = ctypes.c_ulong

    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.GetClientRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
    user32.SetWindowLongW.restype = ctypes.c_long

    if ctypes.sizeof(ctypes.c_void_p) == 8:
        user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.GetWindowLongPtrW.restype = ctypes.c_void_p
        user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    else:
        user32.GetWindowLongPtrW = user32.GetWindowLongW
        user32.SetWindowLongPtrW = user32.SetWindowLongW

    user32.CallWindowProcW.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p
    ]
    user32.CallWindowProcW.restype = ctypes.c_long

    user32.DefWindowProcW.argtypes = [
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p
    ]
    user32.DefWindowProcW.restype = ctypes.c_long

    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]

    user32.SetWindowPos.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_uint,
    ]

    user32.SetWindowRgn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
    user32.SetWindowRgn.restype = ctypes.c_int

    gdi32.CreateRoundRectRgn.argtypes = [
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int
    ]
    gdi32.CreateRoundRectRgn.restype = ctypes.c_void_p

    dwmapi.DwmSetWindowAttribute.argtypes = [
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint
    ]
    dwmapi.DwmGetWindowAttribute.argtypes = [
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint
    ]

    GWL_STYLE = -16
    GWLP_WNDPROC = -4

    WS_THICKFRAME = 0x00040000
    WS_SYSMENU = 0x00080000
    WS_MINIMIZEBOX = 0x00020000
    WS_MAXIMIZEBOX = 0x00010000

    SWP_FRAMECHANGED = 0x0020
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010

    SW_MINIMIZE = 6

    WM_NCHITTEST = 0x0084
    WM_NCCALCSIZE = 0x0083
    WM_SIZE = 0x0005

    HTCAPTION = 2
    HTCLIENT = 1
    HTLEFT = 10
    HTRIGHT = 11
    HTTOP = 12
    HTTOPLEFT = 13
    HTTOPRIGHT = 14
    HTBOTTOM = 15
    HTBOTTOMLEFT = 16
    HTBOTTOMRIGHT = 17

    DWMWA_WINDOW_CORNER_PREFERENCE = 33
    DWMWCP_DEFAULT = 0
    DWMWCP_DONOTROUND = 1
    DWMWCP_ROUND = 2
    DWMWCP_ROUNDSMALL = 3

    DWMWA_BORDER_COLOR = 34
    DWMWA_COLOR_NONE = 0xFFFFFFFE

    DWMWA_USE_IMMERSIVE_DARK_MODE = 20

    WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_long,
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p
    )
else:
    user32 = None
    kernel32 = None
    dwmapi = None
    gdi32 = None



def is_windows_11():
    if sys.platform != "win32":
        return False
    try:
        return sys.getwindowsversion().build >= 22000
    except Exception:
        return False



class ViewportCustomizer:
    def __init__(self, title: str, radius: int = CORNER_RADIUS):
        self.hwnd = None
        self.radius = radius
        self._orig_proc = None
        self._wndproc_ref = None

        if sys.platform != "win32":
            return

        self.hwnd = self._find_hwnd(title)
        if not self.hwnd:
            print("[ViewportCustomizer] could not find DPG HWND")
            return
        print(f"[ViewportCustomizer] found DPG HWND = {self.hwnd}")

        style = user32.GetWindowLongW(self.hwnd, GWL_STYLE)
        style |= WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
        style &= ~WS_THICKFRAME   
        user32.SetWindowLongW(self.hwnd, GWL_STYLE, style)
        user32.SetWindowPos(
            self.hwnd, None, 0, 0, 0, 0,
            SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
        )

        try:
            dark = ctypes.c_int(1)
            dwmapi.DwmSetWindowAttribute(
                self.hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(dark), ctypes.sizeof(dark),
            )
            dwmapi.DwmSetWindowAttribute(
                self.hwnd, 19, ctypes.byref(dark), ctypes.sizeof(dark),
            )
        except Exception as e:
            print("[ViewportCustomizer] dark mode:", e)

        if is_windows_11():
            try:
                pref = ctypes.c_int(DWMWCP_ROUND)
                dwmapi.DwmSetWindowAttribute(
                    self.hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                    ctypes.byref(pref), ctypes.sizeof(pref),
                )
                print("[ViewportCustomizer] DWM rounding requested")
            except Exception as e:
                print("[ViewportCustomizer] DWM rounding error:", e)

        try:
            color = ctypes.c_uint(DWMWA_COLOR_NONE)
            dwmapi.DwmSetWindowAttribute(
                self.hwnd, DWMWA_BORDER_COLOR,
                ctypes.byref(color), ctypes.sizeof(color),
            )
            print("[ViewportCustomizer] DWM border disabled")
        except Exception as e:
            print("[ViewportCustomizer] border disable:", e)


        self._apply_region()


        self._wndproc_ref = WNDPROC(self._wnd_proc)
        self._orig_proc = user32.GetWindowLongPtrW(self.hwnd, GWLP_WNDPROC)
        user32.SetWindowLongPtrW(
            self.hwnd, GWLP_WNDPROC,
            ctypes.cast(self._wndproc_ref, ctypes.c_void_p),
        )
        print("[ViewportCustomizer] subclassed WndProc")

    def _apply_region(self):
        if not self.hwnd:
            return
        try:
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w <= 0 or h <= 0:
                return
            rgn = gdi32.CreateRoundRectRgn(
                0, 0, w + 1, h + 1,
                self.radius * 2, self.radius * 2,
            )
            if rgn:
                user32.SetWindowRgn(self.hwnd, rgn, True)
        except Exception as e:
            print("[ViewportCustomizer] apply_region:", e)

    def _find_hwnd(self, title: str):
        our_pid = kernel32.GetCurrentProcessId()
        found = []

        EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def callback(hwnd, lparam):
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != our_pid:
                return True
            if user32.GetParent(hwnd):
                return True
            tb = ctypes.create_unicode_buffer(256)
            cb = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, tb, 256)
            user32.GetClassNameW(hwnd, cb, 256)
            print(f"[enum] hwnd={hwnd} class={cb.value!r} title={tb.value!r}")
            found.append((hwnd, tb.value, cb.value))
            return True

        user32.EnumWindows(EnumProc(callback), 0)
        for hwnd, t, c in found:
            if t == title:
                return hwnd
        for hwnd, t, c in found:
            if "dear" in c.lower() or "dpg" in c.lower():
                return hwnd
        return found[0][0] if found else None

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_NCCALCSIZE and wparam:
            return 0

        if msg == WM_NCHITTEST:
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))

            rel_x = x - rect.left
            rel_y = y - rect.top
            w = rect.right - rect.left
            h = rect.bottom - rect.top

            BORDER = 8
            left = rel_x < BORDER
            right = rel_x > w - BORDER
            top = rel_y < BORDER
            bottom = rel_y > h - BORDER

            if top and left: return HTTOPLEFT
            if top and right: return HTTOPRIGHT
            if bottom and left: return HTBOTTOMLEFT
            if bottom and right: return HTBOTTOMRIGHT
            if left: return HTLEFT
            if right: return HTRIGHT
            if top: return HTTOP
            if bottom: return HTBOTTOM

            if 0 <= rel_y < 36 and rel_x < w - 120:
                return HTCAPTION

            return HTCLIENT

        if msg == WM_SIZE:
            self._apply_region()

        return user32.CallWindowProcW(
            self._orig_proc, hwnd, msg, wparam, lparam
        )

    def minimize(self):
        if sys.platform == "win32" and self.hwnd:
            user32.ShowWindow(self.hwnd, SW_MINIMIZE)


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def _fmt_ms(ms) -> str:
    try:
        ms = max(0, int(ms or 0))
    except (TypeError, ValueError):
        ms = 0
    total = ms // 1000
    return f"{total // 60}:{total % 60:02d}"


def ensure_librespot_config(config_dir: str, device_name: str = "PythonSpotifyReplacement"):
    path = os.path.join(config_dir, "config.yml")
    if os.path.exists(path):
        return
    cfg = {
        "device_name": device_name,
        "credentials": {"type": "interactive"},
        "zeroconf_enabled": True,
        "server": {"enabled": True, "address": "127.0.0.1", "port": 3678},
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f)


def make_spotify(client_id: str, client_secret: str):
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth

    return spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri="http://127.0.0.1:8888/callback",
            scope=(
                "user-read-playback-state user-modify-playback-state "
                "user-read-currently-playing playlist-read-private "
                "playlist-read-collaborative user-library-read "
                "user-top-read user-read-recently-played"
            ),
            cache_path=TOKEN_CACHE_PATH,
            open_browser=True,
        )
    )


_texture_cache: dict = {}


def cover_path(url: str) -> str:
    name = (url or "").split("/")[-1].split("?")[0] or "cover"
    if not any(name.lower().endswith(e) for e in (".jpg", ".jpeg", ".png", ".webp")):
        name += ".jpg"
    return os.path.join(COVER_CACHE_DIR, name)


def load_texture(url: Optional[str], size: int = 64) -> Optional[int]:
    if not url:
        return None
    key = (url, size)
    if key in _texture_cache:
        return _texture_cache[key]

    path = cover_path(url)
    try:
        if not os.path.exists(path):
            r = requests.get(url, timeout=8)
            r.raise_for_status()
            with open(path, "wb") as f:
                f.write(r.content)

        img = Image.open(path).convert("RGBA")
        img = img.resize((size, size), Image.LANCZOS)

        radius = min(28, max(6, int(size * 0.18)))
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, size - 1, size - 1], radius=radius, fill=255
        )
        alpha = ImageChops.multiply(img.split()[-1], mask)
        img.putalpha(alpha)

        data = list(img.getdata())
        flat = []
        for r_, g_, b_, a_ in data:
            flat.extend([r_ / 255.0, g_ / 255.0, b_ / 255.0, a_ / 255.0])

        with dpg.texture_registry():
            tag = dpg.add_static_texture(size, size, flat)
        _texture_cache[key] = tag
        return tag
    except Exception as e:
        print("cover load error:", e)
        return None


def build_track_from_spotify(t: dict) -> dict:
    if not t:
        return {}
    imgs = (t.get("album") or {}).get("images") or []
    uri = t.get("uri")
    if not uri and t.get("id"):
        uri = f"spotify:track:{t['id']}"
    if not uri:
        ext = (t.get("external_urls") or {}).get("spotify")
        if ext:
            tid = ext.rstrip("/").split("/")[-1].split("?")[0]
            if tid:
                uri = f"spotify:track:{tid}"
    return {
        "uri": uri,
        "name": t.get("name") or "Unknown",
        "artists": ", ".join(a["name"] for a in t.get("artists") or []),
        "album": (t.get("album") or {}).get("name", ""),
        "cover": (imgs[1]["url"] if len(imgs) > 1 else (imgs[0]["url"] if imgs else None)),
        "cover_small": imgs[-1]["url"] if imgs else None,
        "duration_ms": t.get("duration_ms") or 0,
    }


class SpotifyApp:
    def __init__(self):
        self.cfg = load_config()
        self.sp = None
        self.librespot_proc = None
        self._device_id = None
        self._pool = ThreadPoolExecutor(max_workers=6)
        self._poller_stop = False
        self._seeking = False
        self._current_view = "home"
        self._playlists: list = []
        self._top_tracks: list = []
        self._recent_tracks: list = []
        self._status_data: dict = {}
        self._player_cover_tag = None
        self._right_cover_tag = None
        self._row_seq = 0
        self._customizer: Optional[ViewportCustomizer] = None

        dpg.create_context()
        self._setup_font()
        self._setup_theme()
        self._build_ui()

        if self._config_ok():
            self._show_status("Signing in to Spotify...")
            threading.Thread(target=self._boot, daemon=True).start()
        else:
            self._show_setup()

        clear = (BG_DARK[0] / 255.0, BG_DARK[1] / 255.0, BG_DARK[2] / 255.0, 1.0)

        dpg.create_viewport(
            title=WINDOW_TITLE,
            width=1280,
            height=800,
            decorated=False,
            resizable=True,
            vsync=True,
            clear_color=clear,
        )
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("main_window", True)

        if sys.platform == "win32":
            time.sleep(0.5)
            self._customizer = ViewportCustomizer(WINDOW_TITLE)

        while dpg.is_dearpygui_running():
            self._tick()
            dpg.render_dearpygui_frame()

        self.cleanup()
        dpg.destroy_context()

    def _config_ok(self) -> bool:
        return all(self.cfg.get(k) for k in ("client_id", "client_secret", "librespot_path"))

    def _setup_font(self):
        """Load a real system font with Latin-1 + general-punctuation
        coverage so accented artist/track names and curly quotes/dashes
        never fall back to '?' glyphs. Silently skips if none is found -
        DPG's built-in font still covers plain ASCII fine."""
        font_path = next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)
        if not font_path:
            print("[font] no system font found, using DPG default (ASCII only)")
            return
        try:
            with dpg.font_registry():
                with dpg.font(font_path, FONT_SIZE) as default_font:
                    dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                    dpg.add_font_range(0x0100, 0x017F)  
                    dpg.add_font_range(0x2000, 0x206F)  
            dpg.bind_font(default_font)
            print("[font] loaded", font_path)
        except Exception as e:
            print("[font] failed to load", font_path, e)

    def _setup_theme(self):
        with dpg.theme() as global_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, BG_DARK)
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, BG_PANEL)
                dpg.add_theme_color(dpg.mvThemeCol_Button, (34, 40, 54, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (44, 52, 70, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, ACCENT)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (26, 31, 44, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Header, (32, 38, 52, 255))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (42, 50, 68, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Text, TEXT_BRIGHT)
                dpg.add_theme_color(dpg.mvThemeCol_CheckMark, ACCENT)
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, ACCENT)
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, ACCENT_LIGHT)
                dpg.add_theme_color(dpg.mvThemeCol_Separator, (40, 46, 62, 255))
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 8)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 10)
                dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 4)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 8, 8)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 6)
        dpg.bind_theme(global_theme)


        with dpg.theme() as tight_theme:
            with dpg.theme_component(dpg.mvGroup):
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0)
        self._tight_theme = tight_theme

    def _build_ui(self):
        with dpg.window(
            tag="main_window",
            label=WINDOW_TITLE,
            no_title_bar=True,
            no_move=True,
            no_resize=True,
            no_scrollbar=True,
            no_collapse=True,
        ):
            with dpg.group(horizontal=True, tag="title_strip"):
                dpg.add_text(f"  {WINDOW_TITLE}", color=ACCENT)
                dpg.add_spacer(width=1130)
                dpg.add_button(
                    label="-", width=32, height=24,
                    callback=lambda: self._minimize(),
                )
                dpg.add_button(
                    label="X", width=32, height=24,
                    callback=lambda: dpg.stop_dearpygui(),
                )
            dpg.add_separator()

            with dpg.group(horizontal=True):
                dpg.add_input_text(
                    tag="search_input",
                    hint="Search tracks...",
                    width=320,
                    callback=self._on_search_enter,
                    on_enter=True,
                )
                dpg.add_button(
                    label="Search",
                    callback=lambda: self._do_search(dpg.get_value("search_input")),
                )

            dpg.add_separator()

            with dpg.group(horizontal=True):
                with dpg.child_window(width=92, height=-140, border=False):
                    dpg.add_button(label="Home", width=-1, callback=lambda: self._show_home())
                    dpg.add_button(label="Library", width=-1, callback=lambda: self._show_library())
                    dpg.add_button(label="Liked", width=-1, callback=lambda: self._show_liked())
                    dpg.add_button(label="Recent", width=-1, callback=lambda: self._show_recent())
                    dpg.add_spacer(height=16)
                    dpg.add_separator()
                    dpg.add_spacer(height=8)
                    dpg.add_text("Status", color=TEXT_DIM)
                    dpg.add_text("Ready", tag="status_label", color=TEXT_DIM, wrap=80)

                with dpg.child_window(tag="content_area", width=-280, height=-140, border=False):
                    dpg.add_text("Loading...", tag="content_placeholder")


                with dpg.child_window(tag="right_panel", width=270, height=-140, border=False):
                    dpg.add_text("NOW PLAYING", color=TEXT_DIM)
                    dpg.add_spacer(height=10)
                    with dpg.group(tag="right_now_playing_cover_group"):
                        dpg.add_dummy(width=230, height=230)
                    dpg.add_spacer(height=14)
                    dpg.add_text("Nothing playing", tag="right_np_title", color=TEXT_BRIGHT, wrap=250)
                    dpg.add_spacer(height=2)
                    dpg.add_text("", tag="right_np_artist", color=TEXT_DIM, wrap=250)

            dpg.add_separator()

            with dpg.child_window(tag="player_bar_container", height=120, border=False):
                dpg.add_spacer(height=6)
                with dpg.group(horizontal=True, tag="player_bar_top"):
                    with dpg.group(tag="player_cover_group"):
                        dpg.add_dummy(width=68, height=68)
                    with dpg.group():
                        dpg.add_spacer(height=6)
                        dpg.add_text("Nothing playing", tag="player_title", color=TEXT_BRIGHT)
                        dpg.add_text("", tag="player_artist", color=TEXT_DIM)
                    dpg.add_spacer(width=40)
                    dpg.add_button(label="Prev", callback=lambda: self._prev(), width=54, height=36)
                    dpg.add_button(label="Play", tag="play_btn", callback=lambda: self._play_pause(), width=64, height=36)
                    dpg.add_button(label="Next", callback=lambda: self._next(), width=54, height=36)
                    dpg.add_spacer(width=40)
                    dpg.add_text("Volume", color=TEXT_DIM)
                    dpg.add_slider_int(
                        tag="vol_slider",
                        default_value=60,
                        min_value=0,
                        max_value=100,
                        width=120,
                        callback=self._on_volume,
                    )
                dpg.add_spacer(height=10)
                with dpg.group(horizontal=True, tag="player_bar_seek"):
                    dpg.add_spacer(width=84)
                    dpg.add_text("0:00", tag="pos_text", color=TEXT_DIM)
                    dpg.add_slider_float(
                        tag="seek_slider",
                        default_value=0,
                        min_value=0,
                        max_value=1000,
                        width=760,
                        callback=self._on_seek,
                        format="",
                    )
                    dpg.add_text("0:00", tag="dur_text", color=TEXT_DIM)

        with dpg.window(tag="setup_window", label="Setup", show=False, modal=True,
                        width=480, height=320, pos=(400, 200)):
            dpg.add_text("SPOTIFY REPLACEMENT", color=ACCENT)
            dpg.add_text("Enter your Spotify credentials and go-librespot path.")
            dpg.add_spacer(height=10)
            dpg.add_input_text(tag="setup_client_id", label="Client ID", width=400)
            dpg.add_input_text(tag="setup_client_secret", label="Client Secret", password=True, width=400)
            dpg.add_input_text(tag="setup_librespot", label="go-librespot path", width=400)
            dpg.add_spacer(height=10)
            dpg.add_button(label="Continue", callback=self._setup_submit, width=120)

    def _minimize(self):
        if self._customizer:
            self._customizer.minimize()

    def _show_setup(self):
        dpg.set_value("setup_client_id", self.cfg.get("client_id", ""))
        dpg.set_value("setup_client_secret", self.cfg.get("client_secret", ""))
        dpg.set_value("setup_librespot", self.cfg.get("librespot_path", ""))
        dpg.configure_item("setup_window", show=True)

    def _setup_submit(self):
        cid = dpg.get_value("setup_client_id").strip()
        sec = dpg.get_value("setup_client_secret").strip()
        path = dpg.get_value("setup_librespot").strip()
        if not cid or not sec or not path:
            self._show_status("Fill in all fields")
            return
        if not os.path.exists(path):
            self._show_status("Path does not exist")
            return
        self.cfg.update({"client_id": cid, "client_secret": sec, "librespot_path": path})
        save_config(self.cfg)
        dpg.configure_item("setup_window", show=False)
        self._show_status("Signing in to Spotify...")
        threading.Thread(target=self._boot, daemon=True).start()

    def _show_status(self, text: str):
        try:
            dpg.set_value("status_label", text)
            print("[status]", text)
        except Exception:
            pass

    def _boot(self):
        try:
            self.sp = make_spotify(self.cfg["client_id"], self.cfg["client_secret"])
            self.sp.current_user()
        except Exception as e:
            self._show_status(f"Login failed: {e}")
            return

        self._show_status("Starting go-librespot...")
        self._start_librespot()
        self._show_status("Waiting for daemon...")
        if not self._wait_daemon(90):
            self._show_status("Daemon not ready - continuing")

        self._start_poller()
        self._pool.submit(self._transfer_playback)
        self._pool.submit(self._load_all_data)
        self._show_status("Ready")
        time.sleep(0.5)
        self._show_home()

    def _start_librespot(self):
        config_dir = os.path.dirname(os.path.abspath(self.cfg["librespot_path"]))
        ensure_librespot_config(config_dir)

        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        self.librespot_proc = subprocess.Popen(
            [self.cfg["librespot_path"], "--config_dir", config_dir],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            startupinfo=startupinfo,
        )
        threading.Thread(target=self._stream_log, daemon=True).start()
        threading.Thread(target=self._wait_daemon, daemon=True).start()

    def _stream_log(self):
        try:
            for line in self.librespot_proc.stdout:
                print("[librespot]", line, end="")
                if "authorize?" in line or "spotify.com/pair" in line.lower():
                    self._show_status("Login required - check terminal")
        except Exception:
            pass

    def _wait_daemon(self, timeout: int = 90) -> bool:
        for _ in range(timeout):
            try:
                r = requests.get(f"{GO_LIBRESPOT_API}/", timeout=1)
                if r.ok and r.json().get("playback_ready"):
                    return True
            except requests.RequestException:
                pass
            time.sleep(1)
        return False

    def _transfer_playback(self):
        try:
            r = requests.get(f"{GO_LIBRESPOT_API}/status", timeout=3)
            if r.status_code == 200:
                self._device_id = r.json().get("device_id")
            if self._device_id and self.sp:
                self.sp.transfer_playback(device_id=self._device_id, force_play=False)
                print("[transfer] transferred to", self._device_id)
        except Exception as e:
            print("transfer:", e)

    def _start_poller(self):
        def loop():
            while not self._poller_stop:
                try:
                    r = requests.get(f"{GO_LIBRESPOT_API}/status", timeout=2)
                    if r.status_code == 200:
                        self._status_data = r.json()
                except requests.RequestException:
                    pass
                time.sleep(1)

        threading.Thread(target=loop, daemon=True).start()

    def _tick(self):
        data = self._status_data
        if not data:
            return
        track = data.get("track") or {}
        paused = data.get("paused", True)

        try:
            dpg.configure_item("play_btn", label="Play" if paused else "Pause")
            title = track.get("name") or "Nothing playing"
            artists = ", ".join(track.get("artist_names") or [])

            dpg.set_value("player_title", title)
            dpg.set_value("player_artist", artists)
            dpg.set_value("right_np_title", title)
            dpg.set_value("right_np_artist", artists)

            pos = int(data.get("position") or 0)
            dur = int(track.get("duration") or 0)
            if not self._seeking and dur > 0:
                dpg.set_value("seek_slider", pos / dur * 1000)
            dpg.set_value("pos_text", _fmt_ms(pos))
            dpg.set_value("dur_text", _fmt_ms(dur))

            cover_url = (
                track.get("album_cover_url")
                or track.get("cover_url")
                or track.get("image_url")
            )
            if cover_url:
                tex_small = load_texture(cover_url, size=64)
                if tex_small is not None and tex_small != self._player_cover_tag:
                    self._player_cover_tag = tex_small
                    if dpg.does_item_exist("player_cover_group"):
                        dpg.delete_item("player_cover_group", children_only=True)
                        dpg.add_image(tex_small, parent="player_cover_group", width=64, height=64)

                tex_large = load_texture(cover_url, size=230)
                if tex_large is not None and tex_large != self._right_cover_tag:
                    self._right_cover_tag = tex_large
                    if dpg.does_item_exist("right_now_playing_cover_group"):
                        dpg.delete_item("right_now_playing_cover_group", children_only=True)
                        dpg.add_image(tex_large, parent="right_now_playing_cover_group", width=230, height=230)
        except Exception:
            pass

    def _load_all_data(self):
        if not self.sp:
            return
        try:
            top = self.sp.current_user_top_tracks(limit=30, time_range="short_term")
            self._top_tracks = [
                build_track_from_spotify(t) for t in (top.get("items") or []) if t
            ]
        except Exception as e:
            print("[load] top tracks error:", e)
            self._top_tracks = []

        try:
            rec = self.sp.current_user_recently_played(limit=40)
            seen, recent = set(), []
            for it in rec.get("items") or []:
                t = it.get("track") or {}
                if not t:
                    continue
                tr = build_track_from_spotify(t)
                u = tr.get("uri")
                if u and u not in seen:
                    seen.add(u)
                    recent.append(tr)
            self._recent_tracks = recent
        except Exception as e:
            print("[load] recent error:", e)
            self._recent_tracks = []

        try:
            playlists, offset = [], 0
            while True:
                page = self.sp.current_user_playlists(limit=50, offset=offset)
                for pl in page.get("items") or []:
                    if pl and pl.get("id"):
                        playlists.append(pl)
                if not page.get("next"):
                    break
                offset += 50
            self._playlists = playlists
        except Exception as e:
            print("[load] playlists error:", e)
            self._playlists = []

    def _clear_content(self):
        children = dpg.get_item_children("content_area", slot=1) or []
        for c in children:
            dpg.delete_item(c)

    def _show_home(self):
        self._current_view = "home"
        self._clear_content()
        with dpg.group(parent="content_area"):
            h = datetime.datetime.now().hour
            part = "morning" if h < 12 else "afternoon" if h < 18 else "evening"
            name = ""
            try:
                if self.sp:
                    me = self.sp.current_user()
                    name = me.get("display_name") or ""
            except Exception:
                pass
            dpg.add_text(f"Good {part}{', ' + name if name else ''}", color=TEXT_BRIGHT)
            dpg.add_spacer(height=8)

            dpg.add_text("Jump back in", color=ACCENT)
            if not self._recent_tracks:
                dpg.add_text("Nothing recent yet.", color=TEXT_DIM)
            else:
                for it in self._recent_tracks[:8]:
                    self._add_track_row(it)

            dpg.add_spacer(height=12)
            dpg.add_text("Your top tracks", color=ACCENT)
            if not self._top_tracks:
                dpg.add_text("No top tracks yet.", color=TEXT_DIM)
            else:
                for i, it in enumerate(self._top_tracks[:12], 1):
                    self._add_track_row(it, index=i)

            dpg.add_spacer(height=12)
            dpg.add_text("Your playlists", color=ACCENT)
            if not self._playlists:
                dpg.add_text("No playlists.", color=TEXT_DIM)
            else:
                for pl in self._playlists[:20]:
                    nm = pl.get("name") or "Playlist"
                    total = (pl.get("tracks") or {}).get("total", 0)
                    dpg.add_button(
                        label=f"{nm}  ({total} tracks)",
                        callback=self._on_playlist_clicked,
                        user_data=pl,
                        width=-1,
                    )

    def _show_library(self):
        self._current_view = "library"
        self._clear_content()
        with dpg.group(parent="content_area"):
            dpg.add_text("Your Library", color=TEXT_BRIGHT)
            dpg.add_spacer(height=8)
            if not self._playlists:
                dpg.add_text("No playlists loaded yet.", color=TEXT_DIM)
            else:
                for pl in self._playlists:
                    nm = pl.get("name") or "Playlist"
                    total = (pl.get("tracks") or {}).get("total", 0)
                    dpg.add_button(
                        label=f"{nm}  ({total} tracks)",
                        callback=self._on_playlist_clicked,
                        user_data=pl,
                        width=-1,
                    )

    def _on_playlist_clicked(self, sender, app_data, user_data):
        self._open_playlist(user_data)

    def _show_liked(self):
        self._current_view = "liked"
        self._clear_content()
        with dpg.group(parent="content_area"):
            dpg.add_text("Liked Songs", color=TEXT_BRIGHT)
            dpg.add_text("Loading...", tag="liked_status", color=TEXT_DIM)
        self._pool.submit(self._load_liked)

    def _load_liked(self):
        items = []
        try:
            offset = 0
            while offset < 200:
                page = self.sp.current_user_saved_tracks(limit=50, offset=offset)
                for it in page.get("items") or []:
                    t = it.get("track") or {}
                    if not t:
                        continue
                    tr = build_track_from_spotify(t)
                    if tr.get("uri"):
                        items.append(tr)
                if not page.get("next"):
                    break
                offset += 50
        except Exception as e:
            print("liked error:", e)

        def update():
            self._clear_content()
            with dpg.group(parent="content_area"):
                dpg.add_text(f"Liked Songs  ({len(items)} tracks)", color=TEXT_BRIGHT)
                dpg.add_spacer(height=6)
                if not items:
                    dpg.add_text("No liked songs.", color=TEXT_DIM)
                else:
                    for i, it in enumerate(items, 1):
                        self._add_track_row(it, index=i)

        try:
            update()
        except Exception:
            pass

    def _show_recent(self):
        self._current_view = "recent"
        self._clear_content()
        with dpg.group(parent="content_area"):
            dpg.add_text("Recently Played", color=TEXT_BRIGHT)
            dpg.add_spacer(height=6)
            if not self._recent_tracks:
                dpg.add_text("Nothing recent.", color=TEXT_DIM)
            else:
                for i, it in enumerate(self._recent_tracks, 1):
                    self._add_track_row(it, index=i)

    def _open_playlist(self, pl):
        if not pl or not isinstance(pl, dict):
            self._clear_content()
            with dpg.group(parent="content_area"):
                dpg.add_text("Playlist unavailable.", color=TEXT_DIM)
            return
        name = pl.get("name") or "Playlist"
        pid = pl.get("id")
        if not pid:
            self._clear_content()
            with dpg.group(parent="content_area"):
                dpg.add_text("Playlist has no id.", color=TEXT_DIM)
            return
        self._clear_content()
        with dpg.group(parent="content_area"):
            dpg.add_text(name, color=TEXT_BRIGHT)
            dpg.add_text("Loading tracks...", tag="pl_status", color=TEXT_DIM)
        self._pool.submit(lambda: self._load_playlist(pid, name))

    def _load_playlist(self, pid: str, name: str):
        items = []
        try:
            offset = 0
            while True:
                page = self.sp.playlist_items(pid, limit=50, offset=offset, additional_types=("track",))
                for it in page.get("items") or []:
                    t = it.get("track")
                    if not t or t.get("is_local"):
                        continue
                    tr = build_track_from_spotify(t)
                    if tr.get("uri"):
                        items.append(tr)
                if not page.get("next") or offset > 400:
                    break
                offset += 50
        except Exception as e:
            print("playlist error:", e)

        def update():
            self._clear_content()
            with dpg.group(parent="content_area"):
                dpg.add_text(f"{name}  ({len(items)} tracks)", color=TEXT_BRIGHT)
                if items:
                    dpg.add_button(
                        label="Play first",
                        callback=self._on_play_first,
                        user_data=items[0]["uri"],
                    )
                dpg.add_spacer(height=6)
                for i, it in enumerate(items, 1):
                    self._add_track_row(it, index=i)

        try:
            update()
        except Exception:
            pass

    def _on_play_first(self, sender, app_data, user_data):
        self._play_uri(user_data)

    def _on_search_enter(self, sender, app_data):
        self._do_search(app_data)

    def _do_search(self, q: str):
        q = (q or "").strip()
        if not q:
            return
        self._clear_content()
        with dpg.group(parent="content_area"):
            dpg.add_text(f'Search: "{q}"', color=TEXT_BRIGHT)
            dpg.add_text("Searching...", color=TEXT_DIM)
        self._pool.submit(lambda: self._run_search(q))

    def _run_search(self, q: str):
        items = []
        try:
            res = self.sp.search(q=q, type="track", limit=40)
            items = [
                build_track_from_spotify(t)
                for t in (res.get("tracks") or {}).get("items") or []
                if t
            ]
        except Exception as e:
            print("search error:", e)

        def update():
            self._clear_content()
            with dpg.group(parent="content_area"):
                dpg.add_text(f'Search: "{q}"  ({len(items)} results)', color=TEXT_BRIGHT)
                dpg.add_spacer(height=6)
                for i, it in enumerate(items, 1):
                    self._add_track_row(it, index=i)

        try:
            update()
        except Exception:
            pass

    def _add_track_row(self, item: dict, index: int = 0):
        """Taller row: thumbnail + Play button + stacked title/artist."""
        if not item:
            return
        uri = item.get("uri")
        cover_url = item.get("cover") or item.get("cover_small")
        title = item.get("name", "Unknown")
        artists = item.get("artists", "")

        self._row_seq += 1
        img_tag = f"row_img_{self._row_seq}"

        with dpg.group(horizontal=True):
            with dpg.group():
                dpg.add_spacer(height=8)
                dpg.add_button(
                    label=">", width=28, height=28,
                    user_data=uri, callback=self._on_play_row_clicked,
                )
            with dpg.group(tag=img_tag):
                tex = load_texture(cover_url, size=44) if cover_url else None
                if tex is not None:
                    dpg.add_image(tex, width=44, height=44)
                else:
                    dpg.add_dummy(width=44, height=44)
            with dpg.group() as text_group:
                prefix = f"{index:02d}  " if index else ""
                dpg.add_text(prefix + title, color=TEXT_BRIGHT)
                dpg.add_text(artists, color=TEXT_DIM)
            dpg.bind_item_theme(text_group, self._tight_theme)
        dpg.add_spacer(height=3)

    def _on_play_row_clicked(self, sender, app_data, user_data):
        self._play_uri(user_data)

    def _play_uri(self, uri):
        if not uri:
            self._show_status("No URI to play")
            return
        self._show_status(f"Playing {uri.split(':')[-1][:8]}...")

        def work():
            try:
                r = requests.post(
                    f"{GO_LIBRESPOT_API}/player/play",
                    json={"uri": uri},
                    timeout=5,
                )
                if r.status_code >= 400:
                    if self._device_id:
                        self.sp.start_playback(device_id=self._device_id, uris=[uri])
                    else:
                        self.sp.start_playback(uris=[uri])
                    self._show_status("Playing (via Web API)")
                else:
                    self._show_status("Playing")
            except Exception as e:
                print("[_play_uri] ERROR:", e)
                self._show_status(f"Play error: {e}")

        self._pool.submit(work)

    def _play_pause(self):
        self._post("/player/playpause")

    def _next(self):
        self._post("/player/next")

    def _prev(self):
        self._post("/player/prev")

    def _on_seek(self, sender, app_data):
        value = app_data
        try:
            r = requests.get(f"{GO_LIBRESPOT_API}/status", timeout=1)
            dur = int((r.json().get("track") or {}).get("duration") or 0)
            if dur > 0:
                pos = int(dur * value / 1000)
                self._post("/player/seek", {"position": pos})
        except Exception:
            pass

    def _on_volume(self, sender, app_data):
        self._post("/player/volume", {"volume": int(app_data)})

    def _post(self, path: str, payload=None):
        def work():
            try:
                r = requests.post(f"{GO_LIBRESPOT_API}{path}", json=payload or {}, timeout=2)
                if r.status_code >= 400:
                    print(f"[post] {path} -> {r.status_code}: {r.text[:200]}")
            except requests.RequestException as e:
                print(f"[post] {path} error:", e)

        self._pool.submit(work)

    def cleanup(self):
        self._poller_stop = True
        if self.librespot_proc:
            try:
                self.librespot_proc.terminate()
            except Exception:
                pass
        self._pool.shutdown(wait=False)



if __name__ == "__main__":
    SpotifyApp()
