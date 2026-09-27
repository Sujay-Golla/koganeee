# (Draft) Journal for building Kogane
Total number of hours: 48 (so far)

## Sep 25 - Reflow station for fixing PCB #1 and resoldering USB breakout
### Hours spent: 3
- A friend bought a ESP32 module for me to fix up PCB #1
- Used reflow station to replace module
<img width="4000" height="3000" alt="image" src="https://github.com/user-attachments/assets/f015be2f-1cbf-4327-8325-9474d3c3cc4f" />
<img width="1319" height="994" alt="image" src="https://github.com/user-attachments/assets/47a29aed-0fd9-407c-852e-47d5a33cb7f9" />
- Attached USB breakout directly
<img width="4000" height="3000" alt="image" src="https://github.com/user-attachments/assets/9ddf1894-f564-42a9-90fb-a35b95c7e838" />

## Sep 23 - Unsoldering and trying to clear shorts near RX/TX
### Hours spent: 3
- Realized one of the issues was that speaker area was heating up a lot, realized there were shorts all over the pins on the right side of the FC due to the bad soldering practices for RX/TX
- Unsoldered TTL wires, tried to clear out the extra solder with flux, wick, soldering iron, etc.
- Damaged those pads and ruined RX/TX connection AGAIN (Currently nothing works)
<img width="1759" height="1325" alt="image" src="https://github.com/user-attachments/assets/9e373c55-95b3-44b5-9d27-db4e044f8d6f" />

## Sep 22 - Fixing broken uart connection, Soldering USB, Flashing ESP32, Setting up peripherals and firmware 
### Hours spent: 9
- UART broke, tried resoldering but didnt work
- Used USB and this time it worked because of enable being on HIGH
<img width="1759" height="1325" alt="image" src="https://github.com/user-attachments/assets/0d57b439-a922-42d0-bb70-7a20c393f6c8" />
- Flashed ESP32 again and it worked
<img width="1759" height="1325" alt="image" src="https://github.com/user-attachments/assets/062bc7d7-d1d1-48d0-ac74-db2e005b8006" />
- Spent a few hours letting Claude setup codebase while I was making individual connectors for all of the peripherals because I was not paying attention to the type of connectors given by devices and designed FC incorrectly (and some just needed longer wires)
<img width="1759" height="1325" alt="image" src="https://github.com/user-attachments/assets/80b4f187-b97f-499e-b58a-41610a2865ed" />
- None of the peripherals worked but Wifi data packets were received (realized I need to connect battery for it to work)
<img width="1759" height="1325" alt="image" src="https://github.com/user-attachments/assets/8fd742dd-c55f-493e-9b74-fc7264ce5293" />
- Camera stream was supposed to work didn't seem to work

## Sep 21 - Flashing ESP32
### Hours spent: 5
- Gave up on TTL connector, instead tried USB breakout and it didnt work either but retried UART and that worked
- Realized I needed resistor for enable, so brought it from MyFab and soldered it
- Many hours of holding SW1 and SW3 and debugging with Claude, it finally flashed

## Sep 16 - AliExpress iron incident
### Hours spent: 2
- Unpacked and tried to use soldering iron
- Didn't work most of the time so played around with adjusting tip
- Screen wasn't moving so I thought it was updating but 30 seconds later it turns glowing red
- Got advice, tried recreating situation and recorded it
- Submitted return for AliExpress

## Sep 4 - Resoldering with better flux and leaded solder, still caused shorting between RX and TX
### Hours spent: 2
- Tried resoldering with leaded solder and better flux more neatly
<img width="998" height="1325" alt="image" src="https://github.com/user-attachments/assets/d40cc77d-8bf8-46d4-95c4-e5ce757575db" />
- Tried checking for continuity and still failed
- Ordered a new soldering iron and my own equipment on AliExpress

