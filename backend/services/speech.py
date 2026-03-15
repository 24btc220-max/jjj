"""
ExamGuard — Speech Detection Service
Layer 1: VAD using scipy FFT (spectral flatness + mel energy + F0 autocorrelation)
Layer 2: OpenAI Whisper speech-to-text transcription
Both must agree before flagging — eliminates false positives from ambient noise.
"""
import logging
import math
import numpy as np
from typing import Optional

log = logging.getLogger("examguard.speech")

# Try importing Whisper — graceful fallback
try:
    import whisper as _whisper_lib
    _whisper_model = None  # lazy-loaded on first use
    WHISPER_AVAILABLE = True
    log.info("Whisper available")
except ImportError:
    WHISPER_AVAILABLE = False
    log.warning("Whisper not installed — using VAD-only mode")

try:
    from scipy import signal as _scipy_signal
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


# ── Whisper model loader ───────────────────────────────────────────────────

def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None and WHISPER_AVAILABLE:
        log.info("Loading Whisper 'base' model (first call, ~150ms)…")
        _whisper_model = _whisper_lib.load_model("base")
        log.info("Whisper model loaded")
    return _whisper_model


# ── VAD Feature Extraction ─────────────────────────────────────────────────

def _hz_to_mel(hz: float) -> float:
    return 2595 * math.log10(1 + hz / 700)

def _mel_to_hz(mel: float) -> float:
    return 700 * (10 ** (mel / 2595) - 1)


def _spectral_flatness(spectrum: np.ndarray) -> float:
    """Wiener entropy. Speech: 0.10–0.35. Noise: 0.60–1.0."""
    eps = 1e-10
    log_mean = np.mean(np.log(spectrum + eps))
    arith_mean = np.mean(spectrum + eps)
    return float(np.exp(log_mean) / (arith_mean + eps))


def _mel_filterbank_energy(freq_data: np.ndarray, sample_rate: int,
                            n_filters: int = 13) -> np.ndarray:
    """
    13-band mel filterbank. Speech energy is concentrated in bands 2–8.
    Returns normalised energy per band.
    """
    n_fft = len(freq_data)
    mel_min = _hz_to_mel(80)
    mel_max = _hz_to_mel(min(sample_rate / 2, 8000))
    mel_pts = np.linspace(mel_min, mel_max, n_filters + 2)
    bin_pts = np.clip(
        np.round(_mel_to_hz(mel_pts) * n_fft * 2 / sample_rate).astype(int),
        0, n_fft - 1
    )
    energies = []
    for m in range(n_filters):
        lo, mid, hi = bin_pts[m], bin_pts[m + 1], bin_pts[m + 2]
        e = 0.0
        for k in range(lo, hi + 1):
            if k >= n_fft:
                break
            w = ((k - lo) / (mid - lo + 1)) if k <= mid else ((hi - k) / (hi - mid + 1))
            e += max(0, w) * float(freq_data[k])
        energies.append(e)
    total = sum(energies) + 1e-8
    return np.array([e / total for e in energies])


