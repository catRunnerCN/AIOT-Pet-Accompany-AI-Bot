# AI-Powered Pet Companion Robot Project

This project implements the intelligent robot using a Raspberry Pi 5. It enables autonomous pet tracking to keep your furry companion company, analyzes pet behavior patterns to understand their daily activities, and provides emotion insights to help you better connect with your pet's feelings and well-being.

## Setup

**Note:** This project is designed for and tested on the **Raspberry Pi 5** for optimal performance with YOLOv5.

**Cloud Server:** Some AI functionality (Data Logging, Emotion Insights) requires a separate cloud server. You can find the server code here: [https://github.com/CHCYLI/petCar/tree/main](https://github.com/CHCYLI/petCar/tree/main).

Follow the [SETUP_GUIDE.md](SETUP_GUIDE.md) to install dependencies and required libraries.

## Running the API Server

The main entry point is the web API server, which provides a dashboard for controlling the robot and viewing the camera feed.

### 1. Start the Server

Run the following command from the **project root**:

```bash
python3 api_server.py
```

By default, the server listens on port **8000**. You can specify a different host or port:

```bash
python3 api_server.py --host 0.0.0.0 --port 8000
```

### 2. Access the Dashboard

Expose port 8080:

```bash
cd ./web
python3 -m http.server 8080
```

Open your web browser and navigate to:

```
http://<raspberry-pi-ip>:8080/dashboard.html
```

(Replace `<raspberry-pi-ip>` with the IP address of your Raspberry Pi)

## Functionality

This project creates an autonomous pet companion with the following capabilities:

### 1. Intelligent Pet Tracking
The robot uses **Computer Vision** to recognize and follow your pet (specifically dogs by default).
-   **AI Detection:** Utilizes the **YOLOv5** model (via `ultralytics`) to identify pets in real-time.
-   **Auto-Follow:** When a pet is detected, the robot adjusts its steering and speed to keep the pet centered in the frame.
-   **Distance Maintenance:** It attempts to stay at a "safe distance" (e.g., 50cm). It moves forward if too far, stops if close, and backs up if too close.

### 2. Interactive Web Dashboard
A comprehensive web interface allows you to monitor and control the robot from any browser on the network.
-   **Live Camera Stream:** View what the robot sees in real-time (MJPEG stream).
-   **Manual Control:** Take over control with on-screen buttons to drive the robot (Forward, Backward, Left, Right) or trigger specific actions.
-   **Mode Switching:** Toggle between "Auto Follow" mode and "Manual" mode instantly.
-   **Status Monitoring:** View real-time telemetry including CPU usage, memory, disk space, and current robot status.

### 3. Robot Interaction & Feedback
The robot isn't just a passive observer; it reacts to the environment.
-   **Celebrations:** When triggered (or potentially upon specific events), the robot performs "happy" moves like spinning or bouncing.
-   **Audio Feedback:** Plays sound effects (using the Robot Hat's speaker) during interactions to simulate a pet-like personality.

### 4. Safety Systems
To prevent accidents, the robot runs background safety checks:
-   **Obstacle Avoidance:** Uses the **Ultrasonic Sensor** to detect objects directly in front. If an obstacle is too close, the robot stops automatically.
-   **Cliff Detection:** (Optional) Uses **Grayscale Sensors** to detect drop-offs (like stairs) and prevents the robot from driving off edges.

### 5. Cloud Connectivity
The system is designed to work with a cloud backend for data analysis.
-   **Data Logging:** Automatically uploads activity logs and snapshots to a configured Google Cloud Platform (GCP) server.
-   **Emotion Insights:** Can fetch daily summaries or "emotion analysis" reports from the cloud, displaying them on the dashboard to give you insights into your pet's activity levels.

