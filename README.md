# Koganeee
A flying voice assistant project inspired by Kogane from Jujutsu Kaisen.

<img width="998" height="1325" alt="image" src="https://github.com/user-attachments/assets/d20a29b4-c97c-421c-a61c-21d18a431f46" />

**Demo video:** https://youtu.be/gkjLtGN1tb8

## Inspiration

I wanted to combine my interest in drones with a character from Jujutsu Kaisen. The goal is a room assistant that can come to me, answer voice commands and show information on a screen. It would be useful when my hands are busy and I want to check something without reaching for my laptop.

## Current features

- A custom STM32F722 and ESP32-S3 flight controller connects the aircraft electronics.
- ELRS radio control, motor outputs and radio-loss failsafe passed bench tests.
- Saying Kogane opens a voice assistant for live weather and daily tasks on the LCD.
- The laptop handles speech recognition and spoken replies. The onboard microphone also worked in a stationary test.
- Two webcams detect people and objects. An LD2450 radar supplies human positions for the room dashboard.
- The onboard VL53L1X measures distance. A servo output was tested separately.

Autonomous following and screen retraction remain future work. Firmware setup and editable pipeline diagrams are in [firmware/README.md](firmware/README.md).

## Challenges

This was my first custom flight controller and drone build. PCB errors led to repeated soldering repairs, and I made expensive mistakes with batteries and ESCs. Connector mismatches and parts that did not fit also made assembly harder than expected.

The first flight attempt had inadequate lift with the lower shell fitted. I need to revise that design and check the propulsion setup before another attempt. The [journal](JOURNAL.md) records the build, repairs and tests.

## Build
<img width="998" height="1325" alt="image" src="https://github.com/user-attachments/assets/4e5e76a4-c71b-426d-8ef9-f2421329ba21" />
<img width="1843" height="1325" alt="image" src="https://github.com/user-attachments/assets/94a2e731-6f5b-4639-9843-79fbc698d9af" />
<img width="1298" height="1025" alt="image" src="https://github.com/user-attachments/assets/3b1f3aae-5984-47b9-9f7d-79055b54099e" />

## CAD Model
### Kogane
<img width="980" height="964" alt="image" src="https://github.com/user-attachments/assets/b200f94b-656f-4320-be3f-b24d8ce48a3b" />
<img width="992" height="910" alt="image" src="https://github.com/user-attachments/assets/df458ba6-bca9-428b-880d-90deb96635e5" />
<img width="798" height="959" alt="image" src="https://github.com/user-attachments/assets/08c6b247-241f-48a1-9d0e-109e3dd4d917" />

### Internal Drone
<img width="1501" height="799" alt="image" src="https://github.com/user-attachments/assets/ec1bab21-909c-41db-8db9-690d603431c6" />
<img width="1321" height="1109" alt="image" src="https://github.com/user-attachments/assets/93035627-7043-48d6-b1bd-5564a406f42c" />

## PCB
### Fabricated PCB
<img width="1759" height="1325" alt="image" src="https://github.com/user-attachments/assets/f6a1e768-8f11-47f3-93ab-253d0b9b717d" />
<img width="998" height="1325" alt="image" src="https://github.com/user-attachments/assets/3bfc89b6-0390-488f-b560-514c1967c6ac" />

### Schematic
<img width="1387" height="931" alt="image" src="https://github.com/user-attachments/assets/bb2b5ac7-90bc-4274-b931-00fb84bcdf46" />
<img width="1568" height="1069" alt="image" src="https://github.com/user-attachments/assets/1ec1b10e-5e11-453a-8a55-acaed5d3721d" />
<img width="1613" height="1099" alt="image" src="https://github.com/user-attachments/assets/e60abecd-1433-410d-8b17-0e5342c7fff0" />
<img width="1391" height="1060" alt="image" src="https://github.com/user-attachments/assets/3f2907a1-f4bd-4cfd-a7f8-639a140dbec5" />

### PCB Design
<img width="899" height="1078" alt="image" src="https://github.com/user-attachments/assets/e341f406-db60-47e1-9b0b-7e8a7cd45e3c" />

### 3D Model
<img width="1027" height="1165" alt="image" src="https://github.com/user-attachments/assets/e134e38a-ce69-46d6-a08a-3def4d459c11" />
<img width="1085" height="1218" alt="image" src="https://github.com/user-attachments/assets/fe0aefad-1a92-4d20-b16c-394951de0245" />

