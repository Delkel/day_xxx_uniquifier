#!/usr/bin/env python3
import json
import os
import platform
import random
import shutil
import subprocess
import threading
import tempfile
import urllib.request
from pathlib import Path
from tkinter import BooleanVar, Canvas, IntVar, PhotoImage, StringVar, Tk, filedialog, messagebox
from tkinter import ttk
from typing import Optional

import uniquify_engine


APP_NAME = "DuckyBruto Uniq"
APP_VERSION = "1.5.1"
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff"}
UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/Delkel/day_xxx_uniquifier/main/update-manifest.json"
DEFAULT_SETTINGS = {
    "strength": "instagram",
    "variantsPerVideo": 1,
    "separateCopyFolders": True,
    "moveOriginals": False,
    "processVideos": True,
    "processPhotos": True,
    "capcutMetadata": False,
    "updateManifestUrl": UPDATE_MANIFEST_URL,
}


def app_root() -> Path:
    env_root = os.environ.get("DAYXXX_UNIQUIFIER_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    bundle_root = Path(__file__).resolve().parents[3]
    home_app = Path.home() / "Applications"
    if str(bundle_root).startswith("/Applications/") or str(bundle_root).startswith(str(home_app) + "/"):
        return (Path.home() / "Movies" / "day_xxx_uniquifier").resolve()
    return bundle_root


ROOT = app_root()
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
VIDEOS_DIR = OUTPUT_DIR / "videos"
PHOTOS_DIR = OUTPUT_DIR / "photos"
PROCESSED_DIR = ROOT / "processed"
FAILED_DIR = ROOT / "failed"
SETTINGS_PATH = ROOT / "settings.json"


def ensure_dirs() -> None:
    for path in (INPUT_DIR, VIDEOS_DIR, PHOTOS_DIR, PROCESSED_DIR, FAILED_DIR):
        path.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        save_settings(DEFAULT_SETTINGS)
        return dict(DEFAULT_SETTINGS)
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_SETTINGS)
    merged = dict(DEFAULT_SETTINGS)
    merged.update(data)
    if not str(merged.get("updateManifestUrl") or "").strip():
        merged["updateManifestUrl"] = UPDATE_MANIFEST_URL
        save_settings(merged)
    return merged


def save_settings(settings: dict) -> None:
    SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def open_path(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if platform.system() == "Darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def dependency_installer() -> Path:
    return Path(__file__).resolve().with_name("install_dependencies.sh")


def install_dependencies_in_terminal() -> None:
    script = dependency_installer()
    if platform.system() == "Darwin":
        subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script quoted form of "{script}"'])
        return
    subprocess.Popen(["sh", str(script)])


def manifest_url(settings: dict) -> str:
    return str(settings.get("updateManifestUrl") or "").strip()


def version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for chunk in value.split("."):
        number = ""
        for char in chunk:
            if char.isdigit():
                number += char
            else:
                break
        parts.append(int(number or "0"))
    return tuple(parts)


def fetch_update_manifest(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "day_xxx-uniquifier-updater"})
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status >= 400:
            raise RuntimeError(f"сервер обновлений ответил {response.status}")
        raw = response.read(512 * 1024)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("manifest должен быть JSON-объектом")
    if not data.get("version") or not data.get("zip_url"):
        raise RuntimeError("в manifest нужны поля version и zip_url")
    return data


