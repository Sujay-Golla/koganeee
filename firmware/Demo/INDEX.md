# Demo plans and guides

All demo runbooks are collected here. Commands still run from the base-station or ESP-IDF project directory specified in each guide.

## Start here

- [Final demo plan](FINAL_DEMO_PLAN.md): detailed recording-session progress and checks. Its 2–3 hour schedule predates the latest journal's attempted flight with inadequate lift; see the [journal](../../JOURNAL.md) for that later outcome.
- [Shipping checklist](SHIPPING_CHECKLIST.md): repository audit against Stardance's submission guidance.
- [Firmware setup](../README.md): compact build, flash and application instructions.

## Recording and feature guides

| Area | Guide |
| --- | --- |
| Voice activation and physical LCD | [VOICE_LCD_DEMO.md](VOICE_LCD_DEMO.md) |
| Daily task commands | [TASKS_DEMO.md](TASKS_DEMO.md) |
| Live weather | [WEATHER_DEMO.md](WEATHER_DEMO.md) |
| Voice selection | [VOICE_STYLE.md](VOICE_STYLE.md) |
| Stationary onboard microphone | [BOARD_MIC_TEST.md](BOARD_MIC_TEST.md) |
| Radar + two-camera room view | [ROOM_MAPPING_DEMO.md](ROOM_MAPPING_DEMO.md) |
| Furniture detection / floor placement | [OBJECT_MAPPING.md](OBJECT_MAPPING.md) |
| Optional stereo experiment | [STEREO_SETUP.md](STEREO_SETUP.md) |
| Manual-flight preparation | [FIRST_FLIGHT_PLAN.md](FIRST_FLIGHT_PLAN.md) |

## Earlier schedules

[DEMO_TODAY.md](DEMO_TODAY.md) and [DEMO_RECORDING_PLAN.md](DEMO_RECORDING_PLAN.md) preserve earlier planning. Use the final plan for current progress; older passages may describe a picture command, unfinished tests or a battery-off session that has since been superseded.

## Local writing drafts

`drafts/JOURNAL_DRAFT.md` and `drafts/README_FIRMWARE_SETUP_DRAFT.md` were moved here from the repository root. This folder is ignored by Git; these files are local editorial notes. The README template's links intentionally assume it will be pasted into the root README.

Stardance's [shipping guidance](https://stardance.hackclub.com/resources/shipping-hardware) excludes AI-generated READMEs. The generated drafts and technical notes are aids for checking facts; author the submission documentation yourself and resolve any uncertainty about AI-assisted technical documentation with the organizers.

Hardware reference material stays beside its subsystem: [PCB notes](../../pcb/README.md), [power review](../fc-inav/POWER_REVIEW.md), [battery sensing](../fc-inav/BATTERY_SENSE_CHECK.md), [companion bring-up](../companion-esp32s3/BRINGUP.md), [pin map](../companion-esp32s3/PINMAP.md) and [FC link checks](../companion-esp32s3/FC_LINK_CHECK.md). The project-wide [handoff](../../HANDOFF.md) remains at the repository root.
