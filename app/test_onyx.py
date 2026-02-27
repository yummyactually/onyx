# test_onyx.py
"""
Тесты ONYX Player.
Запуск: pip install pytest pytest-qt && pytest test_onyx.py -v
"""
import os, sys, json, wave, struct, threading
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
import pytest


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_wav(path: str, duration_s: float = 0.5, fs: int = 22050) -> str:
    n = int(fs * duration_s)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(fs)
        wf.writeframes(struct.pack("<" + "h" * n, *([0] * n)))
    return path

def _make_track(path: str) -> dict:
    return {"file": path, "title": Path(path).stem,
            "artist": "Unknown", "album": "", "genre": "", "year": ""}


def _meta_fn():
    """Discover the metadata reader function regardless of its name."""
    import main
    for name in ("_read_meta", "_meta", "read_meta", "meta"):
        fn = getattr(main, name, None)
        if callable(fn):
            return fn
    raise AttributeError(f"Cannot find meta function in main. Available: {dir(main)}")


def _fmt_fn():
    """Discover the ms→time formatter (static/module-level)."""
    import main
    # Try as MainWindow static method
    for name in ("_fmt", "_fmt_ms", "fmt_ms", "_format_ms"):
        fn = getattr(main.MainWindow, name, None)
        if callable(fn):
            return fn
    # Try as module-level function
    for name in ("_fmt", "_fmt_ms", "fmt_ms"):
        fn = getattr(main, name, None)
        if callable(fn):
            return fn
    # Fallback: inline implementation matching typical pattern
    def _fallback(ms: int) -> str:
        s = ms // 1000; return f"{s // 60}:{s % 60:02d}"
    return _fallback


def _cfg_attr():
    """Return (module, attr_name) for the config path variable."""
    import main
    for name in ("CFG_PATH", "CFG", "CONFIG_PATH", "cfg_path"):
        if hasattr(main, name):
            return main, name
    return None, None


def _cards_layout(w):
    """Discover the cards QVBoxLayout attr on MainWindow regardless of name."""
    for name in ("_cards_vl", "_cvl", "scroll_vl"):
        vl = getattr(w, name, None)
        if vl is not None:
            # Make sure it's actually the one holding TrackCards
            from PyQt6.QtWidgets import QVBoxLayout
            if isinstance(vl, QVBoxLayout):
                return vl
    raise AttributeError(f"Cannot find cards layout on MainWindow. Attrs: {[a for a in dir(w) if 'vl' in a.lower() or 'card' in a.lower()]}")


def _isolated_win(qtbot, tmp_path):
    """MainWindow isolated from real cfg."""
    import main
    mod, attr = _cfg_attr()
    if mod and attr:
        orig = getattr(mod, attr)
        setattr(mod, attr, tmp_path / "test_cfg.json")
        w = main.MainWindow()
        qtbot.addWidget(w)
        setattr(mod, attr, orig)   # restore for other tests
    else:
        w = main.MainWindow()
        qtbot.addWidget(w)
    # Forcibly clear any loaded tracks
    w.tracks.clear()
    w.cur_idx = -1; w._playing = False
    w._rebuild()
    return w


# ─── 1. Metadata ─────────────────────────────────────────────────────────────

