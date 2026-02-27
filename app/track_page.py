# track_page.py
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPainterPath, QPen, QFont, QLinearGradient, QBrush
from widgets import RoundIconBtn, FlatIconBtn, ToggleIconBtn, SmoothSlider
from icons import icon_pm

_EQ_H = 50; _EQ_R = 18
_SWIPE_DOWN = 70    # px — swipe down to close
_SWIPE_UP   = -70   # px — swipe up to open EQ


class TrackPage(QWidget):
    closed         = pyqtSignal()
    open_eq        = pyqtSignal()
    repeat_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Swipe state — tracked at THIS widget level
        self._sw_y   = None   # press Y
        self._sw_on  = False  # currently tracking a swipe

        outer = QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        content = QWidget(); content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        cvl = QVBoxLayout(content); cvl.setContentsMargins(0,0,0,8); cvl.setSpacing(10)

        # Pill header — small visual pill, full-width tap zone
        self._pill = _CompactPill()
        self._pill.setFixedHeight(30)
        self._pill.tapped.connect(self.closed)
        cvl.addWidget(self._pill)

        inner = QWidget(); inner.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        ivl = QVBoxLayout(inner); ivl.setContentsMargins(24,0,24,0); ivl.setSpacing(10)

        # Cover
        self.cover = QLabel("♫"); self.cover.setFixedSize(196,196)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setFont(QFont("Helvetica Neue",54))
        self.cover.setStyleSheet("background:rgba(255,255,255,7);border:1px solid rgba(255,255,255,16);"
                                  "border-radius:20px;color:rgba(255,255,255,55);")
        cr = QHBoxLayout(); cr.addStretch(); cr.addWidget(self.cover); cr.addStretch()
        ivl.addLayout(cr)

        self.title_lbl  = QLabel("No Track")
        self.artist_lbl = QLabel("Unknown")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artist_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_lbl.setFont(QFont("Helvetica Neue",18,QFont.Weight.Bold))
        self.artist_lbl.setFont(QFont("Helvetica Neue",12))
        self.title_lbl.setStyleSheet("color:rgba(255,255,255,228);background:transparent;")
        self.artist_lbl.setStyleSheet("color:rgba(255,255,255,120);background:transparent;")
        self.title_lbl.setWordWrap(True)
        ivl.addWidget(self.title_lbl); ivl.addWidget(self.artist_lbl)

        # Seek slider
        pos_row = QHBoxLayout(); pos_row.setSpacing(10)
        self.cur_lbl = QLabel("0:00"); self.dur_lbl = QLabel("0:00")
        for lb in (self.cur_lbl, self.dur_lbl):
            lb.setFont(QFont("Helvetica Neue",10))
            lb.setStyleSheet("color:rgba(255,255,255,100);background:transparent;")
            lb.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.pos_slider = SmoothSlider(); self.pos_slider.setRange(0, 1000)
        pos_row.addWidget(self.cur_lbl); pos_row.addWidget(self.pos_slider,1); pos_row.addWidget(self.dur_lbl)
        ivl.addLayout(pos_row)

        # Playback controls
        ctl = QHBoxLayout(); ctl.setSpacing(14)
        self.b_prev   = RoundIconBtn("prev",   52, 20, 26)
        self.b_play   = RoundIconBtn("play",   64, 26, 32)
        self.b_next   = RoundIconBtn("next",   52, 20, 26)
        self.b_repeat = ToggleIconBtn("repeat", 40, 18)
        for btn in (self.b_prev, self.b_play, self.b_next, self.b_repeat):
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.b_repeat.clicked.connect(self._on_repeat)
        spacer = QWidget(); spacer.setFixedSize(40,40)
        spacer.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        ctl.addWidget(self.b_repeat); ctl.addStretch()
        ctl.addWidget(self.b_prev); ctl.addWidget(self.b_play); ctl.addWidget(self.b_next)
        ctl.addStretch(); ctl.addWidget(spacer)
        ivl.addLayout(ctl)

        # Volume
        vol_row = QHBoxLayout(); vol_row.setSpacing(10)
        self.vol_mute  = FlatIconBtn("sound_off",  28, 14)
        self.vol_loud  = FlatIconBtn("sound_loud", 28, 14)
        self.vol_slider = SmoothSlider(); self.vol_slider.setRange(0,100); self.vol_slider.setValue(70)
        for btn in (self.vol_mute, self.vol_loud):
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.vol_mute.clicked.connect(lambda: self.vol_slider.setValue(0))
        self.vol_loud.clicked.connect(lambda: self.vol_slider.setValue(100))
        vol_row.addWidget(self.vol_mute); vol_row.addWidget(self.vol_slider,1); vol_row.addWidget(self.vol_loud)
        ivl.addLayout(vol_row)
        ivl.addStretch()
        cvl.addWidget(inner, 1)
        outer.addWidget(content, 1)

        # EQ cap strip
        self._eq_cap = _EQCap(); self._eq_cap.setFixedHeight(_EQ_H)
        self._eq_cap.clicked.connect(self.open_eq)
        outer.addWidget(self._eq_cap)

    def _on_repeat(self):
        active = not self.b_repeat.is_active()
        self.b_repeat.set_active(active); self.repeat_changed.emit(active)

    def set_track(self, t):
        self.title_lbl.setText(t.get("title","Unknown"))
        self.artist_lbl.setText(t.get("artist","Unknown"))

    def set_playing(self, v): self.b_play.swap("pause" if v else "play")

    # ── Swipe detection ──────────────────────────────────────────────────────
    # We install it on mousePressEvent of the background (self).
    # Child widgets that consume events (sliders, buttons) will NOT propagate
    # to here — that is correct. We only want swipe on "empty" areas.
    # For reliable detection we use event filter on child widgets instead.

    def mousePressEvent(self, e):
        self._sw_y  = e.position().y()
        self._sw_on = True
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if self._sw_on and self._sw_y is not None:
            dy = e.position().y() - self._sw_y
            if   dy >  _SWIPE_DOWN: self.closed.emit()
            elif dy <  _SWIPE_UP:   self.open_eq.emit()
        self._sw_y  = None
        self._sw_on = False
        super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        grad = QLinearGradient(0,0,0,self.height())
        grad.setColorAt(0, QColor(10,9,18,255)); grad.setColorAt(1, QColor(13,11,22,255))
        p.fillRect(self.rect(), QBrush(grad)); p.end()