## Aug 27 - 2 soldering attempts, USB to STL soldering, ESP installation with WSL
### Hours spent: 6
- Started with a dying tip, tried soldering, kept coming off
- Tried more solder, less solder, flux, tinning, retinning until there was no shorting
- Tried uploading code, didn't work, went back to soldering
- Ruined copper pads so had to use PCB #2
- Used a bad soldering iron but with a good tip and tried agdain and it somewhat worked
- Still shorted though, so tried installing ESP with WSL instead

## Aug 23 - Making gyro work
### Hours spent: 2
- Tried plugging in directly with Claude's code but one of the motors didnt work because it was on a different TIM channel
https://photos.app.goo.gl/y1WebvtZ1g6wSLuL6
- Spent a while debugging and figured out that it was the wrong way to configure the TIM channel so switched it and it works
https://photos.app.goo.gl/5kp8YR52DHTmUaiz7

## Aug 22 - Soldering at a friend's house 
### Hours spent: 3
<img width="1495" height="1325" alt="image" src="https://github.com/user-attachments/assets/a6baf7be-3887-45f9-b285-a682666599b6" />

- Used flux to fix up some soldering joints for motors
<img width="998" height="1325" alt="image" src="https://github.com/user-attachments/assets/5c0c98ca-3e2b-4af2-b5a0-844c5624aa29" />

- Resoldered with XT30 connectors
<img width="998" height="1325" alt="image" src="https://github.com/user-attachments/assets/bb6d90d0-93dd-4294-8473-960fac5bd229" />

- Resoldered the wires from ESC to FC, this time with flux and in antiparallel direction to avoid unwanted stresses
<img width="998" height="1325" alt="image" src="https://github.com/user-attachments/assets/9147eace-48c8-4cc1-b04f-3f588f9cb5d5" />

- Fixed up microphone with wick, flux and solder
<img width="998" height="1325" alt="image" src="https://github.com/user-attachments/assets/8604e2f7-84b4-4865-b5c5-5b0cff65f2fd" />