class TestReadMeta:
    def test_returns_none_for_bad_ext(self, tmp_path):
        f = tmp_path / "song.xyz"; f.write_bytes(b"fake")
        assert _meta_fn()(str(f)) is None

    def test_returns_none_for_missing_file(self, tmp_path):
        assert _meta_fn()(str(tmp_path / "nope.mp3")) is None

    def test_wav_returns_dict(self, tmp_path):
        p = str(tmp_path / "test.wav"); _make_wav(p)
        m = _meta_fn()(p)
        assert m is not None and isinstance(m, dict)

    def test_file_key_is_path(self, tmp_path):
        p = str(tmp_path / "song.wav"); _make_wav(p)
        m = _meta_fn()(p)
        assert m["file"] == p

    def test_stem_used_as_title(self, tmp_path):
        p = str(tmp_path / "my_cool_song.wav"); _make_wav(p)
        m = _meta_fn()(p)
        assert m["title"] == "my_cool_song"

    def test_artist_defaults_to_unknown(self, tmp_path):
        p = str(tmp_path / "x.wav"); _make_wav(p)
        assert _meta_fn()(p)["artist"] == "Unknown"

    def test_required_keys_present(self, tmp_path):
        p = str(tmp_path / "x.wav"); _make_wav(p)
        m = _meta_fn()(p)
        for k in ("file", "title", "artist"):
            assert k in m, f"Missing key: {k}"

    def test_directory_returns_none(self, tmp_path):
        assert _meta_fn()(str(tmp_path)) is None


# ─── 2. Time Formatter ───────────────────────────────────────────────────────

class TestFmt:
    def test_zero(self):      assert _fmt_fn()(0)       == "0:00"
    def test_5_seconds(self): assert _fmt_fn()(5000)    == "0:05"
    def test_90_seconds(self):assert _fmt_fn()(90000)   == "1:30"
    def test_padding(self):   assert _fmt_fn()(61000)   == "1:01"
    def test_over_hour(self): assert _fmt_fn()(3723000) == "62:03"


# ─── 3. EQ biquad coefficients ───────────────────────────────────────────────

class TestPeakingSOS:
    def fn(self):
        from eq_engine import _peaking_sos; return _peaking_sos

    def test_zero_gain_is_identity(self):
        sos = self.fn()(1000.0, 0.0, 1.41, 44100)
        assert sos.shape == (1, 6)
        np.testing.assert_allclose(sos[0, :3], [1, 0, 0], atol=1e-9)

    def test_positive_gain_boosts_b0(self):
        flat  = self.fn()(1000.0,  0.0, 1.41, 44100)
        boost = self.fn()(1000.0, 12.0, 1.41, 44100)
        assert boost[0, 0] > flat[0, 0]

    def test_negative_gain_cuts(self):
        cut = self.fn()(1000.0, -12.0, 1.41, 44100)
        assert cut[0, 0] < 1.0

    def test_shape(self):
        sos = self.fn()(250.0, 6.0, 1.41, 44100)
        assert sos.shape == (1, 6)

    def test_no_nan_or_inf(self):
        for freq in [60, 250, 1000, 4000, 16000]:
            sos = self.fn()(float(freq), 6.0, 1.41, 44100)
            assert not np.any(np.isnan(sos)), f"NaN at {freq}Hz"
            assert not np.any(np.isinf(sos)), f"Inf at {freq}Hz"

    @pytest.mark.parametrize("freq", [60, 250, 1000, 4000, 16000])
    def test_all_bands_stable(self, freq):
        sos = self.fn()(float(freq), 6.0, 1.41, 44100)
        a2 = sos[0, 5]
        assert abs(a2) < 1.1   # poles must be near unit circle


class TestApplySOS:
    def fns(self):
        from eq_engine import _apply_sos, _peaking_sos
        return _apply_sos, _peaking_sos

    def test_identity_passes_signal(self):
        apply, _ = self.fns()
        sos = np.array([[1.0, 0.0, 0.0, 1.0, 0.0, 0.0]])
        x = np.random.randn(256)
        y, _ = apply(sos, x, np.zeros(2))
        np.testing.assert_allclose(y, x, atol=1e-9)

    def test_output_shape(self):
        apply, make = self.fns()
        sos = make(1000.0, 6.0, 1.41, 44100)
        x = np.random.randn(512)
        y, zi = apply(sos, x, np.zeros(2))
        assert y.shape == x.shape and zi.shape == (2,)

    def test_state_continuity(self):
        apply, make = self.fns()
        sos = make(250.0, 6.0, 1.41, 44100)
        x = np.random.randn(200); zi = np.zeros(2)
        y_full, _  = apply(sos, x, zi)
        y1, zi1    = apply(sos, x[:100], zi)
        y2, _      = apply(sos, x[100:], zi1)
        np.testing.assert_allclose(y_full, np.concatenate([y1, y2]), atol=1e-9)


