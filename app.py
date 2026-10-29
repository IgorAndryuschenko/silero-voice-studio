from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import queue
import shutil
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import winsound

from speech_engine import DEFAULT_MODEL, ROOT, Engine, Options, write_wav
from model_catalog import CIS_LABEL, RU_LABEL, CIS_PATH, RU_PATH, CIS_VOICES, RU_VOICES, DEFAULT_SPEAKER

RATES = {"Очень медленно": "x-slow", "Медленно": "slow", "Обычно": "medium", "Быстро": "fast", "Очень быстро": "x-fast"}
PITCHES = {"Очень низкий": "x-low", "Низкий": "low", "Обычный": "medium", "Высокий": "high", "Очень высокий": "x-high"}


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.engine = Engine()
        self.events = queue.Queue()
        self.result = None
        self.busy = False
        self.closed = False
        root.title("Silero · Студия голоса")
        root.geometry("900x820")
        root.minsize(760, 680)
        root.configure(bg="#f4f5fa")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#f4f5fa")
        style.configure("TLabel", background="#f4f5fa", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 24, "bold"))
        style.configure("Hint.TLabel", foreground="#62677f")
        style.configure("TButton", font=("Segoe UI", 10), padding=8)
        style.configure("Accent.TButton", background="#6553cc", foreground="white")
        style.map("Accent.TButton", background=[("active", "#5140b5")])
        style.configure("TCheckbutton", background="#f4f5fa", font=("Segoe UI", 10))
        self.mode = tk.StringVar(value="Простой")
        self.speaker = tk.StringVar(value=DEFAULT_SPEAKER)
        self.model_choice = tk.StringVar(value=CIS_LABEL)
        self.model_hint = tk.StringVar()
        self.model_path = tk.StringVar(value=str(DEFAULT_MODEL))
        self.rate = tk.StringVar(value="Обычно")
        self.pitch = tk.StringVar(value="Обычный")
        self.sample_rate = tk.StringVar(value="48000")
        self.trim = tk.BooleanVar(value=True)
        self.normalize = tk.BooleanVar(value=False)
        self.accent = tk.BooleanVar(value=False)
        self.yo = tk.BooleanVar(value=False)
        self.threshold = tk.StringVar(value="-48")
        self.padding = tk.StringVar(value="100")
        self.fade = tk.StringVar(value="5")
        self.autoplay = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Готова озвучивать. Модель работает локально на CPU.")

        body = ttk.Frame(root, padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Студия голоса", style="Title.TLabel").pack(anchor="w")
        ttk.Label(body, text="Silero V5 · текст → речь · локально", style="Hint.TLabel").pack(anchor="w", pady=(2, 16))
        model_bar = ttk.Frame(body)
        model_bar.pack(fill="x", pady=(0, 8))
        ttk.Label(model_bar, text="Модель").pack(side="left")
        self.model_box = ttk.Combobox(model_bar, textvariable=self.model_choice, values=(CIS_LABEL, RU_LABEL), state="readonly", width=30)
        self.model_box.pack(side="left", padx=10)
        self.model_box.bind('<<ComboboxSelected>>', self.select_model)
        ttk.Label(body, textvariable=self.model_hint, style="Hint.TLabel", wraplength=790).pack(anchor='w', pady=(0, 8))
        toolbar = ttk.Frame(body)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Голос").pack(side="left")
        self.voice_box = ttk.Combobox(toolbar, textvariable=self.speaker, values=CIS_VOICES, state="readonly", width=18)
        self.voice_box.pack(side="left", padx=(10, 24))
        ttk.Label(toolbar, text="Интерфейс").pack(side="left")
        modes = ttk.Combobox(toolbar, textvariable=self.mode, values=("Простой", "Расширенный"), state="readonly", width=18)
        modes.pack(side="left", padx=10)
        modes.bind("<<ComboboxSelected>>", self.toggle_advanced)
        ttk.Label(body, text="Текст для озвучивания").pack(anchor="w", pady=(16, 6))
        editor = ttk.Frame(body)
        editor.pack(fill="both", expand=True)
        self.text = tk.Text(editor, height=6, wrap="word", font=("Segoe UI", 13), relief="flat", padx=14, pady=12, undo=True)
        self.text.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(editor, command=self.text.yview)
        scrollbar.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.insert("1.0", "Прив+ет! +Я +Ада. Дав+ай преврат+им тво+и слов+а в г+олос.")
        self.text.bind("<Control-Return>", lambda _: self.generate())

        self.advanced = ttk.Frame(body, padding=(0, 10))
        model_row = ttk.Frame(self.advanced)
        model_row.pack(fill="x", pady=4)
        ttk.Label(model_row, text="Модель .pt").pack(side="left")
        ttk.Entry(model_row, textvariable=self.model_path).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(model_row, text="Выбрать…", command=self.choose_model).pack(side="left")
        synth = ttk.Frame(self.advanced)
        synth.pack(fill="x", pady=5)
        for label, variable, values, width in [("Темп", self.rate, tuple(RATES), 17), ("Тон", self.pitch, tuple(PITCHES), 16), ("Гц", self.sample_rate, ("8000", "24000", "48000"), 8)]:
            ttk.Label(synth, text=label).pack(side="left", padx=(0, 6))
            ttk.Combobox(synth, textvariable=variable, values=values, state="readonly", width=width).pack(side="left", padx=(0, 14))
        checks = ttk.Frame(self.advanced)
        checks.pack(fill="x", pady=5)
        self.auto_checks = []
        for label, variable in [("Автоударения", self.accent), ("Автоматическая «ё»", self.yo), ("Нормализация пика до −1 dBFS", self.normalize)]:
            check = ttk.Checkbutton(checks, text=label, variable=variable)
            check.pack(side="left", padx=(0, 14))
            if variable is not self.normalize:
                self.auto_checks.append(check)
        edges = ttk.Frame(self.advanced)
        edges.pack(fill="x", pady=5)
        ttk.Checkbutton(edges, text="Обрезать тишину по краям", variable=self.trim).pack(side="left", padx=(0, 12))
        for label, variable, low, high in [("Порог, dBFS", self.threshold, -80, -20), ("Запас, мс", self.padding, 30, 500), ("Сглаживание, мс", self.fade, 0, 20)]:
            ttk.Label(edges, text=label).pack(side="left", padx=(0, 5))
            ttk.Spinbox(edges, from_=low, to=high, textvariable=variable, width=5).pack(side="left", padx=(0, 12))
        ttk.Label(self.advanced, text="Обрезка удаляет только тихие края. Щелчки сглаживаются; шум и лишние слоги требуют отдельной обработки.", style="Hint.TLabel", wraplength=780).pack(anchor="w", pady=5)

        self.actions = ttk.Frame(body)
        self.actions.pack(fill="x", pady=(16, 8))
        self.generate_button = ttk.Button(self.actions, text="✦  Создать дорожку", style="Accent.TButton", command=self.generate)
        self.generate_button.pack(side="left")
        self.play_button = ttk.Button(self.actions, text="▶  Слушать", command=self.play, state="disabled")
        self.play_button.pack(side="left", padx=8)
        ttk.Button(self.actions, text="■  Стоп", command=lambda: winsound.PlaySound(None, 0)).pack(side="left")
        self.save_button = ttk.Button(self.actions, text="Сохранить WAV…", command=self.save, state="disabled")
        self.save_button.pack(side="right")
        ttk.Checkbutton(body, text="Слушать после генерации", variable=self.autoplay).pack(anchor="w")
        self.waveform = tk.Canvas(body, height=92, bg="#eae8f6", highlightthickness=0)
        self.waveform.pack(fill="x", pady=(12, 6))
        self.waveform.bind("<Configure>", lambda _: self.draw_wave())
        self.progress = ttk.Progressbar(body, mode="indeterminate")
        self.progress.pack(fill="x", pady=5)
        ttk.Label(body, textvariable=self.status, style="Hint.TLabel", wraplength=790).pack(anchor="w")
        ttk.Label(body, text="Ctrl + Enter — создать · В простом режиме используются стандартные настройки", style="Hint.TLabel").pack(anchor="w", pady=(8, 0))
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.select_model()
        root.after(100, self.poll)

    def select_model(self, _=None):
        cis = self.model_choice.get() == CIS_LABEL
        self.model_path.set(str(CIS_PATH if cis else RU_PATH))
        self.voice_box.configure(values=CIS_VOICES if cis else RU_VOICES)
        self.speaker.set(DEFAULT_SPEAKER if cis else 'kseniya')
        self.accent.set(not cis)
        self.yo.set(not cis)
        for check in self.auto_checks:
            check.configure(state='disabled' if cis else 'normal')
        self.model_hint.set('MIT · коммерческое использование разрешено. Ударения задавайте вручную: прив+ет, к+ошка. Автоударений нет.' if cis else 'Некоммерческая лицензия. Автоударения доступны. Для коммерческого проекта выбирайте v5_cis_base.')

    def toggle_advanced(self, _=None):
        if self.mode.get() == "Расширенный":
            self.advanced.pack(fill="x", before=self.actions)
            self.root.geometry("960x940")
        else:
            self.advanced.pack_forget()
            self.root.geometry("900x820")

    def choose_model(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(title="Модель Silero", filetypes=[("Silero PyTorch", "*.pt")])
        if path:
            selected = Path(path).resolve()
            if selected in (CIS_PATH.resolve(), RU_PATH.resolve()):
                self.model_choice.set(CIS_LABEL if selected == CIS_PATH.resolve() else RU_LABEL)
                self.select_model()
            else:
                self.model_path.set(path)
                self.model_choice.set('Пользовательская')
                self.model_hint.set('Пользовательская модель: проверьте её собственную лицензию и требования к тексту.')

    def options(self):
        if self.mode.get() == "Простой":
            auto = self.model_choice.get() == RU_LABEL
            return Options(speaker=self.speaker.get(), accent=auto, yo=auto)
        threshold, padding, fade = float(self.threshold.get()), int(self.padding.get()), int(self.fade.get())
        if not (-80 <= threshold <= -20 and 30 <= padding <= 500 and 0 <= fade <= 20):
            raise ValueError("Порог: −80…−20 dBFS, запас: 30…500 мс, сглаживание: 0…20 мс.")
        return Options(speaker=self.speaker.get(), sample_rate=int(self.sample_rate.get()),
                       rate=RATES[self.rate.get()], pitch=PITCHES[self.pitch.get()],
                       trim=self.trim.get(), threshold_db=threshold, padding_ms=padding,
                       fade_ms=fade, normalize=self.normalize.get(), accent=self.accent.get(), yo=self.yo.get())

    def generate(self):
        if self.busy:
            return
        text = self.text.get("1.0", "end-1c")
        try:
            options = self.options()
            if not text.strip():
                raise ValueError("Введите слово или предложение.")
            model_path = Path(self.model_path.get()).expanduser()
            if not model_path.is_file():
                self.mode.set("Расширенный")
                self.toggle_advanced()
                raise ValueError("Модель не найдена. Выберите установленный файл Silero V5 .pt.")
        except (ValueError, KeyError) as exc:
            messagebox.showinfo("Проверь настройки", str(exc))
            return
        self.busy = True
        self.model_box.configure(state='disabled')
        self.voice_box.configure(state='disabled')
        winsound.PlaySound(None, 0)
        self.generate_button.configure(state="disabled")
        self.play_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self.progress.start()
        self.status.set("Загружаю модель… Первый запуск может занять немного времени.")
        threading.Thread(target=self.worker, args=(text, model_path, options), daemon=True).start()

    def worker(self, text, model_path, options):
        try:
            started = time.perf_counter()
            raw, audio, speakers = self.engine.generate(text, model_path, options, lambda m: self.events.put(("status", m)))
            out = ROOT / "output"
            out.mkdir(exist_ok=True)
            name = f"silero-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1000000:06d}"
            path, raw_path = out / f"{name}.wav", out / f"{name}-original.wav"
            write_wav(raw_path, raw, options.sample_rate)
            write_wav(path, audio, options.sample_rate)
            metadata = {"text": text, "model": str(model_path), "model_license": 'MIT' if model_path.resolve() == CIS_PATH.resolve() else 'see model license', "settings": asdict(options),
                        "seconds": len(audio) / options.sample_rate, "original": raw_path.name}
            path.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            self.events.put(("done", (path, audio, metadata, time.perf_counter() - started, speakers)))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == "status":
                    self.status.set(value)
                    continue
                self.busy = False
                self.model_box.configure(state='readonly')
                self.voice_box.configure(state='readonly')
                self.progress.stop()
                self.generate_button.configure(state="normal")
                if event == "done":
                    self.result = value
                    path, audio, metadata, elapsed, speakers = value
                    self.voice_box.configure(values=speakers)
                    self.status.set(f"Готово · {metadata['seconds']:.1f} с аудио · создано за {elapsed:.1f} с · {path.name}")
                    self.draw_wave()
                    if self.autoplay.get():
                        self.play()
                else:
                    self.status.set("Не удалось создать дорожку. Можно исправить настройки и повторить.")
                    messagebox.showerror("Ошибка генерации", value)
                state = "normal" if self.result else "disabled"
                self.play_button.configure(state=state)
                self.save_button.configure(state=state)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def draw_wave(self):
        self.waveform.delete("all")
        width, height = self.waveform.winfo_width(), self.waveform.winfo_height()
        if not self.result or width < 2:
            self.waveform.create_text(max(150, width / 2), height / 2, text="Здесь появится звуковая дорожка", fill="#726a96", font=("Segoe UI", 10))
            return
        import numpy as np
        audio = self.result[1]
        for x, part in enumerate(np.array_split(audio, max(1, width // 3))):
            peak = float(np.max(np.abs(part))) if len(part) else 0
            amplitude = max(1, peak * height * .44)
            self.waveform.create_line(x * 3, height / 2 - amplitude, x * 3, height / 2 + amplitude, fill="#7964ce", width=2)

    def play(self):
        if self.result:
            try:
                winsound.PlaySound(str(self.result[0]), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            except RuntimeError as exc:
                messagebox.showerror("Прослушивание", str(exc))

    def save(self):
        if not self.result:
            return
        source = self.result[0]
        target = filedialog.asksaveasfilename(title="Сохранить дорожку", defaultextension=".wav", initialfile=source.name, filetypes=[("WAV audio", "*.wav")])
        if target:
            try:
                if Path(target).resolve() != source.resolve():
                    shutil.copyfile(source, target)
                self.status.set(f"Сохранено: {target}")
            except OSError as exc:
                messagebox.showerror("Сохранение", str(exc))

    def close(self):
        if self.busy and not messagebox.askyesno("Закрыть студию?", "Генерация ещё идёт. Закрыть окно и прервать её?"):
            return
        self.closed = True
        winsound.PlaySound(None, 0)
        self.root.destroy()


if __name__ == "__main__":
    App(tk.Tk()).root.mainloop()
