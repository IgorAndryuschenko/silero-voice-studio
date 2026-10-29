"""Local Silero synthesis. The entered text and its speech rendition stay separate."""
from __future__ import annotations

from dataclasses import dataclass
import html
import os
from pathlib import Path
import re
import wave
from model_catalog import CIS_PATH, DEFAULT_SPEAKER

ROOT = Path(__file__).resolve().parent
LOCAL_MODEL = ROOT / "models" / "silero-v5_ru.pt"
LEGACY_MODEL = Path(os.environ.get("LOCALAPPDATA", str(ROOT))) / "SumomoScreenPet" / "voice_models" / "silero-v5_ru.pt"
DEFAULT_MODEL = CIS_PATH


@dataclass(frozen=True)
class Options:
    speaker: str = DEFAULT_SPEAKER
    sample_rate: int = 48000
    rate: str = "medium"
    pitch: str = "medium"
    trim: bool = True
    threshold_db: float = -48
    padding_ms: int = 100
    fade_ms: int = 5
    normalize: bool = False
    accent: bool = False
    yo: bool = False


def render_ssml(text: str, options: Options) -> str:
    # Literal XML is escaped; user text is never executed as SSML.
    return (f'<speak><prosody rate="{options.rate}" pitch="{options.pitch}">'
            f'{html.escape(text)}</prosody></speak>')


def split_text(text: str, limit: int = 500) -> list[str]:
    """Bound each model call while preserving every word and punctuation mark."""
    chunks: list[str] = []
    remaining = text.strip()
    while len(remaining) > limit:
        window = remaining[:limit]
        endings = list(re.finditer(r'[.!?…][»"\)]*\s+|\n+', window))
        end = endings[-1].end() if endings else window.rfind(" ")
        if end <= 0:
            raise ValueError("Слишком длинное слово: добавьте пробелы (не более 500 символов подряд).")
        chunks.append(remaining[:end].strip())
        remaining = remaining[end:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def process_audio(samples, sample_rate: int, options: Options):
    """Trim only outer quiet frames; never remove pauses within speech."""
    import numpy as np
    audio = np.asarray(samples, dtype=np.float32).reshape(-1).copy()
    if not len(audio) or not np.isfinite(audio).all():
        raise ValueError("Модель вернула пустое или повреждённое аудио.")
    if options.trim:
        frame = max(1, round(sample_rate * 0.01))
        # Peak per 10 ms window protects quiet consonants better than mean RMS.
        padded = np.pad(np.abs(audio), (0, (-len(audio)) % frame))
        peaks = padded.reshape(-1, frame).max(axis=1)
        active = np.flatnonzero(peaks > 10 ** (options.threshold_db / 20))
        if len(active):
            padding = round(sample_rate * options.padding_ms / 1000)
            start = max(0, int(active[0]) * frame - padding)
            end = min(len(audio), (int(active[-1]) + 1) * frame + padding)
            audio = audio[start:end].copy()
    if options.normalize:
        peak = float(np.max(np.abs(audio)))
        if peak > 1e-6:
            audio *= (10 ** (-1 / 20)) / peak
    fade = min(round(sample_rate * options.fade_ms / 1000), len(audio) // 2)
    if fade > 1:
        ramp = np.linspace(0, 1, fade, dtype=np.float32)
        audio[:fade] *= ramp
        audio[-fade:] *= ramp[::-1]
    return np.clip(audio, -1, 1)


def write_wav(path: Path, samples, sample_rate: int) -> None:
    import numpy as np
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm.tobytes())


class Engine:
    def __init__(self):
        self.model = None
        self.path: Path | None = None

    def load(self, path: Path):
        if not path.is_file():
            raise FileNotFoundError("Выберите локальный файл модели Silero V5 (.pt).")
        if self.model is None or path != self.path:
            import torch
            torch.set_num_threads(4)
            model = torch.package.PackageImporter(str(path)).load_pickle("tts_models", "model")
            model.to(torch.device("cpu"))
            self.model, self.path = model, path
        return self.model

    def generate(self, text: str, path: Path, options: Options, progress=lambda message: None):
        import numpy as np
        import torch
        if not text.strip():
            raise ValueError("Введите слово или предложение.")
        if len(text) > 20000:
            raise ValueError("За один раз можно озвучить до 20 000 символов.")
        model = self.load(path)
        if options.speaker not in model.speakers:
            raise ValueError(f"Голоса {options.speaker} нет в выбранной модели. Доступны: {', '.join(model.speakers)}")
        chunks = split_text(text)
        pieces = []
        with torch.inference_mode():
            for index, chunk in enumerate(chunks):
                progress(f"Озвучиваю фрагмент {index + 1} из {len(chunks)}…")
                kwargs = dict(speaker=options.speaker, sample_rate=options.sample_rate,
                              put_accent=options.accent, put_stress_homo=options.accent,
                              stress_single_vowel=options.accent,
                              put_yo=options.yo, put_yo_homo=options.yo)
                if options.rate == options.pitch == "medium":
                    audio = model.apply_tts(text=chunk, **kwargs)
                else:
                    audio = model.apply_tts(ssml_text=render_ssml(chunk, options), **kwargs)
                pieces.append(audio.detach().cpu().numpy().reshape(-1))
        raw = np.concatenate(pieces)
        return raw, process_audio(raw, options.sample_rate, options), list(model.speakers)
