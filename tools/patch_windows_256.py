from pathlib import Path
import re

p = Path('win/app.py')
s = p.read_text(encoding='utf-8')

s = re.sub(r'APP_VERSION\s*=\s*["\'][^"\']+["\']', 'APP_VERSION = "2.5.6"', s, count=1)

# Qt URL helpers.
lines = s.splitlines()
for i, line in enumerate(lines[:80]):
    if line.startswith('from PySide6.QtCore import ') and 'QUrl' not in line:
        lines[i] = line.rstrip() + ', QUrl'
    if line.startswith('from PySide6.QtGui import ') and 'QDesktopServices' not in line:
        lines[i] = line.rstrip() + ', QDesktopServices'
s = '\n'.join(lines) + ('\n' if s.endswith('\n') else '')

# Windows media root and frozen resource path.
s = s.replace(
    'ROOT = Path(os.environ.get("ENKI_UNIQ_ROOT", Path.home() / "Movies" / "Enki Agency Uniq"))',
    'DEFAULT_MEDIA_ROOT = (Path.home() / "Videos" / "Enki Agency Uniq") if platform.system()=="Windows" else (Path.home() / "Movies" / "Enki Agency Uniq")\nROOT = Path(os.environ.get("ENKI_UNIQ_ROOT", DEFAULT_MEDIA_ROOT))'
)
s = s.replace('RESOURCES = Path(__file__).resolve().parent', 'RESOURCES = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))')

# Make bundled ffmpeg/ffprobe discoverable.
anchor = 'LOGO = RESOURCES / "EnkiAgencyUniq.png"'
if anchor in s and 'getattr(sys, "frozen", False)' not in s:
    s = s.replace(anchor, anchor + '\nif platform.system()=="Windows" and getattr(sys, "frozen", False):\n    os.environ["PATH"] = str(Path(sys.executable).resolve().parent) + os.pathsep + os.environ.get("PATH", "")', 1)

# Windows-safe folder opener.
start = s.find('    def open_path(self,path):')
if start >= 0:
    end = s.find('\n    def ', start + 5)
    if end > start:
        block = '''    def open_path(self,path):
        if platform.system()=="Windows":
            os.startfile(str(path))
        elif platform.system()=="Darwin":
            subprocess.Popen(["open",str(path)])
        else:
            subprocess.Popen(["xdg-open",str(path)])
'''
        s = s[:start] + block + s[end:]

# Telegram works on Windows via the system handler.
start = s.find('    def open_team(self):')
if start >= 0:
    end = s.find('\n    def ', start + 5)
    if end > start:
        block = '''    def open_team(self):
        QDesktopServices.openUrl(QUrl("https://t.me/enki_agency_bot"))
'''
        s = s[:start] + block + s[end:]

# Ensure logo is clickable.
if 'logo.mousePressEvent' not in s:
    a = 'side.addWidget(logo)'
    if a in s:
        s = s.replace(a, 'logo.setCursor(Qt.PointingHandCursor)\n        logo.setToolTip("Перейти в команду")\n        logo.mousePressEvent=lambda event:self.open_team()\n        ' + a, 1)

# Functional Windows updater. Manifest keeps legacy mac zip_url plus platforms.windows.url.
start = s.find('    def check_updates(self):')
if start >= 0:
    end = s.find('\n    def ', start + 5)
    if end > start:
        block = '''    def check_updates(self):
        try:
            req = urllib.request.Request(UPDATE_MANIFEST_URL, headers={"User-Agent":"Enki-Agency-Uniq-Windows"})
            with urllib.request.urlopen(req, timeout=20) as response:
                manifest = json.loads(response.read(512 * 1024).decode("utf-8"))
            latest = str(manifest.get("version") or "0")
            if version_tuple(latest) <= version_tuple(APP_VERSION):
                QMessageBox.information(self,"Обновления",f"Установлена актуальная версия {APP_VERSION}.")
                return
            win = (manifest.get("platforms") or {}).get("windows") or {}
            url = str(win.get("url") or "").strip()
            if not url:
                QMessageBox.warning(self,"Обновления","Для Windows новая версия пока не опубликована.")
                return
            answer = QMessageBox.question(self,"Доступно обновление",f"Доступна версия {latest}. Скачать и установить?")
            if answer != QMessageBox.Yes:
                return
            target = Path(tempfile.gettempdir()) / f"Enki_Agency_Uniq_{latest}_Setup.exe"
            urllib.request.urlretrieve(url, target)
            subprocess.Popen([str(target)])
            QApplication.quit()
        except Exception as exc:
            QMessageBox.warning(self,"Ошибка обновления",str(exc))
'''
        s = s[:start] + block + s[end:]

p.write_text(s, encoding='utf-8')
print(p)
