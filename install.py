import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
import zipfile
import tempfile
from tkinter import messagebox, filedialog


DEFAULT_GITHUB_REPO_URL = "https://github.com/OverlayC/Pyify.git"

GO_LIBRESPOT_RELEASES_URL = (
    "https://github.com/devgianlu/go-librespot/releases/latest"
)

SPOTIFY_DASHBOARD_URL = (
    "https://developer.spotify.com/dashboard"
)

GO_LIBRESPOT_API = "http://127.0.0.1:3678"

LIBRESPOT_DEVICE_NAME = "Pyify"

AUTHORIZE_URL_RE = re.compile(
    r"https://accounts\.spotify\.com/authorize\?[^\s<>\[\]\"']+",
    re.IGNORECASE,
)

APP_DIR = os.path.join(
    os.path.expanduser("~"),
    ".spotify_replacement"
)

CONFIG_PATH = os.path.join(
    APP_DIR,
    "config.json"
)


def ensure_librespot_config(
    config_dir: str,
    device_name: str = LIBRESPOT_DEVICE_NAME
):
    path = os.path.join(config_dir, "config.yml")

    if os.path.exists(path):
        return

    content = (
        f"device_name: {device_name}\n"
        "credentials:\n"
        "  type: interactive\n"
        "zeroconf_enabled: true\n"
        "server:\n"
        "  enabled: true\n"
        "  address: 127.0.0.1\n"
        "  port: 3678\n"
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def parse_owner_repo(url: str):
    url = url.strip().rstrip("/")

    if url.endswith(".git"):
        url = url[:-4]

    parts = url.split("/")

    if len(parts) < 2:
        raise ValueError(
            "That doesn't look like a full GitHub repo URL."
        )

    return parts[-2], parts[-1]


def download_github_repo(
    repo_url: str,
    dest_path: str,
    status_cb
):
    owner, repo = parse_owner_repo(repo_url)

    os.makedirs(dest_path, exist_ok=True)

    last_error = None

    for branch in ("main", "master"):
        zip_url = (
            f"https://github.com/{owner}/{repo}"
            f"/archive/refs/heads/{branch}.zip"
        )

        status_cb(
            f"Trying {branch} branch..."
        )

        try:
            with urllib.request.urlopen(
                zip_url,
                timeout=30
            ) as resp:
                data = resp.read()

        except urllib.error.HTTPError as e:
            last_error = e
            continue

        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Network error reaching GitHub: {e}"
            )

        status_cb("Extracting files...")

        with zipfile.ZipFile(
            io.BytesIO(data)
        ) as zf:
            names = zf.namelist()

            if not names:
                raise RuntimeError(
                    "Downloaded zip was empty."
                )

            top_folder = names[0].split("/")[0]

            with tempfile.TemporaryDirectory(
                prefix="pyify_install_"
            ) as tmp_dir:
                zf.extractall(tmp_dir)

                extracted_root = os.path.join(
                    tmp_dir,
                    top_folder
                )

                merge_copy(
                    extracted_root,
                    dest_path,
                    status_cb
                )

        return

    raise RuntimeError(
        f"Could not find a 'main' or 'master' branch for "
        f"{owner}/{repo}. Check the repo URL is correct "
        f"and public. ({last_error})"
    )


def merge_copy(
    src_root: str,
    dest_root: str,
    status_cb
):
    for dirpath, dirnames, filenames in os.walk(
        src_root
    ):
        rel = os.path.relpath(
            dirpath,
            src_root
        )

        target_dir = (
            dest_root
            if rel == "."
            else os.path.join(dest_root, rel)
        )

        os.makedirs(
            target_dir,
            exist_ok=True
        )

        for fname in filenames:
            src_file = os.path.join(
                dirpath,
                fname
            )

            dst_file = os.path.join(
                target_dir,
                fname
            )

            shutil.copy2(
                src_file,
                dst_file
            )

    status_cb("Files copied.")