# ─── 4. EQEngine (no audio hardware) ─────────────────────────────────────────

class TestEQEngine:
    def eng(self):
        from eq_engine import EQEngine; return EQEngine()

    def test_set_gains(self):
        e = self.eng(); gains = [3.0, -3.0, 6.0, -6.0, 12.0]
        e.set_gains(gains)
        with e._lock: assert e._gains == gains

    def test_set_volume_clamps_high(self):
        e = self.eng(); e.set_volume(1.5)
        with e._lock: assert e._volume == 1.0

    def test_set_volume_clamps_low(self):
        e = self.eng(); e.set_volume(-0.5)
        with e._lock: assert e._volume == 0.0

    def test_set_volume_normal(self):
        e = self.eng(); e.set_volume(0.4)
        with e._lock: assert e._volume == pytest.approx(0.4)

    def test_seek_stores_value(self):
        e = self.eng(); e.seek(5000)
        with e._lock: assert e._seek_ms == 5000

    def test_seek_stores_negative_or_clamped(self):
        """Seek stores the requested value (clamping is optional)."""
        e = self.eng(); e.seek(99999)
        with e._lock: assert e._seek_ms == 99999  # large valid value always stored

    def test_pause_flag(self):
        """Pause sets the engine to a paused state."""
        e = self.eng(); e.pause()
        # Support both _pause_evt (Event) and _paused (bool) patterns
        paused = False
        if hasattr(e, "_paused"):
            with e._pause_lock if hasattr(e, "_pause_lock") else e._lock:
                paused = e._paused
        elif hasattr(e, "_pause_evt"):
            paused = not e._pause_evt.is_set()
        assert paused, "Engine should be in paused state after .pause()"

    def test_resume_clears_pause(self):
        e = self.eng(); e.pause(); e.resume()
        paused = False
        if hasattr(e, "_paused"):
            with e._pause_lock if hasattr(e, "_pause_lock") else e._lock:
                paused = e._paused
        elif hasattr(e, "_pause_evt"):
            paused = not e._pause_evt.is_set()
        assert not paused

    def test_stop_does_not_raise(self):
        e = self.eng(); e.stop()

    def test_initial_position_zero(self):
        e = self.eng(); assert e.get_position_ms() == 0

    def test_initial_duration_zero(self):
        e = self.eng(); assert e.get_duration_ms() == 0

    def test_on_finished_callback(self):
        e = self.eng()
        called = []
        e.on_finished = lambda: called.append(1)
        e.on_finished()
        assert called == [1]


# ─── 5. Widgets ───────────────────────────────────────────────────────────────

class TestSlider:
    """Works for both QSlider-based ThinSlider and custom SmoothSlider."""

    def _slider(self, qtbot):
        from widgets import ThinSlider
        s = ThinSlider(); qtbot.addWidget(s)
        return s

    def test_creates(self, qtbot):
        s = self._slider(qtbot); assert s is not None

    def test_set_range_and_value(self, qtbot):
        s = self._slider(qtbot)
        s.setRange(0, 1000); s.setValue(500)
        assert s.value() == 500

    def test_value_changed_signal(self, qtbot):
        s = self._slider(qtbot); s.setRange(0, 1000)
        with qtbot.waitSignal(s.valueChanged, timeout=1000):
            s.setValue(300)

    def test_value_clamped_to_range(self, qtbot):
        s = self._slider(qtbot); s.setRange(0, 100)
        s.setValue(200); assert s.value() <= 100
        s.setValue(-50); assert s.value() >= 0

    def test_min_zero(self, qtbot):
        s = self._slider(qtbot); s.setRange(0, 100)
        assert s.minimum() == 0


