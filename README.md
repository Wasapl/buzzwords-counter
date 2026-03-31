# BuzzWords Counter

A cross-platform application (macOS, Linux, Windows) that uses **Vosk** (offline, real-time speech recognition) for two live modes:

- **Buzzword mode**: count how many times you say one target word
- **Dashboard mode**: track all recognized words and show frequency ranking (most-used to least-used)

It automatically catches many abbreviation mis-transcriptions like "AI", "GPU", "ML" with phonetic matching. No internet connection or API keys required.

## Features

- 🎤 Real-time streaming speech recognition (~250ms latency)
- 🔀 Two modes with a UI toggle: Buzzword and Dashboard
- 🔢 Live word counting with partial result tracking
- 🎯 Customizable target word (default: "AI")
- 📊 Live word-frequency dashboard (all words, sorted by count)
- 🔊 **Automatic phonetic matching** — catches "ay", "a i", "ay eye" etc. for "AI"
- 📐 **Plural & possessive support** — "AIs", "AI's", "hellos" etc. matched automatically
- 🎙️ Microphone selector with refresh support
- 📝 Transcript display showing what was heard
- ▶️ Start/Stop controls
- 🔄 Reset counter
- 🛡️ Robust error handling with automatic retries (audio read, model loading)
- 🔒 Fully offline — no API keys, no internet, no data leaves your machine

## Requirements

- **macOS, Linux, or Windows**
- Python 3.8+
- Microphone access
- Tkinter (usually bundled with Python; see platform notes below)

### Platform notes

| Platform | Tkinter | PortAudio (for PyAudio) |
|----------|---------|-------------------------|
| **macOS** | `brew install python-tk@3.13` | `brew install portaudio` |
| **Linux** | `sudo apt install python3-tk` (Debian/Ubuntu) | `sudo apt install portaudio19-dev` |
| **Windows** | Included with the official python.org installer | Included in the PyAudio wheel |

## Installation

1. **Clone or download** the project:
   ```
   cd word-counter-app
   ```

2. **Create a virtual environment and install dependencies:**

   macOS / Linux:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

   Windows (Command Prompt or PowerShell):
   ```bat
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Download a Vosk speech model**:

   Recommended (better recognition, larger RAM/disk):
   ```bash
   # macOS / Linux
   curl -L -o vosk-model.zip https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip
   unzip -q vosk-model.zip && rm vosk-model.zip
   ```
   ```powershell
   # Windows PowerShell
   Invoke-WebRequest https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip -OutFile vosk-model.zip
   Expand-Archive vosk-model.zip . && Remove-Item vosk-model.zip
   ```
   This creates `vosk-model-en-us-0.22/`.

   Lightweight alternative (40 MB):
   ```bash
   # macOS / Linux
   curl -L -o vosk-model.zip https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
   unzip -q vosk-model.zip && rm vosk-model.zip
   ```
   ```powershell
   # Windows PowerShell
   Invoke-WebRequest https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -OutFile vosk-model.zip
   Expand-Archive vosk-model.zip . && Remove-Item vosk-model.zip
   ```
   This creates `vosk-model-small-en-us-0.15/`.

   The app prefers the large model automatically when both are present.

   > **Tip:** The `run_app.py` launcher installs missing Python packages and downloads a model automatically. It only requires an existing `venv/` directory.

4. **Grant microphone permissions** (macOS / Linux):
   - macOS: System Settings > Privacy & Security > Microphone — allow Terminal or your Python IDE
   - Linux: ensure your user is in the `audio` group (`sudo usermod -aG audio $USER`)

## Usage

1. **Run the application:**

   **Recommended — works on all platforms:**
   ```bash
   python run_app.py        # macOS / Linux
   python run_app.py        # Windows
   ```

   **macOS / Linux shell shortcut:**
   ```bash
   chmod +x run_app.sh
   ./run_app.sh
   ```

   **Or manually (after activating the venv):**
   ```bash
   # macOS / Linux
   source venv/bin/activate
   python word_counter.py

   # Windows
   venv\Scripts\activate
   python word_counter.py
   ```

2. **Select your microphone** from the dropdown (refresh if needed)

3. **Choose a mode**:
   - **Buzzword**: enter a target word (default "AI")
   - **Dashboard**: no target word required

4. **Click "Start"** to begin speech recognition

   - The app first runs a short **3-second mic calibration** phase.
   - During this time, status shows `Calibrating mic...` and early audio is intentionally ignored.
   - After calibration, status switches to `Listening...` and counting begins.

5. **Speak naturally** — the app will:
   - Display what it heard in the transcript area
   - In Buzzword mode: count occurrences of your target word in real time
   - In Dashboard mode: build a sorted word-frequency table
   - Show both partial (live) and final (committed) results

6. **Click "Stop"** to pause listening

7. **Click "Reset"** to clear counters and transcript

## How It Works

The app uses:
- **Vosk** for offline, streaming speech-to-text (via `KaldiRecognizer`)
- **jellyfish** for phonetic matching (Metaphone, Soundex, Jaro-Winkler similarity)
- **PyAudio** for direct microphone audio capture (16 kHz, mono, 250ms chunks)
- **Tkinter** for the graphical user interface

### Dual Recognizer Architecture
The app adapts its recognizer strategy based on the target word type:

**For abbreviations** (AI, GPU, SAS, ...), the app runs **two Vosk recognizers** simultaneously on the same audio stream:

1. **Grammar-constrained recognizer** — configured with only the phonetic variants of the target word (+ `[unk]`). This biases Vosk's decoder heavily toward the target, dramatically improving detection of short/unusual tokens.
2. **Unconstrained recognizer** — runs freely for human-readable transcript display.

The grammar recognizer drives the count; the unconstrained recognizer drives the transcript.

**For regular words** (long, hello, ...), only the **unconstrained recognizer** runs. It handles both transcript display and counting via compiled phonetic regex matching. A grammar-constrained approach is counterproductive for common words — a tiny grammar like `["long", "[unk]"]` causes Vosk to force-map unrelated speech to the target, producing many false positives.

### Confidence Filtering
The grammar recognizer returns per-word confidence scores. Tokens with confidence below the threshold (default: 0.6) are discarded to prevent false positives — e.g. when background noise or common words like "hey" are force-mapped to target variants.

### Peak Partial Tracking
Vosk emits partial results as speech is being recognized. Sometimes a partial correctly detects a target word, but a later partial revision or the final result loses it. The app tracks the **peak partial match count** per utterance so that once a match is detected, it is never lost to a later revision.

### Audio Pipeline
PyAudio captures 250ms frames → for abbreviations, both recognizers process each frame (grammar results drive the counter with confidence filtering, unconstrained results drive the transcript); for regular words, only the unconstrained recognizer runs and drives both counting and transcript.

### Startup Calibration
To improve first-run accuracy, the app ignores the first **3.0 seconds** of microphone input after Start is pressed. This allows audio routing, gain control, and noise suppression to stabilize before recognition/counting begins.

### Phonetic Matching
When you click "Start" in Buzzword mode, the app builds a `PhoneticMatcher` for your target word:

- **Abbreviations** (e.g. "AI", "GPU", "ML", "SAS"): auto-generates letter-by-letter phonetic variants using a built-in pronunciation table. For short abbreviations (like "AI"), standalone sounds (e.g. "ay") are included for recall. For longer abbreviations (3+ letters), standalone letter sounds are excluded to reduce false positives. Phonetic neighbours are intentionally skipped for abbreviations.
- **Regular words**: uses Metaphone and Soundex phonetic algorithms to find similar-sounding words.
- **Plurals & possessives**: all variants also match their plural (`AIs`, `ais`) and possessive (`AI's`) forms automatically via an optional regex suffix.
- All variants are compiled into a single regex for fast real-time matching.

