# Stationary onboard-microphone demonstration

The main demo video keeps the **laptop microphone**. Board microphone input is a
separate, opt-in stationary test. Natural remains the voice for spoken replies.
The board captures sound; the laptop still recognizes speech and runs the apps.

**Status:** software receiver and recognition path tested with synthetic speech
over localhost UDP. Actual microphone clarity and commands on the physical FC
remain unverified until the next powered session. No new soldering is expected.

## 1. Keep the known working demo command

From `firmware\base-station`:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --device 3
```

This selects the laptop microphone. Add `--host 10.0.0.47` for the FC LCD when
using your normal display power. No board audio streaming is requested.

## 2. When ready: record the board microphone first

1. Leave motors stopped and props removed for this stationary bench check.
2. Power the FC/ESP32 and let it join the same home Wi-Fi as the laptop. The
   microphone uses the 3.3 V supply and should be testable with the board's USB
   power alone; the LCD needs its separate normal 5 V supply arrangement.
3. Close the assistant with **Q** and close other tools receiving FC telemetry
   or audio on UDP port 5005. The receiver needs sole ownership of that port.
4. Check the laptop Wi-Fi IPv4 address with `ipconfig`. Current ESP32 build
   sends audio to **10.0.0.66:5005**. Merely setting `--host` does not change
   that destination. If the laptop has a different address, share that address
   before changing settings; the firmware's base destination needs updating.
5. Use the ESP32's current Wi-Fi IP below (last verified **10.0.0.47**):

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.esp_mic_check --host 10.0.0.47 --seconds 12
```

Wait for **Recording**, then speak from about 30–50 cm away: **Kogane. Show me
my tasks for today. Testing the onboard microphone.** The tool records only
incoming board audio; it does not open the laptop microphone or speakers.

It saves a timestamped WAV and JSON report under `outputs\board_mic` and prints
their paths. Open the WAV in your audio player. Check that your actual words
are clear, with no sustained buzz, silence or distortion. The report gives
duration, peak level, clipping fraction and packet-loss counters. Receiving
packets does not by itself prove intelligible speech.

The tool requests **MIC_OFF** on exit, including on exceptions. UDP has no
acknowledgement, so the serial monitor's **mic streaming disabled** log is the
hardware confirmation; reboot also restores the configured stream-off default.

If no audio arrives, the tool reports an error after about eight seconds.
Check the laptop address, ESP32 address, power and Windows private-network
firewall permission for this project's Python. A port-in-use error means another
program already owns the receive port. The existing `mic level` serial logs can
help check whether capture is responding to speech.

## 3. Try real commands using only the board microphone

Once the recording is clear:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --mic-source esp32 --mic-host 10.0.0.47
```

Do **not** include `--device 3` in this mode. The laptop microphone is not opened,
and a failed board stream does not silently switch to it. `--mic-host` selects
audio input without sending LCD updates, so this can run as a laptop-preview
test while the physical screen is unpowered.

1. Wait for **Say Kogane**; this appears only after board audio arrives.
2. Say **Kogane** near the board. Wait for **Listening**.
3. Say **Show me my tasks for today** and wait for the reply.
4. While the list footer says Listening, try a task command if desired.
5. Say **Stop listening**. Wake again and ask **Show me the weather today**.
   Weather needs laptop internet access as usual.
6. Repeat from the distance you want to film. Press **D** to show **Mic: Board**
   in the laptop details. Wake/action logs also record `microphone: esp32`.

For LCD output as well, use:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --mic-source esp32 --host 10.0.0.47
```

`--host` supplies both the LCD destination and the board mic host in this form.
LCD orientation and Natural speech settings keep their current defaults.

## 4. What a successful short clip establishes

Show the stationary board, speak toward it, capture Listening and the task card,
and identify the microphone source in the laptop details. This demonstrates
**board microphone → Wi-Fi → laptop recognition → answer/display**. It does not
establish voice recognition during flight or recognition running on the ESP32.

Press **Q** before returning to the laptop demo command in section 1.

## Implementation notes

- Uses existing 16 kHz mono signed-16 PCM `AUDIO_MIC` packets; no ESP32 firmware
  changes were required in the repository. A deployed build mismatch can still
  require attention during the physical test.
- Sends only microphone ON/OFF controls plus the existing optional LCD packets.
  No motor, arm, flight-mode, setpoint or servo commands are sent.
- Accepts valid audio only from the selected ESP32 IP/UDP port. Reordering is
  limited to a small window of about 80 ms; duplicates/late packets are discarded. Packet loss or queue
  overload resets the wake session and asks for Kogane again, preventing delayed
  fragments from being combined into a command. A three-second stream outage
  reports microphone failure and requires restarting the test.
- Incoming audio is drained and discarded during spoken replies, and pending
  audio is cleared on resume. This avoids replaying the assistant's own reply.
  It is not full acoustic echo cancellation.
- `--mic-gain` can tune recognition level later; first inspect the raw recording.
  Increasing gain also raises noise and cannot fix a wrong I2S slot or wiring.
