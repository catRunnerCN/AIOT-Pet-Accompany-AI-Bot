companion_dog runs on Raspberry Pi 5

```

git clone https://github.com/RobbieFeng/companion_dog.git

```

petCar runs on Google Cloud

```
git clone https://github.com/CHCYLI/petCar.git

```

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


# Pet Car Project

A backend server for the Pet Car project that provides HTTP APIs for uploading and analyzing pet images and videos using AI.

## Overview

This project runs a Flask API server on your PC that:
- Receives images and videos from a Raspberry Pi
- Uses AI (OpenAI and Hugging Face) to analyze pet behavior
- Maintains daily activity logs
- Provides insights about your pet's mood and behavior

## Prerequisites

- Python 3.7 or higher
- OpenAI API key (for image/video analysis and daily log analysis)
- Optional: Hugging Face API key (if using HF models)

## Setup

### 1. Install Dependencies

Navigate to the `PythonCode` directory and install the required packages:

```bash
cd PythonCode
pip install -r requirements.txt flask opencv-python
```

**Note:** If `requirements.txt` doesn't include Flask, install it separately:
```bash
pip install flask
```

### 2. Configure Environment Variables

Create a `.env` file in the `PythonCode` directory (or in the project root) with your API keys:

```env
OPENAI_API_KEY=your_openai_api_key_here
HF_API_KEY=your_huggingface_api_key_here
```

The server will automatically look for `.env` files in:
1. `PythonCode/.env`
2. Project root `.env`
3. System environment variables

**Important:** At minimum, you need `OPENAI_API_KEY` for the server to function properly.

### 3. Directory Structure

The server automatically creates the following directories if they don't exist:
- `PythonCode/images/` - Stores uploaded images
- `PythonCode/videos/` - Stores uploaded videos
- `PythonCode/logs/` - Stores daily activity logs

## Running the Server

### Start the API Server

From the `PythonCode` directory, run:

```bash
python api_server.py
```

The server will start on `http://0.0.0.0:5000` (accessible from your local network).

**Note:** The server runs with `debug=True` by default, which is useful for development but should be disabled in production.

### Verify the Server is Running

Test the health check endpoint:

```bash
curl http://localhost:5000/api/test
```

Or open in your browser: `http://localhost:5000/api/test`

You should receive:
```json
{
  "status": "ok",
  "message": "Pet Car cloud API is running."
}
```

## API Endpoints

### `GET /api/test`
Health check endpoint. Returns server status.

### `POST /api/upload-image`
Upload an image from the Pi.
- **Content-Type:** `multipart/form-data`
- **Field:** `image` (file)
- **Response:** Returns saved path and AI-generated caption

### `POST /api/upload-video`
Upload a video from the Pi.
- **Content-Type:** `multipart/form-data`
- **Field:** `video` (file)
- **Response:** Returns saved path and AI-generated summary

### `POST /api/append-event`
Manually append an event to today's log.
- **Content-Type:** `application/json`
- **Body:**
  ```json
  {
    "description": "dog is eating",
    "extra": {"food": "kibble"}
  }
  ```

### `GET /api/today-log`
Get today's activity log as plain text (wrapped in JSON).

### `GET /api/analyze-today`
Analyze today's log using AI and return insights.

### `GET /api/emotion-insight`
Get the most recent emotion analysis for your pet.

### `GET /api/today-log-path`
Get the path and content of the most recent log file.

## Network Configuration

The server binds to `0.0.0.0:5000`, making it accessible from:
- Localhost: `http://localhost:5000`
- Local network: `http://<your-pc-ip>:5000`

To find your PC's IP address:
- **Windows:** `ipconfig` (look for IPv4 Address)
- **Linux/Mac:** `ifconfig` or `ip addr`

Make sure your Raspberry Pi can reach your PC on the same local network.

## Troubleshooting

### Server won't start
- Check that port 5000 is not already in use
- Verify all dependencies are installed: `pip list | grep flask`
- Check for Python syntax errors: `python -m py_compile api_server.py`

### API key errors
- Verify your `.env` file is in the correct location
- Check that `OPENAI_API_KEY` is set correctly
- The server will print warnings if API keys are missing

### Images/videos not saving
- Check that the `images/` and `videos/` directories exist and are writable
- Verify disk space is available

## Project Structure

```
petCar/
├── PythonCode/
│   ├── api_server.py      # Main Flask server
│   ├── cloud_ai.py        # AI analysis functions
│   ├── config.py          # Configuration and environment variables
│   ├── logger.py          # Logging utilities
│   ├── requirements.txt   # Python dependencies
│   ├── images/            # Uploaded images (auto-created)
│   ├── videos/            # Uploaded videos (auto-created)
│   └── logs/              # Daily activity logs (auto-created)
└── README.md
```

## Notes

- The server runs in debug mode by default (useful for development)
- Logs are stored as JSONL files with format: `pet_log_YYYY-MM-DD.jsonl`
- Images and videos are saved with timestamps: `from_pi_YYYYMMDD_HHMMSS.jpg/mp4`
- This project is designed to run on your PC while a Raspberry Pi sends data to it

