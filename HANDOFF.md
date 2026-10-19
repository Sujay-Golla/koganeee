# Handoff — Kogane (2026-09-23)

**PROPOSED FIRST-HOVER SITE INDOOR ROOM 2026-10-19:** User answers physical
site is "a large empty room with high ceilings". Combined with no prior quad
flight experience, unknown loaded weight and unresolved5500KV/3018/4S margin,
recommend clear outdoor model-flying area in calm conditions with experienced
pilot for maiden. High ceiling alone does not resolve lateral/flip risks.
Actual prop guards, assembly and clearances unknown; full top/side photos
requested but not supplied. Keep props off pending actual mechanical/propulsion
review; no first-flight instructions/clearance yet. Continue preparation rather
than assume room is suitable or short flight duration establishes safety.

**PREFLIGHT INPUTS / FIRST-TIME PILOT 2026-10-19:** User has no scale, plans
to balance charge replacement 4S LiPo to4.2V/cell, confirms actual GEPRC
SPEEDX2 1303.5 5500KV + Gemfan3018 props. Actual loaded mass remains unknown;
no manufacturer test data for this exact4S/3018 loaded build located. GEPRC
rates2-4S but describes2-2.5in applications, so don't claim sufficient lift or
current margin from nominal motor/ESC specs or props-off tests. User says
will hover as soon as charged and HAS NEVER FLOWN A QUAD. Recommend experienced
pilot for maiden; don't treat charged battery as clearance. Requested physical
site separately (large outdoor/garden/indoor); answer pending. Can progress
mechanical inspection / full aircraft photos / borrow kitchen scale while
charging, no new mandatory purchase. Battery label capacity/condition and
post-charge actual cell readings still not supplied. Original shorted FC
remains unpowered; bench tests on substitute passed, flight still pending.

**RADIO-LOSS FAILSAFE + ROTATION PASS 2026-10-19:** User reports armed
props-off radio-off test: motors stopped YES in1-2s; stayed stopped after
radio returned YES. User then explicitly says "rotation check is done";
accept final physical rotations checked against confirmed Quad+ layout
M1 left CCW / M2 rear CW / M3 right CCW / M4 front CW. Custom Plus mmix,
direction OFF, yaw900 physical response, calibration and ARM/ANGLE already
verified. Battery-only arm/disarm and radio-loss stop/recovery tests passed.
Next loaded aircraft weight, actual motor/prop/replacement-pack confirmation,
external actual pack/per-cell readings after bench use, mechanical/radio range
check and suitable first-flight site/pilot. Original LCD board stays unpowered
with suspected VSYS short; substitute FC for manual flight. No first flight
yet; do not redo rotation or portray existing tests as flight clearance.

**PROPS-OFF ARM/DISARM PASS 2026-10-19:** User clarifies via explicit answer:
"I meant ARM: they idle, speed up with throttle, and stop when disarmed."
Previous ambiguous DISARM statement superseded; controlled battery-only
arm/disarm now user-confirmed. No abnormality reported. Next props-off armed
radio-off DROP test: lowest idle, TX off, observe driven rotation stop/disarm;
abort/disconnect battery if drive persists beyond short observation (~2s),
never test radio loss in flight. Put SA low/throttle minimum while TX off
before TX on; require no automatic restart on link recovery. Test result
pending. Definitive final motor directions, actual loaded weight/propulsion
match, external battery health and flight site/pilot still outstanding.

**ARM/DISARM REPORT AMBIGUOUS — NOT PASSED 2026-10-19:** User describes
"as soon as i disarm, it spins relatively slowly" and then throttle increases
speed; otherwise works well. Could mean ARM (normal armed idle) or actually
DISARM (unsafe continued motor drive/throttle response). User did not fill
the yes/no result template. Requested throttle minimum/battery disconnected
and asked explicit ARM-vs-DISARM clarification. Do NOT mark arm/disarm passed
or proceed to failsafe/props/flight before clear answer. Genuine disarmed
state must stop driven rotation and ignore throttle; brief passive coast is
different. If actual disarmed control persists inspect CH5 ARM range and
live armed state / Outputs test mode without bypassing protections.

**ARMING FLAGS CLEAR 2026-10-19:** User confirms live Status arming flags now
empty after beeper-resolution instructions; whether dshot_beeper_enabled was
actually changed not explicitly stated. Next controlled battery-only PROPS-OFF
arm/disarm: SA low/throttle low, exit motor testing, disconnect USB/battery,
cold battery-only boot still/level, deliberately SA high, brief lowest-throttle
motor response if motorstop_on_low keeps them stopped, then throttle minimum
and SA low, confirm all four lose drive/stop and no resets. Armed radio-loss
DROP test is separate and pending. Directions still visually uncertain and
must be verified before fitting props; no flight clearance yet.

**LIVE STATUS RX CLEAR / DSHOT BEEPER ONLY 2026-10-19:** User screenshot
outside CLI shows RX absent, only ARMING_DISABLED_DSHOT_BEEPER, pre-arm checks
green. Pitch -6 / roll -7.6 explained by user explicitly confirming aircraft
physically tilted; do not recalibrate/trim from that image. False ADC still
shows ~4.8-4.9 V/2S empty. Next place flat, SA low/throttle low, beep mode off,
wait several seconds on Status and see if DSHOT_BEEPER clears. Source motor
beeper can repeat for any non-muted beeper event, including false battery
alerts; cause not proven. If persistent, selectively disabling
dshot_beeper_enabled removes motor-as-buzzer notifications (including lost
model), not ESC firmware startup tones; don't force-clear arming flags.
No motor direction, arm/disarm or failsafe pass yet claimed.

**ALL QUAD+ MIX ROWS VERIFIED / RX FLAG CHECK NEXT 2026-10-19:** User mmix
readback now exactly (1,1,0,1); (1,0,1,-1); (1,-1,0,1); (1,0,-1,-1),
correct for M1 left/M2 rear/M3 right/M4 front. Prior direction OFF confirmed.
Status gyro/accel OK, RX CLI flags remain, task RX rate49 is not proof valid
receiver data. Source cliEnter sets CLI, while RX comes from failsafe receive
state; don't automatically dismiss RX as CLI artifact. Next exit CLI/reboot
with TX on SA low/throttle low and receiver powered, check live Receiver and
Status arming flags outside CLI before any arm attempt; obtain screenshot.
Actual final physical directions still uncertain, armed DROP test pending.

**QUAD+ SENSOR ALIGNMENT PASS 2026-10-19:** User explicitly confirms Status
movement accurate using M4 nose/M3 right after readback align_board_roll=0,
pitch=0, yaw=900. Preserve yaw900; do not add speculative 45-degree adjustment.
Six-point calibration previously stored. Corrected mmix row0 (1,1,0,1) has
not yet been pasted after correction instruction; last actual readback row0
was wrong. Next receiver-powered SA-low/throttle-low readback mmix + status
before props-off arm/disarm. Motor direction remains user visually uncertain;
definitive check still needed before props, plus armed DROP failsafe and other
remaining flight gates. No flight authorization implied by alignment pass.

**PLUS READBACK HAS ONE BAD ROW 2026-10-19:** User mmix readback has row0
(1,1,-1,-1), still old X front-left coefficients. Rows1=(1,0,1,-1),
row2=(1,-1,0,1), row3=(1,0,-1,-1) and direction inverted OFF are correct
for confirmed PLUS M1 left/M2 rear/M3 right/M4 front. Next replace ONLY row0:
`mmix 0 1.000 1.000 0.000 1.000`, `save`; read back full mmix. Current
mixed rows are NOT flight-ready. Verify body alignment with M4 nose/M3 right
after readback, plus outstanding actual rotations and props-off armed tests.

**QUAD+ POSITIONS CONFIRMED 2026-10-19:** User confirms actual nose toward M4,
M4 front / M3 right / M2 rear / M1 left, top view. Give custom Plus mix for
existing wires: `mmix 0 1 1 0 1`, `mmix 1 1 0 1 -1`,
`mmix 2 1 -1 0 1`, `mmix 3 1 0 -1 -1`, then
`set motor_direction_inverted = OFF`, `save`. Derived from stock Quad+ rows
and checked balanced/orthogonal. This SUPERSEDES prior custom X/ON setup.
Target physical rotations: M1 LEFT CCW, M2 REAR CW, M3 RIGHT CCW, M4 FRONT CW.
Same physical target as before nose clarification; no further ESC changes by
assumption. User has not yet confirmed applying new Plus commands. Next
USB-only readback mmix/direction/align_board and recheck Status nose-down toward
M4 yields pure pitch-down, right-down toward M3 yields right-roll. Do not guess
a new alignment value or assume previous 900 applies to new body axes. Do not
load stock Quad+ output numbering over this custom mix. All final directions,
armed props-off checks, loaded-weight/propulsion checks and flight still pending.

**AIRCRAFT NOSE REDEFINED / QUAD+ GEOMETRY 2026-10-19:** User clarifies real
nose points directly toward M4, rather than between M1/M4. This supersedes
Quad X body-frame assumption. From last output positions inferred new Quad+
layout: front M4, right M3, rear M2, left M1; confirm actual top-view layout
before applying another mix. Stock Quad+ output numbering differs, so don't
blindly load preset. Current applied custom X mix and previously accepted
90-degree yaw alignment must be reviewed against new nose before arming.
Potential plus rows for that confirmed layout: M1=(1,1,0,1),
M2=(1,0,1,-1), M3=(1,-1,0,1), M4=(1,0,-1,-1). With physical front/rear CW,
sides CCW use motor_direction_inverted=OFF (currently ON). Physical target
rotations then same as latest requested FL/RL/RR/FR X pattern, but not verified.
No new plus configuration applied yet; need geometry confirmation and body
alignment verification, not another six-point calibration by assumption.

**ALIGNMENT RESPONSE / ACC CALIBRATION STORED 2026-10-19:** User confirms
90-degree alignment adjustment works (actual final align_board_yaw value not
explicitly pasted; 900 suggested, do not assume readback). Calibration readback
accgain=(4094,4092,4086), acczero=(-1,3,15), all non-default and consistent with
completed six-point calibration. Final mounted level attitude still should be
checked. Next configure/check ARM CH5 1800-2100 and ANGLE CH5 900-2100 for
always-active ANGLE across both SA positions; save and confirm ARM inactive /
ANGLE active with SA low, props off. Arm/disarm, armed DROP failsafe, final
physical motor-direction verification and flight readiness remain pending.

**DIRECTION STILL UNCERTAIN / ACC CALIBRATION NEXT 2026-10-19:** User thinks
rotations match but visual apparent reversals make identification uncertain;
do NOT mark final motor directions verified. Recommend power-off marker dot
on bell and low-speed individual startup/final coast-down slow-motion video;
steady high-speed video can also alias. User says accelerometer needs calibration.
Next battery disconnected/USB-only six-point Calibration, reference FC/IMU
orientation shown: level, inverted, right side, nose up, left side, nose down;
capture each while stationary, save, verify acc gains/offsets and Status model
roll/pitch response. Calibration is pending, not completed. No props/flight yet.

**COLD REBOOT RESTORED OPERATION 2026-10-19:** User says "works again after
cold reboot" following M3/receiver test instructions. This confirms restored
operation, not explicit final all-four direction or battery-only flight
readiness. Preserve full battery+USB power cycle after ESC configurator changes;
passthrough state is plausible but root cause not proven. Next confirm final
top-view pattern M1 FL CCW, M2 RL CW, M3 RR CCW, M4 FR CW, then battery-off
USB Status model nose-down/right-side-down response before calibration/modes.

**CUSTOM MIX VERIFIED / THREE-TONE RECHECK 2026-10-19:** After user reports
only first three ESC startup tones again, full battery+USB-off restart and
USB-only CLI readback confirms PWM_OUTPUT_ENABLE ON, DSHOT300, custom mmix
rows for FINAL FL/RL/RR/FR output positions and motor_direction_inverted=ON.
GYRO/ACC OK; RX CLI flags. Missing output-enable no longer explains symptom.
Next exit CLI, keep SA low/props off, Outputs sliders minimum/test toggle OFF,
connect battery, verify receiver response then individual motor test (M3 first,
expected rear-right CCW). Actual post-restart motor response and saved ESC3
direction reversal still not explicitly confirmed. No further flash/settings
changes until this test. Three tones alone not proof of failed ESC.

**ESC READ SUCCESS 2026-10-19:** User screenshot identifies all four replacement
ESC channels as J-H-40 / BLHeli_S 16.7, each Motor Direction Normal. Port
conflict resolved; screenshot shows Read Settings and Write Settings controls.
Next change ONLY ESC3 Normal->Reversed (not bidirectional), Write Settings,
Read Settings verify, full power-cycle and props-off test M3 to confirm actual
rear-right changes CW->CCW, with other outputs unchanged. No ESC firmware flash
needed. Custom mmix and motor_direction_inverted=ON from previous instructions
have not yet been explicitly confirmed applied; obtain CLI readback before
arming. IMU alignment/calibration, ANGLE and armed failsafe still pending.

**FINAL MOTOR LIST 2026-10-19 (supersedes ALL earlier observations):** User
explicitly finalizes M1 front-left CCW, M2 rear-left CW, M3 rear-right CW,
M4 front-right CW (top view). Use these only. Proposed custom Quad X row order
for existing output wiring: mmix0=(1,1,-1,-1), mmix1=(1,1,1,1),
mmix2=(1,-1,1,-1), mmix3=(1,-1,-1,1); motor_direction_inverted=ON for props-out.
Rows checked balanced/orthogonal against stock positional Quad X coefficients.
Physical change required ONLY M3 REAR-RIGHT CW->CCW. Earlier rear-left M3
instruction superseded. Save actual diff all first; USB-only CLI update,
readback, then ESC Configurator read/identify actual firmware before toggling
individual ESC direction. Application/reversal still pending. Custom mix does
not renumber Outputs; don't reload stock Quad X preset afterward. All four
positions/rotations and IMU alignment, ARM/ANGLE/failsafe still need verification.

