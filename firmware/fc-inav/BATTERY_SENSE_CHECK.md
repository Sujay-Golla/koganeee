# Battery sensing: missing connection on the repaired FC

**Power review update (2026-10-17):** F1 voltage rating and Q2 gate-source
stress require resolution before further battery-powered FC tests. See
[POWER_REVIEW.md](POWER_REVIEW.md). The standalone divider test remains valid
with the divider disconnected from the FC and ESC electronics. The user's
battery is now identified as a 4S LiHV GNB11004S120AHV; include its full allowed
voltage in the power review, not just conventional 4S LiPo voltage.

## Confirmed on 2026-10-17

- User measured about 14.8 V across the flight battery with a meter.
- iNAV reported about 4.76 V and incorrectly detected a critical 2S pack.
- iNAV IO readback assigns PC0 to ADC CH1; status uses ADC CH1 for BATTERY.
- `pcb/FC/FC.kicad_pcb` marks U1 PC0, pad 8, as unconnected.
- User confirms PC0 was untouched during repair.
- The PCB's +BATT net connects J1 pin 1 and F1 pin 1. It has no resistor
  divider connected to PC0 in this PCB source.

The battery ADC input is floating. Its current reading is not a measurement
of pack voltage. Do not compensate for this with vbat_scale, and do not rely
on the current battery alarm, cell count or forwarded voltage.

## Power and voltage measurement are separate

The ESC supplies raw pack voltage through J1 pin 1 (+BATT), then F1 to VSYS
and U7's 5 V regulator. This power path already exists. It does not provide
a scaled battery-voltage signal to the STM32 ADC. J1 pin 4 is CURR (current
sense), not a battery-voltage input; J1 pin 3 is unconnected in the PCB source.

The proposed divider is only for measuring pack voltage through PC0. It is
not needed to power the FC or to continue controlled props-off peripheral
checks using an external meter. Earlier notes treating battery sensing as a
technical prerequisite for every motor bench test were too restrictive.
Arming, motor behavior and flight readiness still require their own checks;
the current displayed voltage must not be trusted. Arrange reliable battery
monitoring before flight. These conclusions describe the saved PCB design;
verify any differences on the physical board before adding hardware.

## Proposed repair: prepare and measure before connecting to the MCU

### Identified ESC

User supplied listing screenshots and confirmed the 45 A variant: JHEMCU
EM-45A, 20 x 20 mm, 4-in-1, advertised Bluejay, 2-6S. Listing item
1005009278492069. This identifies the purchased variant, not its currently
installed firmware version. The supplied 45A/50A diagram lists, in order:
VBAT+, GND, NC, CURR, M4, M3, M2, M1. This matches the saved FC J1 logical
pin order. Do not infer actual cable orientation or wire colors from that
match without inspecting the harness.

VBAT+ is raw pack voltage, CURR is analog current output, and NC is explicitly
unused. No separate serial telemetry output is identified by this diagram.
iNAV 9.1's ESC voltage meter uses its serial ESC sensor input; a working
voltage telemetry route is not established by the Bluejay product label.
The planned CURR-pad/PC1 ADC route remains the practical documented option.

### Preferred accessible connection: repurpose J1 CURR

User considers direct STM32 pin soldering impractical. The saved PCB provides
an alternative: J1 pin 4, CURR, is a 1.7 x 1.95 mm through-hole pad on a
2.5 mm pitch connector and already routes to ADC-capable PC1/pin 9. This is
much more accessible than a bare STM32 leg.

Proposed path: verified divider SENSE -> J1 pin 4/CURR -> existing trace ->
PC1. First identify and disconnect/isolate the ESC's existing current-sense
output from this net. Do not join that output and the divider output together.
Firmware must then map battery sensing to PC1 and disable conflicting current
sensing. This trades the analog current input for battery-voltage monitoring.
It requires a firmware rebuild/reflash, but no direct STM32 pin soldering.

This alternative is not implemented. Confirm the actual ESC connector/wiring
and inspect its model/pinout before altering the harness. The direct-PC0 route
below is optional and is no longer the preferred route for this user.

For a conventional 4S LiPo (up to 16.8 V), prepare an external divider:

