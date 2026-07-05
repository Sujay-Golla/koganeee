# Koganeee 
(JJK Reference) Flying room voice assistant with a screen  

## Inspiration
As a Jujutsu Kaisen fan and an admirer of flying pets, I wanted to make Kogane for my room. The objective of Kogane is to be a person-following flying pet assistant that can communicate with voice and through a retractable screen, sort of like a flying Alexa but friendlier! I also wanted to make drones for a while and it seemed like a cool approach to make Kogane. A use case that I had in mind is when I'm working in my room and my hands are busy and if I need to quickly pull up a tutorial, I would normally have to put things down to find my laptop. Instead with Kogane, I can call for Kogane wherever I am in my room and quickly check for information or pull up a Youtube tutorial from its screen without any physical contact. 

## Challenges
I was new to building FCs and drones, so I had to spend a lot of time getting advice from my friends and revising designs. The timeline was also a bit tight as I had to finish it by Open Sauce

## Technical Features
In terms of the technical features, it is a drone controlled by a room-based camera-mmWave sensor fused navigation system. It has a mic and speaker for voice activation and vocal communication, as well as a retractable screen to present any information prompted by the user. It hosts 1303 Brushless motors, a big 1100mAH 4S LiPo battery, a custom FC with STM32F722RET6 and ESP32-S3-WROOM, an on-device camera for object detection, faceID, and AprilTag detection with potential for extension for radio control as needed. 

## CAD Model
### Kogane

### Internal Drone

## PCB
### Schematic

### PCB Design

### 3D Model

## BOM

| Item | Qty | Price (USD) | Link | Notes |
|------|-----|-------------|------|-------|
| 1303 5500KV brushless motor | 4 | $67.61 | [Rotor Village](https://rotorvillage.ca/geprc-speedx2-1303-5-5500kv-motor/) | |
| 3-inch Gemfan 3018 2-Blade Propeller (4 pairs) | 1 | $3.94 | [AliExpress](https://www.aliexpress.com/item/1005007476443932.html) | |
| 4-in-1 ESC 45A 20x20 | 1 | $30.55 | [AliExpress](https://www.aliexpress.com/item/1005009278492069.html) | |
| GNB 1100mAh 4S 120C HV LiPo XT60 | 1 | $19.72 | [Rotor Village](https://rotorvillage.ca/gnb-1100mah-4s-120c-hv-lipo-xt60/) | |
| Battery strap | 1 | $3.88 | [AliExpress](https://www.aliexpress.com/item/4001316238579.html) | |
| Custom Kogane FC PCB | 1 | $168.84 | [JLCPCB](https://jlcpcb.com) | Design submitted |
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
| Radio TX module | 1 | $4.23 | [AliExpress](https://www.aliexpress.com/item/1005010228737836.html) | Out of budget |
| JST Connector kit | 1 | $6.09 | [AliExpress](https://www.aliexpress.com/item/1005010491522001.html) | |
| M2 nylon standoff kit | 1 | $3.68 | [AliExpress](https://www.aliexpress.com/item/32862529967.html) | |

**Total cost: $384.47**

## Credits
https://macondo.hackclub.com/docs/flight-controller#stm32cubemx - Very useful guide :D
Thanks to Surya and Alvik for all their guidance with the PCB and drone design!


## Note - Updated July 4
- Had to rush the firmware with Claude due to the timeline but tested different elements manually with test code and will continue working on it as I wait for the PCB and parts