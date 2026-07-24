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
from tkinter import BooleanVar, IntVar, StringVar, Tk, filedialog, messagebox
from tkinter import ttk

import uniquify_engine


APP_NAME = "DuckyBruto Uniq"
APP_VERSION = "1.2.0"
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff"}
DEFAULT_SETTINGS = {
    "strength": "instagram",
    "variantsPerVideo": 1,
    "separateCopyFolders": True,
    "moveOriginals": False,
    "processVideos": True,
    "processPhotos": True,
    "capcutMetadata": False,
    "updateManifestUrl": "",
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
        self.status = StringVar(value="Готово")
        self.running = False

        self.build_ui()
        self.refresh_file_list()

    def build_ui(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", font=("Helvetica", 12))
        style.configure("TFrame", background="#10161e")
        style.configure("Panel.TFrame", background="#1a222d")
        style.configure("TLabel", background="#10161e", foreground="#ebf1f7")
        style.configure("Muted.TLabel", background="#10161e", foreground="#96a3b2")
        style.configure("Panel.TLabel", background="#1a222d", foreground="#ebf1f7")
        style.configure("TButton", padding=(12, 8))
        style.configure("Accent.TButton", padding=(14, 10))
        style.configure("TCheckbutton", background="#10161e", foreground="#ebf1f7")

        outer = ttk.Frame(self.root, padding=22)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text=APP_NAME, font=("Helvetica", 24, "bold")).pack(side="left")
        ttk.Label(header, text=f"v{APP_VERSION}", style="Muted.TLabel").pack(side="left", padx=(10, 0))
        ttk.Label(header, textvariable=self.status, style="Muted.TLabel").pack(side="right")

        controls = ttk.Frame(outer, style="Panel.TFrame", padding=16)
        controls.pack(fill="x", pady=(18, 12))
        controls.columnconfigure(3, weight=1)

        ttk.Label(controls, text="Режим", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            controls,
            textvariable=self.strength,
            values=("light", "normal", "strong", "instagram"),
            state="readonly",
            width=16,
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        ttk.Label(controls, text="Копий", style="Panel.TLabel").grid(row=0, column=1, sticky="w", padx=(22, 0))
        ttk.Spinbox(controls, from_=1, to=20, textvariable=self.variants, width=8).grid(
            row=1, column=1, sticky="w", padx=(22, 0), pady=(6, 0)
        )

        ttk.Checkbutton(controls, text="Копии в отдельные папки", variable=self.separate).grid(
            row=1, column=2, sticky="w", padx=(22, 0)
        )
        ttk.Checkbutton(controls, text="Удалять оригинал", variable=self.move_originals).grid(
            row=1, column=3, sticky="w", padx=(22, 0)
        )
        ttk.Checkbutton(controls, text="Видео", variable=self.process_videos).grid(
            row=2, column=0, sticky="w", pady=(12, 0)
        )
        ttk.Checkbutton(controls, text="Фото", variable=self.process_photos).grid(
            row=2, column=1, sticky="w", padx=(22, 0), pady=(12, 0)
        )
        ttk.Checkbutton(controls, text="След CapCut в MP4", variable=self.capcut_metadata).grid(
            row=2, column=2, columnspan=2, sticky="w", padx=(22, 0), pady=(12, 0)
        )

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(0, 12))
        ttk.Button(actions, text="Добавить видео", command=self.add_videos).pack(side="left")
        ttk.Button(actions, text="Добавить фото", command=self.add_photos).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Открыть input", command=lambda: open_path(INPUT_DIR)).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Открыть output", command=lambda: open_path(OUTPUT_DIR)).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Проверить обновления", command=self.check_updates).pack(side="left", padx=(8, 0))
        self.run_button = ttk.Button(actions, text="Уникализировать", style="Accent.TButton", command=self.start)
        self.run_button.pack(side="right")

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)

        files_panel = ttk.Frame(body, style="Panel.TFrame", padding=14)
        files_panel.pack(side="left", fill="both", expand=True, padx=(0, 10))
        ttk.Label(files_panel, text="Файлы в input", style="Panel.TLabel", font=("Helvetica", 14, "bold")).pack(anchor="w")
        self.files_box = ttk.Treeview(files_panel, show="tree", height=12)
        self.files_box.pack(fill="both", expand=True, pady=(10, 0))
        ttk.Button(files_panel, text="Обновить", command=self.refresh_file_list).pack(anchor="w", pady=(10, 0))

        log_panel = ttk.Frame(body, style="Panel.TFrame", padding=14)
        log_panel.pack(side="right", fill="both", expand=True)
        ttk.Label(log_panel, text="Лог", style="Panel.TLabel", font=("Helvetica", 14, "bold")).pack(anchor="w")
        self.log_box = self.make_log_box(log_panel)
        self.log_box.pack(fill="both", expand=True, pady=(10, 0))

    def make_log_box(self, parent):
        from tkinter import Text

        box = Text(parent, wrap="word", height=12, bg="#10161e", fg="#ebf1f7", insertbackground="#ebf1f7", relief="flat")
        box.configure(font=("Menlo", 11))
        return box

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
            self.files_box.insert("", "end", text=f"Видео: {path.relative_to(INPUT_DIR)}")
        for path in photos:
            self.files_box.insert("", "end", text=f"Фото: {path.relative_to(INPUT_DIR)}")
        self.set_status(f"В input: {len(videos)} видео, {len(photos)} фото")

    def add_videos(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Выбери видео",
            filetypes=(("Video files", "*.mp4 *.mov *.m4v *.avi *.mkv *.webm"), ("All files", "*.*")),
        )
        self.add_input_files(paths)

    def add_photos(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Выбери фото",
            filetypes=(("Photo files", "*.jpg *.jpeg *.png *.webp *.heic *.heif *.tif *.tiff"), ("All files", "*.*")),
        )
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
        videos = video_files() if self.process_videos.get() else []
        photos = photo_files() if self.process_photos.get() else []
        if not videos and not photos:
            messagebox.showinfo(APP_NAME, "Положи видео или фото в папку input либо нажми Добавить видео/фото.")
            return
        self.persist_settings()
        self.running = True
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
                        uniquify_engine.uniquify(input_path, out_dir, 1, seed, strength, capcut_metadata)
                    else:
                        uniquify_engine.uniquify_photo(input_path, out_dir, 1, seed, strength)

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
        self.running = False
        self.run_button.configure(state="normal")
        self.refresh_file_list()
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