def write_update_helper(manifest: dict) -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix="dayxxx_update_"))
    helper = tmp_dir / "update_day_xxx_uniquifier.command"
    zip_url = str(manifest["zip_url"])
    version = str(manifest["version"])
    script = f'''#!/bin/sh
set -eu

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

APP_NAME="{APP_NAME}.app"
OLD_APP_NAME="@day_xxx Uniquifier.app"
ZIP_URL={json.dumps(zip_url)}
VERSION={json.dumps(version)}
WORK_DIR="$(mktemp -d /tmp/dayxxx_update.XXXXXX)"
ZIP_PATH="$WORK_DIR/update.zip"
UNPACK_DIR="$WORK_DIR/unpack"
DEST_DIR="$HOME/Applications"
DEST_APP="$DEST_DIR/$APP_NAME"
OLD_DEST_APP="$DEST_DIR/$OLD_APP_NAME"
BACKUP_APP="$WORK_DIR/$APP_NAME.backup"

echo "== @day_xxx Uniquifier update $VERSION =="
echo "Скачиваю обновление..."
curl -fL "$ZIP_URL" -o "$ZIP_PATH"

echo "Распаковываю..."
mkdir -p "$UNPACK_DIR"
ditto -x -k "$ZIP_PATH" "$UNPACK_DIR"

SRC_APP="$(find "$UNPACK_DIR" -maxdepth 3 -name "$APP_NAME" -type d | head -n 1)"
if [ -z "$SRC_APP" ]; then
  echo "В архиве не найдено $APP_NAME"
  read -r -p "Нажми Enter, чтобы закрыть окно..." _
  exit 1
fi

echo "Ставлю зависимости..."
DAYXXX_NO_PAUSE=1 sh "$SRC_APP/Contents/Resources/install_dependencies.sh" || true

echo "Обновляю приложение в $DEST_DIR..."
mkdir -p "$DEST_DIR"
if [ -d "$OLD_DEST_APP" ]; then
  rm -rf "$OLD_DEST_APP"
fi
if [ -d "$DEST_APP" ]; then
  mv "$DEST_APP" "$BACKUP_APP"
fi
cp -R "$SRC_APP" "$DEST_APP"
chmod +x "$DEST_APP/Contents/MacOS/day_xxx_uniquifier"
chmod +x "$DEST_APP/Contents/Resources/install_dependencies.sh"
xattr -dr com.apple.quarantine "$DEST_APP" 2>/dev/null || true

echo "Готово. Открываю новую версию."
open "$DEST_APP"
read -r -p "Нажми Enter, чтобы закрыть окно..." _
'''
    helper.write_text(script, encoding="utf-8")
    helper.chmod(0o755)
    return helper


def run_command_in_terminal(path: Path) -> None:
    if platform.system() == "Darwin":
        subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script quoted form of "{path}"'])
        return
    subprocess.Popen(["sh", str(path)])


def video_files() -> list[Path]:
    if not INPUT_DIR.exists():
        return []
    return sorted(path for path in INPUT_DIR.rglob("*") if path.is_file() and path.suffix.lower() in VIDEO_EXTS)


def photo_files() -> list[Path]:
    if not INPUT_DIR.exists():
        return []
    return sorted(path for path in INPUT_DIR.rglob("*") if path.is_file() and path.suffix.lower() in PHOTO_EXTS)


def unique_output_dir(media_kind: str, index: int, separate: bool) -> Path:
    base_dir = PHOTOS_DIR if media_kind == "photo" else VIDEOS_DIR
    if separate:
        return base_dir / f"copy_{index:02d}"
    return base_dir


def count_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.rglob("*") if item.is_file())


