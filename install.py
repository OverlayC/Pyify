"""
Pyify Installer

A small Tkinter wizard that:
  1. Explains how to create a Spotify Developer app (Client ID/Secret)
  2. Downloads the project files from GitHub into a folder you choose
  3. Explains how to set up go-librespot
  4. Offers to launch the app once everything is in place

This installer itself only uses the Python standard library, so it can run
before you've pip-installed anything else - it just gets files into place
and (optionally) pre-fills config.json so the app's own first-run setup
screen can be skipped.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
import zipfile
from tkinter import ttk, messagebox, filedialog

# ---------------------------------------------------------------------------
# Edit this once you've pushed the project to your own GitHub repo.
# It's also editable directly in the installer window, so leaving the
# placeholder here is fine - you can type the real URL when you run it.
# ---------------------------------------------------------------------------
DEFAULT_GITHUB_REPO_URL = "https://github.com/YOUR-USERNAME/YOUR-REPO"

GO_LIBRESPOT_RELEASES_URL = "https://github.com/devgianlu/go-librespot/releases/latest"
SPOTIFY_DASHBOARD_URL = "https://developer.spotify.com/dashboard"

APP_DIR = os.path.join(os.path.expanduser("~"), ".spotify_replacement")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")


# ---------------------------------------------------------------------------
# GitHub download helpers (no external packages needed)
# ---------------------------------------------------------------------------
def parse_owner_repo(url: str):
    url = url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    parts = url.split("/")
    if len(parts) < 2:
        raise ValueError("That doesn't look like a full GitHub repo URL.")
    return parts[-2], parts[-1]


def download_github_repo(repo_url: str, dest_path: str, status_cb):
    """Downloads the repo as a zip (tries 'main' then 'master') and merges
    its contents into dest_path. No git installation required."""
    owner, repo = parse_owner_repo(repo_url)
    os.makedirs(dest_path, exist_ok=True)

    last_error = None
    for branch in ("main", "master"):
        zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"
        status_cb(f"Trying {branch} branch...")
        try:
            with urllib.request.urlopen(zip_url, timeout=30) as resp:
                data = resp.read()
        except urllib.error.HTTPError as e:
            last_error = e
            continue
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error reaching GitHub: {e}")

        status_cb("Extracting files...")
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            if not names:
                raise RuntimeError("Downloaded zip was empty.")
            # GitHub zips have one top-level folder like "repo-main/"
            top_folder = names[0].split("/")[0]
            with _temp_extract_dir() as tmp_dir:
                zf.extractall(tmp_dir)
                extracted_root = os.path.join(tmp_dir, top_folder)
                _merge_copy(extracted_root, dest_path, status_cb)
        return  # success

    raise RuntimeError(
        f"Could not find a 'main' or 'master' branch for {owner}/{repo}. "
        f"Check the repo URL is correct and public. ({last_error})"
    )


class _temp_extract_dir:
    """Small context manager so we don't need the tempfile module's
    trickier cleanup-on-Windows edge cases spread through the function."""

    def __enter__(self):
        import tempfile
        self.path = tempfile.mkdtemp(prefix="pyify_install_")
        return self.path

    def __exit__(self, *exc):
        shutil.rmtree(self.path, ignore_errors=True)


def _merge_copy(src_root: str, dest_root: str, status_cb):
    """Copies src_root's contents into dest_root, overwriting existing
    files (so re-running the installer updates an existing install)."""
    for dirpath, dirnames, filenames in os.walk(src_root):
        rel = os.path.relpath(dirpath, src_root)
        target_dir = dest_root if rel == "." else os.path.join(dest_root, rel)
        os.makedirs(target_dir, exist_ok=True)
        for fname in filenames:
            src_file = os.path.join(dirpath, fname)
            dst_file = os.path.join(target_dir, fname)
            shutil.copy2(src_file, dst_file)
    status_cb("Files copied.")


# ---------------------------------------------------------------------------
# Config helpers (same location/schema the app itself reads on launch)
# ---------------------------------------------------------------------------
def save_partial_config(**fields):
    os.makedirs(APP_DIR, exist_ok=True)
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    cfg.update({k: v for k, v in fields.items() if v})
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------
class InstallerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Pyify - Setup")
        self.root.geometry("560x480")
        self.root.resizable(False, False)

        self.dest_path = tk.StringVar()
        self.repo_url = tk.StringVar(value=DEFAULT_GITHUB_REPO_URL)
        self.client_id = tk.StringVar()
        self.client_secret = tk.StringVar()
        self.librespot_path = tk.StringVar()
        self.launch_after = tk.BooleanVar(value=True)

        self.container = tk.Frame(self.root)
        self.container.pack(fill="both", expand=True)

        self.steps = [
            self.build_step_spotify,
            self.build_step_download,
            self.build_step_librespot,
            self.build_step_finish,
        ]
        self.step_index = 0
        self.show_step()

    # ---- step scaffolding ----

    def clear(self):
        for w in self.container.winfo_children():
            w.destroy()

    def show_step(self):
        self.clear()
        self.steps[self.step_index]()

    def nav_buttons(self, parent, next_label="Next", on_next=None, next_enabled=True):
        row = tk.Frame(parent)
        row.pack(side="bottom", fill="x", pady=12, padx=16)
        if self.step_index > 0:
            tk.Button(row, text="Back", width=10, command=self.go_back).pack(side="left")
        btn = tk.Button(
            row, text=next_label, width=12,
            command=on_next or self.go_next,
            state="normal" if next_enabled else "disabled",
        )
        btn.pack(side="right")
        return btn

    def go_back(self):
        self.step_index -= 1
        self.show_step()

    def go_next(self):
        self.step_index += 1
        self.show_step()

    # ---- step 1: Spotify developer app ----

    def build_step_spotify(self):
        f = self.container
        tk.Label(f, text="Step 1 of 4 - Spotify Developer App",
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=16, pady=(16, 4))

        instructions = (
            "1. Open the Spotify Developer Dashboard and log in.\n"
            "2. Click 'Create app'.\n"
            "3. Give it any name/description.\n"
            "4. Set Redirect URI to exactly:\n"
            "     http://127.0.0.1:8888/callback\n"
            "5. Check 'Web API' under 'Which API/SDKs are you planning to use'.\n"
            "6. Save, then open the app and click 'View client secret'.\n"
            "7. Copy the Client ID and Client Secret below (optional - you can\n"
            "   also enter these later, inside the app itself)."
        )
        tk.Label(f, text=instructions, justify="left", fg="#333").pack(
            anchor="w", padx=16, pady=(0, 8)
        )

        tk.Button(
            f, text="Open Spotify Developer Dashboard",
            command=lambda: webbrowser.open(SPOTIFY_DASHBOARD_URL),
        ).pack(anchor="w", padx=16, pady=(0, 12))

        form = tk.Frame(f)
        form.pack(anchor="w", padx=16, fill="x")
        tk.Label(form, text="Client ID (optional):").grid(row=0, column=0, sticky="w", pady=4)
        tk.Entry(form, textvariable=self.client_id, width=42).grid(row=0, column=1, pady=4)
        tk.Label(form, text="Client Secret (optional):").grid(row=1, column=0, sticky="w", pady=4)
        tk.Entry(form, textvariable=self.client_secret, width=42, show="*").grid(row=1, column=1, pady=4)

        self.nav_buttons(f)

    # ---- step 2: pull files from GitHub ----

    def build_step_download(self):
        f = self.container
        tk.Label(f, text="Step 2 of 4 - Get the App Files",
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=16, pady=(16, 4))
        tk.Label(
            f,
            text="Choose where to install the app, and the GitHub repo to pull it from.",
            justify="left", fg="#333",
        ).pack(anchor="w", padx=16, pady=(0, 10))

        form = tk.Frame(f)
        form.pack(anchor="w", padx=16, fill="x")

        tk.Label(form, text="Install folder:").grid(row=0, column=0, sticky="w", pady=4)
        dest_row = tk.Frame(form)
        dest_row.grid(row=0, column=1, sticky="w", pady=4)
        tk.Entry(dest_row, textvariable=self.dest_path, width=34).pack(side="left")
        tk.Button(dest_row, text="Browse", command=self.browse_dest).pack(side="left", padx=4)

        tk.Label(form, text="GitHub repo URL:").grid(row=1, column=0, sticky="w", pady=4)
        tk.Entry(form, textvariable=self.repo_url, width=42).grid(row=1, column=1, sticky="w", pady=4)

        self.download_status = tk.Label(f, text="", fg="gray", justify="left", wraplength=500)
        self.download_status.pack(anchor="w", padx=16, pady=(10, 4))

        btn_row = tk.Frame(f)
        btn_row.pack(anchor="w", padx=16, pady=(0, 8))
        tk.Button(btn_row, text="Download files", command=self.do_download).pack(side="left")
        tk.Button(
            btn_row, text="Skip (I already have the files)",
            command=self.skip_download,
        ).pack(side="left", padx=8)

        self.nav_buttons(f)

    def browse_dest(self):
        path = filedialog.askdirectory(title="Choose install folder")
        if path:
            self.dest_path.set(path)

    def skip_download(self):
        if not self.dest_path.get().strip():
            messagebox.showwarning("Install folder needed",
                                    "Pick or type an install folder first, even if you're "
                                    "supplying the files yourself.")
            return
        self.go_next()

    def do_download(self):
        dest = self.dest_path.get().strip()
        repo = self.repo_url.get().strip()
        if not dest:
            messagebox.showwarning("Missing folder", "Choose an install folder first.")
            return
        if not repo or repo == DEFAULT_GITHUB_REPO_URL:
            messagebox.showwarning(
                "Missing repo URL",
                "Enter the actual GitHub repo URL for the project (the default "
                "placeholder won't work).",
            )
            return

        import threading

        def work():
            try:
                download_github_repo(repo, dest, self.set_download_status)
                self.set_download_status(f"Done. Files installed to: {dest}")
            except Exception as e:
                self.set_download_status(f"Failed: {e}")

        self.set_download_status("Starting download...")
        threading.Thread(target=work, daemon=True).start()

    def set_download_status(self, text):
        self.root.after(0, lambda: self.download_status.config(text=text))

    # ---- step 3: go-librespot ----

    def build_step_librespot(self):
        f = self.container
        tk.Label(f, text="Step 3 of 4 - go-librespot Setup",
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=16, pady=(16, 4))

        instructions = (
            "go-librespot lets the app register itself as a real Spotify Connect\n"
            "device and play audio directly, without the official Spotify app.\n\n"
            "1. Download a build for your OS/CPU from the releases page below.\n"
            "2. Extract the archive fully into its own folder - keep every file\n"
            "   from the archive together (on Windows this includes some .dll\n"
            "   files the .exe needs; don't move the .exe out on its own).\n"
            "3. Point this installer at the .exe (or binary) below.\n"
            "4. The first time it runs, it'll print a Spotify login link to its\n"
            "   console - open that link once and approve it. After that it\n"
            "   logs in automatically on every future launch."
        )
        tk.Label(f, text=instructions, justify="left", fg="#333").pack(
            anchor="w", padx=16, pady=(0, 8)
        )

        tk.Button(
            f, text="Open go-librespot releases page",
            command=lambda: webbrowser.open(GO_LIBRESPOT_RELEASES_URL),
        ).pack(anchor="w", padx=16, pady=(0, 12))

        form = tk.Frame(f)
        form.pack(anchor="w", padx=16, fill="x")
        tk.Label(form, text="Path to go-librespot executable:").grid(row=0, column=0, sticky="w")
        path_row = tk.Frame(form)
        path_row.grid(row=1, column=0, sticky="w", pady=4)
        tk.Entry(path_row, textvariable=self.librespot_path, width=44).pack(side="left")
        tk.Button(path_row, text="Browse", command=self.browse_librespot).pack(side="left", padx=4)

        self.nav_buttons(f)

    def browse_librespot(self):
        path = filedialog.askopenfilename(
            title="Select go-librespot executable",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
        )
        if path:
            self.librespot_path.set(path)

    # ---- step 4: finish ----

    def build_step_finish(self):
        f = self.container
        tk.Label(f, text="Step 4 of 4 - Finish",
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=16, pady=(16, 4))

        summary_lines = [
            f"Install folder: {self.dest_path.get() or '(not set)'}",
            f"Spotify Client ID: {'set' if self.client_id.get() else '(you can add this in the app)'}",
            f"go-librespot path: {self.librespot_path.get() or '(not set)'}",
        ]
        tk.Label(f, text="\n".join(summary_lines), justify="left", fg="#333").pack(
            anchor="w", padx=16, pady=(0, 12)
        )

        tk.Checkbutton(
            f, text="Launch the app now", variable=self.launch_after,
        ).pack(anchor="w", padx=16, pady=(0, 12))

        row = tk.Frame(f)
        row.pack(side="bottom", fill="x", pady=12, padx=16)
        tk.Button(row, text="Back", width=10, command=self.go_back).pack(side="left")
        tk.Button(row, text="Finish", width=12, command=self.finish).pack(side="right")

    def finish(self):
        save_partial_config(
            client_id=self.client_id.get().strip(),
            client_secret=self.client_secret.get().strip(),
            librespot_path=self.librespot_path.get().strip(),
        )

        if self.launch_after.get():
            dest = self.dest_path.get().strip()
            app_path = os.path.join(dest, "app.py") if dest else None
            if app_path and os.path.exists(app_path):
                try:
                    subprocess.Popen([sys.executable, app_path], cwd=dest)
                except Exception as e:
                    messagebox.showerror("Couldn't launch", str(e))
            else:
                messagebox.showinfo(
                    "app.py not found",
                    "Couldn't find app.py in the install folder to launch automatically. "
                    "You can run it yourself once the files are in place.",
                )

        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    InstallerApp().run()