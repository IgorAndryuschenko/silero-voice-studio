"""Optional integration check using the installed model; run from the project root."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    import tkinter as tk
    import wave
    from app import App
    from speech_engine import DEFAULT_MODEL, ROOT, Engine, Options, write_wav
    from model_catalog import CIS_VOICES, RU_PATH, CIS_LABEL, RU_LABEL

    engine = Engine()
    output = ROOT / 'output'
    output.mkdir(exist_ok=True)
    assert set(engine.load(DEFAULT_MODEL).speakers) == set(CIS_VOICES)
    for speaker in ('ru_zhadyra', 'ru_oksana', 'ru_eduard'):
        raw, audio, _ = engine.generate('Прив+ет! Провер+яем г+олос.', DEFAULT_MODEL, Options(speaker=speaker))
        assert len(audio) > 0
        assert len(audio) <= len(raw)
        write_wav(output / f'check-{speaker}.wav', audio, 48000)
        print(f'OK voice {speaker}: {len(audio) / 48000:.2f}s', flush=True)
    for sample_rate in (8000, 24000):
        _, audio, _ = engine.generate('Всё раб+отает?', DEFAULT_MODEL,
                                     Options(sample_rate=sample_rate, rate='slow', pitch='low', accent=False, yo=False))
        write_wav(output / f'check-ssml-{sample_rate}.wav', audio, sample_rate)
        print(f'OK SSML {sample_rate}Hz: {len(audio) / sample_rate:.2f}s', flush=True)
    root = tk.Tk()
    root.withdraw()
    app = App(root)
    app.engine = engine
    assert app.options() == Options()
    assert all(str(check['state']) == 'disabled' for check in app.auto_checks)
    app.model_choice.set(RU_LABEL)
    app.select_model()
    assert app.options().speaker == 'kseniya' and app.options().accent
    app.model_choice.set(CIS_LABEL)
    app.select_model()
    assert app.options() == Options()
    app.mode.set('Расширенный')
    app.toggle_advanced()
    app.rate.set('Быстро')
    assert app.options().rate == 'fast'
    app.mode.set('Простой')
    app.toggle_advanced()
    assert app.options().rate == 'medium'
    # Exercise the same file-writing worker and main-thread completion used by the UI.
    app.worker('Прив+ет! +Я +Ада. Ст+удия г+олоса гот+ова к раб+оте.', DEFAULT_MODEL, app.options())
    app.poll()
    assert app.result is not None
    path, _, metadata, _, _ = app.result
    assert path.with_suffix('.json').is_file()
    with wave.open(str(path)) as wav:
        assert wav.getframerate() == 48000
        assert wav.getnchannels() == 1
        assert wav.getnframes() > 0
    root.update_idletasks()
    assert str(app.play_button['state']) == 'normal'
    app.close()
    if RU_PATH.is_file():
        _, legacy_audio, _ = engine.generate('Проверка.', RU_PATH, Options(speaker='kseniya', accent=True, yo=True))
        assert len(legacy_audio) > 0
        print('OK legacy v5_ru compatibility', flush=True)
    print(f'OK UI, worker, WAV and metadata: {path}', flush=True)


if __name__ == '__main__':
    main()
