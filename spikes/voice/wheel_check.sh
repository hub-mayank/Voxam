#!/bin/bash
# Which speech packages resolve to binary wheels on this Python? Dry runs only: nothing is installed.
# Usage: bash spikes/voice/wheel_check.sh   (from the worktree root, venv active)
cd "$(dirname "$0")/../.." || exit 1
python --version
for pkg in numpy soundfile av ctranslate2 onnxruntime faster-whisper tokenizers piper-tts kokoro-onnx kokoro silero-vad pysilero-vad \
           webrtcvad webrtcvad-wheels torch pipecat-ai livekit livekit-agents websockets sounddevice jiwer indic-transliteration; do
  out=$(pip install --dry-run --only-binary=:all: --quiet --disable-pip-version-check --report - "$pkg" 2>&1)
  if echo "$out" | grep -q '"install"'; then
    echo "$out" | python -c "
import sys, json
r = json.load(sys.stdin)
names = {i['metadata']['name'].lower(): (i['metadata']['version'], i['download_info']['url'].rsplit('/',1)[-1]) for i in r['install']}
want = '$pkg'.lower().replace('_','-')
v, f = names.get(want) or next(((v, f) for n, (v, f) in names.items() if n.replace('_','-') == want), ('?', '?'))
heavy = [n for n in names if n in ('torch','torchaudio','onnxruntime','ctranslate2','av','tokenizers','numpy')]
print(f'OK    {\"$pkg\":18} {v:12} {f[:60]:60} also pulls: {\",\".join(heavy)}')"
  else
    echo "FAIL  $pkg   $(echo "$out" | grep -E 'ERROR|No matching|Could not' | head -1 | cut -c1-150)"
  fi
done
