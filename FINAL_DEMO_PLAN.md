# Kogane: finish the demo video in 2–3 hours

Updated 2026-10-19. Start the clock when beginning the steps below. This is the
current plan; it supersedes the earlier overnight recording schedule and the
older estimates in FIRST_FLIGHT_PLAN.md.

**Progress:** user confirmed the physical LCD/assistant works and recorded a good
video. An initially white screen cleared after disconnecting battery/all USB,
waiting, then connecting battery first without SW3. Use that working startup
order so the LCD is powered when the ESP32 initializes it. Exact cause of the
white screen was not independently established. User confirms the board-mic
recording works and has now recorded the live onboard-microphone assistant clip.
Both audio/LCD clips are secured. ToF is now enabled, detected healthy, and the
user confirms changing distance readings work with a video recorded.
The original LCD board now has a suspected VSYS short and stays unpowered;
the substitute FC is used for manual radio flight. Its custom Quad+ layout
is M4 front, M3 right, M2 rear, M1 left. Mixer, physical sensor alignment,
accelerometer calibration, ARM/ANGLE, battery-only arm/disarm, motor rotation
and armed radio-loss stop/recovery checks have passed. Radio-off stop took
1-2 seconds; motors stayed stopped when the radio returned. Next: loaded
weight/actual propulsion suitability, external battery health, mechanical and
range checks and first-flight location/pilot. No first flight yet.

## Scope for this recording

- **Main voice demonstration:** laptop microphone, Natural voice through laptop
  speakers, real weather and editable tasks on the physical FC LCD.
- **Radio flight:** Pocket/ELRS, manual throttle and ANGLE mode, brief hover only
  after the flight checks pass. Voice and room tracking do not steer the aircraft.
- **Mapping:** reuse the working laptop webcams/LD2450 demonstration or record
  one short take. The onboard ESP32 camera is deferred.
- **Extra bench clips:** onboard microphone and ToF are optional, time-limited
  demonstrations. Neither is required for the manual flight.
- **Deferred:** battery-sense divider/ADC work, onboard camera, onboard amplifier,
  autonomous following/docking, altitude/position hold and new UI features.
- User reports the power arrangement is verified and the replacement battery
  setup is ready. Motor order/direction and radio-loss bench checks are done.

**Target:** finish and export a coherent video within three hours. A flight clip
depends on passing the checks below; the video can still be completed with the
working voice/LCD, mapping and bench clips if a flight issue appears.

## Remaining work at a glance

| Item | Current status | Required today? |
| --- | --- | --- |
| Main voice/LCD demonstration | User confirms working and good video recorded | Clip secured |
| LCD orientation, readable cards, Wi-Fi delivery | Physical assistant screen now working after battery-first restart | Done for recorded take |
| Basic motor operation | All four respond on substitute FC/new ESC | Bench check passed |
| Motor number → physical corner and rotation | User confirms final rotation check done; custom Quad+ M1 left CCW, M2 rear CW, M3 right CCW, M4 front CW | Bench check passed |
| Quad mixer, FC orientation, accelerometer calibration | Correct Plus mmix, yaw900 response and stored six-point calibration verified | Bench check passed |
| ARM/ANGLE switches, endpoints and low throttle | SA/CH5 ARM 1800-2100; ANGLE 900-2100; radio response verified | Bench check passed |
| Battery-only arm/disarm and armed RC-loss failsafe | Passed; radio-off stop in1-2s, no restart on radio recovery | Bench check passed |
| Complete aircraft weight and motor/prop/load suitability | Weight pending | Before flight |
| Mechanical inspection, radio check and stable battery-only operation | Pending | Before flight |
| Actual board microphone recording/recognition | User confirms recording works and live command video captured | Clip secured |
| ToF detection and changing distance readings | VL53L1X healthy; user confirms distance response and video captured | Clip secured |
| Mapping clip | Working capability reported; saved usable take needs selecting | Include existing take or one short new take |
| Film selection, captions and export/playback check | Pending | Yes |

