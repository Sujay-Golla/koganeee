# Kogane first-flight plan

**Current plan, 2026-10-18:** [FINAL_DEMO_PLAN.md](FINAL_DEMO_PLAN.md) supersedes
this document's schedule and earlier power/battery-sense prerequisites for today's
demo. User reports power verified and battery setup ready; battery sensing is
deferred with external pack/cell checks. Basic motors were tested; order/direction,
orientation/calibration, ANGLE controls, armed failsafe and loaded propulsion
suitability remain pending. Those flight checks still apply. Older power-review
instructions below are retained as engineering history, not a renewed approval
request or mandatory soldering task for the stationary clips.

Updated 2026-10-17. Target: a brief, manually controlled hover using the
RadioMaster Pocket and iNAV ANGLE mode. Autonomous following, voice control,
camera streaming and automatic docking are later milestones.

This plan records remaining work. It is not clearance to arm or fly.

**2026-10-17 update:** User reports the power issue has been manually verified and
is fine. Accept that report for the voice/LCD demo using the verified arrangement;
do not repeat the earlier power-blocker approval flow. The detailed review below
records the earlier engineering findings, not a new request to re-prove the setup.
Battery sensing, propulsion checks and flight verification remain separate tasks.

## Schedule estimate

The user reports having the assembled frame/motors/ESC, matching props and
charger. Total aircraft weight has not been measured.

Plan for roughly **8-16 hours of hands-on work**, usually **3-5 focused
sessions**, if the power repair is straightforward and the motor/prop/weight
combination is suitable. Add parts delivery and pilot practice separately.
This is an engineering estimate, not a promised flight date. A power-board
rework problem or inadequate lift could add days and require a different
approach. The first two stages below determine whether this estimate holds.

## What already works

| Item | Evidence / limitation |
|---|---|
| ESP32 boot | Cold-boots after IO0 repair |
| Wi-Fi, display, microphone, servo | Individually verified during bring-up |
| Laptop audio | Audible output confirmed; onboard amplifier remains disabled |
| ELRS | Bound, stick channels move; disarmed loss/recovery passed |
| SA switch | CH5 toggles 1000/2000 |
| ARM range | Screenshot shows CH5 1800-2100, marker at 1000; verify saved after reboot |
| IMU | iNAV reports ICM45686 gyro/accelerometer OK; live tilt data changes |
| FC/ESP UART | Both directions verified with a bounded read request |
| Laptop telemetry | Heading/link data and expiry/recovery verified |
| Battery voltage | NOT verified: floating PC0 produces false iNAV readings |
| Motors / armed failsafe / flight | NOT verified |

## 1. Resolve power ratings and verify the physical board

**Estimate: 2-4 hours, plus any parts/rework delay. Current priority.**

Read [POWER_REVIEW.md](firmware/fc-inav/POWER_REVIEW.md) first. The FC already
has F1, D4 and regulator protection; these are not missing items to buy.

- [ ] Confirm installed F1 and Q2 against the saved PCB/BOM and repair history.
- [ ] Resolve F1's listed 16 V rating versus the full voltage of the 4S pack.
- [ ] Resolve Q2's gate-to-source overvoltage risk in the USB/battery power path.
- [ ] Select a specific repair and compatible parts before ordering or soldering.
      Direct STM32-leg soldering is not part of the planned repair.
- [ ] Inspect any existing damaged/heating parts; confirm normal 3.3 V and 5 V
      rails and stable startup after repair, including battery-only operation.
- [ ] Verify the existing ESC input capacitor and its voltage rating rather
      than buying another capacitor by assumption.
- [ ] Verify charger model/mode against the actual battery label. User's pack
      link identifies GNB11004S120AHV, 4S LiHV, 1100 mAh, XT60. Design for its
      full permitted voltage, not just the present 14.8 V meter reading.

Until this power review is resolved, keep the FC on USB only. The divider may
be tested on the battery separately while disconnected from the FC and ESC.
Do not bypass F1 with a wire or improvise a Q2 bypass.

**Pass:** confirmed physical configuration and a power path whose components
are within ratings for the chosen battery, with stable rails and no resets.

## 2. Check the weight and propulsion match early

**Estimate: 30-60 minutes for inspection and data review; longer if changes are needed.**

- [ ] Weigh the aircraft in the proposed first-flight configuration, including
      battery, props, fasteners, wiring and anything it will carry.
- [ ] Confirm the actual motor KV and prop size/pitch/blade count from markings.
- [ ] Check propulsion data for that combination and adequate control/thrust
      margin at the actual weight. Do not treat ESC's 45 A rating as motor thrust.
- [ ] Inspect frame stiffness, motor screws/windings, prop clearance, battery
      restraint, FC mounting and antenna clearance from motors/carbon/wires.