def _autocorrelation_pitch(samples: np.ndarray, sample_rate: int) -> float:
    """
    Simplified YIN-style autocorrelation pitch detector.
    Human speech F0: 70–310 Hz.
    Returns detected pitch in Hz, or 0 if no clear pitch found.
    """
    buf = samples[:2048]
    min_period = int(sample_rate / 310)   # max 310 Hz
    max_period = int(sample_rate / 70)    # min 70 Hz

    rms = float(np.sqrt(np.mean(buf ** 2)))
    if rms < 0.005:
        return 0.0

    best_corr = -np.inf
    best_period = -1

    for tau in range(min_period, min(max_period + 1, len(buf) // 2)):
        a = buf[:len(buf) - tau]
        b = buf[tau:]
        corr = float(np.dot(a, b))
        norm = float(np.dot(a, a) + np.dot(b, b)) / 2 + 1e-8
        ncorr = corr / norm
        if ncorr > best_corr:
            best_corr = ncorr
            best_period = tau

    if best_corr > 0.35 and best_period > 0:
        return float(sample_rate / best_period)
    return 0.0


def _zcr(samples: np.ndarray) -> float:
    """Zero-crossing rate. Voiced speech: 0.03–0.20. Noise: higher."""
    crossings = int(np.sum(np.abs(np.diff(np.sign(samples)))))
    return crossings / (2 * len(samples))


# ── Main VAD scorer ────────────────────────────────────────────────────────

# Per-session adaptive noise floor
_noise_floors: dict[str, list] = {}

def _get_noise_floor(session_id: str) -> float:
    floors = _noise_floors.get(session_id, [])
    return float(np.mean(floors)) if floors else 0.005


def score_vad(audio_samples: list, sample_rate: int, session_id: str) -> dict:
    """
    6-feature probabilistic VAD.
    Returns {is_speech, prob (0–100), pitch, flatness, snr, zcr_val, rms}.
    """
    samples = np.array(audio_samples, dtype=np.float32)
    if len(samples) < 512:
        return {"is_speech": False, "prob": 0}

    rms = float(np.sqrt(np.mean(samples ** 2)))

    # Update adaptive noise floor during quiet periods
    if rms < 0.02:
        floors = _noise_floors.setdefault(session_id, [])
        floors.append(rms)
        if len(floors) > 200:
            floors.pop(0)

    noise_level = _get_noise_floor(session_id)
    snr = rms / (noise_level + 1e-6)

    # FFT spectrum
    fft_mag = np.abs(np.fft.rfft(samples))

    # Feature 1: Autocorrelation pitch (F0)
    pitch = _autocorrelation_pitch(samples, sample_rate)
    pitch_score = 28 if 70 < pitch < 310 else 0

    # Feature 2: Spectral flatness
    flatness = _spectral_flatness(fft_mag)
    flat_score = 25 if flatness < 0.35 else (12 if flatness < 0.50 else 0)

    # Feature 3: Mel filterbank concentration (bands 2–8 = speech range)
    mel = _mel_filterbank_energy(fft_mag, sample_rate)
    speech_mel_energy = float(np.sum(mel[2:9]))
    mel_score = 20 if speech_mel_energy > 0.55 else (10 if speech_mel_energy > 0.38 else 0)

    # Feature 4: ZCR in voiced speech range
    zcr_val = _zcr(samples)
    zcr_score = 12 if 0.03 < zcr_val < 0.22 else 0

    # Feature 5: SNR above adaptive noise floor
    snr_score = 10 if snr > 4.0 else (5 if snr > 2.5 else 0)

    # Feature 6: Minimum RMS energy
    rms_score = 5 if rms > 0.015 else 0

    total = pitch_score + flat_score + mel_score + zcr_score + snr_score + rms_score

    return {
        "is_speech": total >= 52,
        "prob": total,
        "pitch": round(pitch, 1),
        "flatness": round(flatness, 3),
        "snr": round(snr, 2),
        "zcr": round(zcr_val, 4),
        "rms": round(rms, 5),
    }


# ── Whisper transcription ──────────────────────────────────────────────────

# Keywords that indicate possible cheating
_ANSWER_PATTERN = {
    "answer", "option", "choice", "correct", "right", "wrong", "true", "false",
    "select", "pick", "choose",
    "a", "b", "c", "d",
    "one", "two", "three", "four",
    "first", "second", "third", "fourth",
}

_TECH_PATTERN = {
    "stack", "queue", "binary", "hash", "sort", "loop", "function", "variable",
    "array", "class", "object", "algorithm", "complexity", "protocol",
    "http", "sql", "dns", "tcp", "ip", "memory", "pointer", "tree", "graph",
    "database", "server", "client", "network", "encryption",
}


def transcribe_audio(audio_samples: list, sample_rate: int = 16000) -> Optional[dict]:
    """
    Transcribe audio using Whisper base model.
    Returns {text, suspicious, language} or None if Whisper unavailable.
    """
    if not WHISPER_AVAILABLE:
        return None

    model = _get_whisper_model()
    if model is None:
        return None

    try:
        import tempfile, os
        import soundfile as sf

        samples = np.array(audio_samples, dtype=np.float32)
        # Resample to 16kHz if needed
        if sample_rate != 16000 and SCIPY_AVAILABLE:
            samples = _scipy_signal.resample_poly(samples, 16000, sample_rate)

        # Write to temp WAV
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name

        try:
            sf.write(tmp_path, samples, 16000, subtype="PCM_16")
            result = model.transcribe(
                tmp_path,
                language="en",
                fp16=False,
                condition_on_previous_text=False,
            )
        finally:
            os.remove(tmp_path)

        text = result.get("text", "").strip()
        if not text or len(text) < 3:
            return None

        words = set(text.lower().split())
        suspicious = bool(words & _ANSWER_PATTERN) or bool(words & _TECH_PATTERN)

        return {
            "text": text,
            "suspicious": suspicious,
            "language": result.get("language", "en"),
        }

    except ImportError:
        log.warning("soundfile not installed — using raw Whisper input")
        try:
            samples = np.array(audio_samples, dtype=np.float32)
            result = _get_whisper_model().transcribe(samples, language="en", fp16=False)
            text = result.get("text", "").strip()
            if not text or len(text) < 3:
                return None
            words = set(text.lower().split())
            suspicious = bool(words & _ANSWER_PATTERN) or bool(words & _TECH_PATTERN)
            return {"text": text, "suspicious": suspicious, "language": result.get("language", "en")}
        except Exception as e:
            log.error(f"Whisper transcription error: {e}")
            return None
    except Exception as e:
        log.error(f"transcribe_audio error: {e}")
        return None