**CORRECTED MOTOR RESULTS 2026-10-19 (supersedes previous positions):** User
corrects top-view observations to M1 rear-right CCW, M2 front-right CW, M3
rear-left CCW, M4 front-left CCW. Order NOW MATCHES standard Quad X; no mixer
row reorder needed. Proposed props-out pattern matches M1/M2/M4, with only
M3 rear-left needing physical CCW->CW reversal. Must pair with iNAV
motor_direction_inverted=ON, not yet set/verified. Next read replacement ESC
settings in ESC Configurator and identify firmware/direction controls before
changing individual ESC. Reverify all four rotations after changes. Earlier
180-degree mapping diagnosis superseded. 3D model orientation check still pending.

**MOTOR IDENTIFICATION RESULTS 2026-10-19:** User top-view reports M1 front-left
CCW, M2 rear-left CW, M3 front-right CCW, M4 rear-right CCW. All four spin;
positions are a 180-degree permutation of standard Quad X and three CCW/one CW
cannot match either regular quad rotation pattern. Props remain off. Next
verify chosen aircraft nose vs 3D model roll/pitch response and read actual
align_board_* and motor_direction_inverted before changes. Possible software
mix-row reorder avoids resoldering; must independently correct physical ESC
directions and reverify. Normal pattern would require three reversals, reversed
pattern only M3 reversal, but no pattern chosen/settings changed yet. Board
alignment and motor order are separate; do not assume rotating board alignment
alone remaps motors or global direction toggle physically reverses ESCs.

**SUBSTITUTE STARTUP/RADIO PASS 2026-10-19:** User confirms all previous-step
checks work: motor-output enable saved, full ESC startup tones, FC powered,
stick bars responding and SA/CH5 approx1000/2000. This is not a motor-spin or
flight-readiness confirmation. Next props-off individual Outputs M1-M4 test,
record actual corner and top-view rotation; Quad X expected M1 rear-right,
M2 front-right, M3 rear-left, M4 front-left. Saved normal/reversed direction
setting still needs verification before evaluating observed rotations.

**SUBSTITUTE FC POST-FLASH READBACK 2026-10-19:** User confirms resource shows
UART3 PB10/PB11 and motors PA0-PA3, matching latest custom image. Quad X mmix,
DSHOT300 and DROP present; gyro/accel ICM45686 OK. PWM_OUTPUT_ENABLE is now
absent after flash/wizard (was enabled before). RX CLI flags; receiver channels
and motor response remain unverified. Next enable PWM_OUTPUT_ENABLE and save,
verify persistence, then props-off receiver check under verified battery power
and individual motor identification. False ADC 4.69 V/1S OK is not pack health.

**SUBSTITUTE FC REFLASH REQUEST 2026-10-19:** User requests latest flash on
substitute FC. Latest local custom image is firmware/fc-inav/
inav_9.1.0_MATEKF722_uart3-pb10-pb11.hex (2026-10-15); SHA256 verified
68fe6438b728f1db63ab9dedb0c02c29d640017b75ecaf2494fcf0c1aa365f69.
Same iNAV 9.1.0 version string alone does not identify UART3 patch presence.
Instructions: props/battery off, save this board's actual `diff all`, STM32 DFU
via SW2 BOOT/SW1 RESET, Load Firmware Local using that image; same-version
update with Full chip erase OFF, No reboot sequence ON. Verify success and
reconnect without BOOT; read resource/status/feature and check UART3 PB10/PB11,
motor PA0-PA3 and retained settings. Do not flash stock Online 8 MHz image or
paste hand-written kogane-fc.diff. User flash/result still pending.

**SUBSTITUTE FC READBACK 2026-10-19:** User's other FC boots iNAV MATEKF722
9.1.0 e519b69b; ICM45686 gyro/accel OK. PWM_OUTPUT_ENABLE enabled. Actual mmix
is Quad X (M1 -1/+1/-1, M2 -1/-1/+1, M3 +1/+1/+1, M4 +1/-1/-1 for R/P/Y).
Status flags RX CLI DSHOTBEEPER; valid radio control still needs confirmation
with receiver powered. RANGEFINDER NONE is expected/deferred on this board.
4.90 V ADC reading is not verified actual battery voltage. Next verify battery
startup/radio channels with props removed and SA low, then individual Outputs
motor identification. No motor response or flight readiness yet confirmed.

**DEMO BOARD SUBSTITUTION PROPOSED 2026-10-19:** User has another FC with
ESP32-peripheral soldering faults and believes ESC/radio control works. Wants
to use it for the manual radio flight clip to avoid delaying for input-short
repair. This is feasible conditionally: verify faults do not affect shared
power/STM32, unplug optional peripherals, confirm actual ESC harness mapping,
read spare FC status/feature/mmix and preserve its configuration. Motor
order/direction, frame/mixer alignment, IMU/accel calibration, ARM/ANGLE, armed
props-off DROP failsafe, battery-only stability and remaining flight checks
still required on the substitute. Existing voice/LCD/mic/ToF clips remain
separate feature demonstrations; no claim of integrated flight on one board.
Shorted FC stays unpowered. Substitute flight readiness not yet verified.

**FC INPUT SHORT SUSPECTED 2026-10-19:** After replacement ESC wiring repair,
user measures 16.8 V at FC +BATT/GND but no 5 V or 3.3 V. With battery/USB,
ESC harness and detachable peripherals disconnected, user reports VSYS-to-GND
resistance remains near probe baseline (earlier approximate 0–10 ohms; no exact
stable numbers provided). Treat as suspected hard short; no further LiPo/USB
power tests. PCB directly connects VSYS to F1 pad2, D4 pad1, C5 pad1, U7 pads3/5
and Q2 pad3. D4 SMAJ18A is a shunt TVS across VSYS/GND, accessible first
isolation candidate: lift one end/remove only with power disconnected, then
remeasure board and isolated device. This test/repair is not yet performed.
Do not assume old ESC or MCUs dead; do not bypass F1 or power without protection.

**REPLACEMENT ESC / FC NOT BOOTING 2026-10-18:** User reports old ESC showed
no useful result in ESC Configurator (no actual read log supplied; failure not
confirmed). Replaced ESC: now initial three motor beeps, no later two, and FC
does not power up. Replacement model and cable mapping unknown. First isolate
power: battery/USB off, disconnect ESC-to-FC harness, test STM32 USB-only boot;
obtain new ESC connector labels/photo and whether cable reused. Saved FC J1:
1 +BATT, 2 GND, 3 NC, 4 CURR, 5 M4, 6 M3, 7 M2, 8 M1. Do not assume a matching
connector housing implies pin compatibility or reconnect battery to FC before
mapping verified. Old ESC damage remains unproven. No motor/flight clearance.

**MOTOR DIAGNOSIS 2026-10-18:** User measured battery 16.43 V and ESC input
16.41 V; reports motor solder joints good and no startup chimes since the old
pack undervoltage event. This does not establish ESC damage. Live `feature`
omits PWM_OUTPUT_ENABLE; motor_pwm_protocol=DSHOT300. Actual mmix is Quad+
(roll/pitch coefficients 0/+1, -1/0, +1/0, 0/-1). Next user action is props-off,
battery disconnected: `feature PWM_OUTPUT_ENABLE`, `save`, verify persistence,
then controlled individual motor test. Enable/test result pending. Confirm
physical frame orientation and correct mixer before any flight. No reflash.

**MOTOR CHECK NOW BLOCKED 2026-10-18 (latest):** User reports none spin and
attached Mixer screenshot. It shows Multirotor, preset selector Quad+, normal
props-in, timer overridesAUTO, mappingS1–S3Timer2->M1–M3 andS4Timer5->M4 matching
intended customtimerlayout. Screenshot is Mixer, not Outputs/test-toggle state;
selector alone doesn't establish applied mix rules. Do not assume motors
physicallytestednoworwrongfirmware; previous basicspinreport superseded bythis
currentfailure. Next confirmESCbattery/chimes, Outputs safetyenable/sliders and
readfeature/getmotor_pwm_protocol/mmix beforechangingfeature/protocol/mixer.
PhysicalframeXvs+ andactualsavedmixneedconfirmationbeforeflight. No reflash or
settingchangemadebasedonlyonscreenshot. ToF/audio clips remain secured.

**TOF MEASUREMENT CLIP RECORDED 2026-10-18 (latest):** User confirms the Sensors
Sonar graph/card movement distance test works and video captured. ToF detection
and changing measurements are user-confirmed; exact20/40/60cm readings were not
provided, so do not claim calibrated accuracy or altitude hold. Main voice/LCD,
stationary board-mic command and ToF clips secured. Next motor identification
against the selected iNAV mixer, then physical direction and remaining props-off
flight checks. Motor order/direction, calibration/ANGLE/armedfailsafe, loaded
weight/propulsionsuitability and firstflight remain unverified.

**TOF DETECTED 2026-10-18 (latest):** User read live rangefinder_hardware=NONE,
then set VL53L1X/save as instructed. Newstatus confirms persistedVL53L1X and
RANGEFINDER=OK. GYRO/ACCOK; I2C Errors50 unchanged frombefore enabling, so not
evidence of growing ToF faults. Measurement response stillpending. Next exitCLI,
Sensors tab Sonar checkbox/graph (confirmed Configurator9.1.1 source), keepFC
still/level and move mattecard alongsensoraxis20/40/60cm; filmactualresponsive
valuesifworking. No altitude/navmodeenable. ArmingflagsANGLE RX CLI DSHOTBEEPER
remainforflightchecks, reportedbattery~5VisstillfalseADCandnotpackmeasurement.

**BOARD MIC COMMAND CLIP RECORDED 2026-10-18 (latest):** User followed live
assistant --mic-source esp32 --host10.0.0.47 instructions and reports video
captured. Mark the stationary onboard-mic assistant capability clip secured,
in addition to the main laptop-mic/LCD clip. Next ToF readback (get
rangefinder_hardware/status), then motor order/direction and remaining flight
checks. Do not repeat audio tests or infer any in-flight microphone validation.

**BOARD MIC RECORDING WORKS 2026-10-18 (latest):** After the secured main LCD
video, user ran the stationary esp_mic_check recording step and says it works.
Mark physical board-to-laptop audio recording as user-confirmed; do not yet
infer live wake/command recognition. Next run assistant --mic-source esp32
--host10.0.0.47 (no --device), Kogane/Listening/showtasks, optional short clip,
then Q and proceed to ToF. Main demo remains laptop mic/Natural audio. Motor
order/direction, IMU/calibration/ANGLE/armedfailsafe and weight remain pending.

**MAIN LCD CLIP RECORDED 2026-10-18 (latest):** Physical screen initially lit
white with no image. User followed full shutdown (battery + all USB disconnected,
wait10s) then battery-first boot without SW3; reports it works and good video
recorded. Working startup procedure recorded, root cause not independently
proven; plausible LCD5V arriving after USB-powered ESP initialization. No code
or firmware change was made for this fix. Main laptop-mic/Natural/LCD clip now
secured; don't repeat it or retune UI/voice. Next short optional stationary
board-mic recording/recognition (10mincap), then ToF, motororder/direction and
remainingprops-offflightchecks. Basicmotorsspinconfirmed; armedfailsafe, loaded
weight/propulsionsuitability and firstflight stillunverified.

**FINAL DEMO SPRINT 2026-10-18 (latest):** User now has battery setup ready and
wants video finished in2–3h. Explicitly defers onboard battery sensing and camera;
main demo uses laptop mic/speaker/Natural voice. Wants audio+screen, then ToF+
motors, then first flight. User clarified basic motor testing DONE, order/direction
PENDING; loaded weight not supplied. Created FINAL_DEMO_PLAN.md with180min and
120min variants, actual commands, clip list and editing/export reservation.
Current sequence prep10/audioLCDfilm30/optionalboardmic10/mapping15/optionalToF10/
flightchecks50/conditionalhover25/edit30. At125min onlyflyifchecksallpass; don't
trade flight checks fordeadline. ToF separate10mincheck, no altitude/navmode
enable; notprerequisite for manualANGLEhover. PhysicalLCDorientation/latestcards
andboardmic/ToF remainunverified. Optionalboardmic streamdestlaptop.66:5005.

Battery ADC soldering explicitlydeferred, external pack/cellchecks before/after
andfreshcheckedpackafterbenchtime, one10–20shover target ratherthanassuming
30–60sishealthy. Accept prior userverifiedpower, no renewedQ2/F1blocker.
Needweight and actual1303.5 5500KV/3018prop/loadmatch: manufacturer2–4SLiPo but
recommends2–2.5in applications; exactloaded3inbuildnotestablished. Motororder/
directionmixer, IMUorientation/accelerometercalibration, savedARM/ANGLEcontrols,
battery-onlyarm/disarm, armedRC-lossDROP/recoverynorestart, range/mechanics/
stabilitystillrequired. No blindarmingbypass orfirmwarerebuild. CurrentS3config
RX_ONLYy,bootservosweepoff,cameraoff,speakeroff,read-onlyPARAM_REQUEST_LISTtesty;
testonlyreadsparametersandends, notamandatoryreflashfortoday'sindependentRCflight.
Old FIRST_FLIGHT_PLAN/DEMO_RECORDING_PLAN headers point to finalplan. No actual
hardwaretestsperformedorclaimedthisturn. Mainnextactionprep/backup/weightthen
runassistant--device3--host10.0.0.47andfilmLCD+weather+tasksbeforeexperimentation.

**STATIONARY BOARD MIC PREPARED 2026-10-18 (latest):** User keeps laptop mic for
demo video, wants a separate proof that board mic works while stationary. Added
opt-in assistant --mic-source esp32 --mic-host 10.0.0.47 (or --host for LCD too).
Laptop remains default; --device 3 normal demo command preserved. Natural voice
still default for replies. Board mode does not open sounddevice/laptop capture
or fall back silently. ESP32 streams to configured laptop 10.0.0.66:5005; receiver
must own UDP5005, and laptop IP/firewall need physical-session check. No firmware
edits or board/network interaction performed in this turn.

