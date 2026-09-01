from pathlib import Path
import re

root = Path('mac256')
apps = list(root.rglob('app.py'))
if not apps:
    raise SystemExit('app.py not found')
p = apps[0]
s = p.read_text(encoding='utf-8')
s = re.sub(r'APP_VERSION\s*=\s*["\'][^"\']+["\']', 'APP_VERSION = "2.5.6"', s, count=1)
replacements = {
    '＋  Добавить видео': 'Добавить видео',
    '＋  Добавить фото': 'Добавить фото',
    '↻  Обновить очередь': 'Обновить очередь',
    '⌂  Открыть папку исходников': 'Открыть папку исходников',
    '⇩  Открыть папку результатов': 'Открыть папку результатов',
    '⌫  Удалить готовые фото': 'Удалить готовые фото',
    '⌫  Удалить готовые видео': 'Удалить готовые видео',
    '↗  Перейти в команду': 'Перейти в команду',
    '↻ Обновить': 'Обновить',
}
for old, new in replacements.items():
    s = s.replace(old, new)
s = s.replace('self.compact_update_btn.setObjectName("compactUpdateButton")', 'self.compact_update_btn.setObjectName("sideButton")')
s = s.replace('self.compact_update_btn.setFixedHeight(30)', 'self.compact_update_btn.setFixedHeight(44)')
start = s.find('    def side_button(self,text,fn):')
if start >= 0:
    end = s.find('\n    def ', start + 5)
    if end > start:
        block = """    def side_button(self,text,fn):
        b=QPushButton(text,objectName='sideButton')
        b.setFixedHeight(44)
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(fn)
        return b
"""
        s = s[:start] + block + s[end:]
style = """
        QPushButton#sideButton {
            background: transparent;
            border: 1px solid transparent;
            border-radius: 9px;
            padding: 0 14px;
            min-height: 44px;
            max-height: 44px;
            text-align: left;
            font-size: 14px;
            font-weight: 600;
        }
        QPushButton#sideButton:hover { background:#17130e; border-color:#3f2f1a; }
        QPushButton#sideButton:pressed { background:#21190f; }
"""
s = re.sub(r'\s*QPushButton#sideButton\s*\{.*?\}\s*QPushButton#sideButton:hover\s*\{.*?\}', '\n' + style, s, count=1, flags=re.S)
if 'min-height: 44px' not in s:
    q1 = s.find('"""', s.find('def apply_style'))
    q2 = s.find('"""', q1 + 3) if q1 >= 0 else -1
    if q2 >= 0:
        s = s[:q2] + style + s[q2:]
s = re.sub(r'\s*QPushButton#compactUpdateButton\s*\{.*?\}\s*QPushButton#compactUpdateButton:hover\s*\{.*?\}', '\n', s, flags=re.S)
p.write_text(s, encoding='utf-8')
print(p)