## Troubleshooting

### Microphone not working
- **macOS**: System Settings > Privacy & Security > Microphone — allow Terminal / your IDE
- **Linux**: Run `sudo usermod -aG audio $USER` and log out/in; check `arecord -l` for device list
- **Windows**: Settings > Privacy > Microphone — allow desktop apps access
- Ensure your microphone is working in other applications
- Try selecting a different microphone from the dropdown
- Try restarting the application

### PyAudio installation errors

**macOS** — install PortAudio first:
```bash
brew install portaudio
pip install pyaudio
```

**Linux (Debian/Ubuntu)**:
```bash
sudo apt install portaudio19-dev python3-dev
pip install pyaudio
```

**Windows** — pre-built wheels are available for Python 3.8+:
```bat
pip install pyaudio
```
If that fails, try:
```bat
pip install pipwin && pipwin install pyaudio
```

### Vosk model not found
Make sure at least one model directory exists in the project root:
- `vosk-model-en-us-0.22/` (preferred)
- `vosk-model-small-en-us-0.15/`

Re-download if needed (macOS / Linux):
```bash
curl -L -o vosk-model.zip https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip
unzip -q vosk-model.zip && rm vosk-model.zip
```

Windows PowerShell:
```powershell
Invoke-WebRequest https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip -OutFile vosk-model.zip
Expand-Archive vosk-model.zip . && Remove-Item vosk-model.zip
```

### Poor recognition accuracy
- Wait for calibration to finish (`Calibrating mic...` → `Listening...`) before speaking target words
- Speak clearly and at a moderate pace
- Reduce background noise
- Move your microphone closer
- For better accuracy (especially fillers/short sounds), use `vosk-model-en-us-0.22`

## Running Tests

```bash
# macOS / Linux
source venv/bin/activate
python -m unittest test_word_counter

# Windows
venv\Scripts\activate
python -m unittest test_word_counter
```

All 151 tests should pass.

## Notes

- Fully offline — no internet connection or API keys required
- Word matching is case-insensitive
- **Abbreviations are auto-expanded** into phonetic variants, with stricter matching for 3+ letter acronyms to reduce false positives
- **Plurals and possessives** are matched automatically (e.g. "AIs", "AI's")
- The counter increments for each occurrence of the word, even if it appears multiple times in one phrase
- Dashboard mode tracks all recognized words in memory and sorts by highest count
- The app uses peak-partial tracking and confidence filtering so words are not double-counted or lost during streaming
- Audio stream retries up to 5 consecutive read errors before stopping
- Vosk model loading retries up to 3 times with 1-second delays
- Stream cleanup is thread-safe (guarded by a dedicated lock)

## License

Free to use and modify for personal and commercial purposes.
