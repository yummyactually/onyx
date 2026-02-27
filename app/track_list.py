# track_list.py
from PyQt6.QtWidgets import QWidget, QLabel, QHBoxLayout, QVBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPainterPath, QPen, QFont
from widgets import ElidingLabel, FlatIconBtn

_CARD_H = 64


class TrackCard(QWidget):
    clicked = pyqtSignal(int)
    deleted = pyqtSignal(int)

    def __init__(self, track, idx, active=False, parent=None):
        super().__init__(parent)
        self.idx = idx; self._hov = False; self._active = active
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(_CARD_H)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        hl = QHBoxLayout(self); hl.setContentsMargins(10,0,10,0); hl.setSpacing(10)

        cov = QLabel("♪"); cov.setFixedSize(40,40)
        cov.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cov.setFont(QFont("Helvetica Neue",14))
        cov.setStyleSheet("color:rgba(255,255,255,80);background:rgba(255,255,255,7);"
                          "border:1px solid rgba(255,255,255,15);border-radius:8px;")
        hl.addWidget(cov)

        vl = QVBoxLayout(); vl.setSpacing(2); vl.setContentsMargins(0,0,0,0)
        self.t_lbl = ElidingLabel(track.get("title","Unknown"))
        self.t_lbl.setFont(QFont("Helvetica Neue",13,QFont.Weight.Bold))
        self.t_lbl.setStyleSheet("color:rgba(255,255,255,220);background:transparent;")
        self.t_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.a_lbl = ElidingLabel("— " + track.get("artist","Unknown"))
        self.a_lbl.setFont(QFont("Helvetica Neue",11))
        self.a_lbl.setStyleSheet("color:rgba(255,255,255,100);background:transparent;")
        self.a_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        vl.addWidget(self.t_lbl); vl.addWidget(self.a_lbl)
        hl.addLayout(vl, 1)

        self.del_btn = FlatIconBtn("delete", size=32, icon_px=13)
        self.del_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.del_btn.clicked.connect(lambda: self.deleted.emit(self.idx))
        hl.addWidget(self.del_btn)

    def set_active(self, v): self._active = v; self.update()
    def enterEvent(self, e): self._hov = True;  self.update()
    def leaveEvent(self, e): self._hov = False; self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if not self.del_btn.geometry().contains(e.position().toPoint()):
                self.clicked.emit(self.idx)
        super().mousePressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 12, 12)
        if self._active:
            p.fillPath(path, QColor(180,150,255,28))
            pen = QPen(QColor(200,170,255,60)); pen.setWidthF(1.0); p.setPen(pen); p.drawPath(path)
        elif self._hov:
            p.fillPath(path, QColor(255,255,255,13))
            pen = QPen(QColor(255,255,255,20)); pen.setWidthF(1.0); p.setPen(pen); p.drawPath(path)
        else:
            p.fillPath(path, QColor(255,255,255,6))
        p.end()


class EmptyState(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        vl = QVBoxLayout(self)
        vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.setContentsMargins(20,60,20,60); vl.setSpacing(14)
        note = QLabel("♫"); note.setFont(QFont("Helvetica Neue",52))
        note.setStyleSheet("color:rgba(255,255,255,30);background:transparent;")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel("Нет треков\nНажмите + чтобы добавить музыку")
        hint.setFont(QFont("Helvetica Neue",13))
        hint.setStyleSheet("color:rgba(255,255,255,55);background:transparent;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(note); vl.addWidget(hint)