**Latest preflight inputs (2026-10-19):** User confirms actual SPEEDX2 1303.5
5500KV motors and Gemfan3018 props, has no scale, and is balance charging the
replacement4S pack to4.2V/cell. Loaded mass and exact propulsion margin remain
unresolved. User has never flown a quad; recommend an experienced pilot for
the maiden. Proposed first-flight site is a large empty indoor room with high
ceilings. Recommend a suitable clear outdoor model-flying area with calm
conditions and experienced pilot for the maiden; indoor site suitability and
prop guards are not established from ceiling height. Continue mechanical
inspection and obtain complete-aircraft photos / borrowed kitchen-scale weight
while charging. No flight readiness has been established from bench passes.

## Three-hour schedule

| Elapsed | Work | Finish condition |
| --- | --- | --- |
| 0–10 min | Prepare bench, charge/check pack, save FC settings, weigh aircraft | Props off; working settings backed up; weight recorded |
| 10–40 min | Laptop audio + physical LCD; film the successful sequence now | Weather and task/edit clip saved and played back |
| 40–50 min | Optional stationary board mic recording + command | Clear received speech and successful command, or defer at 10 min |
| 50–65 min | Select existing mapping take; record a replacement only if needed | One usable map/radar/camera clip |
| 65–75 min | Optional ToF detection/distance check | Real changing range reading, or defer at 10 min |
| 75–125 min | FC orientation/calibration, controls, motor order/direction, battery-only arming/failsafe, final inspection | Every flight check below passed |
| 125–150 min | Conditional short flight session and inspection; otherwise film bench evidence | One usable flight or bench clip |
| 150–180 min | Edit, captions, export and playback | Final video file checked |

The flight slot assumes a suitable, nearby, well-lit flying location is already
available. Travel, missing compatible propulsion data, firmware rebuilding or
major troubleshooting can push flight beyond this window.

If the pack needs a long charge, start it now and move laptop-only rehearsal,
mapping selection and overview filming into that time. Charge with the pack
disconnected from the aircraft, using the specified rate; charging and powering
the aircraft are separate operations. Reorder the table around charge completion
and recheck charge after battery-powered bench work. Do not increase charge rate
to meet the deadline. A pack that isn't ready moves the flight slot.

**Two-hour version:** omit board mic, ToF and a new mapping take. Use 5 minutes
prep, 25 minutes voice/LCD, 10 minutes selecting mapping/overview footage,
40 minutes flight checks, 15 minutes conditional flight/bench filming and
25 minutes editing/export. If checks take longer, use the remaining time to
finish the video rather than compressing the flight checks.

**Time limits:** record the working features before experimenting. At 125 minutes,
make the flight decision. Keep the final 30 minutes for export. A failed optional
sensor check gets a follow-up note, not a rushed soldering or firmware session.

## A. First 10 minutes: preparation

- [ ] Remove all props. Set Pocket ARM/SA low and throttle fully down.
- [ ] Use a healthy replacement pack and the charge mode specified on its actual
      label. Do not assume it has the same LiHV charge limit as the retired pack.
      Charge on a suitable surface with the charger/pack instructions followed.
- [ ] In iNAV CLI, save the actual `diff all` output to a new dated text file.
      Keep this backup; do not paste the repository's hand-written reference diff.
- [ ] Weigh the complete intended flying configuration, including battery and
      fitted payload/props. Note motor markings and actual prop size/pitch.
- [ ] Fix the phone framing so it can see the LCD and hear you and the laptop.
      Make a short framing/audio test and play it back.

### Battery sensing is deferred; charge tracking is still external

Do not use the FC's roughly 4.8 V reading to judge this pack. Check the actual
pack/cells using the balance charger or cell checker before flight and again
after landing. Disconnect the flight battery between stationary takes when it
isn't needed, and account for bench use before the hover. Use a freshly checked
pack for the flight slot; topping up after prolonged bench testing may be needed.

For this initial flight, aim for **one 10–20 second hover**, then land/disarm and
inspect. A short timer limits exposure; it does not establish battery health or
remaining charge. There is no reliable live low-voltage warning from the FC yet.
If the false ADC reading creates an arming blocker, bring back `status` and the
battery settings for a targeted adjustment; do not disable all arming checks.

## B. Audio and LCD together: secure the main clip first

Use the verified power arrangement for the screen. In PowerShell:

