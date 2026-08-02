#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

try:
    from PySide6.QtCore import Qt, QThread, Signal, QSize
    from PySide6.QtGui import QAction, QIcon, QPixmap
    from PySide6.QtWidgets import (
        QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
        QLabel, QMainWindow, QMessageBox, QPushButton, QProgressBar, QScrollArea,
        QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
        QHeaderView, QAbstractItemView
    )
except ImportError:
    raise SystemExit("PySide6 не установлен. Запустите Install DuckyBruto Uniq.command")

from uniquify_engine import PHOTO_EXTS, media_duration, uniquify, uniquify_photo

APP_VERSION = "2.0.5"
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
ROOT = Path(os.environ.get("DAYXXX_UNIQUIFIER_ROOT", Path.home() / "Movies" / "day_xxx_uniquifier"))
INPUT = ROOT / "input"
OUTPUT = ROOT / "output"
VIDEOS_OUT = OUTPUT / "videos"
PHOTOS_OUT = OUTPUT / "photos"
PROCESSED = ROOT / "processed"
FAILED = ROOT / "failed"
RESOURCES = Path(__file__).resolve().parent
ICON = RESOURCES / "DuckyBrutoUniq.icns"
SETTINGS_PATH = ROOT / "settings.json"
UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/Delkel/day_xxx_uniquifier/main/update-manifest.json"

for folder in (INPUT, VIDEOS_OUT, PHOTOS_OUT, PROCESSED, FAILED):
    folder.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    defaults = {"updateManifestUrl": UPDATE_MANIFEST_URL}
    if not SETTINGS_PATH.exists():
        SETTINGS_PATH.write_text(json.dumps(defaults, ensure_ascii=False, indent=2), encoding="utf-8")
        return defaults
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    merged = dict(defaults)
    merged.update(data)
    if not str(merged.get("updateManifestUrl") or "").strip():
        merged["updateManifestUrl"] = UPDATE_MANIFEST_URL
    SETTINGS_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def version_tuple(value: str) -> tuple[int, ...]:
    result = []
    for chunk in value.split("."):
        digits = ""
        for char in chunk:
            if char.isdigit():
                digits += char
            else:
                break
        result.append(int(digits or "0"))
    return tuple(result)


def fetch_update_manifest(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "DuckyBruto-Uniq-updater"})
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(512 * 1024)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict) or not data.get("version") or not data.get("zip_url"):
        raise RuntimeError("В update-manifest.json нужны поля version и zip_url")
    return data


def write_update_helper(manifest: dict) -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix="duckybruto_update_"))
    helper = tmp_dir / "update_duckybruto_uniq.command"
    zip_url = shlex.quote(str(manifest["zip_url"]))
    version = shlex.quote(str(manifest["version"]))
    script = f"""#!/bin/bash
set -e
ZIP_URL={zip_url}
VERSION={version}
WORK_DIR="$TMPDIR/duckybruto_uniq_update_$VERSION"
ZIP_FILE="$WORK_DIR/DuckyBruto_Uniq_$VERSION.zip"

echo "DuckyBruto Uniq: ставлю обновление $VERSION"
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"
curl -L --fail -o "$ZIP_FILE" "$ZIP_URL"

if command -v ditto >/dev/null 2>&1; then
  ditto -x -k "$ZIP_FILE" "$WORK_DIR"
else
  unzip -q "$ZIP_FILE" -d "$WORK_DIR"
fi

cd "$WORK_DIR"
if [ -f "Install DuckyBruto Uniq.command" ]; then
  chmod +x "Install DuckyBruto Uniq.command"
  open "Install DuckyBruto Uniq.command"
elif [ -d "DuckyBruto Uniq.app" ]; then
  mkdir -p "$HOME/Applications"
  rm -rf "$HOME/Applications/DuckyBruto Uniq.app"
  cp -R "DuckyBruto Uniq.app" "$HOME/Applications/"
  xattr -dr com.apple.quarantine "$HOME/Applications/DuckyBruto Uniq.app" >/dev/null 2>&1 || true
  open "$HOME/Applications/DuckyBruto Uniq.app"
else
  echo "В архиве не найдено приложение DuckyBruto Uniq.app"
  exit 1
fi
"""
    helper.write_text(script, encoding="utf-8")
    helper.chmod(0o755)
    return helper


def run_command_in_terminal(path: Path):
    subprocess.run([
        "osascript",
        "-e", 'tell application "Terminal" to activate',
        "-e", f'tell application "Terminal" to do script {json.dumps(str(path))}',
    ], check=True)