New audio/esp_mic.py validates CRC/format and selected peer IP/port, small bounded
reorder buffer, drops duplicates/late packets, sequence-loss/queue-overload resets
wake/task session rather than splicing partial commands. Input drains during TTS
and clears on rearm. After3s audio outage reports mic error; initial8s no-audio
timeout. MIC_ON retries untilfirstaudio; MIC_OFF sent3times on exit (no UDP ACK,
so serial log/reboot is physical confirmation). Sender permits MIC_ON/OFF only,
no flight/servo/PCM playback commands. Panel remains separate display-only sink.
Voice worker uses same decoder/wake/task flow for both inputs. D details show
Mic: Board/Laptop; wake/action logs record microphone source. Error card uses
board/WiFi hint in board mode. New tools/esp_mic_check.py records12s timestamped
16k WAV+JSON peak/RMS/loss/clipping report, no laptop mic opened, no automatic
playback, refuses overwriting prior output. BOARD_MIC_TEST.md is current guide;
VOICE_LCD,recordingplan/baseREADME linked. First physical action: record/listen
to board audio, then launch board-mode assistant; no hardware success claimed.

97 focused tests passed. Actual localhost UDP -> real Vosk decoder replay using
existing synthetic Windows speech passed Kogane/showtasks and MIC_OFF cleanup;
report outputs/board_mic_loopback.json explicitly simulation=true and
actual_board_verified=false. Sandbox UDP initially blocked; normal Windows
invocation of owned localhost test succeeded. No physical board, user mic,
speaker playback, task data or live weather used by that test. Static board-mode
error/layout preview also generated. Onboard audio clarity/recognition remain
unverified until user can power board. ToF bring-up also deferred by user: last
shared iNAV status RANGEFINDER=NONE; PCB U5 VL53L1X wired to STM32 I2C1 PB6/PB7,
XSHUT PB8, interrupt PB5; no live config read or enabling attempted.

**NATURAL VOICE SELECTED 2026-10-18 (latest):** User prefers the new Natural
sample. Set assistant DEFAULT_SPEECH_STYLE to mascot-natural for both CLI and
prepare_speech defaults; both weather and task replies use it. Other voice
styles remain explicit overrides. Required model/runtime already installed.
Current guides updated. User should Q old assistant, then restart --device 3;
no --speech-style flag needed. Historical default-normal notes below superseded.

**LIVELIER / LESS ROBOTIC MASCOT 2026-10-18 (latest):** User likes Mascot best but
wants more lively/natural delivery. Added optional local Kokoro neural base,
retaining English and higher mascot pitch: mascot-natural = af_heart +4 semitones,
source speed .90; mascot-lively = af_bella +4.5, speed .92. Original mascot/Zira
preserved, default normal unchanged. --speech-style selects for weather/tasks;
--tts-voice uses Kokoro IDs for neural styles, --tts-rate adjusts neural speed.
Kokoro generates intonation/phrasing; no reply facts or task titles rewritten.
Installed kokoro-onnx0.6.1 / onnxruntime1.31.0 / phonemizer3.4.0 / bundled espeak
dependencies in project venv. Free, local after setup, no account/audio uploads.

Downloaded maintainer release model-files-v1.1 into ignored models/kokoro-v1.0.
INT8 114 MB was extremely slow in inference; stopped our preview process via its
owned execution session. Full precision 325505369 bytes SHA256
beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a
is the selected backend, with voices-v1.0.bin 28214398 bytes SHA256
bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d.
tools/setup_kokoro_voice downloads these fixed assets and verifies hashes/sizes;
source.json records provenance. Optional pyproject character-voice extra pins
runtime. Backend loads lazily once with CPU-only ORT/four threads. Full model
loaded1.19s, task sentence generated.70s and weather sentence3.62s in actual local
benchmark. Cache identity includes model variant; no old INT8 samples reused.
Original simple styles unchanged, no silent SAPI fallback if neural files fail.
Sandbox phonemizer DLL-copy permission failure required normal Windows context
for actual generation (same class of environment issue as SAPI). User's normal
assistant invocation uses that environment. Voice samples in outputs/voice_samples
mascot-natural.wav / mascot-lively.wav; user listening still required. Guide
VOICE_STYLE.md updated. No mic/FC/audio playback opened by agent.
92 focused tests passed, including native neural WAV output, unchanged reply
text, style forwarding, cache reuse and missing-backend recovery without silent
voice substitution. Actual samples are valid non-silent 24 kHz mono PCM, about
5.5/5.4 seconds respectively, with peaks below clipping.

**JAPANESE CHARACTER VOICE STYLE 2026-10-18 (latest):** User wants voice similar
to original Kogane, clarified Japanese voice style. Keeping English replies as
stated in commentary. Installed Windows voices David/Zira verified in normal
Windows context (sandbox SAPI probe fails). Generated four real comparison WAVs
in outputs/voice_samples: normal, bright (Zira +3 semitones), mascot (Zira +5,
source rate -1), electronic (mascot + mild 55 Hz amplitude texture). No actor
recording/cloning, no new dependencies/network/account. User has not yet listened
or chosen. Default stays normal; --speech-style mascot/bright/electronic enables
candidate for both tasks/weather; --tts-voice/--tts-rate override base settings.
New audio/character_voice.py uses NumPy low-pass + resampling (pitch/formant AND
speed change, source rate compensates partly), bounded output, silence-preserving
texture. Speech cache now includes text/resolved voice/rate/effects/version and
publishes atomically. Existing muted mic/rearm flow retained. tools/voice_preview
generates samples with no playback/mic/network/FC. VOICE_STYLE.md guide explains
limitations and Japanese-language VOICEVOX as an uninstalled future option.
Need user listening judgment; do not claim samples match original or Japanese
accent. No user audio or FC opened.
89 focused voice/task/weather/display/local-playback checks passed, including
four new character-effect/cache/integration checks. All four generated samples
are valid non-silent 16 kHz mono PCM WAVs with peaks below clipping.

**REAL WEATHER 2026-10-18 (latest):** Replaced the assistant's fixed weather
values with free Open-Meteo geocoding/forecast HTTPS requests, no key/account for
this personal non-commercial demo. New tools/weather.py validates location,
local forecast date, current timestamp freshness, Celsius units and numeric
values. Default Toronto/CA; --city/--country resolve the actual requested place.
Removed --temperature/--condition preset flags. Requests run in a background
thread after the accepted weather command; Checking card then current temp,
condition, today's high/low, provider and local update time. Speech uses actual
current/daily conditions. Failures clear previous values and show Weather
unavailable. Geocoding is cached in process; forecasts fetched on every request.
Voice/tasks stay local, no new packages or FC firmware needed. Existing wake,
task follow-ups, compact cards and LCD orientation preserved. Static --preview
does not connect and shows Not loaded. Activity log records provider/result/
timestamps or failure, preserving voice/keyboard provenance. WEATHER_DEMO.md is
the current guide; older preset/picture instructions below are historical.

Actual Toronto API request succeeded (sandbox DNS initially blocked; authorized
normal network invocation succeeded), result in outputs/live_weather_check.json.
21 new weather tests and 63 existing focused voice/task/display checks passed.
LCD-size loading/success/error/keyboard cards visually checked in
outputs/live_weather_ui/states.png. No user microphone or FC opened; physical
LCD check remains for the next powered session. User should Q old assistant,
restart --device 3; Kogane -> Listening -> Show me the weather today. Internet
needed on laptop; add --host 10.0.0.47 for LCD once powered.

**COMPACT UI FOLLOW-UP 2026-10-18 (latest):** Whilefixingrecognized-new-taskflow,
useralsoasksremoveunnecessarytext/sleekcompactUI. TaskcardnowTodayheader+fine
divider,24px(22previous)titles,subtlecheckboxes,onefooterListening/SayKogane;
noremainingcounter,nopagecounterifsinglepage,noempty-screenrepeatedinstructions.
Onlyrealwarnings/errorsshowtask_feedback; successfulboard.noticesstayconsole/
spokenreplyandaredisabledoncard. ReadyonlySay/Kogane;Listeningonlywaveform/heading
(keyboardprovenanceifapplicable);removedWeatherortasks/Speaknow/Pleasewaitredundancy.
State/provenance/errorretained. Contactsheetvisuallyinspectedoutputs/task_ui_compact/
contact_sheet.png(exampledataonly). Guideupdated. UsermustrestartoldassistantwithQ
then--device3; firstKogane/showtasks,waitreply/footerListening,thennewtaskdirectly.
Thisretainsthebounded30sfollowupfixbelowanddoesnotreplayignoreduserutterances.

**RECOGNIZED NEW TASK NOT EXECUTED / FOLLOW-UP FIX 2026-10-18 (latest):** User
reportsHeard(command)newtaskbuygroceriesconfidence.96butnotadded. Readactivitylog:
showtasksaccepted,eventnolatertaskedit,actualdata/tasks.jsonabsent. Reproduced
flowdefect:showconsumesonewakewindow, emptyLCDstillsaidNewtaskwhileinactive.
CannotprovetheexactuserutterancestatefromsingleHeardline; couldalsohaveoldprocess.
Fixedhumanflow:bounded30sTASK-ONLYfollowupsaftereachtaskreply. Workerreceives
task_mode/rearmEvents;resetsplaybackdecoderthenbegin_tasksafteractualmicresume;
alsohandlesmutedreplywithoutmissingpauseedge. TaskfooterListeningonlyafter
worker'stask_ready;inactiveSayKogane, emptypromptcorrespondsstate. stoplistening
endsmode;weatherstillrequireswake. --task-session-seconds5..120default30.
SpeechDecoderrestrictsfollowupstotasks/stop,consumesuntilreply,expiresandreset
closesmode. Recognizedinactive/lowconfidencecommandsnowNotexecutedreasonandGUI
hint+ignoredreasonJSONevent; successfulTaskactionprintsoutcome. Nodroppedcommand
isautomaticallyreplayed. Noactualuserdatafilecreated/changedthisturn.

63focusedtestspass: addedfollowup/expiry/taskonly/stopandthreadedcontroller
show->mutedreplyrearm->newtask->persist->activeLCD regression. ActualcachedSAPI
Vosksequencewake/showtasks,thenpostreplynewtaskpassedandsaved/reopenedtestfile.
Reportoutputs/task_follow_up_20261018_012915_442003/report.json; statecardsvisually
checkedstates.png(sandboxexampledataonly). No usermic/FCopened. TASKS_DEMO,
VOICE_LCD,recordingplan,baseREADMEupdated. NextuserQoldassistant/restart--device3;
Kogane->Show me my tasks for today;waitreply/footerListening;New task buy groceries.

**NEW TASK WORDING 2026-10-18 (latest):** User replacescreationphrasewith"New task
[title]". task_list parser nowacceptsnewtaskprefixinstead ofoldaddtask/addtomylist.
UpdatedemptyLCDprompt,spokenempty-listhelp,terminalhelp,free-speecheditingguard,
taskguide/recordingplanandexistingtests. Internalaction/storageunchanged. Actual
localSAPI"New task buy groceries" decodedandpassedwake-gatedSpeechDecoder; no
useraudioorFCopened. Restartassistant --device3;Kogane->Listening->New task buy
groceries. Existingtasksremainstored. Olderhandoffentriesusepreviouswording.

**VOICE-EDITABLE DAILY TASKS 2026-10-18 (latest):** User replacespicturewith
"Show me my tasks for today" andasksaverysimplevoiceeditabletodoapp. Implemented
tools/task_list.py: strictcommandparser(show/add/complete/delete/rename/undo/page),
TaskStoreatomictempfile/fsync/replace, validatesexistingJSONwithoutoverwritingbad
data; separateper-local-laptop-calendar-date lists/history, stabletaskIDs, max30
items/day,120charstitle,10persistedundos; failedsavesleaveoldfile/memoryintact.
DefaultprivatefileBASE/data/tasks.json (ignoredwithpendingtmp), --tasks-fileoverride.
TaskBoard3rows/page, autofocuseditedID,showresetpage0,next/previousclamped. Empty
liststartsrealempty, noexampletasksinserted; olddatesretained,nocarryover.

demo_assistant.pycurrentflowweather+tasks ONLY: picturecommand/Pshortcut/--picture
removed. Tkeyboard-labelledtasksview;A/Wstilltests. Largefullcardtaskswithcheckboxes,
fixednumbers,2linetitles,donechecks/strike,remaining/page/shortnotice;no sidebar.
Updatedready/listeningprompts. EveryvoicecommandneedsKoganefirstandwaitListening;
add/renamecompleteutterancecontainsnewtitle. Taskeditscommittedbeforeconfirmation;
dynamiclocalSAPIreplygeneratedinplaybackthreadwhilemicpaused. LCDdisplay-only
guard/orientation/quicklisteningbandunchanged,noreflashornewdependency.

SpeechDecoderhasthirdunconstrainedVoskcommandrecognizerforarbitrarytasktitles.
General speech is required for add/complete/delete/rename; grammarcannotinvent
titles/IDs. Fixedgrammarfallbackforview/weather/pagingandundo(with.75gate) retains
recognition; blockedwhilefreepartial/recentutterancecontainseditingverbs. Wake
grammar unchanged, resetallrecognizersduringplayback. Jointcombinedwakeonlyallowed
fixedviewcommands; recommendtwo-stepeverytime. wake_sample now reports general
commandsseparately, notmixedintowake_name_grammar.

60focusedtestspass(finalpytest-tasks-final),includingpersistence/undo/dayseparation/
savefailure/stableIDs/wakegating/recognizerboundaryandheadlessvoice->savedtask->LCD.
RealVoskSAPIreplaypassedshowtasks/add/complete/delete/undo/pages/weatherandexplicit
"Rename task number one to charge the battery"; eachrejectedwithoutwake; unrelated
speechnoactionevenafterwake. "Rename task one to" sometimeshears"taskwantto";
guideusesexplicitnumber. Generatedspeechchecksnotliveuservoiceproof. Report
outputs/task_rehearsal_20261018_011239_292961/report.json; sequenceresultcorrect
onecompletedrenamedtaskafteradd/complete/rename/delete/undo. No user mic/camera/FC
opened. VisualLCD/nativecardscheckedoutputs/task_cards/contact_sheet.png(example
dataonly);user'sactualdatafileNOTcreated. NewTASKS_DEMO.mdprimaryguide;VOICE_LCD,
DEMO_RECORDING_PLAN,DEMO_TODAY,baseREADMEupdated. Historicalpictureinstructionsin
olderguidesectionsaresuperseded. UsernextQoldassistant,restart--device3, sayKogane,
waitListening,Add task buy groceries;wakeagainShow me my tasks for today. Physical
LCDverificationpendingbattery; addhost/orientationflagslater.

