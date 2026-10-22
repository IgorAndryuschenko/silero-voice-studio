"""Install/check the standalone environment before opening the desktop application."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / 'models' / 'silero-v5_ru.pt'
MODEL_URL = 'https://models.silero.ai/models/tts/ru/v5_ru.pt'
MODEL_SHA256 = '7ba04d42340fe0398042eed2e0d12d62e23096d626b1b9feff4dcb1309197ab4'
PROBE = '''
import sys, tkinter, torch, numpy, scipy
from importlib.metadata import version
assert tuple(map(int, version('numpy').split('.')[:2])) >= (2, 2)
assert int(version('numpy').split('.')[0]) < 3
assert tuple(map(int, version('scipy').split('.')[:2])) >= (1, 13)
assert int(version('scipy').split('.')[0]) < 2
assert tuple(map(int, version('torch').split('+')[0].split('.')[:2])) >= (2, 6)
assert int(version('torch').split('.')[0]) < 3
assert torch.tensor([1.0]).numpy().shape == (1,)
print('Python', sys.version.split()[0], '| PyTorch', torch.__version__, '| NumPy', numpy.__version__, '| SciPy', scipy.__version__)
'''


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def valid_model(path: Path) -> bool:
    return path.is_file() and digest(path) == MODEL_SHA256


def ensure_model(destination: Path = MODEL_PATH, legacy: Path | None = None):
    if valid_model(destination):
        print('Model checksum: OK', flush=True)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix('.pt.part')
    if legacy is None:
        legacy = Path(os.environ.get('LOCALAPPDATA', str(ROOT))) / 'SumomoScreenPet' / 'voice_models' / destination.name
    try:
        if valid_model(legacy):
            print('Reusing a verified local model (copy only).', flush=True)
            shutil.copyfile(legacy, partial)
        else:
            print('Downloading Silero V5 (~139 MiB) from models.silero.ai...', flush=True)
            request = urllib.request.Request(MODEL_URL, headers={'User-Agent': 'SileroVoiceStudio/1.0'})
            with urllib.request.urlopen(request, timeout=60) as response, partial.open('wb') as target:
                total = int(response.headers.get('Content-Length', 0))
                downloaded = 0
                last_report = time.monotonic()
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    target.write(block)
                    downloaded += len(block)
                    if time.monotonic() - last_report > 2:
                        print(f'  {downloaded // (1024 * 1024)} / {total // (1024 * 1024)} MiB', flush=True)
                        last_report = time.monotonic()
        if not valid_model(partial):
            raise RuntimeError('Model SHA-256 mismatch. The old file was preserved. Retry or check for an application update.')
        os.replace(partial, destination)
        print('Model downloaded and verified.', flush=True)
    finally:
        partial.unlink(missing_ok=True)


def run(*args):
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def probe_dependencies():
    return subprocess.run([sys.executable, '-c', PROBE], cwd=ROOT, capture_output=True, text=True)


def ensure_dependencies():
    result = probe_dependencies()
    if result.returncode == 0:
        print(result.stdout.strip(), flush=True)
        print('Dependencies: OK', flush=True)
        return
    print('Installing missing dependencies. This may take several minutes; allow 2 GB of free space.', flush=True)
    pip_check = subprocess.run([sys.executable, '-m', 'pip', '--version'], capture_output=True)
    if pip_check.returncode:
        run('-m', 'ensurepip', '--upgrade')
    run('-m', 'pip', 'install', '--disable-pip-version-check', '--index-url', 'https://pypi.org/simple', 'numpy>=2.2,<3', 'scipy>=1.13,<2')
    # The CPU wheel avoids downloading CUDA libraries on machines without a GPU.
    run('-m', 'pip', 'install', '--disable-pip-version-check', '--index-url', 'https://download.pytorch.org/whl/cpu', 'torch>=2.6,<3')
    run('-m', 'pip', 'check')
    result = probe_dependencies()
    if result.returncode and any(marker in result.stderr for marker in ('DLL load failed', 'WinError 126', 'WinError 1114')):
        print('Installing Microsoft Visual C++ runtime from Microsoft...', flush=True)
        subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                        str(ROOT / 'launcher.ps1'), '-InstallVCRuntime'], check=True)
        result = probe_dependencies()
    if result.returncode:
        raise RuntimeError('Dependency check failed:\n' + result.stderr)
    print(result.stdout.strip(), flush=True)


@contextmanager
def install_lock():
    """Windows releases the lock even if a setup process is interrupted."""
    import msvcrt
    setup = ROOT / '.setup'
    setup.mkdir(exist_ok=True)
    with (setup / 'install.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError('Another launcher is installing/checking this application. Wait for it to finish.') from exc
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Install/check everything without opening the app')
    args = parser.parse_args()
    if sys.platform != 'win32':
        raise RuntimeError('The desktop application requires Windows 10/11 x64.')
    if sys.prefix == sys.base_prefix:
        raise RuntimeError('Use run.bat to install dependencies into the private .venv environment.')
    with install_lock():
        ensure_dependencies()
        ensure_model()
        print('Checking actual speech synthesis...', flush=True)
        from speech_engine import Engine, Options
        _, audio, speakers = Engine().generate('Проверка.', MODEL_PATH, Options())
        if len(audio) == 0:
            raise RuntimeError('The model produced empty audio.')
        print('Speech check: OK | Voices: ' + ', '.join(speakers), flush=True)
    if args.check:
        print('All checks passed. The application is ready.', flush=True)
        return
    print('Opening Silero Voice Studio...', flush=True)
    log_path = ROOT / '.setup' / 'app.log'
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    with log_path.open('a', encoding='utf-8') as log:
        subprocess.Popen([str(pythonw if pythonw.is_file() else Path(sys.executable)), str(ROOT / 'app.py')],
                         cwd=ROOT, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr, flush=True)
        sys.exit(1)