def fmt_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def fmt_duration(seconds: float) -> str:
    if not seconds:
        return "—"
    return f"{int(seconds)//60:02d}:{int(seconds)%60:02d}"


class Worker(QThread):
    progress = Signal(int, str)
    file_status = Signal(str, str)
    completed = Signal(int, int)
    failed = Signal(str)

    def __init__(self, files: list[Path], copies: int, strength: str, capcut: bool, move_originals: bool):
        super().__init__()
        self.files = files
        self.copies = copies
        self.strength = strength
        self.capcut = capcut
        self.move_originals = move_originals
        self.stop_requested = False

    def stop(self):
        self.stop_requested = True

    def run(self):
        done = 0
        errors = 0
        total = max(1, len(self.files))
        for index, path in enumerate(self.files):
            if self.stop_requested:
                break
            self.file_status.emit(path.name, "Обработка")
            try:
                def update(local: float):
                    overall = int(((index + local) / total) * 100)
                    self.progress.emit(overall, f"Обработка: {path.name}")
                if path.suffix.lower() in PHOTO_EXTS:
                    uniquify_photo(path, PHOTOS_OUT, self.copies, None, self.strength)
                    update(1.0)
                else:
                    uniquify(path, VIDEOS_OUT, self.copies, None, self.strength, self.capcut, update)
                self.file_status.emit(path.name, "Готов")
                done += 1
                if self.move_originals and path.exists():
                    target = PROCESSED / path.name
                    if target.exists():
                        target = PROCESSED / f"{path.stem}_{int(time.time())}{path.suffix}"
                    shutil.move(str(path), str(target))
            except Exception as exc:
                errors += 1
                self.file_status.emit(path.name, "Ошибка")
                self.failed.emit(f"{path.name}: {exc}")
        self.progress.emit(100 if not self.stop_requested else 0, "Готово" if not self.stop_requested else "Остановлено")
        self.completed.emit(done, errors)