```powershell
cd C:\Users\sujay\OneDrive\Documents\koganeee\firmware\base-station
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --device 3 --host 10.0.0.47
```

Use the current ESP32 Wi-Fi address if it changed. Natural is already the
default. Keep the laptop online for weather. No model download, firmware flash
or further voice tuning is scheduled.

1. Confirm the physical LCD shows the same card as the laptop and is readable
   in the correct orientation. If still horizontally mirrored, **H** toggles the
   transmitted mirror; **R** resends the current card. Resolve orientation once.
2. Say **Kogane**, wait for Listening, then **Show me the weather today**. Check
   the physical card and actual spoken forecast. Allow time for generation.
3. Say **Kogane**, wait for Listening, then **Show me my tasks for today**.
4. After the spoken reply and the list footer's Listening cue, say **New task
   record the demo video**. Check it appears. Say **Complete task [shown number]**
   after the next reply; use the stable number actually displayed.
5. Say **Stop listening**. Repeat the short sequence once if necessary.
6. Record a continuous phone take showing the real wake/listening transition,
   screen response and audible reply. Play it back before moving on.

**Pass:** clear audio, correctly oriented physical LCD, successful weather and
task edit, with no resets. If Wi-Fi or the LCD fails, fix that before adding
another peripheral. Keyboard A/W/T remain labelled rehearsal, not voice footage.

### Optional board-microphone clip: maximum 10 minutes

Close the assistant with Q. Follow [BOARD_MIC_TEST.md](BOARD_MIC_TEST.md):

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.esp_mic_check --host 10.0.0.47 --seconds 12
```

Play the saved recording. If intelligible, try:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --mic-source esp32 --host 10.0.0.47
```

Show one real wake/command and Mic: Board in D details. Close with Q afterward.
Current firmware sends audio to laptop **10.0.0.66:5005**; if the address differs
or no audio arrives, stop at the time limit and keep the main laptop-mic clip.
This is a stationary capability check; no in-flight microphone claim is needed.

## C. Mapping take: reuse the working setup

Use an existing clean take if available. Otherwise, leave the two monitor webcams
and radar placement unchanged. Quit other camera/COM6 users, then:

```powershell
$take = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
.\.venv\Scripts\python.exe -m kogane_base.tools.mapping_demo --position-source radar --camera 2 --camera2 1 --baseline 0.40 --camera-yaw 15 --camera2-yaw -15 --radar-port COM6 --room-width 5 --room-depth 4 --map-objects --record-width 1920 --record "outputs\room_demo_$take.mp4"
```

These are the last documented device IDs/settings; retain different settings
from your current working launch if applicable. Use F for fullscreen and C to
clear the trail. Walk for 30–45 seconds; include the chair box in a camera view.
Press Q to finalize the video, then play the saved file.

Caption the actual behavior: **Radar person tracking + camera object detection**.
Chair floor position calibration remains deferred, so don't describe the chair
as accurately placed on the floor map. This clip is separate from flight.

## D. ToF: a separate check before motor work

