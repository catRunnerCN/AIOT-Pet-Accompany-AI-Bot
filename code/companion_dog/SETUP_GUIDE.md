# Picar-X Environment Setup Guide

This guide details the complete installation process for the Picar-X Robot project on a Raspberry Pi (Recommended: **Raspberry Pi 5**).

## 1. Prerequisites & System Update

Before installing specific libraries, ensure your Raspberry Pi OS is up to date and has essential tools installed.

```bash
sudo apt update
sudo apt upgrade
sudo apt install git python3-pip python3-setuptools python3-smbus libatlas-base-dev libopenblas-dev libhdf5-dev libhdf5-serial-dev
```

*Note: The extra `lib` packages are often required for NumPy and OpenCV on Raspberry Pi.*

## 2. Install Hardware & System Libraries

This project relies on SunFounder's hardware drivers. You need to install `robot_hat` and `vilib`.

### A. Robot Hat (Hardware Driver)

Controls motors, servos, and audio.

```bash
cd ~
git clone -b v2.0 https://github.com/sunfounder/robot-hat.git
cd robot-hat
sudo python3 setup.py install
```

**Configure Audio (Important):**
Run the script to enable the sound card (I2S amplifier).

```bash
sudo bash i2samp.sh
```
*Type `y` and press Enter when prompted to reboot.*

### B. Vilib (Visual Library)

Provides camera support. We use the `picamera2` branch.

```bash
cd ~
git clone -b picamera2 https://github.com/sunfounder/vilib.git
cd vilib
sudo python3 install.py
```

## 3. Install Python Dependencies

This project uses modern Python libraries for the web server (FastAPI) and AI object detection (YOLO/Ultralytics).

Navigate to the project directory (where this file is located) and run:

```bash
cd /path/to/your/project
pip3 install -r requirements.txt
```

*Note: Installing `ultralytics` and `opencv-python` may take some time on a Raspberry Pi.*

## 4. Verification

To verify the installation, run:

```bash
python3 api_server.py --help
```

If you see the help message, the environment is set up correctly.

## 5. (Optional) Legacy Picar-X Library

The core Picar-X control code is **included** in this project directly (under the `picarx` folder), so you do **NOT** need to install the system-wide `picar-x` library. If you have it installed, it shouldn't conflict, but this project uses its own modified version.
