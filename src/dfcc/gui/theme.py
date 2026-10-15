"""Alpine dark theme + painted logo (mountain, debris-flow tongue, sediment dots)."""
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QPixmap, QPainter, QPainterPath, QLinearGradient, QColor, QBrush, QPen, QIcon, QRadialGradient)

C = dict(bg="#0b1620", panel="#13222f", card="#182b3a", line="#26405a", ink="#e8f1f7", muted="#8aa4b8",
         ice="#7fd1f2", ice2="#3aa3d6", snow="#f4f9fc", ember="#f4723c", moss="#3fae5a", rock="#c9b79c")

QSS = f"""
* {{ font-family: 'Segoe UI', 'Inter', 'Noto Sans', sans-serif; font-size: 10pt; color: {C['ink']}; }}
QMainWindow, QWidget#root {{ background: {C['bg']}; }}
QWidget#header {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #0f2a3f, stop:1 #0b1620); border-bottom: 1px solid {C['line']}; }}
QLabel#title {{ font-size: 20pt; font-weight: 700; letter-spacing: 3px; color: {C['snow']}; }}
QLabel#subtitle {{ color: {C['muted']}; font-size: 9pt; }}
QScrollArea {{ border: none; background: transparent; }}
QWidget#side {{ background: {C['panel']}; }}
QGroupBox {{ background: {C['card']}; border: 1px solid {C['line']}; border-radius: 10px; margin-top: 16px; padding: 14px 10px 8px 10px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {C['ice']}; }}
QGroupBox::indicator {{ width: 14px; height: 14px; }}
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {{ background: {C['bg']}; border: 1px solid {C['line']}; border-radius: 6px; padding: 4px 6px; selection-background-color: {C['ice2']}; }}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {C['ice']}; }}
QComboBox QAbstractItemView {{ background: {C['panel']}; selection-background-color: {C['ice2']}; }}
QPushButton {{ background: {C['card']}; border: 1px solid {C['line']}; border-radius: 8px; padding: 7px 14px; }}
QPushButton:hover {{ border-color: {C['ice']}; background: #1d3447; }}
QPushButton:disabled {{ color: #5b7387; }}
QPushButton#run {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #e2552b, stop:1 #f4893c); border: none; font-weight: 700; font-size: 11pt; padding: 10px; color: white; }}
QPushButton#run:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #ef6a3f, stop:1 #ffa04f); }}
QPushButton#run:disabled {{ background: #4a3a34; color: #9a867c; }}
QTabWidget::pane {{ border: 1px solid {C['line']}; border-radius: 8px; background: {C['panel']}; top: -1px; }}
QTabBar::tab {{ background: transparent; padding: 8px 18px; color: {C['muted']}; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {C['snow']}; border-bottom: 2px solid {C['ember']}; }}
QTabBar::tab:hover {{ color: {C['ice']}; }}
QCheckBox {{ spacing: 7px; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {C['line']}; border-radius: 4px; background: {C['bg']}; }}
QCheckBox::indicator:checked {{ background: {C['ice2']}; border-color: {C['ice']}; }}
QPlainTextEdit, QTableWidget {{ background: {C['bg']}; border: 1px solid {C['line']}; border-radius: 6px; font-family: 'Cascadia Mono', 'Consolas', monospace; font-size: 9pt; gridline-color: {C['line']}; }}
QHeaderView::section {{ background: {C['card']}; border: none; border-bottom: 1px solid {C['line']}; padding: 5px; color: {C['ice']}; }}
QProgressBar {{ background: {C['bg']}; border: 1px solid {C['line']}; border-radius: 6px; text-align: center; height: 16px; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {C['ice2']}, stop:1 {C['ember']}); border-radius: 5px; }}
QStatusBar {{ background: {C['bg']}; color: {C['muted']}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {C['line']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QLabel#note {{ color: {C['muted']}; font-size: 9pt; }}
QLabel#warn {{ color: #ffd9c7; background: #3a2318; border: 1px solid {C['ember']}; border-radius: 8px; padding: 8px; font-size: 9pt; }}
QLabel#custom {{ color: {C['ember']}; font-weight: 600; }}
QToolTip {{ background: {C['card']}; color: {C['ink']}; border: 1px solid {C['ice']}; }}
"""


def logo_pixmap(size=96):
    """Layered peaks with snow caps, an orange debris-flow tongue down a gully and sediment dots."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 100.0
    p.scale(s, s)
    bg = QRadialGradient(50, 40, 70)
    bg.setColorAt(0, QColor("#1b4766"))
    bg.setColorAt(1, QColor("#0b1620"))
    p.setBrush(QBrush(bg))
    p.setPen(QPen(QColor(C["line"]), 1.5))
    p.drawRoundedRect(QRectF(3, 3, 94, 94), 22, 22)
    p.setClipPath(_rr(3, 3, 94, 94, 22))
    back = QPainterPath(QPointF(0, 70)); [back.lineTo(*pt) for pt in [(18, 42), (28, 52), (44, 24), (60, 50), (72, 36), (100, 66), (100, 100), (0, 100)]]
    g = QLinearGradient(0, 20, 0, 90); g.setColorAt(0, QColor("#5f87a6")); g.setColorAt(1, QColor("#1c3447"))
    p.setPen(Qt.NoPen); p.setBrush(QBrush(g)); p.drawPath(back)
    front = QPainterPath(QPointF(0, 86)); [front.lineTo(*pt) for pt in [(22, 50), (38, 66), (58, 30), (82, 70), (100, 58), (100, 100), (0, 100)]]
    g2 = QLinearGradient(0, 30, 0, 100); g2.setColorAt(0, QColor("#8fb4cf")); g2.setColorAt(1, QColor("#142636"))
    p.setBrush(QBrush(g2)); p.drawPath(front)
    snow = QPainterPath(QPointF(58, 30)); [snow.lineTo(*pt) for pt in [(50, 44), (55, 42), (58, 48), (62, 41), (67, 45)]]; snow.closeSubpath()
    p.setBrush(QColor(C["snow"])); p.drawPath(snow)
    s2 = QPainterPath(QPointF(44, 24)); [s2.lineTo(*pt) for pt in [(38, 36), (43, 34), (46, 39), (50, 33)]]; s2.closeSubpath()
    p.drawPath(s2)
    tongue = QPainterPath(QPointF(57, 44)); tongue.cubicTo(55, 58, 64, 66, 60, 78); tongue.cubicTo(58, 88, 70, 90, 76, 97)
    tongue.lineTo(86, 97); tongue.cubicTo(78, 88, 70, 82, 70, 74); tongue.cubicTo(70, 64, 63, 56, 62, 44); tongue.closeSubpath()
    tg = QLinearGradient(0, 44, 0, 97); tg.setColorAt(0, QColor("#d62828")); tg.setColorAt(0.5, QColor("#f77f00")); tg.setColorAt(1, QColor("#3fae5a"))
    p.setBrush(QBrush(tg)); p.drawPath(tongue)
    p.setBrush(QColor(C["rock"]))
    for (x, y, r) in [(74, 84, 2.4), (80, 90, 1.8), (66, 91, 1.6), (84, 80, 1.3), (71, 95, 1.2), (90, 93, 1.5)]:
        p.drawEllipse(QPointF(x, y), r, r)
    p.end()
    return pm


def _rr(x, y, w, h, r):
    path = QPainterPath()
    path.addRoundedRect(QRectF(x, y, w, h), r, r)
    return path


def app_icon():
    return QIcon(logo_pixmap(256))
