# Journal for building Kogane
Total number of hours: 5

## May 31 - Working on BOM
### Hours spent: 2

Spent some time figuring out how to deal with the placement of different components and the scope of this project. Firstly, I decided that it made sense to use lightweight models for voice and video, keeping it limited so that it can run independently on A7S rather than relying on my laptop. Then I decided to have 2 mmWave sensors to cover blindspots and detect position of humans in the room, and decided it would be cool to integrate CV with mmWave, so added a fixed camera to help inform the drone position. A small FPV camera on the drone can allow it to avoid obstacles, and it would be cool to integrate VISTA (a research paper about drones navigating unknown maps) at least for initial calibration. Still figuring out the feasibility of a custom FC or if it would be easier to have a basic FC and a separate ESP32 for communication, camera and for extending the project to control servos for the rolling screen and a gripper in the future. Drafted the BOM but will find more stuff on AliExpress tomorrow.

## June 8 - Working on the sketch
### Hours spent: 3

I wanted to pitch my project as an X-tier project for Stardance, so I started making a sketch to explain my idea to Alex. I had to change a few things to make my life easier and to make the project more feasible. Firstly, I changed the scope so that rather than having a rollable screen with multiple screens, I would just have one large screen with the lower body of kogane being lowered using strings and servos. Then, I went to explore the different modules I would need to make my custom FC, including the STM32, an IMU, ESCs and ESP32 with its peripherals like OV2640, INMP441, MAX98357A, 4ohm speaker, etc. Also decided to use the LiPo 3S battery and to create the ground station, first I explored the possibility of magnetic docking with pogo pins but then realized it would be difficult and complicated. So rather it will be a manual charging connection for now. I decided to use USB Webcams connected with long wires to simplify the compute and directly connect to the A7S without compromising latency. Will also have a mmWave sensor near the ground station for detection in the dark. One concern is still that the CV aspect will be a bit difficult since it is my first time doing it and it might be safer to resort to IR cameras and use IR reflectors on the drone to detect position precisely, but that is an aspect of the scope I can change as I shop for the materials. My next immediate goal is to finish the FC and CAD.
<img width="1920" height="1080" alt="image" src="https://github.com/user-attachments/assets/0ba13870-42f0-40e2-a249-86f18fe76379" />

## Note: The rest was done through Lapse/Lookout and logged with the Stardance project