class App:
    def __init__(self) -> None:
        ensure_dirs()
        self.settings = load_settings()
        self.root = Tk()
        self.root.title(APP_NAME)
        self.root.minsize(780, 560)
        self.root.configure(bg="#10161e")

        self.strength = StringVar(value=self.settings.get("strength", "instagram"))
        self.variants = IntVar(value=int(self.settings.get("variantsPerVideo", 1)))
        self.separate = BooleanVar(value=bool(self.settings.get("separateCopyFolders", True)))
        self.move_originals = BooleanVar(value=bool(self.settings.get("moveOriginals", False)))
        self.process_videos = BooleanVar(value=bool(self.settings.get("processVideos", True)))
        self.process_photos = BooleanVar(value=bool(self.settings.get("processPhotos", True)))
        self.capcut_metadata = BooleanVar(value=bool(self.settings.get("capcutMetadata", False)))
        self.strength_percent = IntVar(value=self.percent_from_strength(self.strength.get()))
        self.status = StringVar(value="Готово")
        self.input_summary = StringVar(value="0 видео / 0 фото")
        self.output_summary = StringVar(value="0 готовых файлов")
        self.root_dir_summary = StringVar(value=str(ROOT))
        self.running = False
        self.progress = IntVar(value=0)
        self.progress_text = StringVar(value="0%")
        self.current_file = StringVar(value="Ожидание запуска")
        self.preview_temp_dir = Path(tempfile.mkdtemp(prefix="dayxxx_preview_"))
        self.preview_images = {}
        self.selected_input_path: Optional[Path] = None

        self.build_ui()
        self.refresh_file_list()

    def build_ui(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        colors = {
            "bg": "#080d14", "sidebar": "#0d141e", "surface": "#101925",
            "card": "#142030", "line": "#223044", "text": "#f4f6fb",
            "muted": "#8f9aad", "accent": "#6c3cff", "accent_hover": "#7b50ff",
            "green": "#37d67a", "danger": "#ff5f57",
        }
        self.colors = colors
        style.configure(".", font=("Helvetica", 11))
        style.configure("TFrame", background=colors["bg"])
        style.configure("Sidebar.TFrame", background=colors["sidebar"])
        style.configure("Panel.TFrame", background=colors["surface"])
        style.configure("Card.TFrame", background=colors["card"])
        style.configure("TLabel", background=colors["bg"], foreground=colors["text"])
        style.configure("Sidebar.TLabel", background=colors["sidebar"], foreground=colors["text"])
        style.configure("Panel.TLabel", background=colors["surface"], foreground=colors["text"])
        style.configure("PanelMuted.TLabel", background=colors["surface"], foreground=colors["muted"])
        style.configure("Card.TLabel", background=colors["card"], foreground=colors["text"])
        style.configure("CardMuted.TLabel", background=colors["card"], foreground=colors["muted"])
        style.configure("TButton", padding=(12, 8), background=colors["card"], foreground=colors["text"], borderwidth=0)
        style.map("TButton", background=[("active", colors["line"])])
        style.configure("Accent.TButton", padding=(18, 12), background=colors["accent"], foreground="#ffffff", borderwidth=0, font=("Helvetica", 11, "bold"))
        style.map("Accent.TButton", background=[("active", colors["accent_hover"]), ("disabled", "#394255")])
        style.configure("Nav.TButton", padding=(12, 10), background=colors["sidebar"], foreground=colors["muted"], borderwidth=0, anchor="w")
        style.map("Nav.TButton", background=[("active", "#1c1740")], foreground=[("active", "#ffffff")])
        style.configure("TCheckbutton", background=colors["surface"], foreground=colors["text"], indicatorcolor=colors["card"])
        style.map("TCheckbutton", background=[("active", colors["surface"])])
        style.configure("TScale", background=colors["surface"], troughcolor=colors["line"])
        style.configure("TSpinbox", fieldbackground=colors["card"], foreground=colors["text"], arrowcolor=colors["text"])
        style.configure("Treeview", background=colors["surface"], fieldbackground=colors["surface"], foreground=colors["text"], borderwidth=0, rowheight=44)
        style.configure("Treeview.Heading", background=colors["card"], foreground=colors["muted"], borderwidth=0, font=("Helvetica", 10, "bold"))
        style.map("Treeview", background=[("selected", "#27204b")], foreground=[("selected", "#ffffff")])
        style.configure("Horizontal.TProgressbar", troughcolor=colors["line"], background=colors["accent"], borderwidth=0)

        self.root.configure(bg=colors["bg"])
        self.root.geometry("1380x820")
        self.root.minsize(1080, 680)
        try:
            icon_path = Path(__file__).resolve().with_name("DuckyBrutoCover.png")
            if icon_path.exists():
                self.app_icon = PhotoImage(file=str(icon_path))
                self.root.iconphoto(True, self.app_icon)
        except Exception:
            pass

        shell = ttk.Frame(self.root, style="TFrame")
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(shell, style="Sidebar.TFrame", padding=18, width=220)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        logo = ttk.Frame(sidebar, style="Sidebar.TFrame")
        logo.pack(fill="x", pady=(8, 28))
        brand_row = ttk.Frame(logo, style="Sidebar.TFrame")
        brand_row.pack(fill="x")
        try:
            logo_path = Path(__file__).resolve().with_name("DuckyBrutoCover.png")
            if logo_path.exists():
                self.logo_image = PhotoImage(file=str(logo_path)).subsample(4, 4)
                ttk.Label(brand_row, image=self.logo_image, style="Sidebar.TLabel").pack(side="left")
        except Exception:
            pass
        brand_text = ttk.Frame(brand_row, style="Sidebar.TFrame")
        brand_text.pack(side="left", padx=(10, 0))
        ttk.Label(brand_text, text="DuckyBruto", style="Sidebar.TLabel", font=("Helvetica", 18, "bold")).pack(anchor="w")
        ttk.Label(brand_text, text="Uniq", style="Sidebar.TLabel", foreground=colors["accent"], font=("Helvetica", 18, "bold")).pack(anchor="w")
        ttk.Label(logo, text=f"Версия {APP_VERSION}", style="Sidebar.TLabel", foreground=colors["muted"], font=("Helvetica", 9)).pack(anchor="w", pady=(4, 0))

        for text, command in (
            ("＋  Добавить видео", self.add_videos), ("＋  Добавить фото", self.add_photos),
            ("↻  Обновить список", self.refresh_file_list), ("⌂  Открыть input", lambda: open_path(INPUT_DIR)),
            ("⇩  Открыть output", lambda: open_path(OUTPUT_DIR)), ("⬆  Проверить обновление", self.check_updates),
        ):
            ttk.Button(sidebar, text=text, style="Nav.TButton", command=command).pack(fill="x", pady=3)
        ttk.Frame(sidebar, style="Sidebar.TFrame").pack(fill="both", expand=True)
        ttk.Label(sidebar, text="●  Готов к работе", style="Sidebar.TLabel", foreground=colors["green"]).pack(anchor="w", pady=(0, 8))
        ttk.Label(sidebar, textvariable=self.root_dir_summary, style="Sidebar.TLabel", foreground=colors["muted"], wraplength=180, font=("Helvetica", 8)).pack(anchor="w")

        main = ttk.Frame(shell, style="TFrame", padding=16)
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(1, weight=1)

        header = ttk.Frame(main, style="TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(2, 14))
        ttk.Label(header, text="Медиафайлы", font=("Helvetica", 22, "bold")).pack(side="left")
        ttk.Label(header, text="Добавьте видео и фото для обработки", foreground=colors["muted"]).pack(side="left", padx=(14, 0), pady=(7, 0))

        left = ttk.Frame(main, style="Panel.TFrame", padding=16)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)
        toolbar = ttk.Frame(left, style="Panel.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Button(toolbar, text="Все", command=lambda: self.set_filter("all")).pack(side="left")
        ttk.Button(toolbar, text="Видео", command=lambda: self.set_filter("video")).pack(side="left", padx=6)
        ttk.Button(toolbar, text="Фото", command=lambda: self.set_filter("photo")).pack(side="left")
        ttk.Button(toolbar, text="Очистить видео", command=lambda: self.clear_outputs("video")).pack(side="right")
        ttk.Button(toolbar, text="Очистить фото", command=lambda: self.clear_outputs("photo")).pack(side="right", padx=6)

        tree_wrap = ttk.Frame(left, style="Panel.TFrame")
        tree_wrap.grid(row=1, column=0, sticky="nsew")
        tree_wrap.rowconfigure(0, weight=1); tree_wrap.columnconfigure(0, weight=1)
        self.files_box = ttk.Treeview(tree_wrap, columns=("name", "type", "status", "size"), show="headings")
        for col, title, width in (("name", "Файл", 360), ("type", "Тип", 100), ("status", "Статус", 130), ("size", "Размер", 100)):
            self.files_box.heading(col, text=title); self.files_box.column(col, width=width, anchor="w", stretch=True)
        scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.files_box.yview)
        self.files_box.configure(yscrollcommand=scroll.set)
        self.files_box.grid(row=0, column=0, sticky="nsew"); scroll.grid(row=0, column=1, sticky="ns")
        self.files_box.bind("<<TreeviewSelect>>", self.on_file_select)
        totals = ttk.Frame(left, style="Panel.TFrame")
        totals.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ttk.Label(totals, textvariable=self.input_summary, style="PanelMuted.TLabel").pack(side="left")
        ttk.Label(totals, textvariable=self.output_summary, style="PanelMuted.TLabel").pack(side="right")

        right_host = ttk.Frame(main, style="TFrame")
        right_host.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        right_host.rowconfigure(0, weight=1); right_host.columnconfigure(0, weight=1)
        canvas = Canvas(right_host, bg=colors["bg"], highlightthickness=0)
        rscroll = ttk.Scrollbar(right_host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=rscroll.set)
        canvas.grid(row=0, column=0, sticky="nsew"); rscroll.grid(row=0, column=1, sticky="ns")
        right = ttk.Frame(canvas, style="TFrame")
        window_id = canvas.create_window((0, 0), window=right, anchor="nw")
        right.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

        preview = ttk.Frame(right, style="Panel.TFrame", padding=16)
        preview.pack(fill="x", pady=(0, 12))
        ttk.Label(preview, text="Предпросмотр", style="Panel.TLabel", font=("Helvetica", 14, "bold")).pack(anchor="w")
        self.preview_card(preview, "До обработки", 1)
        self.preview_card(preview, "После обработки", 2)

        settings = ttk.Frame(right, style="Panel.TFrame", padding=16)
        settings.pack(fill="x", pady=(0, 12))
        ttk.Label(settings, text="Настройки обработки", style="Panel.TLabel", font=("Helvetica", 14, "bold")).pack(anchor="w", pady=(0, 12))
        row = ttk.Frame(settings, style="Panel.TFrame"); row.pack(fill="x")
        ttk.Label(row, text="Сила", style="PanelMuted.TLabel").pack(side="left")
        self.strength_label = ttk.Label(row, text=f"{self.strength_percent.get()}%", style="Panel.TLabel", foreground=colors["accent"], font=("Helvetica", 11, "bold")); self.strength_label.pack(side="right")
        ttk.Scale(settings, from_=25, to=100, variable=self.strength_percent, command=self.on_strength_change).pack(fill="x", pady=(6, 12))
        ttk.Checkbutton(settings, text="Обрабатывать видео", variable=self.process_videos).pack(anchor="w", pady=3)
        ttk.Checkbutton(settings, text="Обрабатывать фото", variable=self.process_photos).pack(anchor="w", pady=3)
        ttk.Checkbutton(settings, text="Копии в отдельные папки", variable=self.separate).pack(anchor="w", pady=3)
        ttk.Checkbutton(settings, text="Переместить исходники после обработки", variable=self.move_originals).pack(anchor="w", pady=3)
        ttk.Checkbutton(settings, text="Добавлять CapCut-метаданные", variable=self.capcut_metadata).pack(anchor="w", pady=3)
        copies = ttk.Frame(settings, style="Panel.TFrame"); copies.pack(fill="x", pady=(12, 8))
        ttk.Label(copies, text="Копий для каждого файла", style="PanelMuted.TLabel").pack(side="left")
        ttk.Spinbox(copies, from_=1, to=20, textvariable=self.variants, width=5).pack(side="right")
        self.run_button = ttk.Button(settings, text="▶  Запустить обработку", style="Accent.TButton", command=self.start)
        self.run_button.pack(fill="x", pady=(10, 0))

        progress_panel = ttk.Frame(main, style="Panel.TFrame", padding=14)
        progress_panel.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        top = ttk.Frame(progress_panel, style="Panel.TFrame"); top.pack(fill="x")
        ttk.Label(top, text="Обработка файлов", style="Panel.TLabel", font=("Helvetica", 12, "bold")).pack(side="left")
        ttk.Label(top, textvariable=self.progress_text, style="Panel.TLabel", foreground=colors["accent"], font=("Helvetica", 12, "bold")).pack(side="right")
        ttk.Label(progress_panel, textvariable=self.current_file, style="PanelMuted.TLabel").pack(anchor="w", pady=(6, 6))
        self.progress_bar = ttk.Progressbar(progress_panel, maximum=100, variable=self.progress, style="Horizontal.TProgressbar")
        self.progress_bar.pack(fill="x")
        status_row = ttk.Frame(progress_panel, style="Panel.TFrame"); status_row.pack(fill="x", pady=(8, 0))
        ttk.Label(status_row, textvariable=self.status, style="PanelMuted.TLabel").pack(side="left")
        ttk.Label(status_row, text=f"DuckyBruto Uniq {APP_VERSION}", style="PanelMuted.TLabel").pack(side="right")

        self.log_box = self.make_log_box(main)

    def preview_card(self, parent, title: str, row: int) -> None:
        ttk.Label(parent, text=title, style="PanelMuted.TLabel", font=("Helvetica", 10, "bold")).pack(anchor="w", pady=(12 if row == 1 else 16, 5))
        card = ttk.Frame(parent, style="Card.TFrame", padding=10)
        card.pack(fill="x")
        image_label = ttk.Label(card, text="Нет превью", style="CardMuted.TLabel", anchor="center")
        image_label.pack(fill="both", expand=True, ipady=22)
        caption = ttk.Label(card, text="Выбери файл в списке", style="CardMuted.TLabel", font=("Helvetica", 9))
        caption.pack(pady=(6, 0))
        if row == 1:
            self.preview_before_image = image_label; self.preview_before_caption = caption
        else:
            self.preview_after_image = image_label; self.preview_after_caption = caption

    def make_log_box(self, parent):
        from tkinter import Text
        box = Text(parent, wrap="word", height=3, bg=self.colors["surface"], fg=self.colors["muted"], insertbackground=self.colors["text"], relief="flat")
        box.configure(font=("Menlo", 9))
        return box

    def process_all_var(self):
        self._process_all = BooleanVar(value=bool(self.process_videos.get() and self.process_photos.get()))
        return self._process_all

    def toggle_all_media(self) -> None:
        value = bool(self._process_all.get())
        self.process_videos.set(value)
        self.process_photos.set(value)

    def set_filter(self, value: str) -> None:
        if value == "photo":
            self.process_photos.set(True)
            self.process_videos.set(False)
        elif value == "video":
            self.process_photos.set(False)
            self.process_videos.set(True)
        else:
            self.process_photos.set(True)
            self.process_videos.set(True)
        if hasattr(self, "_process_all"):
            self._process_all.set(bool(self.process_videos.get() and self.process_photos.get()))
        self.refresh_file_list()

    def percent_from_strength(self, value: str) -> int:
        return {"light": 35, "normal": 55, "strong": 75, "instagram": 75}.get(value, 75)

    def strength_from_percent(self) -> str:
        value = int(self.strength_percent.get())
        if value < 45:
            return "light"
        if value < 65:
            return "normal"
        if value < 85:
            return "strong"
        return "instagram"

    def on_strength_change(self, _value=None) -> None:
        value = int(float(self.strength_percent.get()))
        self.strength_percent.set(value)
        self.strength.set(self.strength_from_percent())
        if hasattr(self, "strength_label"):
            self.strength_label.configure(text=f"{value}%")

    def log(self, text: str) -> None:
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")

    def set_status(self, text: str) -> None:
        self.status.set(text)
        self.root.update_idletasks()

    def refresh_file_list(self) -> None:
        self.files_box.delete(*self.files_box.get_children())
        videos = video_files()
        photos = photo_files()
        for path in videos:
            self.files_box.insert("", "end", iid=str(path), values=(path.relative_to(INPUT_DIR), "▷ Видео", "Ожидание", self.file_size_label(path)))
        for path in photos:
            self.files_box.insert("", "end", iid=str(path), values=(path.relative_to(INPUT_DIR), "▧ Фото", "Ожидание", self.file_size_label(path)))
        self.input_summary.set(f"{len(videos)} видео / {len(photos)} фото")
        output_total = count_files(VIDEOS_DIR) + count_files(PHOTOS_DIR)
        self.output_summary.set(f"{output_total} готовых файлов")
        self.set_status(f"В input: {len(videos)} видео, {len(photos)} фото")
        if self.selected_input_path and self.selected_input_path.exists():
            self.show_previews(self.selected_input_path)
        elif videos or photos:
            first = (videos + photos)[0]
            self.files_box.selection_set(str(first))
            self.files_box.focus(str(first))
            self.show_previews(first)
        else:
            self.selected_input_path = None
            self.clear_previews()

    def on_file_select(self, _event=None) -> None:
        selection = self.files_box.selection()
        if not selection:
            return
        path = Path(selection[0])
        if path.exists():
            self.show_previews(path)

    def show_previews(self, input_path: Path) -> None:
        self.selected_input_path = input_path
        before = self.render_preview(input_path, "before")
        self.set_preview("before", before, input_path.name)
        output_path = self.find_latest_output(input_path)
        if output_path:
            after = self.render_preview(output_path, "after")
            self.set_preview("after", after, output_path.name)
        else:
            self.set_preview("after", None, "После обработки появится тут")

    def clear_previews(self) -> None:
        self.set_preview("before", None, "Выбери файл в списке")
        self.set_preview("after", None, "После обработки появится тут")

    def set_preview(self, slot: str, image_path: Optional[Path], caption: str) -> None:
        image_label = self.preview_before_image if slot == "before" else self.preview_after_image
        caption_label = self.preview_before_caption if slot == "before" else self.preview_after_caption
        if not image_path:
            image_label.configure(image="", text="Нет превью")
            caption_label.configure(text=caption)
            self.preview_images.pop(slot, None)
            return
        try:
            image = PhotoImage(file=str(image_path))
        except BaseException:
            image_label.configure(image="", text="Не удалось открыть превью")
            caption_label.configure(text=caption)
            self.preview_images.pop(slot, None)
            return
        self.preview_images[slot] = image
        image_label.configure(image=image, text="")
        caption_label.configure(text=caption)

    def render_preview(self, media_path: Path, slot: str) -> Optional[Path]:
        if not shutil.which("ffmpeg"):
            return None
        output_path = self.preview_temp_dir / f"{slot}.png"
        filters = "scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2:color=white"
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
        ]
        if media_path.suffix.lower() in VIDEO_EXTS:
            cmd += ["-ss", "00:00:00.5"]
        cmd += [
            "-i",
            str(media_path),
            "-frames:v",
            "1",
            "-vf",
            filters,
            str(output_path),
        ]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
        except BaseException:
            return None
        if result.returncode != 0 or not output_path.exists():
            return None
        return output_path

    def find_latest_output(self, input_path: Path) -> Optional[Path]:
        media_kind = "photo" if input_path.suffix.lower() in PHOTO_EXTS else "video"
        base_dir = PHOTOS_DIR if media_kind == "photo" else VIDEOS_DIR
        if not base_dir.exists():
            return None
        candidates = [
            path
            for path in base_dir.rglob("*")
            if path.is_file()
            and path.stem.startswith(f"{input_path.stem}_unique_")
            and path.suffix.lower() in (PHOTO_EXTS if media_kind == "photo" else VIDEO_EXTS)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda path: path.stat().st_mtime)

    def file_size_label(self, path: Path) -> str:
        size = path.stat().st_size
        if size >= 1024 * 1024:
            return f"{size / 1024 / 1024:.1f} MB"
        if size >= 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size} B"

    def add_videos(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Выбери видео",
            filetypes=(("Video files", "*.mp4 *.mov *.m4v *.avi *.mkv *.webm"), ("All files", "*.*")),
        )
        if paths:
            self.process_videos.set(True)
        self.add_input_files(paths)

    def add_photos(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Выбери фото",
            filetypes=(("Photo files", "*.jpg *.jpeg *.png *.webp *.heic *.heif *.tif *.tiff"), ("All files", "*.*")),
        )
        if paths:
            self.process_photos.set(True)
        self.add_input_files(paths)

    def add_input_files(self, paths) -> None:
        if not paths:
            return
        INPUT_DIR.mkdir(parents=True, exist_ok=True)
        for raw in paths:
            src = Path(raw)
            dst = INPUT_DIR / src.name
            suffix = 1
            while dst.exists():
                dst = INPUT_DIR / f"{src.stem}_{suffix}{src.suffix}"
                suffix += 1
            shutil.copy2(src, dst)
            self.log(f"Добавлено: {dst.name}")
        self.refresh_file_list()

    def clear_outputs(self, media_kind: str) -> None:
        if self.running:
            messagebox.showinfo(APP_NAME, "Сначала дождись окончания обработки.")
            return

        if media_kind == "photo":
            target_dir = PHOTOS_DIR
            label = "готовые фото"
        else:
            target_dir = VIDEOS_DIR
            label = "готовые видео"

        total = count_files(target_dir)
        if total == 0:
            messagebox.showinfo(APP_NAME, f"В папке с результатами нет файлов: {label}.")
            return

        if not messagebox.askyesno(
            APP_NAME,
            f"Удалить все {label}?\n\nБудет очищена только папка:\n{target_dir}\n\nИсходники в input не трогаю.",
        ):
            return

        shutil.rmtree(target_dir, ignore_errors=True)
        target_dir.mkdir(parents=True, exist_ok=True)
        self.log(f"Очищено: {label} ({total} файлов)")
        self.set_status("Результаты очищены")

    def persist_settings(self) -> None:
        settings = dict(self.settings)
        settings.update({
            "strength": self.strength.get(),
            "variantsPerVideo": max(1, int(self.variants.get())),
            "separateCopyFolders": bool(self.separate.get()),
            "moveOriginals": bool(self.move_originals.get()),
            "processVideos": bool(self.process_videos.get()),
            "processPhotos": bool(self.process_photos.get()),
            "capcutMetadata": bool(self.capcut_metadata.get()),
            "updateManifestUrl": manifest_url(self.settings),
        })
        save_settings(settings)
        self.settings = settings

    def check_updates(self) -> None:
        url = manifest_url(self.settings)
        if not url:
            messagebox.showinfo(
                APP_NAME,
                "Ссылка на обновления пока не настроена. Когда GitHub-репозиторий будет готов, я впишу updateManifestUrl в settings.json.",
            )
            return
        self.set_status("Проверяю обновления...")
        threading.Thread(target=self.check_updates_worker, args=(url,), daemon=True).start()

    def check_updates_worker(self, url: str) -> None:
        try:
            manifest = fetch_update_manifest(url)
            latest = str(manifest["version"])
            if version_tuple(latest) <= version_tuple(APP_VERSION):
                self.root.after(0, lambda: self.set_status("Версия актуальна"))
                self.root.after(0, lambda: messagebox.showinfo(APP_NAME, f"У тебя уже свежая версия: {APP_VERSION}"))
                return
            notes = str(manifest.get("notes") or "").strip()
            text = f"Доступна версия {latest}. Установить сейчас?"
            if notes:
                text += f"\n\n{notes}"
            self.root.after(0, lambda: self.offer_update(manifest, text))
        except BaseException as exc:
            self.root.after(0, lambda: self.set_status("Ошибка обновления"))
            self.root.after(0, lambda exc=exc: messagebox.showerror(APP_NAME, f"Не удалось проверить обновления:\n{exc}"))

    def offer_update(self, manifest: dict, text: str) -> None:
        self.set_status("Есть обновление")
        if not messagebox.askyesno(APP_NAME, text):
            return
        try:
            helper = write_update_helper(manifest)
        except BaseException as exc:
            messagebox.showerror(APP_NAME, f"Не удалось подготовить обновление:\n{exc}")
            return
        run_command_in_terminal(helper)
        self.root.after(800, self.root.destroy)

    def start(self) -> None:
        if self.running:
            return
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            if messagebox.askyesno(
                APP_NAME,
                "Нужен FFmpeg. Поставить автоматически через Homebrew? После установки запусти обработку снова.",
            ):
                install_dependencies_in_terminal()
            return
        selected_videos = bool(self.process_videos.get())
        selected_photos = bool(self.process_photos.get())
        process_all = not selected_videos and not selected_photos
        videos = video_files() if process_all or selected_videos else []
        photos = photo_files() if process_all or selected_photos else []
        if not videos and not photos:
            messagebox.showinfo(APP_NAME, "Положи видео или фото в папку input либо нажми Добавить видео/фото.")
            return
        self.persist_settings()
        self.running = True
        self.progress.set(0)
        self.progress_text.set("0%")
        self.current_file.set("Подготовка...")
        self.run_button.configure(state="disabled")
        threading.Thread(target=self.process_files, args=(videos, photos), daemon=True).start()

    def process_files(self, videos: list[Path], photos: list[Path]) -> None:
        try:
            total_variants = max(1, int(self.variants.get()))
            strength = self.strength.get()
            separate = bool(self.separate.get())
            move_originals = bool(self.move_originals.get())
            capcut_metadata = bool(self.capcut_metadata.get())
            self.root.after(0, lambda: self.set_status("Обработка..."))

            all_inputs = [("video", path) for path in videos] + [("photo", path) for path in photos]
            total_jobs = max(1, len(all_inputs) * total_variants)
            completed_jobs = 0
            for copy_index in range(1, total_variants + 1):
                if separate:
                    self.root.after(0, lambda c=copy_index: self.log(f"Папка copy_{c:02d}"))
                for file_index, (media_kind, input_path) in enumerate(all_inputs, start=1):
                    label = "видео" if media_kind == "video" else "фото"
                    self.root.after(0, lambda p=input_path: self.current_file.set(p.name))
                    self.root.after(
                        0,
                        lambda p=input_path, i=file_index, c=copy_index, l=label: self.log(
                            f"[копия {c}/{total_variants}] [{i}/{len(all_inputs)}] {l}: {p.name}"
                        ),
                    )
                    out_dir = unique_output_dir(media_kind, copy_index, separate)
                    seed = random.SystemRandom().randint(100000, 999999999)
                    if media_kind == "video":
                        def update_inner_progress(value: float, completed=completed_jobs) -> None:
                            overall = ((completed + max(0.0, min(1.0, value))) / total_jobs) * 100
                            percent = min(99, int(overall))
                            self.root.after(
                                0,
                                lambda v=percent: (self.progress.set(v), self.progress_text.set(f"{v}%")),
                            )

                        uniquify_engine.uniquify(
                            input_path,
                            out_dir,
                            1,
                            seed,
                            strength,
                            capcut_metadata,
                            progress_callback=update_inner_progress,
                        )
                    else:
                        uniquify_engine.uniquify_photo(input_path, out_dir, 1, seed, strength)
                    completed_jobs += 1
                    percent = int(completed_jobs * 100 / total_jobs)
                    self.root.after(0, lambda v=percent: (self.progress.set(v), self.progress_text.set(f"{v}%")))

            if move_originals:
                moved_dir = PROCESSED_DIR / "deleted_originals"
                moved_dir.mkdir(parents=True, exist_ok=True)
                for input_path in [path for _, path in all_inputs]:
                    if not input_path.exists():
                        continue
                    dst = moved_dir / input_path.name
                    suffix = 1
                    while dst.exists():
                        dst = moved_dir / f"{input_path.stem}_{suffix}{input_path.suffix}"
                        suffix += 1
                    shutil.move(str(input_path), str(dst))

            self.root.after(0, self.done)
        except BaseException as exc:
            self.root.after(0, lambda exc=exc: self.fail(exc))

    def done(self) -> None:
        self.progress.set(100)
        self.progress_text.set("100%")
        self.current_file.set("Обработка завершена")
        self.running = False
        self.run_button.configure(state="normal")
        self.refresh_file_list()
        if self.selected_input_path and self.selected_input_path.exists():
            self.show_previews(self.selected_input_path)
        self.set_status("Готово")
        self.log("Готово. Файлы лежат в output/videos и output/photos.")
        if messagebox.askyesno(APP_NAME, "Готово. Открыть папку с результатами?"):
            open_path(OUTPUT_DIR)

    def fail(self, exc: BaseException) -> None:
        self.current_file.set("Ошибка обработки")
        self.running = False
        self.run_button.configure(state="normal")
        self.set_status("Ошибка")
        self.log(f"Ошибка: {exc}")
        messagebox.showerror(APP_NAME, f"Не удалось обработать файлы:\n{exc}")

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
