#!/usr/bin/env python3
from __future__ import annotations

import json, os, platform, shutil, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

try:
    from PySide6.QtCore import Qt, QThread, Signal, QSize, QRectF, QPropertyAnimation, QEasingCurve
    from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
    from PySide6.QtWidgets import (
        QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
        QLabel, QMainWindow, QMessageBox, QPushButton, QProgressBar, QScrollArea,
        QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
        QHeaderView, QAbstractItemView
    )
except ImportError:
    raise SystemExit("PySide6 не установлен. Запустите установщик Enki Agency Uniq")

from uniquify_engine import PHOTO_EXTS, media_duration, uniquify, uniquify_photo

APP_VERSION = "2.5.1"
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
DEFAULT_MEDIA_ROOT = (Path.home() / "Videos" / "Enki Agency Uniq") if platform.system()=="Windows" else (Path.home() / "Movies" / "Enki Agency Uniq")
ROOT = Path(os.environ.get("ENKI_UNIQ_ROOT", DEFAULT_MEDIA_ROOT))
INPUT, OUTPUT = ROOT / "input", ROOT / "output"
VIDEOS_OUT, PHOTOS_OUT = OUTPUT / "videos", OUTPUT / "photos"
FAILED = ROOT / "failed"
RESOURCES = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ICON = RESOURCES / ("EnkiAgencyUniq.ico" if platform.system()=="Windows" else "EnkiAgencyUniq.icns")
LOGO = RESOURCES / "EnkiAgencyUniq.png"
if platform.system()=="Windows" and getattr(sys, "frozen", False):
    os.environ["PATH"] = str(Path(sys.executable).resolve().parent) + os.pathsep + os.environ.get("PATH","")
SETTINGS_PATH = ROOT / "settings.json"
UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/Delkel/day_xxx_uniquifier/main/update-manifest.json"
for folder in (INPUT, VIDEOS_OUT, PHOTOS_OUT, FAILED): folder.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    defaults = {"updateManifestUrl": UPDATE_MANIFEST_URL, "preset": "instagram", "copies": 1,
                "capcut": False, "deleteOriginal": False, "separateFolders": False, "processAudio": True, "compressVideo": False, "compressionLevel": "25"}
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8")) if SETTINGS_PATH.exists() else {}
        if not isinstance(data, dict): data = {}
    except Exception: data = {}
    merged = defaults | data
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def save_settings(data: dict) -> None:
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def version_tuple(value: str) -> tuple[int, ...]:
    out=[]
    for chunk in value.split('.'):
        digits=''.join(c for c in chunk if c.isdigit())
        out.append(int(digits or 0))
    return tuple(out)


def fetch_update_manifest(url: str) -> dict:
    req=urllib.request.Request(url, headers={"User-Agent":"Enki-Agency-Uniq-updater"})
    with urllib.request.urlopen(req, timeout=20) as r: data=json.loads(r.read(512*1024).decode())
    if not isinstance(data,dict) or not data.get('version'):
        raise RuntimeError("В манифесте отсутствует version")
    if isinstance(data.get("platforms"), dict):
        key="windows" if platform.system()=="Windows" else "macos"
        asset=data["platforms"].get(key) or {}
        if not asset.get("url"):
            raise RuntimeError(f"В манифесте нет сборки для {key}")
        data=dict(data); data["_asset"]=asset; data["_platform"]=key
        return data
    if data.get("zip_url"):
        data=dict(data); data["_asset"]={"url":data["zip_url"]}; data["_platform"]="macos"
        return data
    raise RuntimeError("В манифесте отсутствует ссылка на обновление")


