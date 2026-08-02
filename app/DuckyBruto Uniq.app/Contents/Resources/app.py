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
APP_VERSION = "1.4.1"
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


def cover_image_path() -> Path:
    return Path(__file__).resolve().with_name("DuckyBrutoCover.png")


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
        self.active_filter = "all"
        self.progress_value = IntVar(value=0)
        self.progress_text = StringVar(value="0%")
        self.preview_temp_dir = Path(tempfile.mkdtemp(prefix="dayxxx_preview_"))
        self.preview_images = {}
        self.cover_image = self.load_cover_image()
        self.selected_input_path: Optional[Path] = None

        self.build_ui()
        self.refresh_file_list()

    def load_cover_image(self) -> Optional[PhotoImage]:
        image_path = cover_image_path()
        if not image_path.exists():
            return None
        try:
            return PhotoImage(file=str(image_path)).subsample(3, 3)
        except Exception:
            return None

    def build_ui(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        colors = {
            "bg": "#0B0F17",
            "surface": "#121925",
            "surface_alt": "#182232",
            "line": "#263348",
            "text": "#F4F7FB",
            "muted": "#8D9AAF",
            "accent": "#6C7CFF",
            "accent_hover": "#8190FF",
            "green": "#31D0AA",
            "danger": "#FF6B7A",
        }
        self.colors = colors

        style.configure(".", font=("Helvetica", 12))
        style.configure("TFrame", background=colors["bg"])
        style.configure("Panel.TFrame", background=colors["surface"])
        style.configure("Card.TFrame", background=colors["surface_alt"])
        style.configure("TLabel", background=colors["bg"], foreground=colors["text"])
        style.configure("Muted.TLabel", background=colors["bg"], foreground=colors["muted"])
        style.configure("Panel.TLabel", background=colors["surface"], foreground=colors["text"])
        style.configure("PanelMuted.TLabel", background=colors["surface"], foreground=colors["muted"])
        style.configure("Card.TLabel", background=colors["surface_alt"], foreground=colors["text"])
        style.configure("CardMuted.TLabel", background=colors["surface_alt"], foreground=colors["muted"])
        style.configure("TButton", padding=(12, 8), borderwidth=0, background=colors["surface_alt"], foreground=colors["text"], font=("Helvetica", 11))
        style.map("TButton", background=[("active", colors["line"])])
        style.configure("Accent.TButton", padding=(18, 12), background=colors["accent"], foreground="#FFFFFF", borderwidth=0, font=("Helvetica", 12, "bold"))
        style.map("Accent.TButton", background=[("active", colors["accent_hover"]), ("disabled", "#3A4357")])
        style.configure("Nav.TButton", padding=(12, 9), borderwidth=0, background=colors["surface"], foreground=colors["muted"], font=("Helvetica", 10, "bold"))
        style.map("Nav.TButton", background=[("active", colors["surface_alt"])], foreground=[("active", colors["text"])])
        style.configure("Pill.TButton", padding=(12, 7), borderwidth=0, background=colors["surface_alt"], foreground=colors["muted"], font=("Helvetica", 10, "bold"))
        style.map("Pill.TButton", background=[("active", colors["line"])], foreground=[("active", colors["text"])])
        style.configure("TCheckbutton", background=colors["surface"], foreground=colors["text"], indicatorcolor=colors["surface_alt"])
        style.map("TCheckbutton", background=[("active", colors["surface"])], indicatorcolor=[("selected", colors["accent"])])
        style.configure("TScale", background=colors["surface"], troughcolor=colors["line"])
        style.configure("TSpinbox", fieldbackground=colors["surface_alt"], background=colors["surface_alt"], foreground=colors["text"], arrowcolor=colors["muted"])
        style.configure("Horizontal.TProgressbar", troughcolor=colors["surface_alt"], background=colors["accent"], borderwidth=0)
        style.configure("Treeview", background=colors["surface"], fieldbackground=colors["surface"], foreground=colors["text"], bordercolor=colors["line"], rowheight=40)
        style.configure("Treeview.Heading", background=colors["surface_alt"], foreground=colors["muted"], font=("Helvetica", 10, "bold"), borderwidth=0)
        style.map("Treeview", background=[("selected", "#26345F")], foreground=[("selected", "#FFFFFF")])

        self.root.configure(bg=colors["bg"])
        self.root.geometry("1180x780")
        self.root.minsize(980, 680)

        outer = ttk.Frame(self.root, padding=0)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        header = ttk.Frame(outer, style="Panel.TFrame", padding=(24, 18))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        if self.cover_image:
            ttk.Label(header, image=self.cover_image, style="Panel.TLabel").grid(row=0, column=0, rowspan=2, sticky="w")
        else:
            ttk.Label(header, text="DB", style="Card.TLabel", foreground=colors["accent"], font=("Helvetica", 15, "bold"), padding=(10, 7)).grid(row=0, column=0, rowspan=2, sticky="w")
        ttk.Label(header, text="DuckyBruto Uniq", style="Panel.TLabel", font=("Helvetica", 16, "bold")).grid(row=0, column=1, sticky="sw", padx=(12, 0))
        ttk.Label(header, text="Пакетная подготовка фото и видео", style="PanelMuted.TLabel", font=("Helvetica", 10)).grid(row=1, column=1, sticky="nw", padx=(12, 0))
        ttk.Button(header, text="Проверить обновления", command=self.check_updates).grid(row=0, column=2, rowspan=2, sticky="e")

        body = ttk.Frame(outer, padding=18)
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(1, weight=1)

        drop = ttk.Frame(body, style="Panel.TFrame", padding=22)
        drop.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
        self.draw_drop_zone(drop)

        settings = ttk.Frame(body, style="Panel.TFrame", padding=22)
        settings.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=(0, 10))
        settings.columnconfigure(0, weight=1)
        ttk.Label(settings, text="Параметры обработки", style="Panel.TLabel", font=("Helvetica", 14, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(settings, text="Интенсивность", style="PanelMuted.TLabel").grid(row=1, column=0, sticky="w", pady=(18, 4))
        scale_row = ttk.Frame(settings, style="Panel.TFrame")
        scale_row.grid(row=2, column=0, sticky="ew")
        scale_row.columnconfigure(0, weight=1)
        ttk.Scale(scale_row, from_=25, to=100, variable=self.strength_percent, command=self.on_strength_change).grid(row=0, column=0, sticky="ew")
        self.strength_label = ttk.Label(scale_row, text=f"{self.strength_percent.get()}%", style="Panel.TLabel", foreground=colors["accent"], font=("Helvetica", 12, "bold"))
        self.strength_label.grid(row=0, column=1, padx=(12, 0))
        ttk.Checkbutton(settings, text="Обрабатывать фото и видео", variable=self.process_all_var(), command=self.toggle_all_media).grid(row=3, column=0, sticky="w", pady=(18, 0))
        ttk.Checkbutton(settings, text="Копии в отдельные папки", variable=self.separate).grid(row=4, column=0, sticky="w", pady=(10, 0))
        ttk.Checkbutton(settings, text="Добавлять CapCut-метаданные", variable=self.capcut_metadata).grid(row=5, column=0, sticky="w", pady=(10, 0))
        copy_row = ttk.Frame(settings, style="Panel.TFrame")
        copy_row.grid(row=6, column=0, sticky="ew", pady=(16, 0))
        copy_row.columnconfigure(1, weight=1)
        ttk.Label(copy_row, text="Количество копий", style="PanelMuted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(copy_row, from_=1, to=20, textvariable=self.variants, width=6).grid(row=0, column=1, sticky="e")
        self.run_button = ttk.Button(settings, text="Запустить обработку", style="Accent.TButton", command=self.start)
        self.run_button.grid(row=7, column=0, sticky="ew", pady=(20, 0))

        files_panel = ttk.Frame(body, style="Panel.TFrame", padding=14)
        files_panel.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        self.filter_bar(files_panel)
        self.files_box = ttk.Treeview(files_panel, columns=("name", "type", "status", "size"), show="headings", height=8)
        for col, title, width in (("name", "Файл", 320), ("type", "Тип", 100), ("status", "Статус", 130), ("size", "Размер", 100)):
            self.files_box.heading(col, text=title)
            self.files_box.column(col, width=width, anchor="w", stretch=True)
        self.files_box.pack(fill="both", expand=True, pady=(12, 0))
        self.files_box.bind("<<TreeviewSelect>>", self.on_file_select)
        totals = ttk.Frame(files_panel, style="Panel.TFrame")
        totals.pack(fill="x", pady=(10, 0))
        ttk.Label(totals, textvariable=self.input_summary, style="PanelMuted.TLabel", font=("Helvetica", 10)).pack(side="left")
        ttk.Label(totals, textvariable=self.output_summary, style="PanelMuted.TLabel", font=("Helvetica", 10)).pack(side="right")

        side = ttk.Frame(body, style="Panel.TFrame")
        side.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        side.rowconfigure(0, weight=1)
        side.columnconfigure(0, weight=1)
        preview_canvas = Canvas(side, bg=colors["surface"], highlightthickness=0, borderwidth=0)
        preview_scroll = ttk.Scrollbar(side, orient="vertical", command=preview_canvas.yview)
        preview_canvas.configure(yscrollcommand=preview_scroll.set)
        preview_canvas.grid(row=0, column=0, sticky="nsew")
        preview_scroll.grid(row=0, column=1, sticky="ns")
        preview_inner = ttk.Frame(preview_canvas, style="Panel.TFrame", padding=16)
        preview_window = preview_canvas.create_window((0, 0), window=preview_inner, anchor="nw")
        preview_inner.columnconfigure(0, weight=1)
        preview_inner.bind("<Configure>", lambda _e: preview_canvas.configure(scrollregion=preview_canvas.bbox("all")))
        preview_canvas.bind("<Configure>", lambda e: preview_canvas.itemconfigure(preview_window, width=e.width))
        preview_canvas.bind_all("<MouseWheel>", lambda e: preview_canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        ttk.Label(preview_inner, text="Превью", style="Panel.TLabel", font=("Helvetica", 14, "bold")).grid(row=0, column=0, sticky="w")
        self.preview_card(preview_inner, "До", 1)
        self.preview_card(preview_inner, "После", 2)

        footer = ttk.Frame(outer, style="Panel.TFrame", padding=(22, 12))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(1, weight=1)
        ttk.Label(footer, text="●", style="Panel.TLabel", foreground=colors["green"], font=("Helvetica", 12, "bold")).grid(row=0, column=0)
        ttk.Label(footer, textvariable=self.status, style="PanelMuted.TLabel").grid(row=0, column=1, sticky="w", padx=(8, 16))
        ttk.Progressbar(footer, variable=self.progress_value, maximum=100, style="Horizontal.TProgressbar", length=220).grid(row=0, column=2, sticky="e")
        ttk.Label(footer, textvariable=self.progress_text, style="PanelMuted.TLabel", width=5).grid(row=0, column=3, padx=(8, 16))
        ttk.Label(footer, text=f"v{APP_VERSION}", style="PanelMuted.TLabel").grid(row=0, column=4)

        self.log_box = self.make_log_box(outer)
    def nav_item(self, parent, icon: str, label: str, column: int, command) -> None:
        button = ttk.Button(parent, text=f"{icon} {label}", style="Nav.TButton", command=command)
        button.grid(row=0, column=column, sticky="w", padx=(0, 28), pady=(10, 8))

    def draw_drop_zone(self, parent) -> None:
        box = ttk.Frame(parent, style="Card.TFrame", padding=30)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text="＋", style="Card.TLabel", foreground=self.colors["accent"], font=("Helvetica", 40, "bold")).pack(pady=(4, 8))
        ttk.Label(box, text="Добавьте материалы", style="Card.TLabel", font=("Helvetica", 17, "bold")).pack()
        ttk.Label(box, text="Фото: JPG, PNG, HEIC  •  Видео: MP4, MOV", style="CardMuted.TLabel", justify="center").pack(pady=(8, 18))
        actions = ttk.Frame(box, style="Card.TFrame")
        actions.pack()
        ttk.Button(actions, text="Добавить фото", command=self.add_photos).pack(side="left")
        ttk.Button(actions, text="Добавить видео", command=self.add_videos).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Открыть input", command=lambda: open_path(INPUT_DIR)).pack(side="left", padx=(8, 0))

    def filter_bar(self, parent) -> None:
        bar = ttk.Frame(parent, style="Panel.TFrame")
        bar.pack(fill="x")
        ttk.Button(bar, text="▧ Фото", style="Pill.TButton", command=lambda: self.set_filter("photo")).pack(side="left")
        ttk.Button(bar, text="▷ Видео", style="Pill.TButton", command=lambda: self.set_filter("video")).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="▦ Все", style="Pill.TButton", command=lambda: self.set_filter("all")).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="Output", style="Small.TButton", command=lambda: open_path(OUTPUT_DIR)).pack(side="right")
        ttk.Button(bar, text="Очистить фото", style="Small.TButton", command=lambda: self.clear_outputs("photo")).pack(side="right", padx=(0, 8))
        ttk.Button(bar, text="Очистить видео", style="Small.TButton", command=lambda: self.clear_outputs("video")).pack(side="right", padx=(0, 8))

    def preview_card(self, parent, title: str, row: int) -> None:
        ttk.Label(parent, text=title, style="PanelMuted.TLabel", font=("Helvetica", 10, "bold")).grid(row=row * 2 - 1, column=0, sticky="w", pady=(12, 4))
        card = ttk.Frame(parent, style="Card.TFrame", padding=18)
        card.grid(row=row * 2, column=0, sticky="nsew")
        image_label = ttk.Label(card, text="Нет файла", style="CardMuted.TLabel", anchor="center", width=36)
        image_label.pack(fill="both", expand=True)
        caption = ttk.Label(card, text="Выбери файл в списке", style="CardMuted.TLabel", font=("Helvetica", 10))
        caption.pack(pady=(6, 0))
        if title == "До":
            self.preview_before_image = image_label
            self.preview_before_caption = caption
        else:
            self.preview_after_image = image_label
            self.preview_after_caption = caption

    def stat_card(self, parent, label: str, value_var: StringVar, column: int) -> None:
        card = ttk.Frame(parent, style="Card.TFrame", padding=(14, 12))
        card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
        ttk.Label(card, text=label.upper(), style="CardMuted.TLabel", font=("Helvetica", 10, "bold")).pack(anchor="w")
        ttk.Label(card, textvariable=value_var, style="Card.TLabel", font=("Helvetica", 13, "bold")).pack(anchor="w", pady=(5, 0))

    def make_log_box(self, parent):
        from tkinter import Text

        box = Text(parent, wrap="word", height=3, bg="#ffffff", fg="#253044", insertbackground="#253044", relief="flat")
        box.configure(font=("Menlo", 10))
        return box

    def process_all_var(self):
        self._process_all = BooleanVar(value=bool(self.process_videos.get() and self.process_photos.get()))
        return self._process_all

    def toggle_all_media(self) -> None:
        value = bool(self._process_all.get())
        self.process_videos.set(value)
        self.process_photos.set(value)

    def set_filter(self, value: str) -> None:
        self.active_filter = value
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
        if self.active_filter in ("all", "video"):
            for path in videos:
                self.files_box.insert("", "end", iid=str(path), values=(path.relative_to(INPUT_DIR), "Видео", "Ожидание", self.file_size_label(path)))
        if self.active_filter in ("all", "photo"):
            for path in photos:
                self.files_box.insert("", "end", iid=str(path), values=(path.relative_to(INPUT_DIR), "Фото", "Ожидание", self.file_size_label(path)))
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
        self.progress_value.set(0)
        self.progress_text.set("0%")
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
            total_jobs = max(1, total_variants * len(all_inputs))
            completed_jobs = 0
            for copy_index in range(1, total_variants + 1):
                if separate:
                    self.root.after(0, lambda c=copy_index: self.log(f"Папка copy_{c:02d}"))
                for file_index, (media_kind, input_path) in enumerate(all_inputs, start=1):
                    label = "видео" if media_kind == "video" else "фото"
                    self.root.after(
                        0,
                        lambda p=input_path, i=file_index, c=copy_index, l=label: self.log(
                            f"[копия {c}/{total_variants}] [{i}/{len(all_inputs)}] {l}: {p.name}"
                        ),
                    )
                    out_dir = unique_output_dir(media_kind, copy_index, separate)
                    seed = random.SystemRandom().randint(100000, 999999999)
                    if media_kind == "video":
                        uniquify_engine.uniquify(
                            input_path, out_dir, 1, seed, strength, capcut_metadata,
                            progress_callback=lambda fraction, base=completed_jobs, total=total_jobs: self.update_job_progress(base, total, fraction),
                        )
                    else:
                        uniquify_engine.uniquify_photo(input_path, out_dir, 1, seed, strength)
                    completed_jobs += 1
                    percent = int(completed_jobs * 100 / total_jobs)
                    self.root.after(0, lambda p=percent: (self.progress_value.set(p), self.progress_text.set(f"{p}%")))

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

    def update_job_progress(self, completed_before: int, total_jobs: int, fraction: float) -> None:
        percent = int(max(0.0, min(1.0, (completed_before + fraction) / max(1, total_jobs))) * 100)
        self.root.after(0, lambda p=percent: (self.progress_value.set(p), self.progress_text.set(f"{p}%")))

    def done(self) -> None:
        self.running = False
        self.run_button.configure(state="normal")
        self.refresh_file_list()
        if self.selected_input_path and self.selected_input_path.exists():
            self.show_previews(self.selected_input_path)
        self.progress_value.set(100)
        self.progress_text.set("100%")
        self.set_status("Готово")
        self.log("Готово. Файлы лежат в output/videos и output/photos.")
        if messagebox.askyesno(APP_NAME, "Готово. Открыть папку с результатами?"):
            open_path(OUTPUT_DIR)

    def fail(self, exc: BaseException) -> None:
        self.running = False
        self.run_button.configure(state="normal")
        self.set_status("Ошибка")
        self.log(f"Ошибка: {exc}")
        messagebox.showerror(APP_NAME, f"Не удалось обработать файлы:\n{exc}")

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