## BOM

The original parts budget is below. The [CSV BOM](BOM.csv) needs reconciliation with replacement parts, the actual radio setup and shipping costs.

| Item | Qty | Price (USD) | Link | Notes |
|------|-----|-------------|------|-------|
| 1303 5500KV brushless motor | 4 | $67.61 | [Rotor Village](https://rotorvillage.ca/geprc-speedx2-1303-5-5500kv-motor/) | |
| 3-inch Gemfan 3018 2-Blade Propeller (4 pairs) | 1 | $3.94 | [AliExpress](https://www.aliexpress.com/item/1005007476443932.html) | |
| 4-in-1 ESC 45A 20x20 | 1 | $30.55 | [AliExpress](https://www.aliexpress.com/item/1005009278492069.html) | |
| GNB 1100mAh 4S 120C HV LiPo XT60 | 1 | $19.72 | [Rotor Village](https://rotorvillage.ca/gnb-1100mah-4s-120c-hv-lipo-xt60/) | |
| Battery strap | 1 | $3.88 | [AliExpress](https://www.aliexpress.com/item/4001316238579.html) | |
| Custom Kogane FC PCB | 1 | $168.84 | [JLCPCB](https://jlcpcb.com) | Revision notes are in the PCB directory.|
| ESP32-S3-WROOM-1-N16R8 | 1 | $15.79 | [AliExpress](https://www.aliexpress.com/item/1005012502278371.html) | Manual solder |
| VL53L1X ToF sensor | 1 | $4.83 | [AliExpress](https://www.aliexpress.com/item/1005007324288727.html) | Manual solder |
| 8GB microSD card | 1 | $3.49 | [AliExpress](https://www.aliexpress.com/item/1005010323860143.html) | FAT32 for iNAV blackbox |
| OV2640 FPC camera module 75MM-160 650nm | 1 | $9.19 | [AliExpress](https://www.aliexpress.com/item/1005003040149873.html) | |
| ILI9341 2.8 inch SPI touch display | 1 | $5.69 | [AliExpress](https://www.aliexpress.com/item/1005006315533240.html) | |
| INMP441 I2S microphone | 1 | $1.59 | [AliExpress](https://www.aliexpress.com/item/1005009213592784.html) | |
| 4 ohm 3W speaker | 1 | $2.46 | [AliExpress](https://www.aliexpress.com/item/1005008626624201.html) | |
| MG90S micro servo | 0 | $0.00 | | Already owned |
| HLK-LD2450 mmWave module | 1 | $6.69 | [AliExpress](https://www.aliexpress.com/item/1005010228798692.html) | |
| USB-UART adapter 3.3V logic | 1 | $1.77 | [AliExpress](https://www.aliexpress.com/item/1005006445462581.html) | Powers LD2450 from laptop USB |
| USB webcam 720p or 1080p | 2 | $7.95 | [AliExpress](https://www.aliexpress.com/item/1005007740023631.html) | Fixed position to laptop USB |
| 4S LiPo charger with AC plug | 1 | $15.00 | [Amazon](https://www.amazon.ca/dp/B0B3Y3JGDG) | |
| XT60 Pigtail Male | 1 | $1.48 | [AliExpress](https://www.aliexpress.com/item/1005009156026988.html) | |
| Radio TX module | 1 | $4.23 | [AliExpress](https://www.aliexpress.com/item/1005010228737836.html) | Original planned module. The build uses a Pocket and ELRS receiver. |
| JST Connector kit | 1 | $6.09 | [AliExpress](https://www.aliexpress.com/item/1005010491522001.html) | |
| M2 nylon standoff kit | 1 | $3.68 | [AliExpress](https://www.aliexpress.com/item/32862529967.html) | |
| Connectors, adapters, USB extensions | Depends | < $30 | AliExpress | |

**Listed total: $384.47.**

## Credits

The [Macondo flight-controller guide](https://macondo.hackclub.com/docs/flight-controller#stm32cubemx) helped with the PCB and firmware setup. Thanks to Surya and Alvik for their advice on the electronics, drone design and build.

## Next steps

- Revise the lower shell and verify lift before another flight attempt.
- Correct the PCB issues listed in [pcb/README.md](pcb/README.md).
- Design and test a servo-driven screen-retraction mechanism.
- Calibrate the room cameras and develop autonomous following.