def write_update_helper(manifest: dict) -> Path:
    asset=manifest.get("_asset") or {}
    url=str(asset.get("url") or "")
    kind=str(asset.get("type") or "").lower()
    if not url:
        raise RuntimeError("Не найдена ссылка на обновление")
    d=Path(tempfile.mkdtemp(prefix='enki_update_'))

    if platform.system()=="Windows":
        # Preferred Windows release format: signed/user-level Setup.exe.
        if kind in {"setup","exe","installer"} or url.lower().endswith(".exe"):
            p=d/'update.ps1'
            ps = """$ErrorActionPreference = "Stop"
$setup = Join-Path $env:TEMP ("Enki_Agency_Uniq_Update_" + [guid]::NewGuid().ToString("N") + ".exe")
Invoke-WebRequest -Uri "__URL__" -OutFile $setup
Start-Process -FilePath $setup -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CLOSEAPPLICATIONS','/RESTARTAPPLICATIONS' -Wait
"""
            p.write_text(ps.replace("__URL__", url), encoding='utf-8')
            return p

        # Backward-compatible Windows ZIP update.
        p=d/'update.ps1'
        ps = """$ErrorActionPreference = "Stop"
$work = Join-Path $env:TEMP ("enki_update_" + [guid]::NewGuid().ToString("N"))
$zip = Join-Path $work "update.zip"
$unpack = Join-Path $work "unpack"
New-Item -ItemType Directory -Force -Path $unpack | Out-Null
Invoke-WebRequest -Uri "__URL__" -OutFile $zip
Expand-Archive -Path $zip -DestinationPath $unpack -Force
$src = Get-ChildItem -Path $unpack -Recurse -Filter "Enki Agency Uniq.exe" | Select-Object -First 1
if (-not $src) { throw "Enki Agency Uniq.exe не найден в обновлении" }
$srcDir = $src.Directory.FullName
$dst = Join-Path $env:LOCALAPPDATA "Programs\\Enki Agency Uniq"
Start-Sleep -Seconds 2
if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item -Recurse -Force (Join-Path $srcDir "*") $dst
Start-Process (Join-Path $dst "Enki Agency Uniq.exe")
"""
        p.write_text(ps.replace("__URL__", url), encoding='utf-8')
        return p

    p=d/'update.command'
    sh = """#!/bin/sh
set -eu
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
W="$(mktemp -d /tmp/enki_update.XXXXXX)"; Z="$W/update.zip"; U="$W/unpack"; D="$HOME/Applications"; A="$D/Enki Agency Uniq.app"
curl -fL "__URL__" -o "$Z"
mkdir -p "$U"; ditto -x -k "$Z" "$U"
S="$(find "$U" -maxdepth 5 -name 'Enki Agency Uniq.app' -type d | head -n 1)"
[ -n "$S" ] || { echo 'Приложение не найдено в архиве'; exit 1; }
chmod +x "$S/Contents/MacOS/enki_agency_uniq" "$S/Contents/Resources/bootstrap.sh" 2>/dev/null || true
/bin/bash "$S/Contents/Resources/bootstrap.sh"
mkdir -p "$D"; rm -rf "$A"; ditto "$S" "$A"
chmod +x "$A/Contents/MacOS/enki_agency_uniq" "$A/Contents/Resources/bootstrap.sh"
xattr -dr com.apple.quarantine "$A" 2>/dev/null || true
open "$A"
"""
    p.write_text(sh.replace("__URL__", url), encoding='utf-8'); p.chmod(0o755); return p


def run_command_in_terminal(path: Path):
    if platform.system()=="Darwin":
        esc=str(path).replace('"','\\\\"')
        subprocess.Popen(["osascript","-e",f'tell application "Terminal" to do script quoted form of "{esc}"'])
    elif platform.system()=="Windows":
        subprocess.Popen(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(path)])
    else:
        subprocess.Popen(["sh",str(path)])


class UpdateWorker(QThread):
    checked=Signal(dict); failed=Signal(str)
    def __init__(self,url): super().__init__(); self.url=url
    def run(self):
        try: self.checked.emit(fetch_update_manifest(self.url))
        except Exception as e: self.failed.emit(str(e))


