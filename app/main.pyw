#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ONYX Player — main.py"""
import sys, os, json, traceback
from pathlib import Path

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QScrollArea, QFrame, QMessageBox, QFileDialog, QSizePolicy)
from PyQt6.QtCore import (Qt, QPropertyAnimation, QEasingCurve, QPoint,
    QTimer, pyqtSignal)
from PyQt6.QtGui import (QColor, QFont, QPalette, QPainter, QPainterPath,
    QLinearGradient, QRadialGradient, QBrush)

from widgets    import DarkEdit
from track_list import TrackCard, EmptyState
from player_bar import PlayerBar
from track_page import TrackPage
from equalizer  import EqualizerSheet
from eq_engine  import EQEngine

try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PyQt6.QtCore import QUrl
    MEDIA_OK = True
except ImportError:
    MEDIA_OK = False

try:
    import mutagen as _mutagen_test
    MUTAGEN_OK = True
except ImportError:
    MUTAGEN_OK = False

CFG = Path.home() / ".onyx_player_cfg.json"


def _meta(path: str) -> dict | None:
    """
    Читает метаданные через mutagen.File() — универсальный способ,
    сам определяет формат (ID3 / VorbisComment / MP4Tags / APEv2 и т.д.)
    """
    try:
        ext = Path(path).suffix.lower()
        if ext not in {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a"}:
            return None
        if not os.path.isfile(path):
            return None

        m = {
            "file":   path,
            "title":  Path(path).stem,
            "artist": "Unknown",
            "album":  "",
            "genre":  "",
            "year":   "",
        }

        if not MUTAGEN_OK:
            return m

        import mutagen

        # ── Универсальное открытие ────────────────────────────────────────────
        audio = mutagen.File(path, easy=False)
        if audio is None:
            return m

        tags = audio.tags
        if tags is None:
            return m

        # ── Определяем тип тегов по классу ───────────────────────────────────
        tname = type(tags).__name__   # 'ID3', 'VCFLACDict', 'OggVComment', 'MP4Tags', ...

        # ── ID3 (MP3, WAV+ID3, AIFF) ──────────────────────────────────────────
        if "ID3" in tname or "ID3" in type(audio).__name__:
            def _id3(key):
                frame = tags.get(key)
                if frame is None:
                    return None
                # TextFrame → .text list
                if hasattr(frame, "text") and frame.text:
                    return str(frame.text[0]).strip()
                return str(frame).strip() or None

            v = _id3("TIT2")
            if v: m["title"] = v
            # TPE1 = Lead artist, TPE2 = Album artist / band
            v = _id3("TPE1") or _id3("TPE2") or _id3("TPE3")
            if v: m["artist"] = v
            v = _id3("TALB")
            if v: m["album"] = v
            v = _id3("TCON")
            if v: m["genre"] = v
            v = _id3("TDRC") or _id3("TYER") or _id3("TDAT")
            if v: m["year"] = v

        # ── MP4 / M4A / AAC ───────────────────────────────────────────────────
        elif "MP4" in tname:
            def _mp4(*keys):
                for k in keys:
                    v = tags.get(k)
                    if v:
                        item = v[0]
                        return str(item).strip() or None
                return None

            v = _mp4("\xa9nam");                      m["title"]  = v or m["title"]
            v = _mp4("\xa9ART", "aART", "©ART");     m["artist"] = v or "Unknown"
            v = _mp4("\xa9alb");                      m["album"]  = v or ""
            v = _mp4("\xa9gen");                      m["genre"]  = v or ""
            v = _mp4("\xa9day");                      m["year"]   = v or ""

        # ── Vorbis Comment (FLAC, OGG Vorbis, OGG Opus, FLAC в OGG) ─────────
        else:
            # Vorbis tags — итерируемый список пар (key, value) ИЛИ dict-like
            try:
                if hasattr(tags, "items"):
                    pairs = list(tags.items())
                else:
                    pairs = list(tags)
            except Exception:
                pairs = []

            tag_dict: dict[str, list[str]] = {}
            for k, v in pairs:
                tag_dict.setdefault(str(k).lower(), []).append(str(v))

            def _vc(*keys):
                for k in keys:
                    vals = tag_dict.get(k)
                    if vals:
                        s = vals[0].strip()
                        if s: return s
                return None

            v = _vc("title", "Title", "TITLE")
            if v: m["title"] = v
            v = _vc("artist", "Artist", "ARTIST",
                    "albumartist", "album_artist", "ALBUMARTIST")
            if v: m["artist"] = v
            v = _vc("album", "Album", "ALBUM")
            if v: m["album"] = v
            v = _vc("genre", "Genre", "GENRE")
            if v: m["genre"] = v
            v = _vc("date", "Date", "DATE", "year", "Year", "YEAR")
            if v: m["year"] = v

        # ── Финальная очистка ─────────────────────────────────────────────────
        for key in ("title", "artist", "album", "genre", "year"):
            if isinstance(m[key], str):
                m[key] = m[key].strip()
        if not m["title"]:
            m["title"] = Path(path).stem
        if not m["artist"]:
            m["artist"] = "Unknown"

        return m

    except Exception:
        try:
            return {"file": path, "title": Path(path).stem,
                    "artist": "Unknown", "album": "", "genre": "", "year": ""}
        except:
            return None


# ── Background ────────────────────────────────────────────────────────────────
class BgWidget(QWidget):
    def __init__(self, p=None):
        super().__init__(p); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    def paintEvent(self, _):
        p = QPainter(self); w, h = self.width(), self.height()
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor(10, 9, 18)); g.setColorAt(1, QColor(8, 7, 14))
        p.fillRect(self.rect(), QBrush(g))
        for cx, cy, cr, col in [
            (w * .82, h * .06, w * .5, QColor(80, 55, 170, 20)),
            (w * .14, h * .9,  w * .5, QColor(25, 80, 150, 14)),
        ]:
            gr = QRadialGradient(cx, cy, cr)
            gr.setColorAt(0, col); gr.setColorAt(1, QColor(0, 0, 0, 0))
            p.fillRect(self.rect(), QBrush(gr))
        p.end()


