# Camera bring-up paused (2026-10-11)

The repaired flight controller has a replacement ESP32-S3 on native USB
(reported as COM13). The user is bringing up one peripheral at a time. Wi-Fi,
outbound telemetry, and the INMP441 microphone have passed bench checks. The
microphone worked with `CONFIG_KGN_MIC_SHIFT=16`; U11 stayed cool. A 10 kOhm
pull-up was soldered from ESP32 EN to 3.3 V, and three cold boots succeeded.

## Camera observation

- Before connecting the OV2640 to FPC1, C33 pad 1 (+1V2) measured about 1.2 V
  and U10 was cool.
- The user checked the flex orientation and connected the OV2640. A photograph
  in the conversation did not clearly show the contacts or full seating, so
  connector orientation has not been independently verified.
- With the camera connected and USB power applied, U10 became hot after an
  unspecified interval. The user reported that the 1.2 V rail was working,
  but did not record its voltage at the point U10 became hot.
- With power off, the user measured 0.509 ohm from +1V2 to GND with the
  camera attached and 0.699 ohm with it removed. The meter's shorted-probe
  resistance has **not** been measured. These close, sub-ohm readings cannot
  establish whether the camera causes a short.
- With the camera removed, the user subsequently confirmed U10 stays cool
  during the USB-only baseline check.
- No camera probe or HTTP snapshot success was reported.

**Stop condition:** Do not power the board with the camera attached until the
heating is understood. The user was told to disconnect USB, leave the battery
disconnected, let U10 cool, and remove the camera. The follow-up cool baseline
with the camera removed confirms the immediate heating stopped. U10 is the
1.2 V camera regulator; see `HANDOFF.md` section 9 and `PINMAP.md` camera
power rails.

When resuming camera diagnosis, with all power disconnected: measure the
shorted-probe resistance; repeat C33 pad 1 to pad 2 (GND) resistance with the
camera removed and attached, allowing readings to settle; inspect both ends
of the flex, its seating, and the camera module's exact pinout. Do not infer a
short from the two readings above or power it again just to obtain another
voltage reading. Keep the camera stage disabled while working elsewhere.

## Continue other peripherals

Leave FPC1 disconnected. Before each new stage, verify the board is cool on
USB with the camera removed. `BRINGUP.md` lists display next, then servo, then
speaker. The display and servo need the battery-backed 5 V rail; remove
propellers and test one peripheral at a time. The speaker has its own U11
history, so do not attach it merely because the camera is paused.

Display stage progress: with J4 empty, the user measured 5 V at J5 pin 1
relative to J5 pin 2 (GND) on battery power. J4 is a keyed 14-pin JST-XH
header on the PCB. After connecting the display to J4, the user reported that
5 V still held and there was no abnormal heat on battery power alone. Display
firmware is enabled in the current local `sdkconfig`, and the generated
`build/config/sdkconfig.h` contains `#define CONFIG_KGN_BRINGUP_DISPLAY 1`.
That verifies the build configuration, but this note has no proof yet that the
new image was flashed to COM13 or that the panel displayed a status page.

To resume in another chat, say: "Read
`firmware/companion-esp32s3/CAMERA_PAUSED.md` and
`firmware/companion-esp32s3/BRINGUP.md`; resume staged bring-up with the camera
left disconnected."