class Switch(QCheckBox):
    def __init__(self,text="",parent=None):
        super().__init__(text,parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(34)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setToolTip(text)

    def hitButton(self, pos):
        # Вся строка и сам ползунок являются кликабельными.
        return self.rect().contains(pos)

    def mousePressEvent(self,event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            self.toggle()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        track=QRectF(self.width()-52,6,46,24)
        if self.isChecked():
            p.setBrush(QColor("#d5a552"))
        elif self.underMouse():
            p.setBrush(QColor("#53483a"))
        else:
            p.setBrush(QColor("#3b352c"))
        p.drawRoundedRect(track,12,12)
        knob_x=track.right()-21 if self.isChecked() else track.left()+3
        p.setBrush(QColor("#f4efe6")); p.drawEllipse(QRectF(knob_x,9,18,18))
        p.setPen(QColor("#f1ece2")); p.drawText(QRectF(0,0,self.width()-64,self.height()), Qt.AlignVCenter|Qt.AlignLeft, self.text())


def fmt_size(n:int)->str: return f"{n/1024:.0f} KB" if n<1048576 else f"{n/1048576:.1f} MB"
def fmt_duration(s:float)->str: return "—" if not s else f"{int(s)//60:02d}:{int(s)%60:02d}"


class Worker(QThread):
    progress=Signal(int,str); file_status=Signal(str,str); completed=Signal(int,int); failed=Signal(str)
    def __init__(self,files,copies,strength,capcut,delete_originals,separate_folders,process_audio,compression_target_mb):
        super().__init__(); self.files=files; self.copies=copies; self.strength=strength; self.capcut=capcut
        self.delete_originals=delete_originals; self.separate_folders=separate_folders; self.process_audio=process_audio; self.compression_target_mb=compression_target_mb; self.stop_requested=False
    def stop(self): self.stop_requested=True
    def run(self):
        done=errors=0; total=max(1,len(self.files))
        for idx,path in enumerate(self.files):
            if self.stop_requested: break
            self.file_status.emit(path.name,"Обработка")
            try:
                def upd(local): self.progress.emit(int(((idx+local)/total)*100),f"Обработка: {path.name}")
                if path.suffix.lower() in PHOTO_EXTS:
                    uniquify_photo(path,PHOTOS_OUT,self.copies,None,self.strength,self.separate_folders); upd(1.0)
                else:
                    uniquify(path,VIDEOS_OUT,self.copies,None,self.strength,self.capcut,upd,self.separate_folders,self.process_audio,self.compression_target_mb)
                self.file_status.emit(path.name,"Готов"); done+=1
                if self.delete_originals and path.exists(): path.unlink()
            except Exception as e:
                errors+=1; self.file_status.emit(path.name,"Ошибка"); self.failed.emit(f"{path.name}: {e}")
        self.progress.emit(100 if not self.stop_requested else 0,"Готово" if not self.stop_requested else "Остановлено")
        self.completed.emit(done,errors)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle(f"Enki Agency Uniq {APP_VERSION}"); self.setMinimumSize(1180,760); self.resize(1480,900)
        if ICON.exists(): self.setWindowIcon(QIcon(str(ICON)))
        self.files=[]; self.mode='all'; self.worker=None; self.update_worker=None; self.settings=load_settings()
        self.build_ui(); self.apply_style(); self.refresh_files()

    def build_ui(self):
        root=QWidget(); self.setCentralWidget(root); outer=QHBoxLayout(root); outer.setContentsMargins(14,14,14,14); outer.setSpacing(14)
        sidebar=QFrame(objectName='sidebar'); sidebar.setFixedWidth(255); side=QVBoxLayout(sidebar); side.setContentsMargins(18,18,18,18); side.setSpacing(8)
        logo=QLabel(objectName='logo'); logo.setFixedHeight(170); logo.setAlignment(Qt.AlignCenter)
        if LOGO.exists(): logo.setPixmap(QPixmap(str(LOGO)).scaled(220,158,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        side.addWidget(logo)
        side.addSpacing(10)
        actions=[
            ("＋  Добавить видео",self.add_video),("＋  Добавить фото",self.add_photo),("↻  Обновить очередь",self.refresh_files),
            ("⌂  Открыть папку исходников",lambda:self.open_path(INPUT)),("⇩  Открыть папку результатов",lambda:self.open_path(OUTPUT)),
            ("⌫  Удалить готовые фото",lambda:self.clear_outputs('photo')),("⌫  Удалить готовые видео",lambda:self.clear_outputs('video')),
            ("⬆  Проверить обновления",self.check_updates)]
        self.update_btn=None
        for text,fn in actions:
            b=self.side_button(text,fn); side.addWidget(b)
            if 'обновления' in text.lower(): self.update_btn=b
        side.addStretch()
        self.ready=QLabel("●  Готов к работе",objectName='ready'); side.addWidget(self.ready)
        footer=QFrame(objectName='brandFooter'); footer_l=QVBoxLayout(footer); footer_l.setContentsMargins(0,12,0,0); footer_l.setSpacing(2)
        footer_l.addWidget(QLabel("<b>ENKI AGENCY</b>  <span style='color:#d5a552'>UNIQ</span>",objectName='footerBrand'))
        footer_l.addWidget(QLabel(f"Версия {APP_VERSION}",objectName='footerText'))
        footer_l.addWidget(QLabel("by DuckyBruto · @day_xxx",objectName='footerText'))
        side.addWidget(footer)
        outer.addWidget(sidebar)

        center=QFrame(objectName='panel'); cl=QVBoxLayout(center); cl.setContentsMargins(20,18,20,18)
        head=QHBoxLayout(); h=QLabel('Файлы',objectName='h1'); head.addWidget(h); head.addWidget(QLabel('Фото и видео для обработки',objectName='muted')); head.addStretch(); cl.addLayout(head)
        filters=QHBoxLayout(); self.all_btn=QPushButton('Все'); self.video_btn=QPushButton('Видео'); self.photo_btn=QPushButton('Фото')
        for mode,b in [('all',self.all_btn),('video',self.video_btn),('photo',self.photo_btn)]:
            b.setObjectName('filter'); b.clicked.connect(lambda _,m=mode:self.set_mode(m)); filters.addWidget(b)
        filters.addStretch(); cl.addLayout(filters)
        self.table=QTableWidget(0,5); self.table.setHorizontalHeaderLabels(['Файл','Тип','Длительность','Размер','Статус'])
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        for c in range(1,5): self.table.horizontalHeader().setSectionResizeMode(c,QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setSelectionMode(QAbstractItemView.SingleSelection); self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self.selection_changed); cl.addWidget(self.table,1)
        self.summary=QLabel('0 видео / 0 фото',objectName='muted'); cl.addWidget(self.summary)
        card=QFrame(objectName='card'); pl=QVBoxLayout(card); top=QHBoxLayout(); top.addWidget(QLabel('Обработка файлов',objectName='h2')); top.addStretch(); self.percent=QLabel('0%',objectName='accent'); top.addWidget(self.percent); pl.addLayout(top)
        self.status=QLabel('Ожидание запуска',objectName='muted'); pl.addWidget(self.status); self.progress=QProgressBar(); self.progress.setRange(0,100); self.progress.setTextVisible(False); pl.addWidget(self.progress); cl.addWidget(card); outer.addWidget(center,1)

        rs=QScrollArea(); rs.setWidgetResizable(True); rs.setFrameShape(QFrame.NoFrame); rs.setFixedWidth(410); rw=QWidget(); rl=QVBoxLayout(rw); rl.setContentsMargins(0,0,0,0); rl.setSpacing(14)
        preview=QFrame(objectName='panel'); pv=QVBoxLayout(preview); pv.addWidget(QLabel('Предпросмотр',objectName='h2')); pv.addWidget(QLabel('До обработки',objectName='muted'))
        self.before=QLabel('Выберите файл',objectName='preview'); self.before.setAlignment(Qt.AlignCenter); self.before.setMinimumHeight(260); pv.addWidget(self.before); rl.addWidget(preview)
        settings=QFrame(objectName='panel'); st=QVBoxLayout(settings); st.addWidget(QLabel('Параметры',objectName='h2')); st.addWidget(QLabel('Сила уникализации',objectName='muted'))
        self.preset=QComboBox(); self.preset.addItem('Лёгкая','light'); self.preset.addItem('Средняя','normal'); self.preset.addItem('Максимальная (Inst) — рекомендуется','instagram')
        idx=max(0,self.preset.findData(self.settings.get('preset','instagram'))); self.preset.setCurrentIndex(idx); self.preset.setToolTip('Максимальная (Inst) — основной профиль для публикации в Instagram')
        st.addWidget(self.preset)
        row=QHBoxLayout(); row.addWidget(QLabel('Копий для каждого файла')); self.copies=QSpinBox(); self.copies.setRange(1,50); self.copies.setValue(int(self.settings.get('copies',1))); row.addWidget(self.copies); st.addLayout(row)
        self.capcut=Switch('Добавлять CapCut-метаданные'); self.capcut.setChecked(bool(self.settings.get('capcut',False)))
        self.delete_originals=Switch('Удалить исходник после обработки'); self.delete_originals.setChecked(bool(self.settings.get('deleteOriginal',False)))
        self.separate_folders=Switch('Разложить копии по отдельным папкам'); self.separate_folders.setChecked(bool(self.settings.get('separateFolders',False)))
        self.process_audio=Switch('Обрабатывать звук'); self.process_audio.setChecked(bool(self.settings.get('processAudio',True)))
        self.process_audio.setToolTip('Создавать новый аудиопоток, сохраняя звучание максимально близким к оригиналу')
        self.compress_video=Switch('Сжимать размер видео'); self.compress_video.setChecked(bool(self.settings.get('compressVideo',False)))
        self.compress_video.setToolTip('Ограничить размер готового видео выбранным уровнем')
        for w in (self.capcut,self.delete_originals,self.separate_folders,self.process_audio,self.compress_video): st.addWidget(w)
        comp_row=QHBoxLayout(); comp_row.addWidget(QLabel('Уровень сжатия'))
        self.compression=QComboBox()
        self.compression.addItem('Лёгкое — до 50 МБ','50')
        self.compression.addItem('Среднее — до 25 МБ','25')
        self.compression.addItem('Максимальное — до 10 МБ','10')
        cidx=max(0,self.compression.findData(str(self.settings.get('compressionLevel','25')))); self.compression.setCurrentIndex(cidx)
        self.compression.setEnabled(self.compress_video.isChecked())
        self.compress_video.toggled.connect(self.compression.setEnabled)
        self.compression.setToolTip('Чем меньше лимит, тем сильнее может снизиться качество длинного видео')
        comp_row.addWidget(self.compression); st.addLayout(comp_row)
        self.start_btn=QPushButton('▶  Обработать',objectName='primary'); self.start_btn.clicked.connect(self.start_processing)
        self.stop_btn=QPushButton('■  Остановить после текущего файла',objectName='danger'); self.stop_btn.clicked.connect(self.stop_processing); self.stop_btn.setEnabled(False)
        st.addWidget(self.start_btn); st.addWidget(self.stop_btn); rl.addWidget(settings); rl.addStretch(); rs.setWidget(rw); outer.addWidget(rs)

    def side_button(self,text,fn): b=QPushButton(text,objectName='sideButton'); b.clicked.connect(fn); return b
    def apply_style(self):
        self.setStyleSheet("""
        *{font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display',Arial;font-size:14px;color:#eee8dc}
        QMainWindow,QWidget{background:#050505}
        #sidebar,#panel,#card{background:#0d0c0b;border:1px solid #3a2d1b;border-radius:15px}
        #sidebar{background:#0b0a09}
        #card{background:#11100e}
        #logo{background:#070707;border:1px solid #221b12;border-radius:8px;padding:6px}
        #brandFooter{border-top:1px solid #302416;background:transparent;border-radius:0}
        #footerBrand{font-size:16px;letter-spacing:.4px}
        #footerText{font-size:12px;color:#b6aa99}
        #h1{font-size:30px;font-weight:800}
        #h2{font-size:19px;font-weight:750}
        #muted{color:#a69b8c}
        #ready{color:#63bea0;font-weight:750;padding:8px 2px}
        #accent{color:#d5a552;font-size:18px;font-weight:850}
        QPushButton{background:#15130f;border:1px solid #44341f;border-radius:10px;padding:11px 14px}
        QPushButton:hover{background:#211b13;border-color:#a47b3d}
        QPushButton:pressed{background:#2d2418}
        QPushButton:disabled{color:#61594f;border-color:#29241d}
        #sideButton{text-align:left;background:transparent;border:none;color:#cfc5b7;padding:12px 10px;border-radius:9px}
        #sideButton:hover{color:#fff8ea;background:#1b1711}
        #filter{min-width:118px;background:#12110e;border:1px solid #4a3821}
        #filter[active='true']{background:#d5a552;color:#090807;font-weight:850;border-color:#d5a552}
        #primary{color:#0b0906;background:#d5a552;border:none;font-weight:850;padding:15px}
        #primary:hover{background:#e2ba75}
        #primary:pressed{background:#bd8e43}
        #danger{color:#ee9a91;background:#24100e;border-color:#6a2d25;padding:13px}
        #danger:hover{background:#321512;border-color:#9b4136}
        QTableWidget{background:#080807;border:1px solid #35291a;border-radius:10px;gridline-color:#201a13;selection-background-color:#4b3820}
        QHeaderView::section{background:#12100d;color:#bcb09f;border:none;border-bottom:1px solid #3a2d1b;padding:11px;font-weight:750}
        QTableWidget::item{padding:10px;border-bottom:1px solid #211b14}
        #preview{background:#11100d;border:1px solid #3b2e1d;border-radius:12px;color:#9f9587}
        QComboBox,QSpinBox{background:#12100d;border:1px solid #4b3922;border-radius:9px;padding:10px}
        QComboBox:hover,QSpinBox:hover{border-color:#9b743a}
        QComboBox::drop-down{border:none;width:28px}
        QProgressBar{background:#292219;border:1px solid #3a2d1b;border-radius:6px;height:12px}
        QProgressBar::chunk{background:#d5a552;border-radius:5px}
        QScrollBar:vertical{background:#080807;width:10px;margin:2px}
        QScrollBar::handle:vertical{background:#4d3c27;border-radius:5px;min-height:30px}
        QScrollBar::handle:vertical:hover{background:#755a34}
        """)
    def add_video(self): self.add_files(VIDEO_EXTS,'Видео (*.mp4 *.mov *.m4v *.avi *.mkv *.webm)')
    def add_photo(self): self.add_files(PHOTO_EXTS,'Фото (*.jpg *.jpeg *.png *.webp *.heic *.heif *.tif *.tiff)')
    def add_files(self,exts,flt):
        names,_=QFileDialog.getOpenFileNames(self,'Выберите файлы',str(Path.home()),flt)
        for name in names:
            src=Path(name); target=INPUT/src.name
            if src.resolve()!=target.resolve():
                if target.exists(): target=INPUT/f"{src.stem}_{int(time.time())}{src.suffix}"
                shutil.copy2(src,target)
        self.refresh_files()
    def refresh_files(self):
        self.files=sorted(p for p in INPUT.iterdir() if p.is_file() and p.suffix.lower() in (VIDEO_EXTS|PHOTO_EXTS)); self.populate()
    def set_mode(self,mode): self.mode=mode; self.populate()
    def visible_files(self): return [p for p in self.files if self.mode=='all' or (self.mode=='photo' and p.suffix.lower() in PHOTO_EXTS) or (self.mode=='video' and p.suffix.lower() in VIDEO_EXTS)]
    def populate(self):
        visible=self.visible_files(); self.table.setRowCount(len(visible)); videos=photos=0
        for b,m in ((self.all_btn,'all'),(self.video_btn,'video'),(self.photo_btn,'photo')):
            b.setProperty('active',self.mode==m); b.style().unpolish(b); b.style().polish(b)
        for r,p in enumerate(visible):
            photo=p.suffix.lower() in PHOTO_EXTS; photos+=photo; videos+=not photo
            vals=[p.name,'Фото' if photo else 'Видео','—' if photo else fmt_duration(media_duration(p)),fmt_size(p.stat().st_size),'Ожидание']
            for c,v in enumerate(vals): item=QTableWidgetItem(str(v)); item.setData(Qt.UserRole,str(p)); self.table.setItem(r,c,item)
        ready=sum(1 for p in OUTPUT.rglob('*') if p.is_file()); self.summary.setText(f"{videos} видео / {photos} фото     •     {ready} готовых файлов")
    def clear_outputs(self,kind):
        folder=PHOTOS_OUT if kind=='photo' else VIDEOS_OUT; label='фото' if kind=='photo' else 'видео'; files=[p for p in folder.rglob('*') if p.is_file()]
        if not files: QMessageBox.information(self,'Готовые файлы',f'Готовых {label} нет.'); return
        if QMessageBox.question(self,'Удалить готовые файлы',f'Удалить {len(files)} готовых {label}?')!=QMessageBox.Yes:return
        for p in files: p.unlink(missing_ok=True)
        for d in sorted([p for p in folder.rglob('*') if p.is_dir()],reverse=True):
            try:d.rmdir()
            except OSError:pass
        self.populate()
    def selection_changed(self):
        items=self.table.selectedItems()
        if not items:return
        pix=self.thumbnail(Path(items[0].data(Qt.UserRole)))
        if pix:self.before.setPixmap(pix.scaled(self.before.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))
    def thumbnail(self,path):
        tmp=Path('/tmp')/f"enki_preview_{abs(hash(str(path)))}.jpg"
        try:
            cmd=['ffmpeg','-y','-loglevel','error']+(['-ss','0.2'] if path.suffix.lower() not in PHOTO_EXTS else [])+['-i',str(path),'-frames:v','1',str(tmp)]
            subprocess.run(cmd,timeout=15); return QPixmap(str(tmp)) if tmp.exists() else None
        except Exception:return None
    def compression_warning(self, files, target_mb):
        if not target_mb:
            return True
        videos=[p for p in files if p.suffix.lower() in VIDEO_EXTS]
        if not videos:
            return True
        warnings=[]
        for path in videos:
            try:
                d=max(1.0, media_duration(path))
                total_kbps=(target_mb*1024*1024*8*0.93/d)/1000
                audio_kbps=96 if target_mb<=25 else 128
                video_kbps=max(1,total_kbps-audio_kbps)
                if video_kbps < 650:
                    warnings.append(f"• {path.name}: очень сильное сжатие, качество может заметно снизиться")
                elif video_kbps < 1100:
                    warnings.append(f"• {path.name}: возможно заметное снижение качества")
            except Exception:
                pass
        if target_mb == 10 and not warnings:
            warnings.append("• Режим до 10 МБ использует максимальное сжатие и на длинных роликах может ухудшить детализацию.")
        if warnings:
            msg="Выбран лимит до %d МБ.\n\n%s\n\nПродолжить обработку?" % (target_mb, "\n".join(warnings[:6]))
            return QMessageBox.warning(self,'Предупреждение о сжатии',msg,QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes
        return True

    def start_processing(self):
        files=self.visible_files()
        if not files: QMessageBox.information(self,'Нет файлов','В выбранном режиме нет файлов для обработки.'); return
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'): QMessageBox.critical(self,'Нет FFmpeg','Запустите установщик зависимостей.'); return
        target_mb=int(self.compression.currentData()) if self.compress_video.isChecked() else None
        if not self.compression_warning(files,target_mb): return
        self.settings.update({'preset':self.preset.currentData(),'copies':self.copies.value(),'capcut':self.capcut.isChecked(),'deleteOriginal':self.delete_originals.isChecked(),'separateFolders':self.separate_folders.isChecked(),'processAudio':self.process_audio.isChecked(),'compressVideo':self.compress_video.isChecked(),'compressionLevel':self.compression.currentData()}); save_settings(self.settings)
        self.worker=Worker(files,self.copies.value(),self.preset.currentData(),self.capcut.isChecked(),self.delete_originals.isChecked(),self.separate_folders.isChecked(),self.process_audio.isChecked(),target_mb)
        self.worker.progress.connect(self.on_progress); self.worker.file_status.connect(self.set_file_status); self.worker.failed.connect(lambda e:self.status.setText(e)); self.worker.completed.connect(self.finished)
        self.start_btn.setEnabled(False); self.stop_btn.setEnabled(True); self.ready.setText('●  Обработка'); self.worker.start()
    def stop_processing(self):
        if self.worker:self.worker.stop();self.status.setText('Остановка после текущего файла…')
    def on_progress(self,v,t): self.progress.setValue(v);self.percent.setText(f'{v}%');self.status.setText(t)
    def set_file_status(self,name,status):
        for r in range(self.table.rowCount()):
            if self.table.item(r,0).text()==name:self.table.item(r,4).setText(status);break
    def finished(self,done,errors): self.start_btn.setEnabled(True);self.stop_btn.setEnabled(False);self.ready.setText('●  Готов к работе');self.status.setText(f'Завершено: {done}, ошибок: {errors}');self.refresh_files()
    def check_updates(self):
        url=str(self.settings.get('updateManifestUrl') or UPDATE_MANIFEST_URL).strip(); self.update_btn.setEnabled(False);self.ready.setText('●  Проверяю обновление…');self.update_worker=UpdateWorker(url)
        self.update_worker.checked.connect(self.on_update_checked);self.update_worker.failed.connect(self.on_update_failed);self.update_worker.finished.connect(lambda:self.update_btn.setEnabled(True));self.update_worker.start()
    def on_update_checked(self,m):
        latest=str(m.get('version','0'))
        if version_tuple(latest)<=version_tuple(APP_VERSION):self.ready.setText('●  Готов к работе');QMessageBox.information(self,'Обновления',f'Установлена актуальная версия {APP_VERSION}.');return
        text=f'Доступна версия {latest}. Установить обновление?'; notes=str(m.get('notes') or '').strip(); text+=f'\n\n{notes}' if notes else ''
        if QMessageBox.question(self,'Обновление Enki Agency Uniq',text)!=QMessageBox.Yes:self.ready.setText('●  Готов к работе');return
        try:run_command_in_terminal(write_update_helper(m));QApplication.instance().quit()
        except Exception as e:QMessageBox.critical(self,'Ошибка обновления',str(e));self.ready.setText('●  Готов к работе')
    def on_update_failed(self,e):self.update_btn.setEnabled(True);self.ready.setText('●  Готов к работе');QMessageBox.critical(self,'Ошибка обновления',f'Не удалось проверить обновления:\n{e}')
    def open_path(self,path):
        if platform.system()=="Windows": os.startfile(str(path))
        elif platform.system()=="Darwin": subprocess.Popen(['open',str(path)])
        else: subprocess.Popen(['xdg-open',str(path)])

if __name__=='__main__':
    app=QApplication(sys.argv); app.setApplicationName('Enki Agency Uniq'); app.setStyle('Fusion'); win=MainWindow(); win.show(); sys.exit(app.exec())