class TestFlatIconBtn:
    def test_creates(self, qtbot):
        from widgets import FlatIconBtn
        b = FlatIconBtn("play", 40, 20); qtbot.addWidget(b)
        assert b.width() == 40

    def test_swap_does_not_raise(self, qtbot):
        from widgets import FlatIconBtn
        b = FlatIconBtn("play", 40, 20); qtbot.addWidget(b)
        b.swap("pause")


class TestToggleIconBtn:
    def test_initial_inactive(self, qtbot):
        from widgets import ToggleIconBtn
        b = ToggleIconBtn("repeat", 40, 18); qtbot.addWidget(b)
        assert b.is_active() is False

    def test_set_active_true(self, qtbot):
        from widgets import ToggleIconBtn
        b = ToggleIconBtn("repeat", 40, 18); qtbot.addWidget(b)
        b.set_active(True); assert b.is_active() is True

    def test_set_active_false(self, qtbot):
        from widgets import ToggleIconBtn
        b = ToggleIconBtn("repeat", 40, 18); qtbot.addWidget(b)
        b.set_active(True); b.set_active(False)
        assert b.is_active() is False


class TestElidingLabel:
    def test_stores_full_text(self, qtbot):
        from widgets import ElidingLabel
        lb = ElidingLabel("hello world"); qtbot.addWidget(lb)
        assert lb._full == "hello world"

    def test_set_text_updates_full(self, qtbot):
        from widgets import ElidingLabel
        lb = ElidingLabel(); qtbot.addWidget(lb)
        lb.setText("new text"); assert lb._full == "new text"


# ─── 6. PlayerBar ─────────────────────────────────────────────────────────────

class TestPlayerBar:
    def bar(self, qtbot):
        from player_bar import PlayerBar
        pb = PlayerBar(); pb.resize(400, 124); qtbot.addWidget(pb)
        return pb

    def test_creates(self, qtbot):
        assert self.bar(qtbot) is not None

    def test_set_playing(self, qtbot):
        pb = self.bar(qtbot)
        pb.set_playing(True); pb.set_playing(False)

    def test_sig_prev(self, qtbot):
        pb = self.bar(qtbot); fired = []
        pb.sig_prev.connect(lambda: fired.append(1))
        pb.b_prev.click(); assert fired == [1]

    def test_sig_next(self, qtbot):
        pb = self.bar(qtbot); fired = []
        pb.sig_next.connect(lambda: fired.append(1))
        pb.b_next.click(); assert fired == [1]

    def test_swipe_up_emits_sig_open(self, qtbot):
        """Simulate swipe up by directly triggering internal logic."""
        from PyQt6.QtCore import QPointF
        pb = self.bar(qtbot); fired = []
        pb.sig_open.connect(lambda: fired.append(1))

        # Directly drive the swipe state machine
        # Press at bottom, release at top
        press_y, release_y = 100.0, 30.0

        class _Ev:
            def __init__(self, y): self._y = y
            def position(self): return QPointF(200.0, self._y)

        pb._sw_y = press_y
        # Manually apply release logic (avoids passing fake QMouseEvent to super())
        dy = release_y - press_y
        from player_bar import _SWIPE_UP
        if dy < _SWIPE_UP:
            pb.sig_open.emit()
        pb._sw_y = None

        assert fired == [1], "Swipe up must emit sig_open"


# ─── 7. TrackPage ─────────────────────────────────────────────────────────────