User has 150 kOhm and 10 kOhm resistors plus a capacitor marked 104
(100 nF). Use these available values; this replaces the earlier 100k/10k
proposal. Verify the actual resistor values with the meter before assembly.

```text
Battery positive ---- 150 kOhm ----+---- SENSE (not connected to MCU yet)
                                 |
                              10 kOhm
                                 |
Battery negative ----------------+---- GND
```

Use 1% resistors. Add a 100 nF ceramic capacitor from SENSE to GND near the
eventual MCU connection for filtering. The two resistors and capacitor must
be mounted securely and insulated; use short signal/ground wiring.

SENSE = battery voltage / 16:

| Battery voltage | Expected SENSE voltage |
|---|---|
| 14.8 V | 0.925 V |
| 16.8 V | 1.050 V |
| 17.4 V (4S HV full, if permitted by pack label) | 1.0875 V |

These are calculated design values, not measured results. This circuit and
its connection to the board have not yet been built or verified.

### First check: divider only

1. Remove all propellers. Keep SA at CH5=1000; do not arm.
2. Disconnect battery and all USB power from the FC.
3. Assemble the divider with power disconnected. Leave SENSE isolated from
   the FC and STM32.
4. Check resistor values and wiring with a meter before applying power.
5. Connect only the divider to the battery, with secure insulated connections.
6. Measure battery positive to battery negative, then SENSE to battery
   negative in DC-voltage mode. SENSE should match battery voltage / 16
   within resistor/meter tolerance (about 0.93 V for a 14.8 V pack).
7. Disconnect the battery. Report both readings before connecting SENSE to U1.

Do not put battery positive directly on PC0 or any STM32 supply pin. U1's
pin named VBAT is the RTC/backup supply; it is not the flight-pack ADC input.
The analog input must remain within its analog supply range. Never power
the divider into an unpowered MCU: test it disconnected, and disconnect all
power before soldering the final wiring.

### Subsequent steps, after the divider check

- Prefer the J1 CURR/PC1 alternative above after isolating the ESC current
  output and preparing the required firmware mapping. The following PC0
  instructions apply only if direct fine-pitch work is deliberately chosen.
- Identify U1 pin 8/PC0 from the package marking and the board layout; use
  magnification and a close-up photo before choosing a solder point. Do not
  infer pin orientation from the connector orientation.
- With all power removed, connect verified SENSE to PC0 and divider ground
  to FC ground. Inspect for bridges to NRST/pin 7 and PC1/pin 9, and secure
  the added wiring mechanically.
- This keeps the existing battery ADC on PC0; no ADC pin remap is expected
  from the reported IO assignment. Read current voltage settings before
  calibration, then compare iNAV against a simultaneous meter reading.
- Confirm the reading changes with actual pack voltage, the correct cell
  count is detected after restart, and telemetry agrees. Actual arming and
  motor/failsafe tests remain separate, unverified stages.

iNAV 9.1 settings define vbat_scale as divider ratio times 100, so the nominal
starting value for 150k/10k is 1600. Do not apply this calibration to the
currently floating PC0 input. First verify the divider, isolate ESC CURR,
connect it through the chosen accessible point and flash the PC1 ADC mapping;
only then calibrate against a simultaneous meter reading.

## Separate finding: current sensing

The PCB routes CURR to PC1/pin 9. Current firmware IO readback instead assigns
ADC CH2 to PC4, which the PCB routes to ICM-INT1. Current sensing is also
unverified and must not be calibrated against this unrelated pin. No firmware
or configuration change for current sensing has been made here.

## References

- [iNAV 9.1 battery monitoring](https://github.com/iNavFlight/inav/blob/9.1.0/docs/Battery.md)
- [STM32F722 datasheet](https://www.st.com/resource/en/datasheet/stm32f722re.pdf)
- [iNAV 9.1 serial ESC sensor implementation](https://github.com/iNavFlight/inav/blob/9.1.0/src/main/sensors/esc_sensor.c)
- [iNAV 9.1 voltage scale definition](https://github.com/iNavFlight/inav/blob/9.1.0/src/main/fc/settings.yaml)
- Local hardware source: `pcb/FC/FC.kicad_pcb`, U1 pads 8, 9 and 24.
