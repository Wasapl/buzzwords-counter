#!/usr/bin/env python3
"""Cross-platform launcher for BuzzWords Counter.

Works on macOS, Linux, and Windows.
Run this script with any Python 3.8+ interpreter — it will re-exec itself
inside the project virtual environment, install missing packages if needed,
and then start word_counter.py.
"""

import os
import platform
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_LARGE_DIR = "vosk-model-en-us-0.22"
MODEL_SMALL_DIR = "vosk-model-small-en-us-0.15"
MODEL_LARGE_URL = "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip"
MODEL_SMALL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"


def _venv_python():
    """Return the path to the Python interpreter inside the venv."""
    if platform.system() == "Windows":
        return os.path.join(SCRIPT_DIR, "venv", "Scripts", "python.exe")
    return os.path.join(SCRIPT_DIR, "venv", "bin", "python")


def _re_exec_in_venv():
    """If we are not already running inside the project venv, re-exec there."""
    venv_py = _venv_python()
    if os.path.realpath(sys.executable) == os.path.realpath(venv_py):
        return  # already inside the venv

    if not os.path.isfile(venv_py):
        print("Error: Virtual environment not found.")
        print("Create one first:")
        if platform.system() == "Windows":
            print("  python -m venv venv")
            print("  venv\\Scripts\\pip install -r requirements.txt")
        else:
            print("  python3 -m venv venv")
            print("  source venv/bin/activate && pip install -r requirements.txt")
        sys.exit(1)

    sys.exit(subprocess.run([venv_py, os.path.abspath(__file__)]).returncode)


def _ensure_deps():
    """Install missing Python packages from requirements.txt if needed."""
    try:
        import jellyfish  # noqa: F401
        import pyaudio  # noqa: F401
        import vosk  # noqa: F401
    except ImportError:
        print("Missing dependencies — installing from requirements.txt...")
        req = os.path.join(SCRIPT_DIR, "requirements.txt")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req])


def _download_with_progress(url, dest):
    """Download *url* to *dest*, printing a progress bar."""
    import urllib.request

    print(f"Downloading {url}")
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as out:  # noqa: S310
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 256 * 1024
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            out.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = downloaded * 100 // total
                mb_done = downloaded // (1024 * 1024)
                mb_total = total // (1024 * 1024)
                print(f"\r  {pct:3d}%  {mb_done} / {mb_total} MB", end="", flush=True)
    print()


def _ensure_model():
    """Make sure at least one Vosk model directory is present."""
    model_large = os.path.join(SCRIPT_DIR, MODEL_LARGE_DIR)
    model_small = os.path.join(SCRIPT_DIR, MODEL_SMALL_DIR)

    if os.path.isdir(model_large):
        print(f"Using large Vosk model ({MODEL_LARGE_DIR}).")
        return
    if os.path.isdir(model_small):
        print(
            f"Using small Vosk model ({MODEL_SMALL_DIR}). "
            "For better accuracy, also download the large model."
        )
        return

    print("No Vosk speech model found.")
    print(f"Downloading large model (~1.8 GB) to: {model_large}")
    print("Press Ctrl+C to cancel and download the small model (40 MB) manually instead:")
    print(f"  {MODEL_SMALL_URL}")
    print()

    import zipfile

    zip_path = os.path.join(SCRIPT_DIR, "vosk-model.zip")
    try:
        _download_with_progress(MODEL_LARGE_URL, zip_path)
        print("Extracting model…")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(SCRIPT_DIR)
        os.remove(zip_path)
        print("Model ready.")
    except KeyboardInterrupt:
        print("\nCancelled.")
        if os.path.exists(zip_path):
            os.remove(zip_path)
        sys.exit(1)


def main():
    _re_exec_in_venv()
    _ensure_deps()
    _ensure_model()

    import runpy
    runpy.run_path(os.path.join(SCRIPT_DIR, "word_counter.py"), run_name="__main__")


if __name__ == "__main__":
    main()