def find_main_app_directory(dest_path: str):
    direct_app = os.path.join(
        dest_path,
        "Pyify.py"
    )

    if os.path.isfile(direct_app):
        return dest_path

    for root, dirs, files in os.walk(dest_path):
        if "Pyify.py" in files:
            return root

    return None


def install_requirements(
    dest_path: str,
    status_cb
):
    app_dir = find_main_app_directory(
        dest_path
    )

    if not app_dir:
        status_cb(
            "Pyify.py was not found. Skipping requirements installation."
        )
        return False

    requirements_path = os.path.join(
        app_dir,
        "requirements.txt"
    )

    if not os.path.isfile(requirements_path):
        status_cb(
            "No requirements.txt found next to Pyify.py."
        )
        return True

    status_cb(
        f"Installing packages from {requirements_path}..."
    )

    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-r",
                requirements_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace"
        )

        if process.stdout:
            for line in process.stdout:
                line = line.strip()

                if line:
                    status_cb(
                        f"pip: {line}"
                    )

        return_code = process.wait()

        if return_code != 0:
            raise RuntimeError(
                f"pip exited with code {return_code}."
            )

        status_cb(
            "All required packages were installed."
        )

        return True

    except Exception as e:
        raise RuntimeError(
            f"Failed to install requirements: {e}"
        )


def save_partial_config(**fields):
    os.makedirs(
        APP_DIR,
        exist_ok=True
    )

    cfg = {}

    if os.path.exists(CONFIG_PATH):
        try:
            with open(
                CONFIG_PATH,
                "r",
                encoding="utf-8"
            ) as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}

    cfg.update({
        k: v
        for k, v in fields.items()
        if v
    })

    with open(
        CONFIG_PATH,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            cfg,
            f,
            indent=2
        )


