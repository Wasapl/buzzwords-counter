#!/bin/zsh
# BuzzWords Counter Launcher
set -e

# Navigate to app directory
cd "$(dirname "$0")"

# Check virtual environment exists
if [[ ! -d "venv" ]]; then
    echo "Error: Virtual environment not found. Run:"
    echo "  python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Check required packages are installed
if ! python -c "import vosk, pyaudio, jellyfish" 2>/dev/null; then
    echo "Missing dependencies. Installing from requirements.txt..."
    pip install -r requirements.txt
fi

# Check Vosk model exists (prefer large model for better accuracy)
if [[ ! -d "vosk-model-en-us-0.22" && ! -d "vosk-model-small-en-us-0.15" ]]; then
    echo "No Vosk speech model found."
    echo "Downloading large model (~1.8 GB) for best accuracy..."
    echo "(To use the small 40 MB model instead, press Ctrl+C and run:)"
    echo "  curl -LO https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip && unzip -q vosk-model-small-en-us-0.15.zip && rm vosk-model-small-en-us-0.15.zip"
    echo ""
    curl -L -o vosk-model.zip https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip
    unzip -q vosk-model.zip && rm vosk-model.zip
    echo "Model downloaded successfully."
elif [[ -d "vosk-model-en-us-0.22" ]]; then
    echo "Using large Vosk model."
else
    echo "Using small Vosk model. For better accuracy, download the large model:"
    echo "  curl -LO https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip && unzip -q vosk-model-en-us-0.22.zip && rm vosk-model-en-us-0.22.zip"
fi

# Run the application
python word_counter.py