The README lists GEPRC SPEEDX2 1303.5 5500KV motors and 3-inch Gemfan 3018
props. GEPRC recommends this motor for 2-inch guarded or 2.5-inch freestyle
models. That does not prove the existing 3-inch two-blade setup is unsuitable,
but it needs verification at the aircraft's actual weight; no lift estimate
has yet been established. The selected battery alone is listed at 122 g.

For the first hover, use the simplest practical aircraft configuration.
Remove optional payload if mechanically straightforward, or secure/stow it;
do not deploy the servo/screen mechanism in flight. Recheck balance and weight
when payload changes. Avoid ad-hoc hand-held full-throttle thrust testing.

**Pass:** documented acceptable motor/prop/battery/load combination and secure
mechanical assembly. Buy different props, battery, motors or frame only if
this check establishes a need.

## 3. Finish battery sensing through the accessible FC connector

**Estimate: 1.5-3 hours, including firmware work.**

- [ ] Assemble the available 150k/10k/104 divider separately and measure it.
      Expected SENSE = pack voltage / 16: 0.925 V at 14.8 V; 1.0875 V at 17.4 V.
- [ ] With all power removed, isolate the ESC CURR output from FC J1 pin 4.
- [ ] Secure the verified divider output to the larger FC CURR connection,
      which already reaches ADC-capable PC1. Insulate the unused ESC output.
- [ ] Secure/insulate the divider and strain-relieve its wiring; preserve BATT,
      ground and all four motor-signal connections.
- [ ] Back up the actual current iNAV `diff all` before reflashing.
- [ ] Prepare one local iNAV build with battery ADC on PC1 and conflicting
      current sensing disabled. Preserve the working 25 MHz clock, ICM45686,
      PB10/PB11 ELRS UART, motor timers and USB fixes. Do not load an online
      stock MATEKF722 image or restore the reference diff wholesale.
- [ ] Flash and read back settings/pin assignments. Only then set the nominal
      voltage scale (1600 for this divider) and calibrate to a simultaneous
      meter reading. Verify correct 4S cell count/alarms for the chosen charge
      limit. Check changing real input voltage changes the iNAV reading.

**Pass:** pack measurement agrees with the meter across more than one actual
voltage, including battery-only power. Analog current measurement is explicitly
unavailable after repurposing CURR. See [BATTERY_SENSE_CHECK.md](firmware/fc-inav/BATTERY_SENSE_CHECK.md).

## 4. Confirm sensors and configure the manual flight controls

**Estimate: 45-90 minutes. Props removed.**

- [ ] Verify iNAV's model follows physical roll, pitch and yaw in the correct
      directions. Live values changing alone did not verify orientation.
- [ ] Complete accelerometer calibration and level alignment; check gyro startup
      with the board still. Investigate growing errors/resets rather than
      clearing arming protections to hide them.
- [ ] Verify roll/pitch/yaw channel identity, direction, centers and endpoints.
      Minimum throttle was 989; confirm THR clears when it is fully down.
- [ ] Confirm the ARM range persists across restart, with CH5 low = disarmed.
- [ ] Assign and verify ANGLE mode on another radio channel; PREARM is an
      optional additional deliberate-action safeguard.
- [ ] Confirm DROP failsafe remains configured. Do not enable GPS-dependent
      modes, autonomous flight or ESP32 flight-command forwarding.
- [ ] Prepare a stable companion build: RX_ONLY remains enabled; disable the
      startup UART request test and servo sweep. Camera/speaker stay disabled.

**Pass:** correct sensor orientation and calibrated controls; deliberate,
understood arm/disarm/mode controls; no unexplained arming blocker.

## 5. Check each motor and ESC output

**Estimate: 1-2 hours. Props removed throughout.**

- [ ] Use iNAV Outputs to run one motor at a time at low speed and identify its
      physical position. Compare against the selected mixer diagram.
- [ ] Verify all four outputs, including the custom M4 timer/DMA assignment.
- [ ] Confirm correct rotation direction; use compatible ESC configuration
      software to reverse motors where possible, rather than resoldering phases.
- [ ] Confirm reliable starts, no scraping, abnormal heat, resets or rough running.
- [ ] Verify ESC firmware/settings before considering bidirectional DShot/RPM
      filtering; do not add that feature just to reach the first hover.

**Pass:** motor number, position and direction all match iNAV's mixer, and
each motor starts/stops reliably. ESC startup beeps alone are not this test.

## 6. Test actual arming, disarming and armed radio failsafe

**Estimate: 45-90 minutes. Props removed.**

- [ ] Verify normal radio arming/disarming on battery power with the aircraft
      secured and USB disconnected; avoid masking behavior with a motor-test override.
- [ ] Confirm the disarm switch stops every motor immediately.
- [ ] Perform a planned armed RC-loss test and observe DROP stop all motors
      and disarm; restore the radio with ARM low and verify no automatic restart.
- [ ] Check recovery/re-arm lockout as documented by iNAV. The earlier disarmed
      RC_LINK check did not exercise this behavior.