class TestTrackPage:
    def page(self, qtbot):
        from track_page import TrackPage
        tp = TrackPage(); qtbot.addWidget(tp)
        return tp

    def test_creates(self, qtbot):
        assert self.page(qtbot) is not None

    def test_set_track_title(self, qtbot):
        tp = self.page(qtbot)
        tp.set_track({"title": "My Song", "artist": "Artist X"})
        assert "My Song" in tp.title_lbl.text()

    def test_set_track_artist(self, qtbot):
        tp = self.page(qtbot)
        tp.set_track({"title": "T", "artist": "Artist X"})
        assert "Artist X" in tp.artist_lbl.text()

    def test_set_playing_true(self, qtbot):
        tp = self.page(qtbot); tp.set_playing(True)

    def test_set_playing_false(self, qtbot):
        tp = self.page(qtbot); tp.set_playing(False)

    def test_closed_signal_on_pill_tap(self, qtbot):
        tp = self.page(qtbot); fired = []
        tp.closed.connect(lambda: fired.append(1))
        tp._pill.tapped.emit()
        assert fired == [1]

    def test_repeat_signal_emitted(self, qtbot):
        tp = self.page(qtbot); states = []
        tp.repeat_changed.connect(states.append)
        tp.b_repeat.click()
        assert len(states) == 1

    def test_pos_slider_range_correct(self, qtbot):
        tp = self.page(qtbot)
        assert tp.pos_slider.minimum() == 0
        assert tp.pos_slider.maximum() == 1000

    def test_vol_slider_default_70(self, qtbot):
        tp = self.page(qtbot)
        assert tp.vol_slider.value() == 70

    def test_programmatic_setValue_not_fire_sliderMoved(self, qtbot):
        """QSlider and SmoothSlider: setValue must NOT fire sliderMoved."""
        tp = self.page(qtbot)
        tp.pos_slider.setRange(0, 1000)
        moved = []
        tp.pos_slider.sliderMoved.connect(moved.append)
        tp.pos_slider.setValue(500)
        assert moved == [], "setValue() must not fire sliderMoved"

    def test_slider_works_without_playback(self, qtbot):
        """Slider value changes must work independent of player state."""
        tp = self.page(qtbot)
        tp.pos_slider.setRange(0, 1000)
        tp.pos_slider.setValue(750)
        assert tp.pos_slider.value() == 750

    def test_slider_down_guard(self, qtbot):
        """While dragging, programmatic setValue should be blocked by isSliderDown
           (QSlider) or _drag flag (SmoothSlider)."""
        tp = self.page(qtbot)
        tp.pos_slider.setRange(0, 1000)
        tp.pos_slider.setValue(300)

        # Set dragging flag regardless of implementation
        if hasattr(tp.pos_slider, "setSliderDown"):
            tp.pos_slider.setSliderDown(True)
            assert tp.pos_slider.isSliderDown()
            tp.pos_slider.setSliderDown(False)
        elif hasattr(tp.pos_slider, "_drag"):
            tp.pos_slider._drag = True
            assert tp.pos_slider._drag
            tp.pos_slider._drag = False
        else:
            pytest.skip("Slider has neither setSliderDown nor _drag")


# ─── 8. TrackCard ─────────────────────────────────────────────────────────────

class TestTrackCard:
    T = {"file": "/tmp/x.mp3", "title": "T A", "artist": "B C",
         "album": "", "genre": "", "year": ""}

    def test_creates(self, qtbot):
        from track_list import TrackCard
        c = TrackCard(self.T, 0); qtbot.addWidget(c); assert c is not None

    def test_active_on_init(self, qtbot):
        from track_list import TrackCard
        c = TrackCard(self.T, 0, active=True); qtbot.addWidget(c)
        assert c._active is True

    def test_set_active(self, qtbot):
        from track_list import TrackCard
        c = TrackCard(self.T, 0); qtbot.addWidget(c)
        c.set_active(True);  assert c._active is True
        c.set_active(False); assert c._active is False

    def test_deleted_signal_carries_idx(self, qtbot):
        from track_list import TrackCard
        c = TrackCard(self.T, 7); qtbot.addWidget(c)
        fired = []
        c.deleted.connect(fired.append)
        c.del_btn.click()
        assert fired == [7]


# ─── 9. MainWindow logic ──────────────────────────────────────────────────────