**LARGE ASSISTANT CARDS / NO SIDEBAR 2026-10-18 (latest):** User first confirms
voiceworksalotbetterwithRealtekMMEinput3; keep--device3, currentfreeVoskbackend.
Thenasksremovesidebar/enlargeeverythingforsmallscreen. Updateddemo_assistant.py:
card-firstlaptopwindow960x720, Ffullscreenlargestfitting4:3card, nosidebar/header/
slogan/permanentkeybar. Doptionalbottomdiagnostics; transporterrorvisiblebanner.
Cardsredrawatnativepixelresolution(320x240LCD, higherreslaptop), cachecurrent
kind/size. LargeKogane/Listening, gianttemperature, simplifiedweather, fullcard
picture, provenancepreset/keyboardlabelsretained. panel_textfitsboundsandfontcache.
Listeningheadingkeptwithin96..144bandsoexistingquickLCDupdateunchanged. Rotation/
mirrorunchanged, noreflash. 22existingdemo_tools/demo_waketestspass. OfflineLCD
contactsheetandnative1080p/4Kgeometrychecked; visuallyinspectedoutputs/
assistant_large_cards/lcd_contact_sheet.png andlaptop_fullscreen.png. No live
mic/camera/FCopened; physicalLCDverificationpendingbattery. GuideVOICE_LCDupdated.

**FREE-ONLY VOICE + WRONG DEFAULT INPUT FINDING 2026-10-18 (latest):** User says
only free tools. Allfuturechoicesmustrespectthis. Installed sherpa-onnx1.13.8
andcore1.13.8intoprojectvenv(normalWindowsaccessneededforpip/network), downloaded
officialsherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20 archivefromGitHubkws-models.
32,885,699bytes SHA25668447f4fbc67e70eee3a93961f36e81e98f47aef73ce7e7ca00885c6cd3616a6.
Ignoredmodeldir/archive. LocalphonemeKogan/Koganevariants0hitsonbothuserWAVs;
limitedSAPIpositivehits, negativesnone. Boost/thresholdtrialsdidnotfixit. Reports
outputs/sherpa_wake_probe.json andsherpa_wake_tuning_probe.json. NOTintegrated
intoliveassistant; noaccuracyclaimorpaidaccountflow. Deviceinventorythenfound
defaultinput1=Microphone(2-USBAudio), input2anotherUSBAudio, laptoparrayinput3
RealtekMME. Input3formatcheck16kmono/int16PASS; duplicateWASAPI15invalidsamplerate.
Noaudioinputopened. Likelywrongmicselectedsince2webcamsadded, butUSBaudioidentity
unconfirmed. Nextusersteprestartassistant --device3, thenifneedednewwake_sample
--device3 --seconds30. Deviceindicesmaychange; querylist. Guidesupdated. No
runtimecodechangedthisturn; existingVosk/filterbackendremains. Uservoiceaudio
wasnotuploaded. Laptopmicselectionneedsactualuserrecording/liveverification.

**VOICE RECOGNIZER RECALIBRATION 2026-10-18 (latest):** User supplies new30s
outputs/wake_samples/kogane_20261018_042508_048038.recognition.json; oldjoint
decoder0wakeevents. Investigated actualPCM: DCoffset~.0115fullscale inbothsamples,
oldrecordingstrong19/56Hznoise. No new aliases/thresholdlowering. Added streaming
SpeechConditioner numpy257tap80Hzhighpass+4xgain(clippedint16), SpeechDecoder
paralleljointgrammarandname-onlygrammar. Fallbackrequireswholeexactname above
existingprofilethreshold; rejectswhat/gane/embeddednames, whilejointretains
combinedrequests. Onceawake duplicatewakeendpointsignored; answerconsumeswindow;
playbackresetclearsbothrecognizersandfilterhistory. --mic-gain1..12 default4.
voice_worker and wake_sample analyzer sharetheexactstreamingdecoder/conditioning.
Newreports .recalibrated.recognition.json preserveoriginals. Namerecognizermatches
4old/5new exactkoganutterances; notallrepetitionsrecognized. Eventsfewerbecause
sessionstaysopen12s/repeatednamesignored; don'tcallmatchcountsuccessrate.
34focusedtestspass. ActualVoskSAPIwake/combinedpass, bareweather/picture/unrelated
rejected; generatedsilence/DC/rumblerejected. Limitednegativeevidence, roomfalse
activation/liveuserflowpending. No mic/camera/FC opened. VOICE_LCD_DEMO updated.

**BATTERY-OFF DEMO PREPARATION 2026-10-18:** User will use another 4S pack but
cannot power the aircraft until tomorrow. Added DEMO_RECORDING_PLAN.md: real
voice rehearsal without --host (PanelOutput exits before socket creation),
mapping/chair detection footage using USB-powered webcams/radar COM6 with unique
Full HD MP4 names, framing/editing tonight, physical LCD/IP/orientation check and
phone recording next session. No new runtime behavior or firmware change. Voice
profile/models/YOLO weights exist locally; physical LCD reception and current
mirror correction still need verification. Object floor calibration remains
deferred: chair boxes in views, radar person position on map, no claimed mapped
chair coordinates. Flight remains a separate unverified milestone. Do not make
the demo video depend on flight or reopen the user's accepted power confirmation.

**USER VOICE TUNING + EXTRA HORIZONTAL MIRROR 2026-10-17 (latest):** User supplies
outputs/wake_samples/kogane_20261018_024847_923836.recognition.json and says screen
still needs horizontal mirror after prior180rotation. Read original report + actual
20sWAV. Peak.123/RMS.021/no clipping. FreeASR why/herguy/holdonit/howi; jointgrammar
what(.707),kogan(.359088),kogan(.432732),kogan(.330674). Original threshold.65 gave
zero wakes. Do NOT adopt common what/why/hold as wake names. Narrow wake-only grammar
experiment gave no results; extra phonetic variants did not improve overall fit.
Implemented optional load_wake_profile (default localcalib/wake_pronunciation.json,
ignored), JSONtype/version validation, finiteconfidence.25..1, per-alias thresholds.
Created profile for kogan.30 ONLY; otheraliases remain.65. No acoustic training or
speaker identification. Grammar deduplicates aliases so profile duplicates do not
implicitly reweight decoder. voiceworker + wake_sample analysis loadprofile.
Replay actualuserWAV now3wakes from4decoded utterances, firststillmissed. Original
report/WAV preserved; .tuned.recognition.json savedbeside. Negative bareweather,
barepicture and one unrelated SAPI sample still0events, not broad false-alarm proof.

PanelOutput newmirror_x applies AFTERrotation tooutgoing PILpixels, defaultFalse
for API; mainCLI --lcd-mirror-x/--no-lcd-mirror-x defaultTrue foruserpanel, rotation
stilldefault180. Composition=additionalhorizontal mirror ofpreviouscorrection.
Any transform uses transformedRGB quicklisteningband, no uncorrected fmt2text.
KeyH togglesadditionalmirror immediately andresendscurrentcard; printON/OFF.
Preview remainsupright; nativeESPstatus notchanged. Usernext Q/restartsamehost
10.0.0.47 with explicit--lcd-rotation180 --lcd-mirror-x, testSayKogane; H if needed.
PhysicalLCDorientation/livewake stillusercheck. No live microphone/network used
byagent. Added peraliasprofilevalidation +all4rotation/mirrorpacketcombos +pixel
corners.24focused tests passed before finaldoc update; guideVOICE_LCD_DEMO updated.

**PRONUNCIATION SAMPLE + LCD ORIENTATION 2026-10-17 (latest):** User asks to record
their pronunciation, then reports LCD mirrored horizontally AND vertically and
requests a fix. Preserve both tasks. Added demo_assistant --lcd-rotation{0,180},
default180 for this panel. PanelOutput rotates only outgoing PIL image before
RGB565 packing; laptop preview stays upright. For180 quick-listening feedback is
an already-rotated RGB heading band y96..144 (24paced2rowpackets), then full120strip
frame. Avoid native fmt2text overlay in rotated mode because firmware text cannot
be remotely rotated. Rotation0 keeps fasttext branch. No ESPflash/MCU changes.
Own ESP status screen retains firmware orientation; correction is assistant-only.
Actual physical orientation still needs user restart/visual confirmation. Added
corner-color RGB565 test and both quick-feedback packet modes;19 focused testspass.

New tools/wake_sample.py: user-run bounded20s(default5..60allowed) laptop microphone
WAV recorder, 3-second countdown, recommends5-6naturalKogane utterances2spause.
UniqueUTCtimestamp names in ignored outputs/wake_samples; neveroverwriteexistingWAV.
Optionaldevice, --analyze existingWAV(no microphone), --no-analysis recordonly.
Default local offline Vosk analysis writes recognition.json with free/constrained
transcripts, word confidence/time, gateevents and signallevels. No networking,
no automatic alias adoption/training, no personal speaker recognition. User can
share Saved path/report for tuning nextturn. No actual user microphone opened by
agent. Tests fake input stream/syntheticexistingaudio only. Prior code-gating uses
English phonetic aliases; do not claim few samples train a custom wake model.
Guide VOICE_LCD_DEMO.md updated with restartrotation flag and sample command.
Final focused run21passed, including sample recorder preservation and no-mic
analysis path. Real offline analysis of existing SAPI-generated wake-session-0.wav
completed: free='cog in it', grammar='coggan a', one wake. This is generated speech,
not the user's recording. Await user-recorded sample before tuning aliases further.

**KOGANE WAKE + PHYSICAL LCD DEMO 2026-10-17 (latest):** User explicitly says power
issue is manually verified and fine, will power FC and run provided command. Accept
that confirmation; do not continue blocking demo on older power-review notes.
No independent re-audit/repair performed this turn. User wants Kogane wake word,
LCD listening indication, then weather/picture card. Implemented standalone
tools/demo_assistant.py WakeSession: each recognized wake opens12s, strict supported
intent only, answer consumes wake, timeout restores last card/ready, mic pauses and
queued audio resets during laptop TTS. Existing microphone sounddevice/Vosk remains
offline. Model lacks literal kogane lexicon entry (find_word=-1); use phonetic known
kogan/cogan/coggan/ko gane, filter unavailable words when building grammar. This is
ASR phrase gating, NOT a trained custom keyword model. --wake-alias supports tuning.
SAPI-generated Kogane decoded 'coggan a'; combined phrase decoded withcoggan prefix.
Real offline tests PASS: wake, both commands, combined, bare-command rejection and
unrelated speech rejection. User actual pronunciation still pending.

LCD cards redesigned ivory/charcoal: Starting up -> Say Kogane (only once mic opens)
-> green Listening/waveform -> weather/picture. Preset responses remain labelled.
PanelOutput changed-event wakes transmitter immediately; tiny fmt2 LISTENING text
atrow3scale3 precedes paced120strip repaint (12ms gap). Listening repaintclearFalse
preserves feedback; keepalive plus8sfullrefresh. Sender guarded SCREEN_FRAME only,
release on exit, UDP has NO delivery acknowledgement. Keyboard A listening, W/P
answers have KEYBOARD labels on LCD/laptop; R resend; F native-density fullscreen.
Combined utterance holds listening at least1.8s. Main preview uses light theme and
native density. --headless for tests; --no-mic labelled rehearsal. No FC commands,
no ESP reflash needed for existing display receiver. No microphone/FC packet run
started on user's behalf. Command in new VOICE_LCD_DEMO.md: base-station venv
-m kogane_base.tools.demo_assistant --host10.0.0.47 (last known IP). User next:
power verified arrangement/homeWiFi, startcommand, waitSayKogane, sayKogane, waitgreen
Listening, sayShowmetheweathertoday; repeatwake thenShowmeapicture. Report actual
LCD/voice results. Readymic errorcard prevents false listening claims. If wakefails
get exactHeardline; ifLCDfailsuseA/W/P diagnostic and currentIP, not another flash.
176 targeted voice/display tests passed in the final run with normal Windows access, including new
wake/controller/panel sequencing and existing localUDP tests. Sandbox stalled in
an existing async test; interrupted that run, same suite outside sandbox passed
175 in5.78s; final run with keyboard provenance case176 in8.03s. Card previews visually inspected; outputs/assistant_wake_cards/sequence.png
is generated layout, not hardware proof. Docs DEMO_TODAY/baseREADME/flightplan updated
to reflect user's power confirmation and current wake flow.

**NATIVE DASHBOARD RESOLUTION 2026-10-17 (latest):** User confirms chair detection,
reports blurry fullscreen and asks if their radar position can help infer object
positions. Async clarification: feet AND chair bases are partly/completely cut off.
Do not project cropped boxes or claim floor calibration is possible in this framing.
Radar-assisted floor mapping is feasible in principle using several stationary
person foot-pixel/radar-xy pairs, with validation, but NOT IMPLEMENTED this turn.
Single radar range to a person does not give unrelated chair depth. Explain camera
tilt/higher placement so floor contacts are visible; left/right bearing alone is
available without that, not dependable metre-valued front/behind placement. Current
implemented path remains measured floor points, guide OBJECT_MAPPING.md.

Fixed blurry fullscreen: mapping_ui DensityDraw rasterizes fonts, map, rules and
geometry directly at requested pixel density using cached font variants. Camera
images resized separately (no new source detail claimed). Dashboard_display helper
enables Windows DPI awareness before OpenCV window creation, reads current image
rectangle and fits16:9 up to3840x2160. Radar and stereo runners share it; no sensor
or calibration changes. --dashboard-width 0(default)auto, override1920/2560/3840.
--record-width default1280 preserves720p;1920 selects1080p. Render once at max
display/record density, resize only finished encoding frame to fixed writer size.
Headless/fallback stays1280x720 unless explicit width/record size. New command
outputs/room_objects_hd_take1.mp4 preserves previous recordings. Q/restart required.
83 targeted tests pass; added1080p/1440p/4K native-font-vs-bitmap, window-size,
record dimension and fallback checks, plus actual1080p MP4 decode from2560 render.
Ignored outputs/room_dashboard_4k.png visually checked, explicit EXAMPLE DATA.
No live GUI/camera/COM6 session launched; actual fullscreen display check pending
user restart. Docs updated with resolution flags and radar-alignment feasibility.