class UpdateWorker(QThread):
    checked = Signal(dict)
    failed = Signal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            self.checked.emit(fetch_update_manifest(self.url))
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"DuckyBruto Uniq {APP_VERSION}")
        self.setMinimumSize(1180, 760)
        self.resize(1480, 900)
        if ICON.exists():
            self.setWindowIcon(QIcon(str(ICON)))
        self.files: list[Path] = []
        self.worker: Worker | None = None
        self.update_worker: UpdateWorker | None = None
        self.settings = load_settings()
        self.build_ui()
        self.apply_style()
        self.refresh_files()

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(14)

        sidebar = QFrame(objectName="sidebar")
        sidebar.setFixedWidth(230)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 20, 18, 18)
        side.setSpacing(10)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setFixedSize(54, 54)
        if ICON.exists():
            logo.setPixmap(QIcon(str(ICON)).pixmap(QSize(54, 54)))
        brand.addWidget(logo)
        title = QLabel(f"<b>DuckyBruto</b><br><span style='color:#8b5cf6'>Uniq</span><br><small>{APP_VERSION}</small>")
        title.setObjectName("brand")
        brand.addWidget(title, 1)
        side.addLayout(brand)
        side.addSpacing(18)

        self.add_video_btn = self.side_button("＋  Добавить видео", self.add_video)
        self.add_photo_btn = self.side_button("＋  Добавить фото", self.add_photo)
        self.refresh_btn = self.side_button("↻  Обновить список", self.refresh_files)
        self.open_input_btn = self.side_button("⌂  Открыть input", lambda: self.open_path(INPUT))
        self.open_output_btn = self.side_button("⇩  Открыть output", lambda: self.open_path(OUTPUT))
        self.update_btn = self.side_button("⬆  Проверить обновление", self.check_updates)
        for b in (self.add_video_btn, self.add_photo_btn, self.refresh_btn, self.open_input_btn, self.open_output_btn, self.update_btn):
            side.addWidget(b)
        side.addStretch()
        self.ready = QLabel("●  Готов к работе")
        self.ready.setObjectName("ready")
        side.addWidget(self.ready)
        path_label = QLabel(str(ROOT))
        path_label.setWordWrap(True)
        path_label.setObjectName("muted")
        side.addWidget(path_label)
        outer.addWidget(sidebar)

        center = QFrame(objectName="panel")
        center_l = QVBoxLayout(center)
        center_l.setContentsMargins(20, 18, 20, 18)
        header = QHBoxLayout()
        h = QLabel("Медиафайлы")
        h.setObjectName("h1")
        header.addWidget(h)
        sub = QLabel("Добавьте видео и фото для обработки")
        sub.setObjectName("muted")
        header.addWidget(sub)
        header.addStretch()
        center_l.addLayout(header)

        filters = QHBoxLayout()
        self.all_btn = QPushButton("Все")
        self.video_btn = QPushButton("Видео")
        self.photo_btn = QPushButton("Фото")
        self.clear_photo_btn = QPushButton("Очистить фото")
        self.clear_video_btn = QPushButton("Очистить видео")
        for b in (self.all_btn, self.video_btn, self.photo_btn, self.clear_photo_btn, self.clear_video_btn):
            b.setObjectName("filter")
            filters.addWidget(b)
        self.all_btn.clicked.connect(lambda: self.populate("all"))
        self.video_btn.clicked.connect(lambda: self.populate("video"))
        self.photo_btn.clicked.connect(lambda: self.populate("photo"))
        self.clear_photo_btn.clicked.connect(lambda: self.clear_type("photo"))
        self.clear_video_btn.clicked.connect(lambda: self.clear_type("video"))
        filters.addStretch()
        center_l.addLayout(filters)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Файл", "Тип", "Длительность", "Размер", "Статус"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 5): self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        center_l.addWidget(self.table, 1)
        self.summary = QLabel("0 видео / 0 фото")
        self.summary.setObjectName("muted")
        center_l.addWidget(self.summary)

        progress_card = QFrame(objectName="card")
        progress_l = QVBoxLayout(progress_card)
        top = QHBoxLayout()
        self.progress_title = QLabel("Обработка файлов")
        self.progress_title.setObjectName("h2")
        self.percent = QLabel("0%")
        self.percent.setObjectName("accent")
        top.addWidget(self.progress_title); top.addStretch(); top.addWidget(self.percent)
        progress_l.addLayout(top)
        self.status = QLabel("Ожидание запуска")
        self.status.setObjectName("muted")
        progress_l.addWidget(self.status)
        self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.setTextVisible(False)
        progress_l.addWidget(self.progress)
        center_l.addWidget(progress_card)
        outer.addWidget(center, 1)

        right_scroll = QScrollArea(); right_scroll.setWidgetResizable(True); right_scroll.setFrameShape(QFrame.NoFrame); right_scroll.setFixedWidth(390)
        right = QWidget(); right_l = QVBoxLayout(right); right_l.setContentsMargins(0,0,0,0); right_l.setSpacing(14)
        preview = QFrame(objectName="panel"); pv = QVBoxLayout(preview)
        ph = QLabel("Предпросмотр"); ph.setObjectName("h2"); pv.addWidget(ph)
        pv.addWidget(QLabel("До обработки", objectName="muted"))
        self.before = QLabel("Выберите файл")
        self.before.setObjectName("preview"); self.before.setAlignment(Qt.AlignCenter); self.before.setMinimumHeight(190)
        pv.addWidget(self.before)
        pv.addWidget(QLabel("После обработки", objectName="muted"))
        self.after = QLabel("Результат появится после обработки")
        self.after.setObjectName("preview"); self.after.setAlignment(Qt.AlignCenter); self.after.setMinimumHeight(190)
        pv.addWidget(self.after)
        right_l.addWidget(preview)

        settings = QFrame(objectName="panel"); st = QVBoxLayout(settings)
        sh = QLabel("Настройки обработки"); sh.setObjectName("h2"); st.addWidget(sh)
        st.addWidget(QLabel("Пресет", objectName="muted"))
        self.preset = QComboBox(); self.preset.addItem("Лёгкий", "light"); self.preset.addItem("Обычный", "normal"); self.preset.addItem("Сильный", "strong"); self.preset.addItem("Instagram", "instagram"); self.preset.setCurrentIndex(1)
        st.addWidget(self.preset)
        row = QHBoxLayout(); row.addWidget(QLabel("Копий для каждого файла")); self.copies = QSpinBox(); self.copies.setRange(1, 50); self.copies.setValue(1); row.addWidget(self.copies); st.addLayout(row)
        self.capcut = QCheckBox("Добавлять CapCut-метаданные")
        self.move_originals = QCheckBox("Перемещать исходники в processed")
        st.addWidget(self.capcut); st.addWidget(self.move_originals)
        self.start_btn = QPushButton("▶  Запустить обработку"); self.start_btn.setObjectName("primary"); self.start_btn.clicked.connect(self.start_processing)
        self.stop_btn = QPushButton("■  Остановить после текущего файла"); self.stop_btn.setObjectName("danger"); self.stop_btn.clicked.connect(self.stop_processing); self.stop_btn.setEnabled(False)
        st.addWidget(self.start_btn); st.addWidget(self.stop_btn)
        right_l.addWidget(settings); right_l.addStretch()
        right_scroll.setWidget(right); outer.addWidget(right_scroll)

    def side_button(self, text, fn):
        b = QPushButton(text); b.setObjectName("sideButton"); b.clicked.connect(fn); return b

    def apply_style(self):
        self.setStyleSheet("""
        * { font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', Arial; font-size: 14px; color:#eef2ff; }
        QMainWindow, QWidget { background:#080e17; }
        #sidebar, #panel, #card { background:#0f1825; border:1px solid #1c2939; border-radius:12px; }
        #card { background:#111c2a; }
        #brand { font-size:20px; } #h1 { font-size:28px; font-weight:800; } #h2 { font-size:18px; font-weight:700; }
        #muted { color:#94a3b8; } #ready { color:#34d399; font-weight:700; } #accent { color:#8b5cf6; font-size:18px; font-weight:800; }
        QPushButton { background:#142033; border:1px solid #243249; border-radius:8px; padding:10px 13px; }
        QPushButton:hover { background:#1b2a42; } QPushButton:disabled { color:#596579; }
        #sideButton { text-align:left; background:transparent; border:none; color:#aab6c8; padding:12px 8px; }
        #sideButton:hover { color:white; background:#152137; }
        #filter { min-width:90px; }
        #primary { background:#6d28d9; border:none; font-weight:700; padding:13px; }
        #primary:hover { background:#7c3aed; }
        #danger { color:#fb7185; background:#24141b; border-color:#55202d; }
        QTableWidget { background:#0d1623; border:1px solid #253247; border-radius:8px; gridline-color:#1b2738; selection-background-color:#30245b; }
        QHeaderView::section { background:#111c2c; color:#94a3b8; border:none; border-bottom:1px solid #253247; padding:10px; font-weight:700; }
        QTableWidget::item { padding:9px; border-bottom:1px solid #172334; }
        #preview { background:#172235; border:1px solid #223149; border-radius:8px; color:#94a3b8; }
        QComboBox, QSpinBox { background:#131e2e; border:1px solid #29384f; border-radius:7px; padding:9px; }
        QProgressBar { background:#202b3b; border:none; border-radius:5px; height:10px; }
        QProgressBar::chunk { background:#7c3aed; border-radius:5px; }
        QScrollBar:vertical { background:#0b121d; width:10px; } QScrollBar::handle:vertical { background:#34445b; border-radius:5px; min-height:30px; }
        """)

    def add_video(self): self.add_files(VIDEO_EXTS, "Видео (*.mp4 *.mov *.m4v *.avi *.mkv *.webm)")
    def add_photo(self): self.add_files(PHOTO_EXTS, "Фото (*.jpg *.jpeg *.png *.webp *.heic *.heif *.tif *.tiff)")

    def add_files(self, exts, file_filter):
        names, _ = QFileDialog.getOpenFileNames(self, "Выберите файлы", str(Path.home()), file_filter)
        for name in names:
            src = Path(name); target = INPUT / src.name
            if src.resolve() != target.resolve():
                if target.exists(): target = INPUT / f"{src.stem}_{int(time.time())}{src.suffix}"
                shutil.copy2(src, target)
        self.refresh_files()

    def refresh_files(self):
        self.files = sorted([p for p in INPUT.iterdir() if p.is_file() and p.suffix.lower() in (VIDEO_EXTS | PHOTO_EXTS)])
        self.populate("all")

    def populate(self, mode):
        visible = [p for p in self.files if mode == "all" or (mode == "photo" and p.suffix.lower() in PHOTO_EXTS) or (mode == "video" and p.suffix.lower() in VIDEO_EXTS)]
        self.table.setRowCount(len(visible))
        videos = photos = 0
        for row, p in enumerate(visible):
            photo = p.suffix.lower() in PHOTO_EXTS
            photos += int(photo); videos += int(not photo)
            values = [p.name, "Фото" if photo else "Видео", "—" if photo else fmt_duration(media_duration(p)), fmt_size(p.stat().st_size), "Ожидание"]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val); item.setData(Qt.UserRole, str(p)); self.table.setItem(row, col, item)
        self.summary.setText(f"{videos} видео / {photos} фото     •     {len(list(VIDEOS_OUT.glob('*'))) + len(list(PHOTOS_OUT.glob('*')))} готовых файлов")

    def clear_type(self, kind):
        targets = [p for p in self.files if (p.suffix.lower() in PHOTO_EXTS) == (kind == "photo")]
        if not targets: return
        if QMessageBox.question(self, "Очистить", f"Удалить {len(targets)} файлов из input?") != QMessageBox.Yes: return
        for p in targets: p.unlink(missing_ok=True)
        self.refresh_files()

    def selection_changed(self):
        items = self.table.selectedItems()
        if not items: return
        path = Path(items[0].data(Qt.UserRole))
        pix = self.thumbnail(path)
        if pix:
            self.before.setPixmap(pix.scaled(self.before.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.after.setText("Результат появится после обработки")

    def thumbnail(self, path: Path):
        tmp = Path("/tmp") / f"ducky_preview_{abs(hash(str(path)))}.jpg"
        try:
            if path.suffix.lower() in PHOTO_EXTS:
                cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-frames:v", "1", str(tmp)]
            else:
                cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", "0.2", "-i", str(path), "-frames:v", "1", str(tmp)]
            subprocess.run(cmd, timeout=15)
            return QPixmap(str(tmp)) if tmp.exists() else None
        except Exception:
            return None

    def start_processing(self):
        if not self.files:
            QMessageBox.information(self, "Нет файлов", "Добавьте видео или фото в input.")
            return
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            QMessageBox.critical(self, "Нет FFmpeg", "Запустите установщик зависимостей.")
            return
        self.worker = Worker(self.files.copy(), self.copies.value(), self.preset.currentData(), self.capcut.isChecked(), self.move_originals.isChecked())
        self.worker.progress.connect(self.on_progress)
        self.worker.file_status.connect(self.set_file_status)
        self.worker.failed.connect(lambda e: self.status.setText(e))
        self.worker.completed.connect(self.finished)
        self.start_btn.setEnabled(False); self.stop_btn.setEnabled(True); self.ready.setText("●  Обработка")
        self.worker.start()

    def stop_processing(self):
        if self.worker: self.worker.stop(); self.status.setText("Остановка после текущего файла…")

    def on_progress(self, value, text):
        self.progress.setValue(value); self.percent.setText(f"{value}%"); self.status.setText(text)

    def set_file_status(self, filename, status):
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).text() == filename:
                self.table.item(row, 4).setText(status); break

    def finished(self, done, errors):
        self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False); self.ready.setText("●  Готов к работе")
        self.status.setText(f"Завершено: {done}, ошибок: {errors}")
        self.refresh_files()

    def check_updates(self):
        url = str(self.settings.get("updateManifestUrl") or UPDATE_MANIFEST_URL).strip()
        if not url:
            QMessageBox.information(self, "Обновления", "Ссылка на манифест обновлений не настроена.")
            return
        self.update_btn.setEnabled(False)
        self.ready.setText("●  Проверяю обновление…")
        self.update_worker = UpdateWorker(url)
        self.update_worker.checked.connect(self.on_update_checked)
        self.update_worker.failed.connect(self.on_update_failed)
        self.update_worker.finished.connect(lambda: self.update_btn.setEnabled(True))
        self.update_worker.start()

    def on_update_checked(self, manifest: dict):
        latest = str(manifest.get("version", "0"))
        if version_tuple(latest) <= version_tuple(APP_VERSION):
            self.ready.setText("●  Готов к работе")
            QMessageBox.information(self, "Обновления", f"Установлена актуальная версия {APP_VERSION}.")
            return
        notes = str(manifest.get("notes") or "").strip()
        text = f"Доступна версия {latest}. Установить обновление?"
        if notes:
            text += f"\n\n{notes}"
        self.ready.setText("●  Доступно обновление")
        if QMessageBox.question(self, "Обновление DuckyBruto Uniq", text) != QMessageBox.Yes:
            self.ready.setText("●  Готов к работе")
            return
        try:
            helper = write_update_helper(manifest)
            run_command_in_terminal(helper)
            QApplication.instance().quit()
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка обновления", f"Не удалось подготовить обновление:\n{exc}")
            self.ready.setText("●  Готов к работе")

    def on_update_failed(self, error: str):
        self.update_btn.setEnabled(True)
        self.ready.setText("●  Готов к работе")
        QMessageBox.critical(self, "Ошибка обновления", f"Не удалось проверить обновления:\n{error}")

    def open_path(self, path):
        subprocess.Popen(["open", str(path)])


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("DuckyBruto Uniq")
    app.setStyle("Fusion")
    win = MainWindow(); win.show()
    sys.exit(app.exec())