class _CompactPill(QWidget):
    """36×4px centred pill, full-width tap area."""
    from PyQt6.QtCore import pyqtSignal as _s
    tapped = _s()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._press = False; self._py = None

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._py = e.position().y(); self._press = True; self.update()
        e.accept()

    def mouseReleaseEvent(self, e):
        if self._press:
            if abs(e.position().y() - (self._py or 0)) < 18: self.tapped.emit()
            self._press = False; self.update()
        e.accept()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if self._press: p.fillRect(0,0,w,h, QColor(255,255,255,6))
        pw, ph = 36, 4
        px2, py2 = (w-pw)//2, (h-ph)//2 - 1
        path = QPainterPath(); path.addRoundedRect(px2, py2, pw, ph, 2, 2)
        p.fillPath(path, QColor(255,255,255,80 if self._press else 55))
        p.end()


class _EQCap(QWidget):
    from PyQt6.QtCore import pyqtSignal as _s
    clicked = _s()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pm = icon_pm("up", 20); self._hov = False; self._press = False

    def enterEvent(self, e): self._hov = True;  self.update()
    def leaveEvent(self, e): self._hov = False; self.update()
    def mousePressEvent(self, e):   self._press = True;  self.update()
    def mouseReleaseEvent(self, e):
        if self._press and self.rect().contains(e.position().toPoint()): self.clicked.emit()
        self._press = False; self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height(); r = _EQ_R
        path = QPainterPath()
        path.moveTo(0,h); path.lineTo(0,r)
        path.arcTo(0,0,r*2,r*2,180,-90); path.lineTo(w-r,0)
        path.arcTo(w-r*2,0,r*2,r*2,90,-90); path.lineTo(w,h); path.closeSubpath()
        p.fillPath(path, QColor(8,8,16, 232 if self._press else (218 if self._hov else 205)))
        pen = QPen(QColor(255,255,255,22)); pen.setWidthF(1.0); p.setPen(pen)
        top = QPainterPath()
        top.moveTo(0,r); top.arcTo(0,0,r*2,r*2,180,-90)
        top.lineTo(w-r,0); top.arcTo(w-r*2,0,r*2,r*2,90,-90)
        p.drawPath(top)
        iw, ih = self._pm.width(), self._pm.height()
        p.setOpacity(0.45 if self._press else (0.95 if self._hov else 0.65))
        p.drawPixmap((w-iw)//2, (h-ih)//2, self._pm)
        p.end()