Keep props off and motors stopped. ToF success is useful footage but does not
enable altitude hold for this first flight. iNAV's rangefinder functionality is
documented in its [rangefinder guide](https://github.com/iNavFlight/inav/blob/9.1.0/docs/Rangefinder.md).

1. Read and save:

```text
get rangefinder_hardware
status
resource
```

2. U5 is the VL53L1X on STM32 I2C1 (PB6/PB7). XSHUT is PB8. If the setting is
   NONE and **VL53L1X is listed among the allowed values**, enable only this
   setting for the bench check:

```text
set rangefinder_hardware = VL53L1X
save
```

3. Reconnect and inspect `status`. Only proceed to a range-readout demonstration
   if it detects a working sensor. Move a matte card along the sensor's viewing
   direction at measured distances such as 20, 40 and 60 cm; verify readings
   change sensibly. A sensor name alone does not prove useful measurements.
4. Check which way its optical window points on the assembled aircraft. An
   upward-facing sensor is not a downward altitude sensor. Do not rotate the
   whole FC just to aim it without correcting and rechecking FC alignment.
5. If undetected/unreliable at ten minutes, restore the recorded previous
   rangefinder setting, save/reboot and defer diagnosis. No rushed XSHUT bodges,
   driver changes or firmware rebuild is included in this session.

Do not enable ALTHOLD, SURFACE, POSHOLD or RTH for the first hover. ANGLE levels
the aircraft; you still control height with throttle.

## E. Flight checks: motor operation already tested, remaining checks pending

**Props remain removed throughout this section.** Recheck configuration after
any changes. The [iNAV getting-started checks](https://github.com/iNavFlight/inav/blob/9.1.0/docs/Getting%20Started.md)
include orientation, receiver/control setup and a props-off failsafe test.

### 1. Assembly, propulsion and FC orientation

- [ ] Battery, FC, receiver antennas, repaired wires and motor leads are secured;
      no wire can reach a prop. Screen/servo mechanism stays stowed and secured.
- [ ] Confirm weight and propulsion suitability. README lists SPEEDX2 1303.5
      5500KV motors and Gemfan 3018 props. GEPRC rates that motor for 2–4S LiPo
      and describes 2-inch guarded/2.5-inch freestyle applications; its page
      does not establish the thrust/current margin of this custom 3-inch loaded
      build. Confirm the actual combination against suitable propulsion data or
      an experienced builder before flight. A 45 A ESC rating is not a lift rating.
      [Manufacturer specifications](https://geprc.com/product/geprc-speedx2-1303-5-3800kv-5500kv-motor/)
- [ ] iNAV's model follows physical roll, pitch and yaw correctly. Complete the
      Configurator accelerometer calibration and level alignment. Moving numbers
      alone did not verify orientation. Keep the aircraft still during boot.

### 2. Radio and modes

- [ ] Correct roll/pitch/yaw channel identity and direction; sensible centers;
      minimum throttle is recognized as low (previous measurement was 989).
- [ ] SA/CH5 low disarms; high requests arm. Verify the saved ARM range survives
      reboot. AUX1/CH5 is the recommended ELRS arm channel.
      [ExpressLRS setup](https://www.expresslrs.org/quick-start/pre-1stflight/)
- [ ] Assign ANGLE to another working latching switch/channel and confirm its
      active state in iNAV Modes. Verify that switch changes the intended channel
      in Receiver first. Keep navigation modes off.
- [ ] Retain SERIAL/CRSF for the receiver and the working custom firmware.
      Do not switch to MSP receiver/voice control or flash an online stock target.

### 3. Motor identification and direction

Use Outputs to run one motor at a time at the lowest reliable speed. Record its
physical corner and direction, viewed from above, against the **selected iNAV
mixer diagram**. Do not assume motor numbering from the ESC's physical layout.

| iNAV output | Actual corner | Actual direction | Matches mixer? |
| --- | --- | --- | --- |
| M1 | | | |
| M2 | | | |
| M3 | | | |
| M4 | | | |

- [ ] All four positions and rotation directions match the mixer.
- [ ] Correct any mismatch using the ESC's supported direction configuration
      or a deliberately planned wiring change; changing a mixer expectation
      alone is not proof that the physical motor reversed.
- [ ] Every motor starts/stops reliably, with no scraping, abnormal heat or resets.
      No high-throttle bench run is needed. Inspect again after any changes.

The repository's custom mapping uses PA0–PA3, with M4 on TIM5 CH4 to avoid a DMA
collision. Preserve that working mapping. If a motor stops working, collect
`resource`, `status` and a description; do not rush a target rebuild for the deadline.

### 4. Battery-only arm/disarm and armed failsafe

Exit Outputs/CLI, disconnect STM32 USB and use the radio on the secured,
props-off aircraft. USB/CLI arming inhibition should not be bypassed just to
perform this test. Close the assistant before normal radio flight checks.

- [ ] ARM low at startup; arm deliberately with throttle low.
- [ ] Disarm switch stops all motors promptly; repeat the normal arm/disarm once.
- [ ] With props off and motors at idle/low speed, perform the planned radio-loss
      test. Confirm the configured **DROP** procedure stops motors/disarms after
      its configured detection delay. Never test this by switching the radio off
      during flight.
- [ ] Restore radio with ARM low. Check there is no automatic motor restart and
      obey the recovery/re-arm lockout. Earlier disarmed RC_LINK tests did not
      establish this behavior. [iNAV failsafe behavior](https://github.com/iNavFlight/inav/blob/9.1.0/docs/Failsafe.md)
- [ ] Perform the radio manufacturer's range/link check for the intended site.
      Confirm intended Wi-Fi/electronics operation does not disrupt ELRS or reset
      the FC. Complete a final battery-only cold start and repeat control checks.

Current saved ESP32 configuration has FC_RX_ONLY enabled, servo boot sweep off,
camera off and onboard speaker off. Its bounded PARAM_REQUEST_LIST test only
reads parameters and returns TX to input; removing that diagnostic is not a
mandatory reflash for today's independent RC flight. Keep flight-command blocking.
Do not launch `kogane_base.main`; the standalone demo tools are the intended apps.

## F. Flight decision and short recording

Proceed only when every item in section E has passed, the propulsion combination
is suitable, and a suitable flying location/pilot is ready. If this is your first
manual quad flight, have an experienced pilot handle the first lift if possible.
Keep it away from people and furnishings; do not hand-launch or string-tether it.
For outdoor flight, check the applicable category/site rules using the measured
operating weight. [Transport Canada categories](https://tc.canada.ca/en/aviation/drone-safety/learn-rules-you-fly-your-drone/drone-operation-categories-pilot-certificates)

1. Disconnect power, fit the correct props to the verified directions, and check
   mounting/clearance. Props go on only after the props-off work is finished.
2. Use the freshly checked pack. Set an audible short-flight timer and arrange
   the recording before arming; the pilot concentrates on flying.
3. Make one brief, low, manual ANGLE hover, about 10–20 seconds, then land/disarm.
   No screen deployment, voice commands, mapping-based control or altitude hold.
4. Stop promptly for oscillation, yaw spin, uncontrolled tilt, weak lift, radio
   trouble or resets. Land/disarm rather than trying to obtain the full clip.
5. Disconnect and inspect the aircraft; check cells and motor/ESC temperature
   before another attempt. Don't turn repeated "short" attempts into one long
   unmonitored battery session.

If flight checks are incomplete at the cutoff, record the props-off motor/order
and RC control work and finish the video with that accurate status. Do not label
bench motor footage as flight.

## G. Edit and export: final 30 minutes

Build a roughly **90–150 second** video from the best clips:

| Sequence | Suggested length | Content |
| --- | --- | --- |
| Aircraft / custom electronics overview | 5–10 s | Establish the physical project |
| Kogane → Listening → real weather | 20–30 s | Physical LCD + laptop audio |
| Tasks → new task → completed task | 20–30 s | Actual voice edits and screen response |
| Room tracking / chair detection | 15–25 s | Existing radar/webcam dashboard |
| Optional board-mic / ToF evidence | 5–15 s each | Include only actual successful checks |
| Manual hover, or accurately labelled bench milestone | 10–20 s | Show what passed today |
| Closing status | 5 s | Tested capabilities and next milestone |

Use concise captions: **Laptop voice recognition · FC LCD**, **Live weather**,
**Voice-editable tasks**, **Radar tracking + camera detection**, and **Manual RC
flight** only for actual flight footage. Optional microphone clip: **Onboard mic
→ Wi-Fi → laptop recognition**. ToF detection alone should not be called altitude hold.

- [ ] Export 1080p using the original high-resolution dashboard clip.
- [ ] Play the complete export; check screen readability, voice volume, beginning
      and ending, and that all clips are present.
- [ ] Keep the original phone clips, dashboard MP4/CSV and exported video.

## Soldering, parts and what waits

No scheduled soldering or new purchases are needed for the voice/LCD and working
mapping clips. Use the existing meter/charger, tools and a borrowed scale if needed.
A suitable motor/prop/load match, secure mounting and external cell checking still
need to be established for flight. If that identifies a missing part, repair or
purchase, flight moves out of today's schedule; the other video sections proceed.

After the deadline: battery sensing/calibration, full ToF diagnosis if needed,
onboard mic optimization, onboard camera/U10, amplifier repair, microSD/blackbox,
longer flight validation and autonomous modes. These are not silently completed
by finishing today's video.
