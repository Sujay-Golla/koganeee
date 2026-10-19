# Kogane voice styles

**Selected voice: Natural.** The user chose `mascot-natural`; it is now the
assistant's default for both weather and task replies. Restart the assistant to
apply it. No speech-style flag is needed.

The requested direction is the Japanese Kogane character's lively mascot style,
with **English replies retained**. The original candidates use Microsoft Zira
plus pitch/texture effects. Two new candidates use the free local Kokoro neural
speech model for a more natural base, retaining the higher mascot pitch. These
are generic synthetic voices, not the anime recording or a clone of its
performer. No service, account or payment is required. Neural voices need a
one-time model/runtime download, already completed on this laptop.

## Listen first

Open the WAV files in `firmware\base-station\outputs\voice_samples`:

| File | Sound direction |
| --- | --- |
| `normal.wav` | Existing Windows default, for comparison |
| `bright.wav` | Zira raised three semitones, a little quicker |
| `mascot.wav` | Zira raised five semitones, slower source delivery to balance playback speed |
| `electronic.wav` | Mascot plus a light buzzy texture |
| `mascot-natural.wav` | Kokoro Heart, raised four semitones; softer candidate |
| `mascot-lively.wav` | Kokoro Bella, raised 4.5 semitones, quicker pacing; animated candidate |

The sample weather sentence uses example values solely to compare voices. The
assistant's real weather command still fetches its actual current forecast.

The user preferred the original **Mascot**, but asked for a livelier, less
robotic result, then selected **mascot-natural** after comparing the new samples. The neural
model supplies the phrasing/intonation; a stronger electronic buzz is not added.
Choose by listening. Pitch processing also
raises formants and speeds playback, so stronger settings can sound cartoonish.
It does not reproduce Japanese pronunciation, acting or an accent. For genuinely
Japanese spoken replies, a Japanese speech engine and translated responses would
be a separate step. [VOICEVOX](https://voicevox.hiroshiba.jp/) is one free option
with multiple character voices and adjustable intonation, subject to the selected
voice's terms. It is not installed or integrated here.

## Use a style

Close the assistant with **Q**, then from the base-station folder run:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --device 3
```

Use `--speech-style mascot-lively` for the more animated candidate, or `mascot`
for the original sample. `bright`, `electronic` and `normal` also remain as explicit
overrides. The default is `mascot-natural`. These options apply to **both weather and task
replies**. The first reply needs a moment to generate; repeated replies use a
cache separated by text, voice, rate and effect settings. The microphone remains
paused through generation/playback to avoid hearing its own reply.

Optional `--tts-rate -2` slows source speech. For Windows styles, `--tts-voice
David` changes the base voice; installed choices are David and Zira. For neural
styles, voice overrides use Kokoro IDs such as `af_heart` or `af_bella` instead.
Keep `--device 3`; speech output settings do not change the microphone selection.
Add the usual `--host 10.0.0.47` for the physical LCD when powered.

## Make another comparison

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.voice_preview
.\.venv\Scripts\python.exe -m kogane_base.tools.voice_preview --style mascot --rate -2 --text "Your task is saved!"
.\.venv\Scripts\python.exe -m kogane_base.tools.voice_preview --style mascot-natural --style mascot-lively
```

This only writes audio files; it does not play sound, open the microphone or
contact the FC. Actual generated WAVs were checked for valid mono 16-bit audio.
Automated checks verify the pitch interval, silence preservation, output bounds,
cache isolation, failed-generation recovery and assistant setting forwarding.
Sound similarity and intelligibility need your listening judgment.

## Neural setup and performance

Already installed here: `kokoro-onnx==0.6.1` and its dependencies, with the
full-precision Kokoro v1.0 model and voice pack in `models\kokoro-v1.0` (ignored
by Git). To reproduce this on another machine:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[character-voice]"
.\.venv\Scripts\python.exe -m kogane_base.tools.setup_kokoro_voice
```

Setup downloads about 354 MB from the maintainer's release and verifies sizes
and SHA-256 hashes. Replies never download files or upload text/audio. A missing
model reports an error; it does not silently substitute the Windows voice.
The model loads once per assistant process and then remains available for new
task titles and actual forecasts. CPU use is limited to four inference threads.

The smaller INT8 model was tried but ran too slowly on this laptop. The selected
full-precision model loaded in about 1.2 seconds, then generated a short task
reply in 0.7 seconds and a weather sentence in 3.6 seconds in a local benchmark.
Those times can change with sentence length and other running applications.
Neural output keeps its native 24 kHz audio for the laptop speaker; display
packets and microphone settings are unchanged.

Sources: [Kokoro ONNX runtime and model downloads](https://github.com/thewh1teagle/kokoro-onnx),
[Kokoro model/voices](https://huggingface.co/hexgrad/Kokoro-82M).