**CAMERA FURNITURE MAP 2026-10-17 (latest):** User wants cameras to contribute
chairs/other objects on map, eventually mounted in top room corners. Implemented
opt-in --map-objects in radar mode. vision/objects.py SceneDetector does ONE local
YOLO inference per image for person + COCO bench/suitcase/chair/sofa/plant/bed/table,
keeping person results separate. Current model yolov8n.pt already includes these
classes; local CPU smoke test on blank generated image completed, zero detections.
ObjectMapper uses each fixed camera's measured FloorHomography via --object-floor
and --object-floor2. Requires image size/point metadata, rejects mismatch, weak or
clipped detections, extrapolation outside calibrated region, and bottom contacts
covered by detected person boxes. Requires repeat support; unique same-class
nearby observations can merge across cameras, same-camera ID gated by distance.
This association is approximate and may merge nearby same-class objects or leave
duplicates. Box bottom gives approximate floor ANCHOR, not footprint/height/3D
geometry or flight avoidance. Floor-standing assumption matters (plants on tables
invalid). Per-run memory: fresh <=1s, outlined/age-labelled last-seen until12s,
thenexpires; repeated frame cannot refresh it. O clears objects, C still path.
Radar person position/independence preserved. No live cameras/COM6 acquired.
UI light style now draws blue labelled objects; no large waiting prompt obscures
object map when radar is empty. D shows floor calibration status; V labelled boxes.
With no floor files, detects boxes but maps NO object positions. Independent CSV
*_objects.csv logs fresh camera observations/provenance only. Preview-only objects
are explicitly synthetic; no fake objects are introduced in live runs.
OBJECT_MAPPING.md has exact chair-first detection, measured tape-point calibration
commands for camera2left/1right at640x480DSHOW, one-camera-first option, combined
record outputs/room_objects_take1.mp4 and limitations. Linked ROOM_MAPPING/baseREADME.
Calibration files objects_left/right.json ignored. 77 targeted checks pass including
CSV integration while one camera fails, memory/occlusion/size checks and old radar,
stereo/geometry. Real chair recognition and independent measured position checks
remain USER hardware tasks. Moving cameras/angle/zoom or resolution requires new
floor calibration; corners need separate per-camera calibrations, no stereo needed.

**LIGHT DASHBOARD REDESIGN 2026-10-17 (latest):** User confirms current radar +
camera coverage works really well, but rejects the generic dark prototype look.
Rebuilt tools/mapping_ui.py as a light architectural/editorial layout: warm ivory,
charcoal, terracotta marker/path, restrained green connection status, Georgia
headings, Bahnschrift measurements, fine rules and a proportionate floor plan.
Removed rounded card/pill grid. Full-frame camera thumbnails, enlarged V views,
D details, recording indicator and stale-data states share the design. Sensor
acquisition/tracking/geometry and 1280x720 BGR recording format preserved. Stale
radar points withheld even in labelled layout previews; separate observations
still drawn above nearby markers without moving coordinates. 64 targeted tests
pass; normal/waiting/details/enlarged-camera/stereo previews visually checked.
Ignored outputs/room_editorial_preview.png is EXAMPLE DATA, not hardware proof.
No live camera/COM6 session started. Q old app and restart using command in
ROOM_MAPPING_DEMO.md, new outputs/room_editorial_take1.mp4 to preserve earlier
takes. Existing functional confirmation is the user's; no measured accuracy claim.

**RADAR POSITION + CAMERA COVERAGE 2026-10-17 (latest direction):** User clarifies
two webcams were wanted because one camera's visual coverage is too narrow. They
now want radar to supply position and both cameras to widen visual coverage. New
--position-source radar dispatches to tools/mapping_radar.py; stereo remains the
default optional mode. New ROOM_MAPPING_DEMO.md is the current guide, linked from
STEREO_SETUP/DEMO_TODAY/baseREADME. Cameras2left/1right can face outward15-25deg with
some centre overlap. RadarCOM6 between them faces forward. No stereo calibration,
pairing or rectification in radar mode: detector receives each FULL ORIGINAL frame.
Camera movement does not require recalibration for radar mode; returning to stereo
after changing angles DOES require recalibration. Existing calibration preserved.

Radar alone drives one main position/distance/path. Camera boxes are independent
views, with no identity fusion claims and no extra camera-derived map markers.
SingleRadarTrack accepts one fresh target only; multiple targets pause selection
and show detections rather than picking arbitrarily; stale/empty/error reports
hide old measurements. Large jumps restart paths. Radar distance is Euclidean from
configured radar origin. UI reads Distance from radar and Camera coverage, remains
usable with either/both cameras lost, and suppresses duplicate amber drawing for
the one radar point already shown as main marker. Added V expanded camera-view
toggle (also supported in stereo) for placement/coverage checks. All raw image
sizes supported in this mode; no calibration file loaded. New filename
outputs/room_coverage_take1.mp4 preserves earlier takes. Q old app before restart.
**64 targeted tests passed**, including unrectified full frame input, one camera
failure with continued radar positions/CSV and absent calibration file, duplicate/
stale/multiple reports, jump reset and existing stereo/UI/geometry checks. Radar-mode
preview outputs/radar_coverage_preview.png is labelled example data. Live placement/
wide-area walking still need user verification; no new camera/COM6 capture started.

**DASHBOARD UI UPDATE 2026-10-17:** User says radar is roughly between cameras,
combined demo partly works, and asks for much nicer/more human-readable UI while
they adjust radar physically. New `tools/mapping_ui.py` renders the stereo view
using Pillow/Segoe UI: dark navy cards, large 5x4 room map, one teal "You" marker
and fading path, amber radar detections drawn above nearby person markers without
moving measured coordinates, prominent numeric depth, approximate room-position
phrases, two small camera previews, plain-language sensor statuses, recording timer,
and small honest calibration/room-alignment notes. No tracking algorithm change.
Default radar x now derives from midpoint of configured camera poses. Numerical
depth/support/skew/alignment passed as structured fields rather than parsing text.
F fullscreen, D technical-details panel, L lock, C clear path, Q save/close; uppercase
keys accepted too. Stale/invalid depth never displayed as current; stale radar says
Paused rather than empty-room. Raw statuses/calibration notes underD. Live camera
and serial acquisition unchanged. No association/fusion claim for radar.
**59 targeted tests passed**, including existing stereo geometry, capture/recording,
camera failure plus UI stale-depth/empty-report distinctions. Main, waiting and
details previews visually inspected; outputs/room_dashboard_preview.png is clearly
labelled LAYOUT PREVIEW / example data, not live hardware proof. User must Q old
app and restart to load UI. New take filename outputs/stereo_radar_ui_take1.mp4
preserves earlier recorded clips. Guide topsection has command and explanations.
No new hardware capture run launched, so user can finish repositioning radar.

**LD2450 COM6 RECEIVING 2026-10-17:** User reports adapter COM6 after5V VCC
verification/wiring. Read-only2560008N1 checks outside sandbox received7valid
reports/6s (one target aroundx0.06,y0.289m), then52validreports/10.12s, badfooters0,
discarded26bytes. Stream has several-second gaps; do not call uninterrupted/stable
reception verified. Raw bytes/summary saved ignored outputs/ld2450_com6_check.*
and ld2450_com6_stability.*. COM6 RELEASED after checks. Use working stereo command
--camera 2 --camera2 1 plus --radar-port COM6,
room5x4 and calib/stereo.json. Ready command at STEREO_SETUP section7. Next user:
Q old display, secure3wires, runcombined, walk toseeLIVE+ambertargets. IfSTALE/gaps
persist, checkconnectionsand5V underload. Physicalradar alignment/direction and
offset to camera rig remain pending; no fusion claim.

**LIVE DEMO / RADAR UPDATE 2026-10-17:** User says stereo display and requested
distance/lens-cover/recovery/movement checks all look good. No numeric distance
errors supplied, so record user-confirmed function, not quantified accuracy.
Now connecting LD2450. User confirms USB-TTL selector controls POWER and measured
5V between VCC/GND when selected5V. Keep5V for radar VCC, GNDcommon, radarTX to
adapterRX; radarRX/adapterTX unused for read-only reports. Adapter exact model /
available5V current not independently verified. Serial inventory currently empty
even outside sandbox; next ask user to wire unplugged, reconnect USB and reportCOM.
Do not guess the port or claim radar reception verified yet.

**18-PAIR CALIBRATION RECOVERED 2026-10-17:** User captured18pairs but coverage
gate blocked solving; asked if images saved and to use existing data. Confirmed
outputs/stereo_samples.json contains18cornerpairs, size640x480, devices[2,1],
square18mm. Backed up to outputs/stereo_samples_backup_20261017_180534.json.
Old running capture process saved CORNERS ONLY, not images. Coordinates suffice
for calibration; never claim old raw images recovered. User may Q old window now.
Current device order is LEFT2/RIGHT1 (supersedes earlier0/1 example commands).

Coverage failure was device1 centre span73.99px vs76.8px heuristic; verticalspan136px
and size ratio1.83 pass. Added --allow-limited-coverage to bypass only that heuristic,
retain all geometric gates, and require3held-out folds + baseline/focal stability.
Actual offline solve from backup PASSED and saved ignored calib/stereo.json.
Full fit baseline0.41668m, RMS0.25291px, verticalmedian0.19135px/p950.58950px.
Held-out baseline0.4175/0.4232/0.4202m and verticalp950.50/1.10/0.77px.
Quality notes persist in calibration JSON and show LIMITED CALIBRATION / CHECK RANGE
in live UI; these metrics do not establish physical range accuracy. Quality report:
outputs/stereo_calibration_report.json. New S captures (after restarting app) now
save raw PNG pairs in outputs/stereo_capture/<run>/ and atomic corner JSON with
image paths. No retroactive images for the completed old process.

Adjusted default disparity search to AUTO using calibrated focal/baseline; this
rig requires304px search (old160px prevented depth closer than~3m). Nominal near
limit now~1.60m. Start live check2.5–3m away, one green marker, then tape-measured
distance checks. Ready command at topSTEREO_SETUP.md uses --camera 2 (left device2)
and --camera2 1 (right device1), room5x4.
**56 targeted tests passed** incl limitedcoverage+heldout validation (bad geometric
data still rejected), calibration-warning persistence, automatic search range and
actual raw-PNG+corner saving. Calibration load/capture validation passed for[2,1].
Live physical depth and room-floor alignment remain PENDING. No need ask user to
recapture before trying saved calibration. Camera rig must stay fixed.

**STEREO CALIBRATION CRASH FIX 2026-10-17:** User's first board detection crashed
at drawing origin0: installed detector returned corners Nx2 instead of assumed
Nx1x2, so pts[0,0] was a scalar. stereo_calibrate now normalizes both shapes to
54x1x2 at the detection boundary, validates finite points and uses native-int x/y
for origin drawing. This also fixes row-direction/orientation and capture-distance
logic that assumed the same shape. Twelve stereo tests pass, including real
installed checkerboard detection -> overlay and both array-shape regression cases.
Retry the same --square-mm18 command. Actual rig calibration/depth still pending.

**TABLET MEASUREMENT CONFIRMED 2026-10-17:** User measured checkerboard square
width **18 mm** at its current tablet display size. Use --square-mm18 for stereo
capture; keep tablet fullscreen/zoom/orientation unchanged. Stereo setup guide
updated with exact command. Next: verify physical left/right indices, capture
20-25 stationary paired board poses (S), then solve (Enter) and report PASS/quality.
Actual stereo calibration and measured live depth are still pending; do not infer
they passed from this square-size confirmation. Server remains at10.0.0.66:8765.

**STEREO CORRECTION 2026-10-17 (supersedes two-camera instructions below):**
User wanted stereo depth / ONE person position, not independent camera tracks.
Cameras are on the **5m wall**, so demo defaults now room-width5, room-depth4;
40cm centred baseline puts lens references x2.3/2.7. `--camera2` now selects new
`tools/mapping_stereo.py`; old independent mode only via --independent-cameras.
Use `STEREO_SETUP.md`, revised DEMO_TODAY section1B, and updated base README.
One left YOLO tracker supplies identity; actual rectified left/right SGBM pixel
correspondence supplies one torso surface 3D fix. Includes bidirectional disparity
consistency, texture/support/depth-spread checks, metric depth limits, receipt-time
pair skew/freshness checks, no repeated frame pairs, no monocular fallback.
Dense Q reconstruction is converted back from rectified to original left frame.
One green map point/trail; same person ID in both views; raw LD2450 remains amber.
Missing/bad calibration, wrong device order/size/baseline or failed matches withhold
depth. Optional --stereo-floor uses measured LEFT-camera floor points + solvePnP
to place 3D in room axes including tilt/height; without it room axes are explicitly
assumed level. Stereo rig angles/focus/zoom must remain fixed after calibration.
Previous outward15deg advice is superseded: start parallel with overlapping views.

User has a **separate tablet** for checkerboard. New vision/stereo_calibrate.py
serves a generated 10x7 square /9x6 inner-corner pattern at port8765, or saves HTML.
Tablet must freeze fullscreen/zoom/orientation then physically measure a square.
Do not guess its size. Async question asks user for square millimetres; pending.
Server is currently running (exec session85350), http://10.0.0.66:8765/; Wi-Fi IP
verified with ipconfig. GET / passed200; GET /HANDOFF.md404; no repository file
serving. Leave server running while user uses tablet; Ctrl+C to stop afterwards.
Calibration captures20-25 stationary board poses (minimum18), independently solves
intrinsics then stereo extrinsics, checks diverse poses, RMS<=1.5px, median vertical
<=1px/p95<=2px, and baseline agreement. Saves calib/stereo.json only on pass;
raw corner observations outputs/stereo_samples.json. Machine-specific stereo/floor
files ignored by Git. Actual rig calibration and measured live depth are PENDING.
Consumer webcams not exposure-synchronized:40ms gate is HOST receipt timing only.
Keep slow/stationary demo checks; this does not enable flight control.
**50 targeted tests passed**, including real SGBM on shifted textures recovering4m,
known synthetic board poses recovering0.4m baseline, rejection of unrelated images,
pair reuse/skew/staleness, floor rigid transform, one-identity MP4+CSV runner and
camera-loss depth removal. Earlier live dual-capture tests below still apply to
camera connectivity; they do not verify calibrated stereo depth. Preview inspected.