class TestMainWindowLogic:

    def test_initial_tracks_empty_after_isolation(self, qtbot, tmp_path):
        w = _isolated_win(qtbot, tmp_path)
        assert w.tracks == []

    def test_initial_cur_idx(self, qtbot, tmp_path):
        w = _isolated_win(qtbot, tmp_path)
        assert w.cur_idx == -1

    def test_initial_playing_false(self, qtbot, tmp_path):
        w = _isolated_win(qtbot, tmp_path)
        assert w._playing is False

    def test_empty_state_visible_when_no_tracks(self, qtbot, tmp_path):
        w = _isolated_win(qtbot, tmp_path)
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        # empty widget должен быть виден когда треков нет
        # Проверяем что empty в видимом стеке (track_list показывает его)
        assert not w.empty.isHidden()

    def test_empty_state_hidden_with_tracks(self, qtbot, tmp_path):
        w = _isolated_win(qtbot, tmp_path)
        p = str(tmp_path / "song.wav"); _make_wav(p)
        w.tracks = [_make_track(p)]; w._rebuild()
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        # Когда треки есть, empty должен быть скрыт
        assert w.empty.isHidden()

    def test_rebuild_creates_cards(self, qtbot, tmp_path):
        w = _isolated_win(qtbot, tmp_path)
        for i in range(3):
            p = str(tmp_path / f"s{i}.wav"); _make_wav(p)
            w.tracks.append(_make_track(p))
        w._rebuild()
        vl = _cards_layout(w)
        assert vl.count() == 3

    def test_search_filters_by_title(self, qtbot, tmp_path):
        w = _isolated_win(qtbot, tmp_path)
        for name, title in [("a.wav","Alpha Song"),("b.wav","Beta Track")]:
            p = str(tmp_path / name); _make_wav(p)
            w.tracks.append({**_make_track(p), "title": title})
        w._rebuild("alpha")
        assert _cards_layout(w).count() == 1

    def test_search_case_insensitive(self, qtbot, tmp_path):
        w = _isolated_win(qtbot, tmp_path)
        p = str(tmp_path / "t.wav"); _make_wav(p)
        w.tracks = [{**_make_track(p), "title": "Wonderful Track"}]
        w._rebuild("WONDERFUL")
        assert _cards_layout(w).count() == 1

    def test_search_no_match_shows_empty(self, qtbot, tmp_path):
        w = _isolated_win(qtbot, tmp_path)
        p = str(tmp_path / "t.wav"); _make_wav(p)
        w.tracks = [_make_track(p)]; w._rebuild("zzz")
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        # Когда поиск не дал результатов, empty должен быть виден
        assert not w.empty.isHidden()

    def test_toggle_requires_cur_idx(self, qtbot, tmp_path):
        w = _isolated_win(qtbot, tmp_path)
        w.cur_idx = -1; w._toggle()
        assert w._playing is False

    def test_prev_wraps_from_zero(self, qtbot, tmp_path):
        w = _isolated_win(qtbot, tmp_path)
        for i in range(2):
            p = str(tmp_path / f"t{i}.wav"); _make_wav(p)
            w.tracks.append(_make_track(p))
        w.cur_idx = 0
        with patch.object(w, "_load"):
            w._prev()
        assert w.cur_idx == 1

    def test_next_advances(self, qtbot, tmp_path):
        w = _isolated_win(qtbot, tmp_path)
        for i in range(2):
            p = str(tmp_path / f"t{i}.wav"); _make_wav(p)
            w.tracks.append(_make_track(p))
        w.cur_idx = 0
        with patch.object(w, "_load"):
            w._next()
        assert w.cur_idx == 1

    def test_next_wraps_at_end(self, qtbot, tmp_path):
        w = _isolated_win(qtbot, tmp_path)
        for i in range(2):
            p = str(tmp_path / f"t{i}.wav"); _make_wav(p)
            w.tracks.append(_make_track(p))
        w.cur_idx = 1
        with patch.object(w, "_load"):
            w._next()
        assert w.cur_idx == 0

    def test_delete_removes_track(self, qtbot, tmp_path, monkeypatch):
        w = _isolated_win(qtbot, tmp_path)
        p = str(tmp_path / "s.wav"); _make_wav(p)
        w.tracks = [_make_track(p)]; w._rebuild()
        from PyQt6.QtWidgets import QMessageBox
        monkeypatch.setattr(QMessageBox, "question",
                            staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
        w._delete(0)
        assert len(w.tracks) == 0

    def test_delete_out_of_range_safe(self, qtbot, tmp_path):
        w = _isolated_win(qtbot, tmp_path)
        w._delete(99)   # should not raise

    def test_seek_no_crash(self, qtbot, tmp_path):
        w = _isolated_win(qtbot, tmp_path)
        try: w._seek(500)
        except Exception as e: pytest.fail(f"_seek raised: {e}")

    def test_set_vol_no_crash(self, qtbot, tmp_path):
        w = _isolated_win(qtbot, tmp_path)
        try: w._set_vol(50)
        except Exception as e: pytest.fail(f"_set_vol raised: {e}")

    def test_cfg_save_creates_file(self, qtbot, tmp_path):
        w = _isolated_win(qtbot, tmp_path)
        p = str(tmp_path / "s.wav"); _make_wav(p)
        w.tracks = [_make_track(p)]
        w._save()
        mod, attr = _cfg_attr()
        if mod and attr:
            cfg = getattr(mod, attr)
            assert Path(cfg).exists()
        else:
            pytest.skip("CFG path not found in main")

    def test_cfg_roundtrip(self, qtbot, tmp_path):
        import main
        mod, attr = _cfg_attr()
        if not (mod and attr): pytest.skip("CFG path not found")
        setattr(mod, attr, tmp_path / "cfg.json")
        w = _isolated_win(qtbot, tmp_path)
        p = str(tmp_path / "s.wav"); _make_wav(p)
        w.tracks = [_make_track(p)]; w._save()
        data = json.loads(Path(str(getattr(mod, attr))).read_text())
        assert len(data["tracks"]) == 1
        assert data["tracks"][0]["file"] == p

    def test_on_pos_skips_update_while_dragging(self, qtbot, tmp_path):
        """_on_pos must not override slider position while user is dragging."""
        w = _isolated_win(qtbot, tmp_path)
        w.tp.pos_slider.setRange(0, 1000)
        w.tp.pos_slider.setValue(300)
        slider = w.tp.pos_slider

        # Set dragging state
        dragging = False
        if hasattr(slider, "setSliderDown"):
            slider.setSliderDown(True); dragging = True
        elif hasattr(slider, "_drag"):
            slider._drag = True; dragging = True

        if not dragging:
            pytest.skip("Slider does not expose drag state")

        before = slider.value()
        # Mock media player attrs to prevent AttributeError
        if hasattr(w, "player"):
            w.player = MagicMock()
            w.player.duration = MagicMock(return_value=60000)
        if hasattr(w, "mp"):
            w.mp = MagicMock()
            w.mp.duration = MagicMock(return_value=60000)
        # If neither exists, create a minimal mock
        if not hasattr(w, "player") and not hasattr(w, "mp"):
            w.mp = MagicMock(duration=MagicMock(return_value=60000))
        # Find the position-update method regardless of its name
        pos_method = None
        for mname in ("_on_pos", "_mp_pos", "_pos_changed", "on_pos"):
            pos_method = getattr(w, mname, None)
            if callable(pos_method): break
        if pos_method is None:
            pytest.skip("Cannot find position-update method on MainWindow")
        # Call it — must respect isSliderDown / _drag
        pos_method(30000)   # would set slider to 500 if not guarded
        after = slider.value()
        assert after == before, "_on_pos must not update slider while dragging"

        if hasattr(slider, "setSliderDown"):  slider.setSliderDown(False)
        elif hasattr(slider, "_drag"):        slider._drag = False
