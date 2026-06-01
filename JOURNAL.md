# Journal for building Kogane
Total number of hours: 2

## May 31 - Working on BOM
### Hours spent: 2

Spent some time figuring out how to deal with the placement of different components and the scope of this project. Firstly, I decided that it made sense to use lightweight models for voice and video, keeping it limited so that it can run independently on A7S rather than relying on my laptop. Then I decided to have 2 mmWave sensors to cover blindspots and detect position of humans in the room, and decided it would be cool to integrate CV with mmWave, so added a fixed camera to help inform the drone position. A small FPV camera on the drone can allow it to avoid obstacles, and it would be cool to integrate VISTA (a research paper about drones navigating unknown maps) at least for initial calibration. Still figuring out the feasibility of a custom FC or if it would be easier to have a basic FC and a separate ESP32 for communication, camera and for extending the project to control servos for the rolling screen and a gripper in the future. Drafted the BOM but will find more stuff on AliExpress tomorrow.