# ── Add button ────────────────────────────────────────────────────────────────
class AddBtn(QWidget):
    clicked = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent); self.setFixedSize(38, 38)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        from icons import icon_pm
        self._pm = icon_pm("add", 44); self._hov = False; self._press = False
    def enterEvent(self, e):   self._hov = True;   self.update()
    def leaveEvent(self, e):   self._hov = False;  self.update()
    def mousePressEvent(self, e):   self._press = True;  self.update()
    def mouseReleaseEvent(self, e):
        if self._press and self.rect().contains(e.position().toPoint()): self.clicked.emit()
        self._press = False; self.update()
    def paintEvent(self, _):
        p = QPainter(self)
        p.setOpacity(0.38 if self._press else (0.95 if self._hov else 0.75))
        iw, ih = self._pm.width(), self._pm.height()
        p.drawPixmap((self.width()-iw)//2, (self.height()-ih)//2, self._pm); p.end()


# ── EQ Overlay ────────────────────────────────────────────────────────────────
class EQOverlay(QWidget):
    close_req = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._py = None; self._sheet_top = 0
    def set_sheet_top(self, y): self._sheet_top = y
    def mousePressEvent(self, e):
        self._py = e.position().y(); e.accept()
    def mouseReleaseEvent(self, e):
        if self._py is not None:
            dy  = e.position().y() - self._py
            tap = e.position().y()
            if dy > 50:                                     self.close_req.emit()
            elif abs(dy) < 15 and tap < self._sheet_top:   self.close_req.emit()
        self._py = None; e.accept()
    def mouseMoveEvent(self, e): e.accept()
    def paintEvent(self, _):
        p = QPainter(self)
        if self._sheet_top > 0:
            p.fillRect(0, 0, self.width(), self._sheet_top, QColor(0, 0, 0, 90))
        p.end()


# ── Main window ───────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    _EQ_RATIO = 0.58

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ONYX Player"); self.setMinimumSize(380, 620); self.resize(450, 820)
        self.tracks: list[dict] = []; self.cur_idx = -1
        self._playing = False; self._repeat = False; self._loading = False
        self._vol = 0.7; self._eq_gains = [0.0] * 5

        self._eq = EQEngine(); self._use_eq = self._eq.is_available()

        if self._use_eq:
            self._eq.set_volume(self._vol)
            self._pos_timer = QTimer(); self._pos_timer.setInterval(200)
            self._pos_timer.timeout.connect(self._poll_pos)
            self._eq.on_finished = self._eq_finished
        elif MEDIA_OK:
            self.mp = QMediaPlayer(); self.ao = QAudioOutput()
            self.mp.setAudioOutput(self.ao); self.ao.setVolume(self._vol)
            self.mp.positionChanged.connect(self._mp_pos)
            self.mp.durationChanged.connect(self._mp_dur)
            self.mp.playbackStateChanged.connect(self._mp_state)

        self._build_ui(); self._load_cfg()

    def _build_ui(self):
        c = QWidget(); c.setStyleSheet("background:transparent;"); self.setCentralWidget(c)
        self.bg = BgWidget(c); self.bg.lower()
        vl = QVBoxLayout(c); vl.setContentsMargins(14, 22, 14, 14); vl.setSpacing(10)

        hdr = QHBoxLayout(); hdr.setSpacing(10)
        ttl = QLabel("ONYX Player"); ttl.setFont(QFont("Helvetica Neue", 21, QFont.Weight.Bold))
        ttl.setStyleSheet("color:rgba(255,255,255,225);background:transparent;")
        self.add_btn = AddBtn(); self.add_btn.clicked.connect(self._add_tracks)
        hdr.addWidget(ttl); hdr.addStretch(); hdr.addWidget(self.add_btn); vl.addLayout(hdr)

        self.search = DarkEdit("Поиск…"); self.search.textChanged.connect(self._filter)
        vl.addWidget(self.search)

        sw = QWidget(); sw.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        sv = QVBoxLayout(sw); sv.setContentsMargins(0, 0, 0, 0); sv.setSpacing(6)
        self._cw = QWidget(); self._cw.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._cvl = QVBoxLayout(self._cw); self._cvl.setContentsMargins(0, 0, 0, 0); self._cvl.setSpacing(6)
        self.empty = EmptyState()
        sv.addWidget(self._cw); sv.addWidget(self.empty); sv.addStretch()
        sa = QScrollArea(); sa.setWidgetResizable(True); sa.setWidget(sw)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sa.setStyleSheet(
            "QScrollArea,QWidget{background:transparent;border:none;}"
            "QScrollBar:vertical{width:3px;background:rgba(255,255,255,7);border-radius:1px;}"
            "QScrollBar::handle:vertical{background:rgba(255,255,255,65);border-radius:1px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}")
        vl.addWidget(sa, 1)

        self.pbar = PlayerBar()
        self.pbar.sig_prev.connect(self._prev)
        self.pbar.sig_next.connect(self._next)
        self.pbar.sig_play.connect(self._toggle)
        self.pbar.sig_open.connect(self._open_tp)
        vl.addWidget(self.pbar)

        self.tp = TrackPage(c)
        self.tp.setGeometry(0, self.height(), self.width(), self.height())
        self.tp.closed.connect(self._close_tp)
        self.tp.open_eq.connect(self._open_eq)
        self.tp.b_play.clicked.connect(self._toggle)
        self.tp.b_prev.clicked.connect(self._prev)
        self.tp.b_next.clicked.connect(self._next)
        self.tp.pos_slider.sliderMoved.connect(self._seek)
        self.tp.vol_slider.valueChanged.connect(self._set_vol)
        self.tp.repeat_changed.connect(lambda v: setattr(self, "_repeat", v))
        self.tp.hide()

        self.eq_ov = EQOverlay(c)
        self.eq_ov.setGeometry(0, 0, self.width(), self.height())
        self.eq_ov.close_req.connect(self._close_eq)
        self.eq_ov.hide()

        eq_h = int(self.height() * self._EQ_RATIO)
        self.eq_sh = EqualizerSheet(c)
        self.eq_sh.setGeometry(0, self.height(), self.width(), eq_h)
        self.eq_sh.gains_changed.connect(self._apply_eq)
        self.eq_sh.close_req.connect(self._close_eq)
        self.eq_sh.hide()

    def resizeEvent(self, e):
        super().resizeEvent(e); w, h = self.width(), self.height()
        self.bg.setGeometry(0, 0, w, h)
        if self.tp.isVisible(): self.tp.setGeometry(0, 0, w, h)
        else:                   self.tp.setGeometry(0, h, w, h)
        self.eq_ov.setGeometry(0, 0, w, h)
        eq_h = int(h * self._EQ_RATIO)
        if self.eq_sh.isVisible(): self.eq_sh.setGeometry(0, h - eq_h, w, eq_h)
        else:                      self.eq_sh.setGeometry(0, h, w, eq_h)

    def _rebuild(self, q=""):
        while self._cvl.count():
            it = self._cvl.takeAt(0)
            if it and it.widget(): it.widget().hide(); it.widget().setParent(None)
        ql = q.lower(); vis = 0
        for i, t in enumerate(self.tracks):
            if ql and ql not in t.get("title","").lower() and ql not in t.get("artist","").lower(): continue
            card = TrackCard(t, i, active=(i == self.cur_idx))
            card.clicked.connect(self._click); card.deleted.connect(self._delete)
            self._cvl.addWidget(card); vis += 1
        self.empty.setVisible(vis == 0)

    def _filter(self, t): self._rebuild(t)

    def _update_active(self):
        for i in range(self._cvl.count()):
            it = self._cvl.itemAt(i)
            if it and isinstance(it.widget(), TrackCard):
                it.widget().set_active(it.widget().idx == self.cur_idx)

    def _add_tracks(self):
        try:
            files, _ = QFileDialog.getOpenFileNames(
                self, "Выберите аудиофайлы", "",
                "Audio (*.mp3 *.wav *.ogg *.flac *.aac *.m4a);;All (*)")
        except: return
        if not files: return
        ex = {t["file"] for t in self.tracks}; added = 0
        for p in files:
            p = str(p)
            if p in ex: continue
            m = _meta(p)
            if m: self.tracks.append(m); ex.add(p); added += 1
        if added: self._save(); self._rebuild(self.search.text())

    def _click(self, idx):
        if idx == self.cur_idx: self._toggle()
        else: self.cur_idx = idx; self._update_active(); self._load(idx)

    def _load(self, idx):
        if not (0 <= idx < len(self.tracks)): return
        self._loading = True; t = self.tracks[idx]; self.tp.set_track(t)
        path = t.get("file", "")
        if self._use_eq:
            if path and os.path.exists(path):
                self._eq.set_gains(self._eq_gains)
                self._eq.play(path); self._pos_timer.start()
        elif MEDIA_OK and path and os.path.exists(path):
            self.mp.setSource(QUrl.fromLocalFile(path)); self.mp.play()
        self._playing = True
        self.pbar.set_playing(True); self.tp.set_playing(True)
        QTimer.singleShot(200, lambda: setattr(self, "_loading", False))

    def _toggle(self):
        if self.cur_idx < 0: return
        self._playing = not self._playing
        if self._use_eq:
            self._eq.resume() if self._playing else self._eq.pause()
        elif MEDIA_OK:
            self.mp.play() if self._playing else self.mp.pause()
        self.pbar.set_playing(self._playing); self.tp.set_playing(self._playing)

    def _prev(self):
        if not self.tracks: return
        self.cur_idx = (self.cur_idx - 1) % len(self.tracks)
        self._update_active(); self._load(self.cur_idx)

    def _next(self):
        if not self.tracks: return
        self.cur_idx = (self.cur_idx + 1) % len(self.tracks)
        self._update_active(); self._load(self.cur_idx)

    def _seek(self, v):
        if self._use_eq:
            dur = self._eq.get_duration_ms()
            if dur > 0: self._eq.seek(int(v / 1000 * dur))
        elif MEDIA_OK and self.mp.duration() > 0:
            self.mp.setPosition(int(v / 1000 * self.mp.duration()))

    def _set_vol(self, v):
        self._vol = v / 100.0
        if self._use_eq: self._eq.set_volume(self._vol)
        elif MEDIA_OK: self.ao.setVolume(self._vol)

    def _apply_eq(self, gains: list):
        self._eq_gains = list(gains)
        if self._use_eq: self._eq.set_gains(self._eq_gains)

    def _poll_pos(self):
        if not self._use_eq: return
        pos = self._eq.get_position_ms(); dur = self._eq.get_duration_ms()
        if dur > 0 and not self.tp.pos_slider._drag:
            self.tp.pos_slider.setValue(int(pos / dur * 1000), emit=False)
        self.tp.cur_lbl.setText(f"{pos//60000}:{(pos//1000)%60:02d}")
        self.tp.dur_lbl.setText(f"{dur//60000}:{(dur//1000)%60:02d}")

    def _eq_finished(self):
        if self._loading: return
        if self._repeat and 0 <= self.cur_idx < len(self.tracks):
            QTimer.singleShot(50, lambda: self._load(self.cur_idx))
        elif len(self.tracks) > 1:
            QTimer.singleShot(50, self._next)

    def _mp_pos(self, pos):
        if MEDIA_OK:
            d = self.mp.duration()
            if d > 0 and not self.tp.pos_slider._drag:
                self.tp.pos_slider.setValue(int(pos / d * 1000), emit=False)
        self.tp.cur_lbl.setText(f"{pos//60000}:{(pos//1000)%60:02d}")

    def _mp_dur(self, d): self.tp.dur_lbl.setText(f"{d//60000}:{(d//1000)%60:02d}")

    def _mp_state(self, s):
        if self._loading: return
        from PyQt6.QtMultimedia import QMediaPlayer as QMP
        if s == QMP.PlaybackState.StoppedState and self._playing:
            if self._repeat: QTimer.singleShot(50, lambda: self._load(self.cur_idx))
            elif len(self.tracks) > 1: QTimer.singleShot(50, self._next)

    def _delete(self, idx):
        if not (0 <= idx < len(self.tracks)): return
        name = self.tracks[idx].get("title", "трек")
        if QMessageBox.question(
            self, "Удалить", f"Удалить «{name}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes: return
        if self.cur_idx == idx:
            if self._use_eq: self._eq.stop(); self._pos_timer.stop()
            elif MEDIA_OK: self.mp.stop()
            self._playing = False; self.cur_idx = -1
            self.pbar.set_playing(False); self.tp.set_playing(False)
        elif self.cur_idx > idx:
            self.cur_idx -= 1
        self.tracks.pop(idx); self._save(); self._rebuild(self.search.text())

    def _anim_in_full(self, w):
        w.setGeometry(0, self.height(), self.width(), self.height()); w.show(); w.raise_()
        a = QPropertyAnimation(w, b"pos", self); a.setDuration(340)
        a.setStartValue(QPoint(0, self.height())); a.setEndValue(QPoint(0, 0))
        a.setEasingCurve(QEasingCurve.Type.OutCubic); a.start(); return a

    def _anim_out_full(self, w):
        a = QPropertyAnimation(w, b"pos", self); a.setDuration(300)
        a.setStartValue(QPoint(0, 0)); a.setEndValue(QPoint(0, self.height()))
        a.setEasingCurve(QEasingCurve.Type.InCubic); a.finished.connect(w.hide); a.start(); return a

    def _open_tp(self):
        if 0 <= self.cur_idx < len(self.tracks):
            self.tp.set_track(self.tracks[self.cur_idx])
        self._a_tp = self._anim_in_full(self.tp)

    def _close_tp(self): self._a_tp = self._anim_out_full(self.tp)

    def _open_eq(self):
        eq_h = int(self.height() * self._EQ_RATIO)
        sheet_top = self.height() - eq_h
        self.eq_ov.set_sheet_top(sheet_top)
        self.eq_ov.setGeometry(0, 0, self.width(), self.height())
        self.eq_ov.show(); self.eq_ov.raise_()
        self.eq_sh.setFixedSize(self.width(), eq_h)
        self.eq_sh.setGeometry(0, self.height(), self.width(), eq_h)
        self.eq_sh.show(); self.eq_sh.raise_()
        a = QPropertyAnimation(self.eq_sh, b"pos", self); a.setDuration(320)
        a.setStartValue(QPoint(0, self.height())); a.setEndValue(QPoint(0, sheet_top))
        a.setEasingCurve(QEasingCurve.Type.OutCubic); a.start(); self._a_eq = a

    def _close_eq(self):
        a = QPropertyAnimation(self.eq_sh, b"pos", self); a.setDuration(280)
        a.setStartValue(self.eq_sh.pos()); a.setEndValue(QPoint(0, self.height()))
        a.setEasingCurve(QEasingCurve.Type.InCubic)
        def _done(): self.eq_sh.hide(); self.eq_ov.hide()
        a.finished.connect(_done); a.start(); self._a_eq_out = a

    def _save(self):
        try:
            CFG.write_text(json.dumps(
                {"tracks": [t for t in self.tracks if t.get("file")]},
                ensure_ascii=False, indent=2), encoding="utf-8")
        except: pass

    def _load_cfg(self):
        try:
            if CFG.exists():
                data = json.loads(CFG.read_text(encoding="utf-8"))
                loaded = [t for t in data.get("tracks", []) if os.path.exists(t.get("file",""))]
                if loaded: self.tracks.extend(loaded); self._rebuild()
        except: pass


def _eh(et, ev, tb):
    try: QMessageBox.critical(None, "Ошибка", "".join(traceback.format_exception(et,ev,tb))[:2000])
    except: pass
    sys.__excepthook__(et, ev, tb)


if __name__ == "__main__":
    sys.excepthook = _eh
    app = QApplication(sys.argv); app.setStyle("Fusion")
    pal = app.palette()
    pal.setColor(QPalette.ColorRole.Window,     QColor(10,  9, 18))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(240,240,248))
    pal.setColor(QPalette.ColorRole.Base,       QColor(14, 13, 22))
    pal.setColor(QPalette.ColorRole.Text,       QColor(240,240,248))
    app.setPalette(pal)
    win = MainWindow(); win.show(); sys.exit(app.exec())