**TWO-CAMERA UPDATE 2026-10-17:** User's single-camera demo is working and they
requested two webcams about 40cm apart on the monitor, adjustable angles, plus
USB-TTL LD2450 later. `mapping_demo --camera2 INDEX` now dispatches to new
`tools/mapping_multi.py`. Independent latest-frame capture threads, detector/
tracker instances, projectors and stale-target expiry; shared map with cyan C1,
purple C2 and amber raw radar, separate CSV provenance and MP4. No stereo depth,
cross-camera identity matching, or automatic fusion. Default baseline0.40m puts
cameras x1.8/2.2 in 4m room. Positive yaw turns left, negative right; suggest
outward +15/-15 with overlap, then secure and floor-calibrate each camera against
the same room coordinates. --homography/--homography2 use separate files; capture
size mismatch rejected. New --camera-test bypasses models for device identification.
Capture requests640x480MJPEG15fps, auto usesDirectShow onWindows; MSMF selectable.
Floor-calibration CLI now accepts matching capture size/backend settings. Actual
indices0+1 captured together (97/22 frames in6s); 8s tracking run processed49/27
frames and wrote121MP4frames plus camera1 person measurements. Both physical
monitor webcams, full-body walk, calibration and radar still require user checks.
Seventeen demo/multicamera tests passed (41 including existing geometry tests);
GUIDE section1B contains exact commands,
camera identification, angles, overlap/empty-room/lens-cover tests and radar step.

**DEMO UPDATE 2026-10-17:** User needs separate demonstration clips today: RC
flight if cleared, laptop microphone -> FC LCD for two preset responses, and a
webcam/person-position map with an optional LD2450 on USB-to-TTL. Webcam goes on
the monitor near the middle of one wall; radar on the same table facing the room.
See root `DEMO_TODAY.md` for wiring, commands, calibration and recording steps.
New standalone `tools/mapping_demo.py` provides webcam boxes, top-down person
trail, optional read-only 256000-baud radar, MP4+CSV and stale-measurement expiry.
Camera/radar points are separate; no SLAM/fusion claim. `tools/demo_assistant.py`
uses real offline Vosk laptop STT, Windows laptop speech and preset 320x240 cards.
Only SCREEN_FRAME packets can leave its display sink; no flight commands. Voice
phrases: "show me the weather today", "show me a picture". Both recognized in
synthesized-speech tests; actual laptop mic capture passed, human speech pending.
Real webcam capture/detection and 8-second recording passed. Demo+display tests
132 passed. Model/dependencies installed in project venv; model/outputs ignored.
Actual radar reports and physical LCD delivery remain unverified; last port
inventory was empty. Need USB-TTL model/COM and verify 5V supply versus 3.3V logic.
User proposed short LiPo use for LCD/flight; reminded them power ratings below
still apply. No safe independent LCD5V supply confirmed. USB-only FC leaves LCD
unpowered; resolve this before the physical screen clip. Main voice pipeline
remains a stub; standalone demo is implemented. Leave flight-command block on.

**PRIORITY UPDATE 2026-10-17: first-flight plan and power review.** User asked
for a complete remaining-work, soldering and shopping plan. See root
`FIRST_FLIGHT_PLAN.md` and `firmware/fc-inav/POWER_REVIEW.md`. User reports
having the assembled aircraft, props and charger; total weight is not measured.
Battery is specifically GNB11004S120AHV 4S LiHV 1100mAh XT60 (Rotor Village
link), listed mass 122g. No need to buy a duplicate polyfuse: F1 already exists.
However PCB+BOM name F1 BSMD2920L-1000-16V (max16V, hold10A/trip20A), which is
below full4S16.8V and LiHV17.4V. Q2 is DMG3415U (VGS max+/-8V), gate=VBUS,
source=U6 input diode-OR node, drain=VSYS. With battery+USB its calculated
gate-source voltage can exceed8V even at measured14.8V pack. No external gate
clamp is present in the saved design. These are design/rating findings, not
measurements or proof of damaged parts. Installed parts/modifications require
confirmation. Keep FC USB-only until this path is resolved; isolated divider
testing is still possible. No component purchase, rework or firmware change
has been performed. Exact power-repair parts/topology remain to be selected.
Estimated first-flight work8-16hands-onhours/3-5sessions is conditional on a
straightforward power repair and suitable propulsion/weight; add parts delivery
and pilot practice. First milestone is manual ANGLE hover, with autonomous
control/camera/amplifier repair deferred. Do not follow old battery-power
instructions below without applying this newer power-review restriction.

**Later hardware finding (2026-10-17):** On the repaired board the ELRS
receiver's channels move in iNAV, and the ESP32 now cold-boots without SW3
after the IO0 repair. The speaker measures 3 ohms; GPIO38 reaches U11 pin 1;
I2S TX/RX starts and the SELFTEST command logs, but no sound plays. The PCB
ties U11 pin 4 `SD_MODE` to GND, confirmed by continuity. The MAX98357A is
therefore held in shutdown. Do not jumper that pin to 3.3 V without isolating
it from GND. Earlier amplifier-overheat analysis below predates this finding;
refer to `firmware/companion-esp32s3/PINMAP.md` for current speaker status.

The user chose laptop-speaker output instead of repairing U11. The base
station's `kogane-say` command now plays through the Windows default audio
device; `--drone` explicitly selects the old network playback path. The
user confirmed audible laptop speech on 2026-10-17. The automatic voice
pipeline remains a stub.

**FC UART check (2026-10-17):** both replacement UART traces passed continuity
(PA9 to GPIO43, PA10 to GPIO44). Previous ESP32 TX/RX settings were reversed:
STM32 PA9 is TX, so ESP32 RX=43 and TX=44. A receive-only diagnostic was built
with TX GPIO44 left as an input and incoming setpoints blocked. Its MAVLink
v1/v2 checksum probe passed host tests against iNAV's generated MAVLink headers.
The user flashed it and configured UART1 for dedicated MAVLink at 115200.
STM32-to-ESP32 reception is HW-VERIFIED: valid frames rose 211 -> 229,
heartbeats 43 -> 47 and attitudes 84 -> 91, with bad_crc=0. The user also
confirmed that tilting the board changes the attitude readings, verifying
live sensor data through the link.
Microphone level logs continue alongside reception. Follow
`firmware/companion-esp32s3/FC_LINK_CHECK.md`. A subsequent build now forwards
fresh heading, voltage and FC heartbeat/armed status into DRONE_STATE over
Wi-Fi. Heartbeat/voltage expire after 3 s, yaw after 1 s, position stays invalid.
The firmware build, host parser/state tests and Python receiver loopback check
pass. Actual FC-to-laptop Wi-Fi reception is now HW-VERIFIED: ESP32 address
10.0.0.47 sent 30 HEARTBEAT and 150 DRONE_STATE frames during a 30 s check,
ending PASS. Received flags=0x1e (yaw, voltage, Wi-Fi and FC link valid;
disarmed, position invalid). FC voltage varied 4.55-5.09 V during this USB
bench check; this does not verify battery-voltage calibration. Physical
telemetry-loss expiry/recovery also passes: disabling UART1 telemetry produced
FC=DOWN with unknown yaw/voltage while ESP32 heartbeats continued; restoring
MAVLink at 115200 restored FC=UP and numeric readings, confirmed by the user.
Use `verify_wifi.py listen --seconds 30 --require-fc`; the configured base IP
matches laptop Wi-Fi 10.0.0.66 as checked on 2026-10-17. The reverse UART
request test subsequently passed as recorded below; flight commands remain blocked.

**Reverse UART request test — HW-VERIFIED:** KGN_FC_REQUEST_TEST enables only a bounded
MAVLink PARAM_REQUEST_LIST query on ESP32 TX GPIO44, after a fresh disarmed
FC heartbeat. iNAV 9.1.0 responds with PARAM_VALUE (an empty list is expected).
At most three requests are sent. A matching CRC-valid reply passes the reverse
UART test; reply/timeout returns GPIO44 to input. KGN_FC_RX_ONLY stays enabled,
so all setpoint/flight-command forwarding is still blocked. This build is
now HW-VERIFIED: the first request at 2049 ms received a matching CRC-valid
reply by 2073 ms, logged PASS, and returned GPIO44 to input. Both physical
UART directions are verified. UART1 stays MAVLink at 115200. Flight-command
forwarding remains blocked. RC loss/recovery is now HW-VERIFIED too: with the
board disarmed, switching the Pocket off produced RC_LINK; switching it back
on cleared RC_LINK and restored stick/channel response. This verifies loss
detection and recovery, not armed motor failsafe behavior. Motor tests and
armed failsafe behavior remain unverified. Next: read current failsafe settings
and inspect the ARM mode/channel before planning any motor test.

**Failsafe/status readback (2026-10-17):** failsafe_procedure=DROP,
failsafe_delay=5, failsafe_recovery_delay=5, failsafe_off_delay=200,
failsafe_throttle_low_delay=0, failsafe_stick_threshold=50,
failsafe_min_distance=0, failsafe_throttle=1000. Status shows ICM45686
GYRO/ACC OK, RX rate 244 Hz, and arming blockers THR CLI DSHOTBEEPER;
RC_LINK is absent. THR requires checking the actual Receiver throttle value
at minimum; DSHOTBEEPER is the guard after a recent DShot beacon command.
Voltage reads 4.76 V with a detected 2S CRITICAL label. Power source and actual
input voltage for this readback are not confirmed; do not assume it is a real
2S pack voltage or change calibration without measuring. ARM/Modes screenshot
is now received: ARM, PREARM, ANGLE and HORIZON have no assigned ranges in the
visible screenshot. The user measured minimum throttle=989. The CH5/AUX1
physical switch and its endpoints are still unknown; identify these before
assigning ARM. Power source/actual voltage remains unanswered. No setting
changes or motor tests have been performed.

**Radio/power follow-up (2026-10-17):** CH5 remains at 1000 when the user
tries the Pocket switches. A missing/incorrect CH5 radio mix is suspected,
not yet confirmed. Next radio step: inspect MIXES and assign one CH5 mix with
Source=SA, Weight=100%, Offset=0, Switch=---; verify CH5 toggles low/high in
iNAV before adding any ARM range. The Pocket manual identifies SA as a
self-locking switch. USB and battery are both connected; battery is reported
around 14.8 V, but whether this is measured or the pack label is unconfirmed.
PCB source FC.kicad_pcb marks U1 PC0/pad8 unconnected, whereas current iNAV
IO readback assigns PC0 to ADC CH1/battery. U1 PC1/pad9 is CURR; PC4/pad24 is
ICM-INT1 while firmware assigns PC4 ADC CH2. This is a target/PCB ADC mapping
mismatch; no vbat_scale adjustment or pin remap has been made. Check actual
hardware wiring/modifications and sensing circuit before fixing battery ADC.

**CH5 switch verified (2026-10-17):** after radio mix setup, SA toggles CH5
between 1000 and 2000 in iNAV. User now explicitly confirms battery voltage
around 14.8 V was measured with a meter. The iNAV 4.76 V / 2S indication is
therefore incorrect. Next configuration step: ARM range on AUX1/CH5,
1800-2100, with SA left at 1000 throughout; this assignment is not yet
confirmed saved. No actual arming or motor test is authorized by this step.
Battery ADC mapping/sensing must be resolved before motor tests.

**ARM and battery follow-up (2026-10-17):** screenshot shows ARM assigned to
CH5 with min=1800, max=2100 and live marker around 1000 (outside range).
Persistence across reconnect has not been checked; user was instructed to
Save. User confirms PC0 is untouched. Combined with PCB netlist and current
ADC assignment this confirms missing battery sensing, not a scale-only error.
Prepared `firmware/fc-inav/BATTERY_SENSE_CHECK.md`: proposed external 100k/10k
divider and 100nF filtering, calculated SENSE=Vpack/11, isolated meter check
before any MCU connection. Parts availability, assembly and measurements are
pending. No hardware repair, voltage calibration, arming or motor test has
been performed. Current ADC on PC4 is also inconsistent with PCB CURR on PC1.

**Power/sense clarification (2026-10-17):** user asks whether ESC +BATT power
already provides voltage sensing. Rechecked PCB: J1 pin1 +BATT -> F1 -> VSYS
-> U7 VIN supplies the 5 V rail. J1 pin4 CURR goes to PC1; J1 pin3 and PC0
are unconnected. No scaled pack-voltage input reaches PC0 in the saved PCB.
The divider is for ADC measurement only, not powering the FC. It may be
postponed during controlled props-off bench checks with an external meter;
earlier statements requiring it before every motor test were too restrictive.
Do not trust existing iNAV battery readings; reliable battery monitoring is
still needed before flight. Verify physical board differences before rework.

**Accessible sensing alternative (2026-10-17):** user cannot practically solder
to an STM32 leg. PCB J1 pin4/CURR is a large through-hole pad (1.7 x 1.95 mm,
2.5 mm pitch) already wired to PC1, an ADC-capable pin. Proposed preferred
repair: isolate the ESC current-sense wire, connect the verified voltage
divider output to the FC CURR pad instead, rebuild/reflash battery ADC on PC1
and disable conflicting current sensing. This sacrifices analog current
measurement but avoids MCU pin soldering. No wiring/configuration/build change
has been made. Need ESC model and clear actual connector/wire-label photo
before identifying the exact harness modification. iNAV 9.1 battery.c also
supports VOLTAGE_SENSOR_ESC when built with USE_ESC_SENSOR; whether this ESC
supports compatible voltage telemetry and an accessible UART is unknown.

**ESC identified from user screenshots (2026-10-17):** JHEMCU EM-45A 45 A
variant, 20x20 mm 4-in-1, advertised Bluejay 2-6S; AliExpress item
1005009278492069. Diagram lists VBAT+, GND, NC, CURR, M4, M3, M2, M1,
matching the FC J1 logical pin order. NC is unused, CURR is analog current,
and VBAT+ is raw battery voltage. No serial telemetry pin is shown. iNAV 9.1's
ESC voltage sensor consumes serial ESC telemetry; this diagram does not
establish that route. Actual ESC firmware has not been read. Prefer the
divider to accessible FC CURR/PC1 with ESC CURR output disconnected and a
firmware ADC remap, if proceeding. No rewire/build/flash yet; divider parts
availability and isolated output measurement remain pending.

