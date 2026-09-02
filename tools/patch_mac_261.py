from pathlib import Path
import re

root = Path('mac261')
apps = list(root.rglob('app.py'))
if not apps:
    raise SystemExit('app.py not found')
p = apps[0]
s = p.read_text(encoding='utf-8')
s = re.sub(r'APP_VERSION\s*=\s*["\'][^"\']+["\']', 'APP_VERSION = "2.6.1"', s, count=1)

# Do not change updater behavior: preserve the working 2.5.7/2.6.0 binding.
marker = 'self.compact_update_btn.clicked.connect(self.check_updates)'
if marker not in s:
    raise SystemExit('working updater binding not found')
if 'self.update_btn = self.compact_update_btn' not in s:
    s = s.replace(marker, marker + '\n        self.update_btn = self.compact_update_btn', 1)

# Logo gets a dedicated fixed block plus a clear gap before actions.
s = s.replace('logo.setFixedHeight(190)', 'logo.setFixedHeight(170)')
s = s.replace('logo.setFixedHeight(170)', 'logo.setFixedHeight(170)')
# Avoid accumulating spacing from previous patches.
s = s.replace('side.addWidget(logo)\n        side.addSpacing(20)\n', 'side.addWidget(logo)\n        side.addSpacing(14)\n', 1)

# Compact 38px action rows like the approved reference.
start = s.find('    def side_button(self,text,fn):')
if start >= 0:
    end = s.find('\n    def ', start + 5)
    if end > start:
        block = """    def side_button(self,text,fn):
        b=QPushButton(text,objectName='sideButton')
        b.setFixedHeight(38)
        b.setMinimumWidth(0)
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(fn)
        return b
"""
        s = s[:start] + block + s[end:]

s = s.replace('self.compact_update_btn.setFixedHeight(44)', 'self.compact_update_btn.setFixedHeight(38)')
s = s.replace('self.compact_update_btn.setFixedHeight(30)', 'self.compact_update_btn.setFixedHeight(38)')
s = s.replace('self.compact_update_btn.setObjectName("compactUpdateButton")', 'self.compact_update_btn.setObjectName("sideButton")')

# Tighter vertical rhythm in sidebar.
s = s.replace('side.setSpacing(8)', 'side.setSpacing(5)')

style = """
        QPushButton#sideButton {
            background:#0f0f0f;
            border:1px solid #302d29;
            border-radius:8px;
            padding:0 12px;
            min-height:38px;
            max-height:38px;
            text-align:left;
            font-size:13px;
            font-weight:600;
        }
        QPushButton#sideButton:hover { background:#17130e; border-color:#76531f; }
        QPushButton#sideButton:pressed { background:#21190f; border-color:#b17a27; }
        QFrame#brandFooter { background:transparent; border:0; }
        QLabel#footerBrand, QLabel#footerText, QLabel#ready { background:transparent; border:0; }
"""
# Append at end of stylesheet so it wins over old 44px rules.
q1 = s.find('"""', s.find('def apply_style'))
q2 = s.find('"""', q1 + 3) if q1 >= 0 else -1
if q2 < 0:
    raise SystemExit('stylesheet not found')
s = s[:q2] + style + s[q2:]

p.write_text(s, encoding='utf-8')
print(p)
