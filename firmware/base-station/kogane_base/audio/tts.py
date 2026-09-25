"""Text-to-speech with no new dependencies.

Windows already ships a speech synthesiser: `System.Speech.Synthesis.SpeechSynthesizer`, the
SAPI 5 wrapper in the .NET Framework. It is reachable from PowerShell, which is also already
there, so "the drone says something" costs zero pip installs. `SapiTts` shells out to
PowerShell, asks for a 16 kHz 16-bit mono WAV via `SpeechAudioFormatInfo` — exactly the
format `fmt = 1` fixes on the wire — and hands back the path. No resampling in the middle,
so nothing to get wrong.

Everything sits behind `TtsBackend` (a two-method protocol) so replacing this with a cloud
voice later means adding a class, not editing the sender or the CLI.

On text safety: the text never goes onto the PowerShell command line. It is written to a
temporary UTF-8 file and the script reads it back, so a line like `"; Remove-Item -Recurse
$HOME ; #` is just words to be spoken rather than a second command. Voice name and rate go
through the environment for the same reason.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..config import CONFIG
from ..protocol import AUDIO_RATE_HZ

log = logging.getLogger("kogane.audio.tts")


class TtsError(RuntimeError):
    """Synthesis was attempted and failed."""


class TtsUnavailable(TtsError):
    """The backend cannot run here at all (no PowerShell, no System.Speech, not Windows)."""


@runtime_checkable
class TtsBackend(Protocol):
    """Text in, WAV file out. That is the whole contract."""

    name: str

    def available(self) -> bool: ...

    def synthesise(self, text: str, out_path: str | os.PathLike) -> Path: ...


# The synthesis script. Reads its inputs from the environment so nothing is interpolated
# into PowerShell source. `SetOutputToWaveFile` with an explicit SpeechAudioFormatInfo is
# what gets 16 kHz mono directly instead of the default 22.05 kHz.
_PS_SYNTH = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$text = [System.IO.File]::ReadAllText($env:KGN_TTS_TEXT_FILE, [System.Text.Encoding]::UTF8)
if ([string]::IsNullOrWhiteSpace($text)) { throw 'nothing to say' }
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    if ($env:KGN_TTS_VOICE) {
        $want = $env:KGN_TTS_VOICE
        $match = $synth.GetInstalledVoices() |
            Where-Object { $_.Enabled -and $_.VoiceInfo.Name -like "*$want*" } |
            Select-Object -First 1
        if ($null -eq $match) { throw "no enabled voice matches '$want'" }
        $synth.SelectVoice($match.VoiceInfo.Name)
    }
    if ($env:KGN_TTS_RATE) { $synth.Rate = [int]$env:KGN_TTS_RATE }
    $fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(
        [int]$env:KGN_TTS_RATE_HZ,
        [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
        [System.Speech.AudioFormat.AudioChannel]::Mono)
    $synth.SetOutputToWaveFile($env:KGN_TTS_OUT, $fmt)
    $synth.Speak($text)
    $synth.SetOutputToNull()
    Write-Output ("voice=" + $synth.Voice.Name)
} finally {
    $synth.Dispose()
}
"""