## Aug 18 - ESC to PCB
### Hours spent: 3
- Spent a while figuring out the best course of action. First started off with the thin wire and tryied crimping and connecting, but it did not work as I expected
- Then I cut pieces of thicker wire and tried soldering the thin wire to the thick wire
- I HAD NO FLUX OR HELPING HANDS SO I WAS DOING IT BY BRUTE FORCE (had to solder wires so they go in the same direction rather than antiparallel
- Eventually got to electrical tape and make it survive
<img width="1759" height="1325" alt="image" src="https://github.com/user-attachments/assets/ad6faa6b-1949-45dc-8f9f-14faebce2009" />
<img width="1759" height="1325" alt="image" src="https://github.com/user-attachments/assets/12534371-5d85-4c82-babf-1f55244a4427" />

## Aug 14 - Soldering ESC
### Hours spent: 2
- Ordered XT30 connectors since those are the oens used by my battery and then unsoldered and resoldered it, along with the capacitor
<img width="1759" height="1325" alt="image" src="https://github.com/user-attachments/assets/3649cff0-75f6-4411-9c6a-bb7f62cd849d" />

- I did not have desoldering equipment nor flux so it was brute forced, luckily I had a solid ESC that survived all that heat
<img width="998" height="1325" alt="image" src="https://github.com/user-attachments/assets/431c6fb6-9e1a-481c-8a13-cffef3f2b547" />

- Tried soldering microphone but ruined it by due to very small copper pads
<img width="998" height="1325" alt="image" src="https://github.com/user-attachments/assets/abb535d5-f108-47b9-b631-72064fa83f36" />


## Timelapse
### Hours spent: 6
https://lapse.hackclub.com/timelapse/Mf367k7zCeD8
https://lapse.hackclub.com/timelapse/Izz86LsU43mH
https://lapse.hackclub.com/timelapse/hhBw-N-66mvc

Roughly summarizing 6 hours of timelapses:
- Had to unpack and arrange all of the electronics I received, checked connectors and what I needed to make connectors for again.
- Realized I had designed for JST-XH rather than JST-SH connectors so spent a while trying to learn all of the different types of connectors so that I can avoid making the same mistake again
- For the time being, I stripped wires, crimped them and used my JST-XH connectors for the FC to ESC connection
- I had no idea how to solder XT60 connectors so I had to learn, and then after a while, I realized I needed to connect a male female pair at the end to avoid deformation so I had wasted the soldering session
<img width="998" height="1325" alt="image" src="https://github.com/user-attachments/assets/27afa257-feca-455d-9971-3ee02ac2adaa" />
- I started using Claude to figure out how the firmware works, created a detailed plan and then started downloading applications I needed (iNav, Zadig, etc.)

## July 21 - JLCPCB error, Soldering JST on my own, CAD fixes
### Hours spent: 2
- My connectors were wrong parts for the JLCPCB order, especially for the 3 pin connector, so I had to tell them to exclude it
<img width="2222" height="960" alt="image" src="https://github.com/user-attachments/assets/38e97530-2197-4530-b739-03a8649c488d" />
- Once the PCB arrived, I checked for continuity and soldered the JST connectors
<img width="998" height="1325" alt="image" src="https://github.com/user-attachments/assets/c3b0b421-a239-4a49-a5a7-6a6d35323fe4" />
<img width="1759" height="1325" alt="image" src="https://github.com/user-attachments/assets/ccad7a72-c4a1-4a10-a82e-b77d5a311303" />
- CAD fixes (had to change diameter and verify 3DP settings with Vedant
<img width="1106" height="859" alt="image" src="https://github.com/user-attachments/assets/dacd12cc-8e07-46de-a4bc-d4e7395e1d14" />


# Journal for designing Kogane
Total number of hours: 59

## May 31 - Working on BOM
### Hours spent: 2

Spent some time figuring out how to deal with the placement of different components and the scope of this project. Firstly, I decided that it made sense to use lightweight models for voice and video, keeping it limited so that it can run independently on A7S rather than relying on my laptop. Then I decided to have 2 mmWave sensors to cover blindspots and detect position of humans in the room, and decided it would be cool to integrate CV with mmWave, so added a fixed camera to help inform the drone position. A small FPV camera on the drone can allow it to avoid obstacles, and it would be cool to integrate VISTA (a research paper about drones navigating unknown maps) at least for initial calibration. Still figuring out the feasibility of a custom FC or if it would be easier to have a basic FC and a separate ESP32 for communication, camera and for extending the project to control servos for the rolling screen and a gripper in the future. Drafted the BOM but will find more stuff on AliExpress tomorrow.

## June 8 - Working on the sketch
### Hours spent: 3

I wanted to pitch my project as an X-tier project for Stardance, so I started making a sketch to explain my idea to Alex. I had to change a few things to make my life easier and to make the project more feasible. Firstly, I changed the scope so that rather than having a rollable screen with multiple screens, I would just have one large screen with the lower body of kogane being lowered using strings and servos. Then, I went to explore the different modules I would need to make my custom FC, including the STM32, an IMU, ESCs and ESP32 with its peripherals like OV2640, INMP441, MAX98357A, 4ohm speaker, etc. Also decided to use the LiPo 3S battery and to create the ground station, first I explored the possibility of magnetic docking with pogo pins but then realized it would be difficult and complicated. So rather it will be a manual charging connection for now. I decided to use USB Webcams connected with long wires to simplify the compute and directly connect to the A7S without compromising latency. Will also have a mmWave sensor near the ground station for detection in the dark. One concern is still that the CV aspect will be a bit difficult since it is my first time doing it and it might be safer to resort to IR cameras and use IR reflectors on the drone to detect position precisely, but that is an aspect of the scope I can change as I shop for the materials. My next immediate goal is to finish the FC and CAD.
<img width="1920" height="1080" alt="image" src="https://github.com/user-attachments/assets/0ba13870-42f0-40e2-a249-86f18fe76379" />

## Note: The rest was done through Lapse/Lookout and logged with the Stardance project
