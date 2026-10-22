# Koganeee 
(JJK Reference) Flying room voice assistant with a screen  

<img width="998" height="1325" alt="image" src="https://github.com/user-attachments/assets/d20a29b4-c97c-421c-a61c-21d18a431f46" />

**Demo video:** https://youtu.be/gkjLtGN1tb8

## Inspiration
As a Jujutsu Kaisen fan and an admirer of flying pets, I wanted to make Kogane for my room. The objective of Kogane is to be a person-following flying pet assistant that can communicate with voice and through a retractable screen, sort of like a flying Alexa but friendlier! I also wanted to make drones for a while and it seemed like a cool approach to make Kogane. A use case that I had in mind is when I'm working in my room and my hands are busy and if I need to quickly pull up a tutorial, I would normally have to put things down to find my laptop. Instead with Kogane, I can call for Kogane wherever I am in my room and quickly check for information or pull up a Youtube tutorial from its screen without any physical contact. 

## Challenges
I was new to building FCs and drones, so I had to spend a lot of time getting advice from my friends and revising designs. The timeline was also a bit tight as I had to finish it by Open Sauce. There were a lot of errors on the PCB that I had not anticipated, so I had to make a lot of tweaks with soldering. I also made expensive mistakes with batteries and ESCs but eventually made it work.  

## Technical Features
In terms of the technical features, it is a drone that can be radio controlled, but ready to be implemented with a room-based camera-mmWave sensor fused navigation system for object and person detection, currently displayed in a dashboard for demo. Koganeee also has a mic and LCD screen for the built-in voice assistant with a live Weather app and a Tasks app. It hosts 1303 Brushless motors, a big 1100mAH 4S LiPo battery, and a custom FC with STM32F722RET6 and ESP32-S3-WROOM. Flight computation with accelerometer and ToF sensor is done on-board with the STM32, and is complemented by the ESP32 for data transmission, whether it be directions for autonomous tracking or for cards to be displayed on the screen. 

## Guide to recreating your very own Koganeee!

1. **Start with a revised BOM:** Start off with my [BOM.csv](BOM.csv), check connector compatibility for different modules, and make a good plan for making reliable harnesses
2. **3D Print your Koganeee:** The [CAD folder](cad/) contains the assembly for the shell and drone design, feel free to change the frame type and revise the shell as needed, taking into account some of the notes I added under [CAD notes](cad/README.md) regarding shell assembly, total weight and propeller-clearance.
3. **The flight controller:** Review the [PCB notes](pcb/README.md) and make adjustments to the PCB before ordering it, it's definitely also possible to make it more compact with smaller connectors and better planning, so plan for space optimization!
4. **Set up the firmware.** Follow the [firmware guide](firmware/README.md) for the toolchains and setup order, most of the details for the firmware setup as well as the firmware files are already available and can easily be modified! 
5. **Test in stages:** The [demo guides](firmware/Demo/INDEX.md) cover voice commands, the LCD, microphone, weather, tasks and room mapping, so check those out and ask your favorite AI (I prefer Sol or Gemini) for any clarifications
6. **Go through tests for a safe flight:** Follow the [flight preparation guide](firmware/Demo/FIRST_FLIGHT_PLAN.md), verifying the orientation, radio control and failsafe with propellers off, and as well as the physical connections, especially harnesses and soldered joints

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

| Item | Qty | Price (USD) | Link | Notes |
|------|-----|-------------|------|-------|
| 1303 5500KV brushless motor | 4 | $67.61 | [Rotor Village](https://rotorvillage.ca/geprc-speedx2-1303-5-5500kv-motor/) | |
| 3-inch Gemfan 3018 2-Blade Propeller (4 pairs) | 1 | $3.94 | [AliExpress](https://www.aliexpress.com/item/1005007476443932.html) | |
| 4-in-1 ESC 45A 20x20 | 1 | $30.55 | [AliExpress](https://www.aliexpress.com/item/1005009278492069.html) | |
| GNB 1100mAh 4S 120C HV LiPo XT60 | 1 | $19.72 | [Rotor Village](https://rotorvillage.ca/gnb-1100mah-4s-120c-hv-lipo-xt60/) | |
| Battery strap | 1 | $3.88 | [AliExpress](https://www.aliexpress.com/item/4001316238579.html) | |
| Custom Kogane FC PCB | 2 | $168.84 | [JLCPCB](https://jlcpcb.com) | Design submitted but revisions noted under in the PCB directory (min 2 assembled PCBs) |
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
| Radio TX module | 1 | $4.23 | [AliExpress](https://www.aliexpress.com/item/1005010228737836.html) | For future integration as RC transmitter is currently out of budget |
| JST Connector kit | 1 | $6.09 | [AliExpress](https://www.aliexpress.com/item/1005010491522001.html) | |
| M2 nylon standoff kit | 1 | $3.68 | [AliExpress](https://www.aliexpress.com/item/32862529967.html) | |
| Connectors, adapters, USB extensions | Depends | < $30 | AliExpress | |
| Radiomaster Pocket | 1 | $96.51 | [Amazon](https://www.amazon.ca/Radiomaster-Transmitter-Portable-Charcoal-transmitter/dp/B0GWPZ96C5?source=ps-sl-shoppingads-lpcontext&th=1) | Or borrow from a friend like I did for testing |

**Total cost (upper bound): $510.98**

## Credits
https://macondo.hackclub.com/docs/flight-controller#stm32cubemx - Very useful guide :D
Thanks to Surya and Alvik for all their guidance with the PCB, drone design, and throughout the build!
Used ChatGPT and various Claude models throughout the design and build process. Only used them for documentation for draft and format generation, I've looked through and edited all of them to keep them consistent with my understanding of the project, so that it is more readable for other people trying to recreate it.

## Next Steps
While all the firmware is available, I didn't have time to install and calibrate cameras for full autonomy. Also didn't have time to design a proper mechanism for screen retraction but that could a simple pulley driven by one servo.
