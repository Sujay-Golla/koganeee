# Stardance shipping audit

Checked October 19, 2026 against the repository, including your README/journal updates through `c441b93`, and the [hardware-shipping guidelines](https://stardance.hackclub.com/resources/shipping-hardware). “Not found” means not visible in these files; a photo or conversation may exist elsewhere. This is preparation for review, not an approval prediction.

## Already present

| Submission item | Repository evidence |
| --- | --- |
| Organized CAD, PCB and firmware | `cad/`, `pcb/`, `firmware/` |
| Root CSV BOM with USD prices and links | [BOM.csv](../../BOM.csv); completeness needs updating below |
| PCB editable sources and manufacturing output | [KiCad project](../../pcb/FC/FC.kicad_pro), schematic sheets, board, libraries and [Gerbers ZIP](../../pcb/FC/jlcpcb/production_files/GERBER-FC.zip) |
| Assembly STEP | [Drone Assembly.step](../../cad/Drone%20Assembly.step), plus separate shell and ground-station STEP files |
| Firmware/software | Custom iNAV HEX/patches, ESP32 source and Python applications |
| Project motivation and design/PCB pictures | [Root README](../../README.md) |
| Demo video link | Root README now links [the YouTube demo](https://youtu.be/gkjLtGN1tb8); logged-out playback was not checked in this audit |
| Built-project photos | Root README now includes a Build section and additional photos; confirm a complete-aircraft view is clear |
| Physical-build history | [Journal](../../JOURNAL.md), with assembly/repair photos and timelapse links |
| Recent devlogs | October 16–18 entries are now present; building total is recorded as 88 hours |
| Design feedback acknowledged | README credits Surya and Alvik; retain your own record of their actual feedback |

The assembly STEP contains 91 product records, including motor, battery, propeller and electronic-package names. This supports that electronics are included, but is not a visual verification that every current part is correctly placed.

## Finish before submitting

### 1. Publish and link the final demo

- [x] Add the YouTube demo link to the root README.
- [ ] Check that the demo plays while logged out and include the same URL in the submission. A Drive-only upload does not satisfy the linked guidance.
- [ ] Select and play back the secured weather/tasks/LCD, stationary board-microphone and ToF clips; choose a usable mapping take.
- [ ] Caption the demonstrated setup accurately: laptop speech processing/output, separate feature and manual-flight boards, radar-based human positions and camera detections. The latest journal records an attempted flight with inadequate lift; a successful hover is not established. Earlier plans predate that attempt.

### 2. Add the full-build photo and external wiring drawing

- [x] Add built-project photos to the root README.
- [ ] Confirm that at least one photo clearly shows the complete assembled aircraft rather than only individual parts.
- [ ] Add a drawing for the external harnesses: battery → ESC → FC, motors, ELRS, ESP32/peripherals, and laptop → webcams/radar adapter. Existing PCB schematic screenshots do not describe all off-board wiring.
- [ ] Label the actual ESC connector order and USB/serial connections. Show prototype repairs where they are needed to reproduce the build.

### 3. Reconcile the BOM with what was built

- [ ] Add explicit shipping charges or document that shipping is included; no shipping row or explanation was found.
- [ ] Replace the obsolete cheap “Radio TX module” plan with the actual RadioMaster Pocket and ELRS receiver, using your receipts for links/prices.
- [ ] Check the replacement ESC and battery, USB breakout, hand-repair components, cables/connectors and printed/mechanical parts against the final assembly. Separate required build parts from optional development tools.
- [ ] Correct the servo's quantity: it is listed as zero because it was already owned, although a servo was used. Record the required quantity and explain ownership/cost separately.
- [ ] Recompute the total and update the README BOM to match the CSV. The README now adds an estimated connectors/adapters/extensions row that is absent from the CSV; reconcile actual costs and shipping. Keep USD conversion and quantity/line-total conventions clear; do not invent purchase costs.

### 4. Finish your own documentation

- [ ] Author the final project README yourself. The guidelines prohibit AI-generated READMEs; the firmware/PCB text and writing drafts generated in this chat need an authorship/policy review, not an assumption that a quick rewording resolves the rule.
- [ ] Make feature wording consistent throughout the README. The new Next Steps section explains that autonomy and the screen-retraction mechanism are unfinished, while Technical Features still describes a navigation-controlled drone and retractable screen. Keep the actual demonstration and future goals clear.
- [x] Add October 16–18 build/devlog entries and media references. These are now in the published journal; the local draft is optional background and should not be copied over the new entries.
- [ ] Confirm the recorded hours and separate building/design totals against your own logs before submission.
- [ ] Preserve credits for outside advice and upstream software. Keep statements about your own design/work and the tools used accurate.

### 5. Verify the final CAD export

- [ ] Open `cad/Drone Assembly.step` and confirm it represents the final mechanism plus all relevant electronics, including the actual FC, ESC, receiver, battery, motors, display and servo. Check the ground-station assembly too if it is part of the submitted design.
- [ ] Confirm imported STEP geometry is intact and identify which file is the complete assembly. The many separate component exports should not leave a reviewer guessing.
- [ ] Add the native editable CAD file if available. The guidance treats this as desirable alongside the STEP; absence of a native file alone was not identified as a mandatory failure.

## Scope of this audit

The guideline allows firmware to be untested, so it does not impose an extra named first-hover test. It does ask for a complete, honestly documented project. Approval depends on the actual submission and reviewer; do not describe an unverified flight, repaired power fault or calibrated furniture map as completed.

Public video status, final assembly completeness, all spending and the substance of design-feedback conversations require your confirmation. README feature claims, journal entries, BOM prices and CAD contents were left for you to verify; this cleanup only updates navigation and groups the existing guides.
