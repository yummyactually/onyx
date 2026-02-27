# eq_engine.py
"""
Real-time 5-band parametric EQ using scipy biquad (peaking) filters.
Audio is read via soundfile, filtered block-by-block, played via sounddevice.
Each band: 2nd-order IIR peaking filter, Q=1.41.
Falls back gracefully if sounddevice/soundfile are unavailable.
"""
import threading, time
import numpy as np

try:
    import soundfile as sf
    import sounddevice as sd
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

BAND_FREQS = [60.0, 250.0, 1000.0, 4000.0, 16000.0]
_Q         = 1.41
_BLOCKSIZE = 1024


def _peaking_sos(freq: float, gain_db: float, Q: float, fs: int) -> np.ndarray:
    """Return SOS coefficients for a peaking EQ biquad."""
    if abs(gain_db) < 0.05:
        return np.array([[1.0, 0.0, 0.0, 1.0, 0.0, 0.0]])
    A    = 10.0 ** (gain_db / 40.0)
    w0   = 2.0 * np.pi * freq / fs
    cosw = np.cos(w0)
    sinw = np.sin(w0)
    alpha = sinw / (2.0 * Q)
    b0 =  1.0 + alpha * A
    b1 = -2.0 * cosw
    b2 =  1.0 - alpha * A
    a0 =  1.0 + alpha / A
    a1 = -2.0 * cosw
    a2 =  1.0 - alpha / A
    return np.array([[b0/a0, b1/a0, b2/a0, 1.0, a1/a0, a2/a0]])


def _apply_sos(sos: np.ndarray, data: np.ndarray, zi: np.ndarray):
    """
    Manual single-section SOS filter with state (zi shape: [2, channels]).
    Returns (output, new_zi).
    """
    b0,b1,b2,_,a1,a2 = sos[0]
    out = np.empty_like(data)
    z0 = zi[0]; z1 = zi[1]
    for n in range(len(data)):
        x  = data[n]
        y  = b0*x + z0
        z0 = b1*x - a1*y + z1
        z1 = b2*x - a2*y
        out[n] = y
    return out, np.array([z0, z1])


class EQEngine:
    def __init__(self):
        self._available    = _AVAILABLE
        self._gains        = [0.0] * 5
        self._volume       = 0.7
        self._path         = None
        self._thread       = None
        self._stop_evt     = threading.Event()
        self._pause_evt    = threading.Event(); self._pause_evt.set()
        self._seek_ms      = None
        self._pos_frames   = 0
        self._dur_frames   = 0
        self._lock         = threading.Lock()
        self.on_finished   = None   # callable()
        self.on_position   = None   # callable(pos_ms, dur_ms)

    def is_available(self):   return self._available
    def set_gains(self, g):
        with self._lock: self._gains = list(g)
    def set_volume(self, v):
        with self._lock: self._volume = max(0.0, min(1.0, v))
    def get_position_ms(self): return int(self._pos_frames / max(1, self._fs) * 1000) if hasattr(self,'_fs') else 0
    def get_duration_ms(self): return int(self._dur_frames / max(1, self._fs) * 1000) if hasattr(self,'_fs') else 0

    def play(self, path: str, start_ms: int = 0):
        self._stop_and_join()
        self._path = path; self._stop_evt.clear(); self._pause_evt.set()
        self._thread = threading.Thread(target=self._run, args=(path, start_ms), daemon=True)
        self._thread.start()

    def pause(self):  self._pause_evt.clear()
    def resume(self): self._pause_evt.set()

    def seek(self, ms: int):
        with self._lock: self._seek_ms = ms

    def stop(self): self._stop_and_join()

    def _stop_and_join(self):
        self._stop_evt.set(); self._pause_evt.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None; self._stop_evt.clear()

    def _run(self, path: str, start_ms: int):
        try:
            with sf.SoundFile(path) as sf_file:
                fs       = sf_file.samplerate
                channels = sf_file.channels
                total_f  = len(sf_file)
                self._fs         = fs
                self._dur_frames = total_f

                start_f = int(start_ms / 1000.0 * fs)
                start_f = max(0, min(start_f, total_f - 1))
                sf_file.seek(start_f)
                self._pos_frames = start_f

                with sd.OutputStream(samplerate=fs, channels=channels,
                                     blocksize=_BLOCKSIZE, dtype='float32') as stream:
                    # Filter state: [band][zi_array(2, channels)]
                    with self._lock: gains = list(self._gains)
                    sos_list = [_peaking_sos(f, g, _Q, fs) for f, g in zip(BAND_FREQS, gains)]
                    zi_list  = [np.zeros((2, channels), dtype=np.float64) for _ in sos_list]

                    while not self._stop_evt.is_set():
                        # Pause
                        if not self._pause_evt.is_set():
                            stream.stop()
                            self._pause_evt.wait()
                            if self._stop_evt.is_set(): break
                            stream.start()

                        # Seek
                        seek_target = None
                        with self._lock:
                            if self._seek_ms is not None:
                                seek_target = self._seek_ms; self._seek_ms = None
                        if seek_target is not None:
                            sf_f = max(0, min(int(seek_target/1000.0*fs), total_f-1))
                            sf_file.seek(sf_f); self._pos_frames = sf_f
                            zi_list = [np.zeros((2, channels), dtype=np.float64) for _ in sos_list]

                        # Read block
                        block = sf_file.read(_BLOCKSIZE, dtype='float32', always_2d=True)
                        if len(block) == 0:
                            if self.on_finished: self.on_finished()
                            break
                        self._pos_frames = sf_file.tell()

                        # Re-build filters if gains changed
                        with self._lock: new_gains = list(self._gains)
                        if new_gains != gains:
                            gains    = new_gains
                            sos_list = [_peaking_sos(f, g, _Q, fs) for f, g in zip(BAND_FREQS, gains)]
                            zi_list  = [np.zeros((2, channels), dtype=np.float64) for _ in sos_list]

                        # Apply all bands channel-by-channel
                        out = block.astype(np.float64)
                        for bi, sos in enumerate(sos_list):
                            for ch in range(channels):
                                col, new_zi = _apply_sos(sos, out[:, ch], zi_list[bi][:, ch])
                                out[:, ch]  = col
                                zi_list[bi][:, ch] = new_zi

                        # Volume + clip
                        with self._lock: vol = self._volume
                        out *= vol
                        np.clip(out, -1.0, 1.0, out=out)

                        stream.write(out.astype(np.float32))

                        if self.on_position:
                            pos_ms = int(self._pos_frames / fs * 1000)
                            dur_ms = int(total_f / fs * 1000)
                            self.on_position(pos_ms, dur_ms)

        except Exception:
            pass