class InstallerApp:

    def __init__(self):
        self.root = tk.Tk()

        self.root.title(
            "Pyify - Setup"
        )

        self.root.geometry(
            "560x760"
        )

        self.root.resizable(
            True,
            True
        )

        self.dest_path = tk.StringVar()

        self.repo_url = tk.StringVar(
            value=DEFAULT_GITHUB_REPO_URL
        )

        self.client_id = tk.StringVar()

        self.client_secret = tk.StringVar()

        self.librespot_path = tk.StringVar()

        self.launch_after = tk.BooleanVar(
            value=True
        )

        self.librespot_test_proc = None

        self._librespot_ready = False

        self.librespot_log_file = None

        self.container = tk.Frame(
            self.root
        )

        self.container.pack(
            fill="both",
            expand=True
        )

        self.steps = [
            self.build_step_spotify,
            self.build_step_download,
            self.build_step_librespot,
            self.build_step_finish,
        ]

        self.step_index = 0

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.on_close
        )

        self.show_step()

    def clear(self):
        for w in self.container.winfo_children():
            w.destroy()

    def show_step(self):
        self.clear()
        self.steps[
            self.step_index
        ]()

    def nav_buttons(
        self,
        parent,
        next_label="Next",
        on_next=None,
        next_enabled=True
    ):
        row = tk.Frame(parent)

        row.pack(
            side="bottom",
            fill="x",
            pady=12,
            padx=16
        )

        if self.step_index > 0:
            tk.Button(
                row,
                text="Back",
                width=10,
                command=self.go_back
            ).pack(
                side="left"
            )

        btn = tk.Button(
            row,
            text=next_label,
            width=12,
            command=on_next or self.go_next,
            state=(
                "normal"
                if next_enabled
                else "disabled"
            )
        )

        btn.pack(
            side="right"
        )

        return btn

    def go_back(self):
        self.step_index -= 1
        self.show_step()

    def go_next(self):
        self.step_index += 1
        self.show_step()

    def build_step_spotify(self):
        f = self.container

        tk.Label(
            f,
            text="Step 1 of 4 - Spotify Developer App",
            font=("Segoe UI", 13, "bold")
        ).pack(
            anchor="w",
            padx=16,
            pady=(16, 4)
        )

        instructions = (
            "1. Open the Spotify Developer Dashboard and log in.\n"
            "2. Click 'Create app'.\n"
            "3. Give it any name/description.\n"
            "4. Set Redirect URI to exactly:\n"
            "   http://127.0.0.1:8888/callback\n"
            "5. Check 'Web API' under 'Which API/SDKs are you planning to use'.\n"
            "6. Save, then open the app and click 'View client secret'.\n"
            "7. Copy the Client ID and Client Secret below (optional - you can\n"
            "   also enter these later, inside the app itself)."
        )

        tk.Label(
            f,
            text=instructions,
            justify="left",
            fg="#333"
        ).pack(
            anchor="w",
            padx=16,
            pady=(0, 8)
        )

        tk.Button(
            f,
            text="Open Spotify Developer Dashboard",
            command=lambda: webbrowser.open(
                SPOTIFY_DASHBOARD_URL
            )
        ).pack(
            anchor="w",
            padx=16,
            pady=(0, 12)
        )

        form = tk.Frame(f)

        form.pack(
            anchor="w",
            padx=16,
            fill="x"
        )

        tk.Label(
            form,
            text="Client ID (optional):"
        ).grid(
            row=0,
            column=0,
            sticky="w",
            pady=4
        )

        tk.Entry(
            form,
            textvariable=self.client_id,
            width=42
        ).grid(
            row=0,
            column=1,
            pady=4
        )

        tk.Label(
            form,
            text="Client Secret (optional):"
        ).grid(
            row=1,
            column=0,
            sticky="w",
            pady=4
        )

        tk.Entry(
            form,
            textvariable=self.client_secret,
            width=42,
            show="*"
        ).grid(
            row=1,
            column=1,
            pady=4
        )

        self.nav_buttons(f)

    def build_step_download(self):
        f = self.container

        tk.Label(
            f,
            text="Step 2 of 4 - Get the App Files",
            font=("Segoe UI", 13, "bold")
        ).pack(
            anchor="w",
            padx=16,
            pady=(16, 4)
        )

        tk.Label(
            f,
            text=(
                "Choose where to install the app, and the GitHub "
                "repo to pull it from."
            ),
            justify="left",
            fg="#333"
        ).pack(
            anchor="w",
            padx=16,
            pady=(0, 10)
        )

        form = tk.Frame(f)

        form.pack(
            anchor="w",
            padx=16,
            fill="x"
        )

        tk.Label(
            form,
            text="Install folder:"
        ).grid(
            row=0,
            column=0,
            sticky="w",
            pady=4
        )

        dest_row = tk.Frame(form)

        dest_row.grid(
            row=0,
            column=1,
            sticky="w",
            pady=4
        )

        tk.Entry(
            dest_row,
            textvariable=self.dest_path,
            width=34
        ).pack(
            side="left"
        )

        tk.Button(
            dest_row,
            text="Browse",
            command=self.browse_dest
        ).pack(
            side="left",
            padx=4
        )

        tk.Label(
            form,
            text="GitHub repo URL:"
        ).grid(
            row=1,
            column=0,
            sticky="w",
            pady=4
        )

        tk.Entry(
            form,
            textvariable=self.repo_url,
            width=42
        ).grid(
            row=1,
            column=1,
            sticky="w"
        )

        self.download_status = tk.Label(
            f,
            text="",
            fg="gray",
            justify="left",
            wraplength=500
        )

        self.download_status.pack(
            anchor="w",
            padx=16,
            pady=(10, 4)
        )

        btn_row = tk.Frame(f)

        btn_row.pack(
            anchor="w",
            padx=16,
            pady=(0, 8)
        )

        tk.Button(
            btn_row,
            text="Download files",
            command=self.do_download
        ).pack(
            side="left"
        )

        tk.Button(
            btn_row,
            text="Skip (I already have the files)",
            command=self.skip_download
        ).pack(
            side="left",
            padx=8
        )

        self.nav_buttons(f)

    def browse_dest(self):
        path = filedialog.askdirectory(
            title="Choose install folder"
        )

        if path:
            self.dest_path.set(path)

    def skip_download(self):
        if not self.dest_path.get().strip():
            messagebox.showwarning(
                "Install folder needed",
                (
                    "Pick or type an install folder first, even if "
                    "you're supplying the files yourself."
                )
            )
            return

        self.go_next()

    def do_download(self):
        dest = self.dest_path.get().strip()
        repo = self.repo_url.get().strip()

        if not dest:
            messagebox.showwarning(
                "Missing folder",
                "Choose an install folder first."
            )
            return

        def work():
            try:
                download_github_repo(
                    repo,
                    dest,
                    self.set_download_status
                )

                self.set_download_status(
                    "Files downloaded. Checking requirements.txt..."
                )

                install_requirements(
                    dest,
                    self.set_download_status
                )

                self.set_download_status(
                    f"Done. Files and required packages installed to: {dest}"
                )

            except Exception as e:
                self.set_download_status(
                    f"Failed: {e}"
                )

        self.set_download_status(
            "Starting download..."
        )

        threading.Thread(
            target=work,
            daemon=True
        ).start()

    def set_download_status(self, text):
        self.root.after(
            0,
            lambda: self._safe_set_download_status(text)
        )

    def _safe_set_download_status(self, text):
        try:
            if (
                hasattr(self, "download_status")
                and self.download_status.winfo_exists()
            ):
                self.download_status.config(
                    text=text
                )
        except tk.TclError:
            pass

    def build_step_librespot(self):
        f = self.container

        tk.Label(
            f,
            text="Step 3 of 4 - go-librespot Setup",
            font=("Segoe UI", 13, "bold")
        ).pack(
            anchor="w",
            padx=16,
            pady=(16, 4)
        )

        instructions = (
            "go-librespot lets the app register itself as a real Spotify Connect\n"
            "device and play audio directly, without the official Spotify app.\n\n"
            "1. Download a build for your OS/CPU from the releases page below.\n"
            "2. Extract the archive fully into its own folder - keep every file\n"
            "   from the archive together (on Windows this includes some .dll\n"
            "   files the .exe needs; don't move the .exe out on its own).\n"
            "3. Point this installer at the .exe (or binary) below, then click\n"
            "   'Start & Get Login Link' - this actually runs it so you can log\n"
            "   in and verify it works, right here in the installer."
        )

        tk.Label(
            f,
            text=instructions,
            justify="left",
            fg="#333"
        ).pack(
            anchor="w",
            padx=16,
            pady=(0, 8)
        )

        tk.Button(
            f,
            text="Open go-librespot releases page",
            command=lambda: webbrowser.open(
                GO_LIBRESPOT_RELEASES_URL
            )
        ).pack(
            anchor="w",
            padx=16,
            pady=(0, 10)
        )

        form = tk.Frame(f)

        form.pack(
            anchor="w",
            padx=16,
            fill="x"
        )

        tk.Label(
            form,
            text="Path to go-librespot executable:"
        ).grid(
            row=0,
            column=0,
            sticky="w"
        )

        path_row = tk.Frame(form)

        path_row.grid(
            row=1,
            column=0,
            sticky="w",
            pady=4
        )

        tk.Entry(
            path_row,
            textvariable=self.librespot_path,
            width=40
        ).pack(
            side="left"
        )

        tk.Button(
            path_row,
            text="Browse",
            command=self.browse_librespot
        ).pack(
            side="left",
            padx=4
        )

        btn_row = tk.Frame(f)

        btn_row.pack(
            anchor="w",
            padx=16,
            pady=(8, 6)
        )

        self.start_librespot_btn = tk.Button(
            btn_row,
            text="Start & Get Login Link",
            command=self.start_librespot_test
        )

        self.start_librespot_btn.pack(
            side="left"
        )

        self.stop_librespot_btn = tk.Button(
            btn_row,
            text="Stop",
            command=self.stop_librespot_test,
            state="disabled"
        )

        self.stop_librespot_btn.pack(
            side="left",
            padx=6
        )

        self.librespot_status = tk.Label(
            f,
            text="Not started.",
            fg="gray",
            justify="left",
            wraplength=500
        )

        self.librespot_status.pack(
            anchor="w",
            padx=16,
            pady=(2, 6)
        )

        link_row = tk.Frame(f)

        link_row.pack(
            anchor="w",
            padx=16,
            fill="x",
            pady=(0, 6)
        )

        tk.Label(
            link_row,
            text="Login link:"
        ).pack(
            side="left"
        )

        self.login_link_entry = tk.Entry(
            link_row,
            width=46
        )

        self.login_link_entry.pack(
            side="left",
            padx=6
        )

        self.open_link_btn = tk.Button(
            link_row,
            text="Open Link",
            command=self.open_login_link,
            state="disabled"
        )

        self.open_link_btn.pack(
            side="left"
        )

        log_frame = tk.Frame(f)

        log_frame.pack(
            fill="both",
            expand=True,
            padx=16,
            pady=(4, 4)
        )

        tk.Label(
            log_frame,
            text="go-librespot log:",
            font=("Segoe UI", 8),
            fg="gray"
        ).pack(
            anchor="w"
        )

        self.librespot_log = tk.Text(
            log_frame,
            height=6,
            font=("Consolas", 8),
            wrap="word"
        )

        self.librespot_log.pack(
            fill="both",
            expand=True
        )

        self.librespot_log.config(
            state="disabled"
        )

        self.nav_buttons(f)

    def browse_librespot(self):
        path = filedialog.askopenfilename(
            title="Select go-librespot executable",
            filetypes=[
                ("Executable", "*.exe"),
                ("All files", "*.*")
            ]
        )

        if path:
            self.librespot_path.set(path)

    def _clean_log_line(self, line):
        line = re.sub(
            r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])",
            "",
            line
        )

        line = "".join(
            char
            for char in line
            if char in "\r\n\t"
            or ord(char) >= 32
        )

        return line

    def _extract_login_url(self, line):
        line = self._clean_log_line(line)

        match = AUTHORIZE_URL_RE.search(line)

        if not match:
            return None

        url = match.group(0).strip()

        url = url.rstrip(
            ".,;:)]}>\"'"
        )

        return url

    def _log_librespot(self, line):
        try:
            if (
                hasattr(self, "librespot_log")
                and self.librespot_log.winfo_exists()
            ):
                self.librespot_log.config(
                    state="normal"
                )

                self.librespot_log.insert(
                    "end",
                    line
                )

                self.librespot_log.see(
                    "end"
                )

                self.librespot_log.config(
                    state="disabled"
                )
        except tk.TclError:
            pass

        if self.librespot_log_file:
            try:
                with open(
                    self.librespot_log_file,
                    "a",
                    encoding="utf-8",
                    errors="replace"
                ) as f:
                    f.write(line)
            except Exception:
                pass

    def start_librespot_test(self):
        path = self.librespot_path.get().strip()

        if not path or not os.path.exists(path):
            messagebox.showwarning(
                "Path needed",
                "Choose a valid go-librespot executable first."
            )
            return

        if self.librespot_test_proc:
            messagebox.showinfo(
                "Already running",
                "go-librespot is already running."
            )
            return

        config_dir = os.path.dirname(
            os.path.abspath(path)
        )

        ensure_librespot_config(
            config_dir
        )

        self.librespot_log_file = os.path.join(
            config_dir,
            "log.txt"
        )

        try:
            with open(
                self.librespot_log_file,
                "w",
                encoding="utf-8"
            ) as f:
                f.write(
                    "=== Pyify go-librespot log ===\n\n"
                )
        except Exception:
            self.librespot_log_file = None

        try:
            self.librespot_test_proc = subprocess.Popen(
                [
                    path,
                    "--config_dir",
                    config_dir
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                errors="replace"
            )

        except Exception as e:
            messagebox.showerror(
                "Couldn't start go-librespot",
                str(e)
            )

            self.librespot_test_proc = None
            return

        self._librespot_ready = False

        try:
            self.start_librespot_btn.config(
                state="disabled"
            )

            self.stop_librespot_btn.config(
                state="normal"
            )

            self.librespot_status.config(
                text="Starting...",
                fg="gray"
            )

            self.login_link_entry.delete(
                0,
                tk.END
            )

            self.open_link_btn.config(
                state="disabled"
            )

            self.librespot_log.config(
                state="normal"
            )

            self.librespot_log.delete(
                "1.0",
                tk.END
            )

            self.librespot_log.config(
                state="disabled"
            )

        except tk.TclError:
            pass

        threading.Thread(
            target=self._stream_librespot_log,
            daemon=True
        ).start()

        threading.Thread(
            target=self._poll_librespot_ready,
            daemon=True
        ).start()

    def _stream_librespot_log(self):
        proc = self.librespot_test_proc

        if not proc or not proc.stdout:
            return

        try:
            for raw_line in proc.stdout:
                line = self._clean_log_line(
                    raw_line
                )

                try:
                    self.root.after(
                        0,
                        self._log_librespot,
                        line
                    )

                    url = self._extract_login_url(
                        line
                    )

                    if url:
                        self.root.after(
                            0,
                            self._show_login_link,
                            url
                        )

                except tk.TclError:
                    return

        except Exception as e:
            try:
                self.root.after(
                    0,
                    self._log_librespot,
                    f"\n[Installer] Log reader stopped: {e}\n"
                )
            except tk.TclError:
                pass

    def _show_login_link(self, url):
        try:
            url = self._extract_login_url(
                url
            )

            if not url:
                return

            self.login_link_entry.delete(
                0,
                tk.END
            )

            self.login_link_entry.insert(
                0,
                url
            )

            self.open_link_btn.config(
                state="normal"
            )

            self.librespot_status.config(
                text=(
                    "Login link ready - click 'Open Link', "
                    "then approve access in your browser."
                ),
                fg="#b8860b"
            )

        except tk.TclError:
            pass

    def open_login_link(self):
        try:
            url = self.login_link_entry.get().strip()
        except tk.TclError:
            return

        if not url:
            return

        cleaned_url = self._extract_login_url(
            url
        )

        if cleaned_url:
            url = cleaned_url

        try:
            if sys.platform == "win32":
                os.startfile(url)
            else:
                webbrowser.open_new(url)

        except Exception as e:
            try:
                webbrowser.open_new(url)

            except Exception:
                messagebox.showerror(
                    "Couldn't open login link",
                    (
                        "Windows could not open the Spotify login URL.\n\n"
                        f"URL:\n{url}\n\n"
                        f"Error:\n{e}"
                    )
                )

    def _poll_librespot_ready(self):
        for _ in range(90):
            proc = self.librespot_test_proc

            if not proc:
                return

            if proc.poll() is not None:
                return

            try:
                with urllib.request.urlopen(
                    f"{GO_LIBRESPOT_API}/",
                    timeout=1
                ) as resp:
                    data = json.loads(
                        resp.read().decode(
                            "utf-8"
                        )
                    )

                if data.get("playback_ready"):
                    try:
                        self.root.after(
                            0,
                            self._on_librespot_ready
                        )
                    except tk.TclError:
                        pass

                    return

            except Exception:
                pass

            time.sleep(1)

    def _on_librespot_ready(self):
        try:
            self._librespot_ready = True

            self.librespot_status.config(
                text=(
                    f"Connected as a Spotify Connect device named "
                    f"'{LIBRESPOT_DEVICE_NAME}'.\n"
                    "Now open Spotify (phone, desktop, or web player), "
                    "click the Connect/devices icon near the playback bar, "
                    f"and select '{LIBRESPOT_DEVICE_NAME}' so playback "
                    "routes through this app."
                ),
                fg="#1a7f37"
            )

        except tk.TclError:
            pass

    def stop_librespot_test(self):
        if self.librespot_test_proc:
            try:
                self.librespot_test_proc.terminate()
            except Exception:
                pass

            self.librespot_test_proc = None

        try:
            if (
                hasattr(self, "start_librespot_btn")
                and self.start_librespot_btn.winfo_exists()
            ):
                self.start_librespot_btn.config(
                    state="normal"
                )
        except tk.TclError:
            pass

        try:
            if (
                hasattr(self, "stop_librespot_btn")
                and self.stop_librespot_btn.winfo_exists()
            ):
                self.stop_librespot_btn.config(
                    state="disabled"
                )
        except tk.TclError:
            pass

    def on_close(self):
        self.stop_librespot_test()
        self.root.destroy()

    def build_step_finish(self):
        f = self.container

        tk.Label(
            f,
            text="Step 4 of 4 - Finish",
            font=("Segoe UI", 13, "bold")
        ).pack(
            anchor="w",
            padx=16,
            pady=(16, 4)
        )

        summary_lines = [
            (
                f"Install folder: "
                f"{self.dest_path.get() or '(not set)'}"
            ),
            (
                "Spotify Client ID: "
                f"{'set' if self.client_id.get() else '(you can add this in the app)'}"
            ),
            (
                f"go-librespot path: "
                f"{self.librespot_path.get() or '(not set)'}"
            )
        ]

        tk.Label(
            f,
            text="\n".join(summary_lines),
            justify="left",
            fg="#333"
        ).pack(
            anchor="w",
            padx=16,
            pady=(0, 12)
        )

        tk.Checkbutton(
            f,
            text="Launch the app now",
            variable=self.launch_after
        ).pack(
            anchor="w",
            padx=16,
            pady=(0, 12)
        )

        row = tk.Frame(f)

        row.pack(
            side="bottom",
            fill="x",
            pady=12,
            padx=16
        )

        tk.Button(
            row,
            text="Back",
            width=10,
            command=self.go_back
        ).pack(
            side="left"
        )

        tk.Button(
            row,
            text="Finish",
            width=12,
            command=self.finish
        ).pack(
            side="right"
        )

    def finish(self):
        if self.librespot_test_proc:
            try:
                self.librespot_test_proc.terminate()
            except Exception:
                pass

            self.librespot_test_proc = None

        save_partial_config(
            client_id=self.client_id.get().strip(),
            client_secret=self.client_secret.get().strip(),
            librespot_path=self.librespot_path.get().strip()
        )

        if self.launch_after.get():
            dest = self.dest_path.get().strip()

            app_dir = find_main_app_directory(
                dest
            ) if dest else None

            app_path = (
                os.path.join(
                    app_dir,
                    "Pyify.py"
                )
                if app_dir
                else None
            )

            if app_path and os.path.exists(app_path):
                try:
                    subprocess.Popen(
                        [
                            sys.executable,
                            app_path
                        ],
                        cwd=app_dir
                    )

                except Exception as e:
                    messagebox.showerror(
                        "Couldn't launch",
                        str(e)
                    )

            else:
                messagebox.showinfo(
                    "Pyify.py not found",
                    (
                        "Couldn't find Pyify.py in the install folder "
                        "to launch automatically. You can run it "
                        "yourself once the files are in place."
                    )
                )

        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    InstallerApp().run()