**Available divider parts (2026-10-17):** user has 150k and 10k resistors and
a 104 capacitor (100nF). Revised proposed divider: 150k from pack positive to
SENSE; 10k and 100nF in parallel from SENSE to pack negative/GND. Ratio=16;
expected SENSE=0.925 V at 14.8 V and 1.05 V at 16.8 V. First test isolated
from the FC/ESC electronics. Nominal future iNAV vbat_scale=1600, supported
by 9.1 settings.yaml (ratio*100), but do not set on floating PC0. Divider
assembly/output, isolation of ESC CURR, PC1 firmware mapping and calibration
are still pending. BATTERY_SENSE_CHECK.md now uses these available values.

Self-contained. Assume no memory of prior sessions. Workspace: `C:\Users\sujay\OneDrive\Documents\koganeee`. Windows. Radio (ELRS TX) arrives tomorrow.

**Read this first:** a very large amount of firmware was written this session and almost none of it has executed on the board. Every section below is tagged:

- **[HW-VERIFIED]** — observed on the physical board.
- **[BUILDS-ONLY]** — compiles and links, never run on hardware.
- **[NETLIST]** — derived from the PCB netlist/BOM, not bench-measured.

---

## Goal

Two independent tracks. Keep them independent.

1. **Flight** — iNAV on the STM32F722, flown on RC only (CRSF into UART3). Working, see the iNAV section.
2. **Companion** — ESP32-S3-WROOM-1-N16R8 (U4) doing Wi-Fi link, camera, LCD, servo, audio. Firmware written, mostly unexercised.

Current state: companion boots, Wi-Fi associates, UDP inbound validated. Peripherals untested. One unresolved hardware overheat.

---

## Status summary

| Area | State |
|---|---|
| ESP32 flash + boot | [HW-VERIFIED] |
| Console / flash path | [HW-VERIFIED] native USB bodge, COM11 |
| Wi-Fi association | [HW-VERIFIED] `10.28.43.18` |
| UDP inbound validation | [HW-VERIFIED] CRC + length rejects counted |
| Telemetry out, servo, LCD, audio, camera | [BUILDS-ONLY] |
| Base station (Python) | 593 tests pass against loopback; never against the drone |
| Pin map | [NETLIST] `firmware/companion-esp32s3/PINMAP.md` is authoritative |
| Board overheating near SW3 | **OPEN, unresolved** |
| iNAV / flight | [HW-VERIFIED] except failsafe and hover |

---

## 1. Console and flash path — [HW-VERIFIED]

The UART **RXD0 castellation on the WROOM module is physically destroyed**. UART0 flashing is dead.

A USB breakout was hand-soldered directly to module pads **13/14 (IO19/IO20 = D-/D+)**, which the PCB never routed. The board now enumerates as **VID_303A / PID_1001 on COM11** with `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y`. This is both the flash path and the log path.

**Those two bodge wires are the first thing to check on a "dead board".**

Superseded: the old FT232-on-UART0 procedure and the "hold SW1 for UART pin contention" dance. Ignore them; RXD0 no longer exists.

Still-valid hardware mod: **ESP32-EN** (WROOM pad 3) is on a net shared only with STM32 PB4 and had no pull-up anywhere — it floated at 0 V. A **10 kΩ** was tacked from pad 2 (3V3) to pad 3 (EN); EN now reads 3.3 V. Do not hard-wire EN to 3.3 V. Next PCB rev: EN gets its own 10 k + 1 µF and PB4 should not own the net.

## 2. The app only runs if SW3 is held at reset — [HW-VERIFIED]

**R22 is a 10 k pulldown on IO0.** Net `/ESP32/IO0` has three connections: U4 pad IO0, R22 (pad 2 → GND, 10 k), SW3 (pad 1 → +3.3 V). The S3 internal pull-up is ~45 k, so IO0 idles near 0.6 V and **every reset lands in download mode**.

Semantics are inverted from the usual convention:

| SW3 | IO0 | Result |
|---|---|---|
| held | 3.3 V | **app boots** |
| released | ~0.6 V | download mode |

**Tape SW3 down.**

**The trap that cost a whole false diagnosis:** esptool ends every operation with `Hard resetting via RTS pin`. With IO0 low that reset lands straight back in the bootloader. So you can flash successfully, walk away, and the app never starts — while the log stays silent and looks like a firmware hang.

Pending rework: lift R22's **GND-side** pad and wire it to 3V3, converting it to a pull-up so IO0 idles high. After that SW3 becomes a no-op and forcing download mode means shorting IO0 to GND by hand. Next PCB rev: R22 = 10 k to 3V3, SW3 shorts IO0 to GND.

## 3. Confirming what is actually on the board without flashing — [HW-VERIFIED]

```
esptool --chip esp32s3 -p COM11 --before no-reset read-flash 0x10000 0x100 hdr.bin
```

Parse `esp_app_desc_t` at offset 0x20: magic `0xABCD5432`, version 0x30, project_name 0x50, time 0x70, date 0x80. This is how it was established that the current build *was* flashed and the app simply was not running (see SW3 above).

## 4. Wi-Fi — [HW-VERIFIED]

| Item | Value |
|---|---|
| SSID | `Sujay's Pixel` (phone hotspot) |
| Security | WPA2-PSK |
| Channel | 11 (2.4 GHz) |
| RSSI | -32 dBm |
| Drone | `10.28.43.18` |
| Laptop | `10.28.43.250` |
| Gateway (phone) | `10.28.43.165` |

Set via `KGN_WIFI_SSID` / `KGN_WIFI_PASS` / `KGN_BASE_IP`.

**Trap:** the SSID was first entered in menuconfig *with quote characters typed in*, which stored `"\"Sujay's Pixel\""` and would never associate. menuconfig string fields take **bare text**.

Hotspot leases change — the drone IP may move. Re-check before blaming firmware.

`esp_wifi_set_ps(WIFI_PS_NONE)` is now called. Real packet loss was measured with power save on (`wifi:pm start, type: 1`). A power-save stall is indistinguishable from RC loss, and iNAV's failsafe is DROP.

## 5. UDP inbound verified end to end — [HW-VERIFIED]

Deliberately corrupted KGN datagrams were sent from the laptop. The drone logged:

```
rx rejects: ver=0 short=0 crc=3 len=0
```

So CRC-16/CCITT-FALSE validation, per-type length validation and rate-limited reject counters all work on real traffic. A valid SETPOINT incremented nothing, as expected.

---

## 6. Pin-assignment bugs — the project's recurring failure mode

Three bugs shipped this session **because code was never cross-checked against the netlist**. All three are fixed. Treat `firmware/companion-esp32s3/PINMAP.md` as authoritative and **check Kconfig defaults against PINMAP.md, not the other way round.**

| Function | Was | Now | Why the old value was wrong |
|---|---|---|---|
| FC UART TX/RX | 17/18 | **43/44** | 17/18 are camera data nets `D6`/`D7` |
| Servo | 21 | **42** | 21 is camera `HSYNC`. 42 = net `SRV_SIG`, pad 35 |
| I2S DOUT | 40 | **38** | swapped; see below |
| I2S DIN | 38 | **40** | swapped; see below |

**The I2S swap overheated the amplifier.** `KGN_I2S_DOUT=38` goes to U11 MAX98357A pin 1 (DIN). `KGN_I2S_DIN=40` comes from the INMP441's SD output on J2.

**The trap:** net names follow the *peripheral's* role, not the ESP32's. The net feeding the amp is called `/ESP32/DIN`; the net coming from the mic is called `SD`. Matching net names to `dout`/`din` gets both backwards.

### GPIO46 was mislabelled

It was `CONFIG_KGN_LCD_PMDN` and `display_spi.c` drove it as a "panel reset", leaving it HIGH. It is actually net `PMDN` → camera FPC1 pad 8 = the OV2640's **PWDN, active high**. So the firmware was holding the camera in power-down; the camera could never have worked. Now `CONFIG_KGN_CAM_PWDN`, owned by `camera_dvp.c` and passed as the driver's `pin_pwdn`.

The LCD's reset is J4 pad 11 on the **board-wide `RESET` net**, shared with SW1 pad 2 and the STM32 NRST. Consequences: **firmware cannot reset the panel**, and pressing SW1 resets the LCD, the STM32 and the ESP32 together. There is deliberately no LCD reset Kconfig option.

### BCLK/WS — CLOSED

Earlier notes warned that net labels `BCLK(38)` / `WS(39)` disagreed with the pads. The `(38)`/`(39)` are **stale label text from an older pin assignment, not copper**. Connectivity is unambiguous: **BCLK = 39** (pad 32), **WS = 41** (pad 34). No scope check needed. Any lingering "verify with a scope" guidance is obsolete.

---

## 7. Power tree — [NETLIST], matters for every bench session

| Rail | Regulator | Source |
|---|---|---|
| +3.3V | U6 | **VBUS** via diode D2 → USB-C powers 3.3 V |
| +5V | U7 LMR51430 | **VSYS**, and VSYS comes only from **+BATT** through fuse F1 |

**The 5 V rail exists only with the battery connected.** U7's EN is tied to VSYS, so it cannot be switched off.

| On 3.3 V (works on USB alone) | On 5 V (**battery required**) |
|---|---|
| ESP32 | ILI9341 display (J4 pin 14) |
| Camera: FPC1 pad 4 +3V3, pad 10 +1V2 (U10), pad 11 +2V8 (U8) | MG90S servo (J5 pin 1) |
| U11 MAX98357A amp | **RC receiver (J7 pin 4)** ← matters for the flight session |
| INMP441 mic | |

J1 pin 3 is NC, so the ESC provides **no BEC**. All 5 V comes from U7.

## 8. Connector map — [NETLIST], silkscreen values in backticks

| Conn | Pins |
|---|---|
| J1 ESC | 1 +BATT, 2 GND, 3 NC, 4 CURR, 5–8 M4..M1 |
| J2 `MIC_1` | SD, +3.3V, GND |
| J3 `MIC_2` | GND, WS, BCLK |
| J4 LCD (14-pin) | 7 LED, 8 LCD_SCK, 9 SDI (MOSI), 10 D/C, 11 RESET (board net), 12 LCD_CS, 13 GND, 14 +5V |
| J5 `SERVO` | +5V, GND, SRV_SIG |
| J6 `SPEAKER` | OUT+, OUT- |
| J7 RC | RC_TX, RC_RX, GND, +5V |
| FPC1 | 25-pin OV2640 camera |

**J2 and J3 together are one INMP441 breakout**, not two devices.