- [ ] Confirm ESP32/laptop power, Wi-Fi loss or application exit cannot command
      arming or interfere with the independent RC control path.

**Pass:** controlled arm/disarm, verified motor stop on RC loss, and deliberate
recovery without unexpected restart. Do not disable protections to force a pass.

## 7. Battery-only system check and pilot preparation

**Estimate: 45-90 minutes, plus practice as needed.**

- [ ] Repeat power-up and low-speed props-off checks with the intended battery,
      antennas, payload, Wi-Fi state and wiring arrangement.
- [ ] Confirm the board stays stable when motors and intended electronics run;
      check telemetry/RC with Wi-Fi on and off for coexistence problems.
- [ ] Perform the radio manufacturer's range check in an appropriate clear area.
- [ ] Verify secure repair wires, USB bodges, battery leads and antenna mounts.
- [ ] Practice the Pocket's throttle, ANGLE control and immediate disarm on a
      simulator or with an experienced pilot before the first live hover.

**Pass:** stable battery-only operation and understood controls. A smoke stopper
is used for limited-current power checks, then removed for motor tests and flight.

## 8. First manual hover

**Estimate: a 30-60 minute session, including setup and inspection.**

Only after the prior stages pass: fit the correct props to the verified motor
directions, check clearance/fasteners, and make a brief manual ANGLE-mode
hover in an appropriate clear area, preferably with an experienced pilot.
Land and inspect before increasing duration or adding payload. Stop for
oscillation, excessive motor heat, voltage collapse or unreliable control.

For outdoor flight in Canada, check the operating-weight/airspace rules before
choosing the site. At 250 g or more, registration and the appropriate pilot
certificate normally apply. A first flight in a furnished room is not planned.
No string-tether hover is assumed; a tether can alter dynamics or reach props.

## Make, solder and buy list

| Item | What remains | Purchase status |
|---|---|---|
| Voltage divider | Build 150k + 10k + 104; isolated measurement, then mount securely | Parts already owned |
| CURR harness | Isolate ESC current output; connect verified divider to FC input | Existing larger connection; wire/insulation only if absent |
| F1 polyfuse | Already present; verify installed part and correct rating | Replacement conditional on confirmed 16 V part; do not order a duplicate |
| Q2 power path | Select and implement rated MOSFET/gate-protection or diode-OR repair | Exact parts not yet selected; may need skilled SOT-23 rework |
| Fast fault protection tool | Optional but recommended for first power-up after rework | Borrow or use a suitable current-limited bench supply; smoke stopper is another option |
| Mounting and insulation | Strain relief, heat-shrink, standoffs/straps if missing | Check existing stock first |
| Scale | Measure total takeoff weight | Borrow a kitchen scale; no need for a special drone scale |
| ESC input capacitor | Confirm existing capacitor and rating | Buy only if missing/unsuitable; select after inspection |
| Props/motors/battery/frame | Check existing combination and weight | No replacement justified until compatibility/lift review |
| Replacement commercial FC | Alternative only if custom power rework is impractical | Optional fallback, not an automatic purchase |

The existing 10 A-hold/20 A-trip polyfuse protects the FC's battery branch.
It is not the same as a 1-2 A fast electronic smoke stopper upstream of the
whole aircraft. A smoke stopper is bench equipment and is not installed for flight.

## Work deferred until after a reliable manual hover

- Camera / U10 heating diagnosis and streaming.
- Onboard amplifier repair: laptop audio is the chosen output for now.
- Moving the servo mechanism during flight and carrying the complete display payload.
- Blackbox/microSD bring-up (valuable for tuning but not proof of flight readiness).
- GPS, compass, barometer or optical-flow hardware: select later according to
  the navigation goal; no purchase is required solely for a manual ANGLE hover.
- Room-camera/mmWave localization, automatic following, docking and voice-driven
  flight. These require a separate controls/sensing validation plan after manual flight.

## References

- [Power component review](firmware/fc-inav/POWER_REVIEW.md)
- [GEPRC motor specifications](https://geprc.com/product/geprc-speedx2-1303-5-3800kv-5500kv-motor/)
- [User's GNB battery listing](https://rotorvillage.ca/gnb-1100mah-4s-120c-hv-lipo-xt60/)
- [iNAV failsafe behavior](https://github.com/iNavFlight/inav/blob/9.1.0/docs/Failsafe.md)
- [ExpressLRS preflight setup](https://www.expresslrs.org/quick-start/pre-1stflight/)
- [Example fast smoke stopper: VIFLY ShortSaver V2](https://viflydrone.com/products/vifly-shortsaver-v2-smart-smoke-stopper)
- [Transport Canada operating categories](https://tc.canada.ca/en/aviation/drone-safety/learn-rules-you-fly-your-drone/drone-operation-categories-pilot-certificates)