_PS_VOICES = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $synth.GetInstalledVoices() | ForEach-Object {
        '{0}|{1}|{2}|{3}' -f $_.VoiceInfo.Name, $_.VoiceInfo.Culture,
                             $_.VoiceInfo.Gender, $_.Enabled
    }
} finally {
    $synth.Dispose()
}
"""


def find_powershell() -> str | None:
    """Locate a usable PowerShell. Prefers `powershell.exe` over `pwsh`.

    Deliberate: `System.Speech` is a .NET Framework assembly that Windows PowerShell 5.1
    loads without help, while PowerShell 7 on .NET Core may not have it at all. `pwsh` is
    the fallback only because on some machines it is the only one on PATH.
    """
    for exe in ("powershell.exe", "powershell", "pwsh.exe", "pwsh"):
        found = shutil.which(exe)
        if found:
            return found
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    fallback = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(fallback) if fallback.exists() else None


class SapiTts:
    """Windows SAPI via PowerShell. Produces 16 kHz 16-bit mono WAV directly."""

    name = "sapi"

    def __init__(self, voice: str | None = None, rate: int | None = None,
                 powershell: str | None = None, timeout_s: float = 60.0,
                 sample_rate: int = AUDIO_RATE_HZ) -> None:
        self.voice = CONFIG.tts_voice if voice is None else voice
        self.rate = CONFIG.tts_rate if rate is None else int(rate)
        self.powershell = powershell or find_powershell()
        self.timeout_s = float(timeout_s)
        self.sample_rate = int(sample_rate)
        self.last_voice: str | None = None

    # ---- capability ----------------------------------------------------------------
    def available(self) -> bool:
        """True if PowerShell exists and `System.Speech` loads. Runs a real probe."""
        if self.powershell is None:
            return False
        try:
            self._run("Add-Type -AssemblyName System.Speech; Write-Output ok",
                      env={}, timeout_s=min(self.timeout_s, 30.0))
            return True
        except TtsError as e:
            log.debug("SAPI probe failed: %s", e)
            return False

    def require(self) -> None:
        """Raise `TtsUnavailable` with something actionable if this cannot work."""
        if self.powershell is None:
            raise TtsUnavailable(
                "no PowerShell found on PATH. SAPI text-to-speech needs Windows "
                "PowerShell (powershell.exe). On non-Windows hosts, pass a different "
                "TTS backend or use `kogane-audio --wav` with a pre-rendered file.")
        if sys.platform != "win32":
            raise TtsUnavailable(
                f"SAPI is Windows-only and this is {sys.platform}. Render speech "
                "elsewhere and send it with `kogane-audio --wav file.wav`.")

    # ---- synthesis -----------------------------------------------------------------
    def synthesise(self, text: str, out_path: str | os.PathLike) -> Path:
        """Speak `text` into `out_path` as a 16 kHz mono 16-bit WAV. Returns the path."""
        self.require()
        text = text.strip()
        if not text:
            raise TtsError("nothing to say: the text is empty")

        out = Path(out_path)
        if out.parent and not out.parent.exists():
            out.parent.mkdir(parents=True, exist_ok=True)

        tmp_dir = Path(tempfile.mkdtemp(prefix="kgn-tts-"))
        text_file = tmp_dir / "say.txt"
        text_file.write_text(text, encoding="utf-8")
        try:
            env = {
                "KGN_TTS_TEXT_FILE": str(text_file),
                "KGN_TTS_OUT": str(out),
                "KGN_TTS_VOICE": self.voice or "",
                "KGN_TTS_RATE": str(self.rate) if self.rate else "",
                "KGN_TTS_RATE_HZ": str(self.sample_rate),
            }
            stdout = self._run(_PS_SYNTH, env=env)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        for line in stdout.splitlines():
            if line.startswith("voice="):
                self.last_voice = line[len("voice="):].strip()

        if not out.exists() or out.stat().st_size == 0:
            raise TtsError(f"SAPI reported success but {out} is missing or empty")
        log.info("SAPI synthesised %d char(s) -> %s (%d bytes, voice=%s)",
                 len(text), out, out.stat().st_size, self.last_voice or "default")
        return out

    def voices(self) -> list[tuple[str, str, str, bool]]:
        """Installed voices as (name, culture, gender, enabled)."""
        self.require()
        rows: list[tuple[str, str, str, bool]] = []
        for line in self._run(_PS_VOICES, env={}).splitlines():
            parts = line.strip().split("|")
            if len(parts) == 4:
                rows.append((parts[0], parts[1], parts[2],
                             parts[3].strip().lower() == "true"))
        return rows

    # ---- plumbing ------------------------------------------------------------------
    def _run(self, script: str, env: dict[str, str], timeout_s: float | None = None) -> str:
        assert self.powershell is not None
        cmd = [self.powershell, "-NoProfile", "-NonInteractive",
               "-ExecutionPolicy", "Bypass", "-Command", script]
        full_env = dict(os.environ)
        full_env.update(env)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, env=full_env,
                                  timeout=timeout_s or self.timeout_s)
        except FileNotFoundError as e:
            raise TtsUnavailable(f"could not start {self.powershell!r}: {e}") from e
        except subprocess.TimeoutExpired as e:
            raise TtsError(f"PowerShell timed out after {timeout_s or self.timeout_s:g}s"
                           ) from e
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            first = detail.splitlines()[0] if detail else "no output"
            if "System.Speech" in detail or "Add-Type" in detail:
                raise TtsUnavailable(
                    "PowerShell could not load System.Speech — this host has no SAPI "
                    f"synthesiser available. PowerShell said: {first}")
            raise TtsError(f"PowerShell exited {proc.returncode}: {first}")
        return proc.stdout


def default_backend() -> TtsBackend:
    """The backend for this host. Only SAPI exists today, and only on Windows."""
    return SapiTts()


def synthesise_to_wav(text: str, out_path: str | os.PathLike | None = None,
                      backend: TtsBackend | None = None) -> Path:
    """Synthesise `text` to a WAV, defaulting to a temp file the caller should delete."""
    be = backend or default_backend()
    if out_path is None:
        fd, tmp = tempfile.mkstemp(prefix="kgn-say-", suffix=".wav")
        os.close(fd)
        out_path = tmp
    return be.synthesise(text, out_path)