On-board, nothing to wire: **U11 = MAX98357A** I2S amp, **U5 = VL53L1X ToF** (on the STM32's I2C, so iNAV owns it — `rangefinder_hardware = VL53L1X`), **ICM-45686** gyro.

---

## 9. OPEN HARDWARE PROBLEM — where the session ended

The board gets **"really hot" near SW3** on USB power only (no battery), with the screen on J4, servo on J5, speaker on J6.

Battery out means U7 and the whole 5 V branch were unpowered — **the display and servo were not even powered**. That leaves two candidates, both ~8.5 mm from SW3:

| Candidate | Rail | Mechanism | Requires |
|---|---|---|---|
| **U11 MAX98357A** | 3.3 V | The DOUT/DIN swap left U11's data input floating while BCLK/WS kept running (TX channel was enabled at boot and never disabled, because the mic needed the clocks). A class-D amp that sees valid clocks does **not** enter no-clock shutdown, so it amplified noise into a 4 Ω load off 3.3 V. | the app **was** running |
| **U10 XC6206-1.2V** | 3.3 V → 1.2 V | In the bootloader GPIO46 is not driven high, so PWDN is low and the OV2640 is powered but unclocked. A SOT-23 LDO dropping 3.3→1.2 V at ~100 mA gets very hot and has **no thermal protection**. | the app was **not** running |

**Which branch applies was never determined.** Given the SW3/RTS trap above, "app not running" is entirely plausible.

Isolation procedure:

1. Power on USB with **J6 empty and FPC1 empty**.
2. Add one peripheral at a time.
3. Feel U11 vs U10.

Damage to check:

- Speaker voice coil — should read **3–4 Ω**; open = cooked.
- U11 — has thermal shutdown, decent survival odds.
- U10 — no thermal protection; confirm **+1V2 still reads 1.2 V**.
- ESP32 — almost certainly fine.

**Do not power up with the speaker or camera attached until the hot part is identified.**

### Speaker is gated off in firmware now — [BUILDS-ONLY]

New `CONFIG_KGN_AUDIO_TX_ENABLE`, default **n**:

- No I2S TX channel is allocated.
- GPIO38 is parked **LOW as a plain GPIO**, so U11 sees constant zeros instead of a floating input.
- The **RX channel becomes clock master**, so the mic still works.

`CONFIG_KGN_AUDIO_BOOT_TONE` default changed from y to **n**. `AUDIO_TTS` frames are accepted and discarded; `SELFTEST` logs a refusal.

Turn the gate on **only after GPIO38 is confirmed to reach U11 pin 1.**

---

## 10. Partition table — [HW-VERIFIED build size, flash pending]

`partitions.csv`:

| Name | Offset | Size |
|---|---|---|
| nvs | 0x9000 | 0x6000 |
| phy_init | 0xf000 | 0x1000 |
| factory (app) | 0x10000 | **0x300000 (3 MB)** |

`nvs` and `phy_init` did **not** move, so stored Wi-Fi/PHY calibration survives. Single factory app, **no OTA** — no OTA mechanism exists, flashing is over USB. ~12.9 MB of flash is unallocated after `factory`.

App is **1,004,016 bytes = 32 %** of 3 MB. The old 1 MB partition would have been 96 % full, so this was not optional.

**The next flash rewrites the partition table.**

---

## 11. Firmware written this session — [BUILDS-ONLY]

**No code path in this section has ever executed on the board.** All of it is in `firmware/companion-esp32s3/main/`.

### `telemetry.c` (new)
DRONE_STATE at 5 Hz + HEARTBEAT at 1 Hz to the base. Introduces a `KGN_DS_F_*` per-field validity bitmask on `drone_state.flags`. Only `LINKQ_VALID` is ever set today (Wi-Fi RSSI mapped -95→1, -35→100) because with no FC link, position/yaw/battery are genuinely unknown. Deliberately does **not** send zeros as if they were measurements.

### `servo_ledc.c`
Real angle control, verified LEDC maths, named RETRACTED/DEPLOYED positions, interpolated sweep, rate limiting, driven by MODE_CMD (FOLLOW and DOCK deploy the screen, everything else retracts).

**`CONFIG_KGN_SERVO_DEPLOYED_DEG = 110` is an invented placeholder.** Tune it with nothing attached before loading the mechanism, or the MG90S will stall against an end stop.

### `display_spi.c`
ILI9341 320x240 via `esp_lcd_new_panel_io_spi` plus a local init sequence (IDF 6.1 core has no ILI9341 panel driver; it lives in a separate managed component). No framebuffer — one 320x32 DMA band buffer. Built-in 5x7 font. Local status screen (name / IP / RSSI / uptime / mode / screen state / TX count) plus SCREEN_FRAME ingest.

MADCTL is **0x68**. If the image is mirrored or colour-swapped, that byte is the knob — try 0x28, 0xA8, 0xE8.

### `audio_i2s.c`
Full-duplex I2S on one controller. INMP441 capture with a documented 24→16-bit shift (`CONFIG_KGN_MIC_SHIFT` default 14) and an RMS/peak level log every 2 s for bench checking. MAX98357A playback (gated off, see §9). AUDIO_TTS ingest, CTRL commands. Mic streaming to the base is **off by default** on privacy and bandwidth grounds; enable with `AUDIO_TTS` fmt 2 cmd 1.

### `camera_dvp.c`
`espressif/esp32-camera` **2.1.7**. (2.1.1 is yanked upstream and fails to compile under IDF 6.1 — it does not declare `esp_driver_ledc` despite its header including it.) OV2640, VGA 640x480, JPEG quality 12, 2 PSRAM frame buffers, 15 fps cap. MJPEG at `/stream`, plus `/snapshot` and `/` status page. HTTP task priority 2, below everything.

**The HTTP server is unauthenticated — anyone who can route to the drone can watch the camera.**

### `wifi_udp.c`
CRC + per-type length validation on inbound; rate-limited reject counters; idempotent socket/task creation (the old code spawned a duplicate `udp_task` and leaked a socket on every reconnect); bounded exponential reconnect backoff with disconnect-reason logging; `WIFI_PS_NONE`.

### `PINMAP.md` (new)
`firmware/companion-esp32s3/PINMAP.md` — authoritative pad / GPIO / net map derived from the netlist, with the three pin bugs recorded as a warning.

---

## 12. Protocol — `firmware/shared/PROTOCOL.md` is current and authoritative

New this session:

- `drone_state.flags` per-field validity bitmask.
- `mode_cmd` → screen-mechanism mapping table.
- Full `screen_frame` (0x30) layout: 8-byte sub-header; `fmt=1` RGB565 tile; `fmt=2` TEXT line, 10 rows of 53 chars, 320x2 strips, 5 s panel reclaim.
- Full `audio_chunk` layout for 0x40 / 0x41: 4-byte sub-header; `fmt=1` PCM S16LE **16 kHz mono**; `fmt=2` CTRL with MIC_ON / MIC_OFF / SELFTEST / FLUSH.

Opus is explicitly **not** implemented.

---

## 13. Base station (Python) — 593 tests passing

Verified by execution against **loopback sockets**, never against the drone.

- Vision worker wired into `BaseStation` on a worker thread. Measured control-loop jitter stayed under **49 ms** against a 33 ms nominal while ~90 ms inference ran.
- Pose via `yolov8n-pose` with a beckon-gesture detector.
- FaceID via OpenCV `FaceDetectorYN` + `FaceRecognizerSF` (no mediapipe, no dlib), with enrolment and a JSON DB. Can override the tracker's `locked_id`.
- Floor-plane homography for fixed room cameras; the pinhole `MonocularEstimator` is kept as the drone-camera fallback.
- `StalenessMonitor` failsafe: stops commanding velocity and sends `HOLD` when measurements go stale. Matters because the FC failsafe is DROP.
- LD2450 serial decoder — **sign-magnitude, not two's complement**: bit 15 set means positive. Plus a `RadarWorker`.
- mmWave simulator.
- Screen senders for text / images / PIL panels.
- Audio senders for WAV / tone / CTRL, plus **Windows SAPI TTS via PowerShell with zero new pip dependencies**. AUDIO_MIC recorder.

CLIs: `kogane-base`, `kogane-cv`, `kogane-calibrate`, `kogane-mmwave-sim`, `kogane-screen`, `kogane-say`, `kogane-audio`.

All senders open their own socket, so the base station need not be running. They default to `CONFIG.drone_ip`, which is still **`192.168.4.2`** — pass `--host 10.28.43.18` or set `KGN_DRONE_IP`.

### No ESP32-C3 in the BOM

`firmware/mmwave-node-esp32c3/` has no hardware to run on. The BOM has one HLK-LD2450 and a USB-UART adapter, so the radar path is **LD2450 → USB-UART → laptop**, handled by the Python `tracking/radar.py`. Needs the `[radar]` extra (`pyserial==3.5`).

---

## 14. iNAV (already working — do not undo)

Built in WSL `~/inav` tag **9.1.0**, target MATEKF722.

1. `target_stm32f722xe(MATEKF722 HSE_MHZ 25)` — repo `firmware/fc-inav/patches/MATEKF722.CMakeLists.txt`
2. `system_stm32f7xx.c`: `PLL_M (HSE_VALUE / 1000000)` — `system_stm32f7xx-pllm.patch`
3. `target.h`: comment `VBUS_SENSING_*`. Gyro **ICM-45686** SPI1 CS **PA4**, INT PC4. No `USE_IMU_MPU6500`.
4. Motors: M1–M3 TIM2 CH1–3 PA0–PA2; **M4 TIM5 CH4 PA3 dmaopt 1**. Comment LED strip TIM2 CH1 PA15. `MATEKF722-motors-pa0-pa3.patch`

Hex: `~/inav/build/inav_9.1.0_MATEKF722.hex`. Flash Local, full chip erase, No reboot sequence. **Never Online**. DFU: hold SW2, tap SW1. Zadig WinUSB on **STM32 BOOTLOADER** VID 0483 PID DF11 only.

Do **not** paste all of `kogane-fc.diff`. Working CLI block (UART2/4 steal motor pins):

```
resource LED_STRIP 1 NONE
resource SERIAL_TX 2 NONE
resource SERIAL_RX 2 NONE
resource SERIAL_TX 4 NONE
resource SERIAL_RX 4 NONE
serial 1 0 115200 115200 0 115200
resource MOTOR 1 A00
resource MOTOR 2 A01
resource MOTOR 3 A02
resource MOTOR 4 A03
feature PWM_OUTPUT_ENABLE
set motor_pwm_protocol = DSHOT300
set failsafe_procedure = DROP
save
```

Gyro yaw: iNAV 9 uses `align_board_yaw` in decidegrees, not `align_gyro`. Fake ~9 V / 21 A ADC is a Matek pin mismatch. iNAV 9 motors live on **Outputs**. PSU ≥3 A to spin.

### MSP RC findings (verified in `~/inav`, no rebuild needed)

- `src/main/target/common.h:158` `#define USE_RX_MSP`, `:159` `#define USE_MSP_RC_OVERRIDE`. Both already default in this tree. A 2019 upstream PR saying otherwise is stale.
- `src/main/rx/msp.c:79` sets `rxRuntimeConfig->rxSignalTimeout = DELAY_5_HZ`; `src/main/rx/rx.h:50` defines `DELAY_5_HZ` as `1000000 / 5` µs = **200 ms**. `MSP_SET_RAW_RC` must be sent **faster than 5 Hz** or iNAV declares RC signal loss. `rx.h:96` `MAX_INVALID_RX_PULSE_TIME` = 300 ms.
- `rx.h:65` has `RX_TYPE_MSP`, so `feature RX_MSP` + `set receiver_type = MSP` is the path. The `BOXMSPRCOVERRIDE` overlay (`mspOverrideChannels`, `rx.h:129`) needs a real receiver underneath.
- With `failsafe_procedure = DROP`, a **>200 ms stall in the ESP32 is an in-air motor cut**. Props off.

### CLI verification checklist (paste before trusting the bridge)

```
get receiver_type
feature
get failsafe_procedure
get failsafe_delay
serial
map
status
```

Expect `receiver_type = MSP`, `RX_MSP` in `feature`, MSP enabled on the UART wired to PA9/PA10 at 115200, and `failsafe_procedure = DROP` recorded. Record `map` — the ESP32 RC channel order depends on it and **it has not been read back yet**.

### FC UART ownership on the ESP32 side

`CONFIG_KGN_FC_UART_TX/RX` = **43/44**. New Kconfig choice `KGN_UART0_PINS_OWNER` picks whether the IDF console or the FC link owns them. Console is default, so `link_fc_start()` logs a warning and returns, and `link_fc_apply_setpoint()` is a safe no-op:

```
W (…) link_fc: FC link disabled: IDF console owns GPIO43/44
```

That is correct output, not a regression. Note that with the console now on native USB the contention picture has changed, but the Kconfig default has not been revisited. Also: RXD0 (pad 36) is the destroyed castellation, so the FC link needs the **PA10 → IO3 rework** before it can work at all.

---

## 15. Flight strategy (radio arrives tomorrow)

**Fly on RC only.** CRSF into the STM32's UART3. Demo the companion's peripherals on the bench, separately.

**Do NOT attempt ESP32-controlled flight.** That would be a first flight with MSP as the receiver, a 200 ms iNAV timeout, DROP failsafe, and a control path that has never moved a motor. The project's own bring-up order puts ESP32 control at step 9, last.

Flight gate, in order, **props off until the last step**:

1. ELRS bind
2. Channel map (`map` in CLI)
3. Arming switch
4. **Failsafe verified on the bench**
5. Motor direction and order via Configurator
6. VBAT scale calibration (the ADC currently reads a fake ~9 V / 21 A)
7. First hover

**2.4 GHz coexistence:** if the radio module is 2.4 GHz ELRS it shares the band with the Wi-Fi link on channel 11, and ELRS hops across the whole band — it cannot be dodged by channel choice. Keep antennas apart. An RC dropout with DROP failsafe means motors stop.

---

## 16. Spec — awaiting review

`.kiro/specs/fc-msp-bridge/requirements.md` exists and is **awaiting review**: 8 requirements plus Non-Goals and 5 Open Questions. No `design.md`, no `tasks.md`.

Key open decisions:

- Link-loss behaviour: send neutral RC frames, or cease transmission and let iNAV's DROP failsafe fire.
- RC channel order, which depends on the iNAV `map` setting that **has never been read back**.
- Target setpoint rate.

---

## 17. Build environment — quirks that cost time

- IDF: `C:\esp\v6.1\esp-idf`. Tools: `C:\Users\sujay\.espressif`.
- Use **CMD**: `install.bat` then `export.bat`. PowerShell `export.ps1` is broken (empty `activate.py`).
- **Do not redirect `export.bat`'s stdout** — it breaks the script's internal `goto` labels.
- `build/` goes stale when the active python env differs from the one that configured it. Symptom is nonsense cmake errors; fix is `rm -r build/`.
- **OneDrive sync and concurrent git have locked `build/` repeatedly.** Retry, or pause sync.
- Project: `firmware/companion-esp32s3`, target esp32s3, 16 MB flash, octal PSRAM. `main/CMakeLists.txt` uses IDF 6 split drivers (`esp_driver_uart`, `esp_driver_ledc`).
- Do not pick Cursor OpenOCD on USB-JTAG. Firmware is IDF, not Arduino.
- `.gitignore` was created this session (the repo had none). `sdkconfig` is **ignored** because it holds the Wi-Fi password; `sdkconfig.defaults` is deliberately still tracked. Also ignores `firmware/*/build/`, `__pycache__/`, the venv, egg-info. Six `.pyc` files were committed before the rule existed and remain tracked.

Boot-log facts [HW-VERIFIED]: chip rev **v0.2**, 16 MB flash, octal PSRAM passed its test (**8 MB**, AP gen-3 die), station MAC **ac:27:6e:ab:56:d0**.

---

## Do not

- **Do not read net names as if they described the ESP32's role.** `/ESP32/DIN` feeds the amp; `SD` comes from the mic. This caused the I2S swap.
- **Do not power up with the speaker on J6** (or the camera on FPC1) until the hot part is identified.
- **Do not enable `KGN_AUDIO_TX_ENABLE`** before confirming GPIO38 physically reaches U11 pin 1.
- **Do not expect the display, servo or RC receiver to work without the battery** — they are all on the 5 V rail, which only exists via +BATT → F1 → VSYS → U7.
- **Do not attempt ESP32-controlled flight.**
- Do not assume SW3 is a download-mode button. On this board it is the opposite.
- Do not walk away after `esptool`; its RTS hard-reset lands in the bootloader with IO0 low.
- Do not type quotes into menuconfig string fields.
- Do not trust `link_fc` logs while the console owns GPIO43/44 — that build never touches the FC bus.
- Do not expect a UART0 fallback: the RXD0 castellation is destroyed. The USB bodge is the only path.
- Online MATEKF722 hex; full `kogane-fc.diff`; M4 on TIM2; `align_gyro`; flash the S3 from FC USB-C; Zadig on anything but STM32 BOOTLOADER; props / 4S hover before the flight gate.

---

## Next

1. **Identify the hot part** near SW3 (U11 vs U10) with the isolation procedure in §9. Everything peripheral is blocked on this.
2. **Flash the current build with SW3 taped down and confirm the boot log.** Nothing in §11 has ever run.
3. **R22 rework** — 10 k pulldown → pull-up on IO0, so the board boots unattended.
4. **PA10 → IO3 rework** for the FC link (RXD0 is destroyed).
5. **Tune the servo angles** with nothing attached; `DEPLOYED_DEG = 110` is a guess.
6. **Review `.kiro/specs/fc-msp-bridge/requirements.md`** and settle its 5 open questions.
7. **Flight gate** (§15) once the radio arrives — RC only.
