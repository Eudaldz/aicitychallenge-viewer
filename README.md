# Multi-Camera Video Player

This repository provides a basic multi-camera video player in Python using PyQt5 (or PySide2), OpenCV, and NumPy. The application can:

- Launch a folder dialog to select a main directory containing multiple subfolders for each camera.
- Load multiple camera videos simultaneously and synchronize them based on optional offset values from an `offsets.txt`.
- Display bounding-box annotations from ground truth or predictions (e.g., from `det/det.txt`).
- Play/pause all videos in sync with a single slider and control panel.
- Double-click any camera view to enlarge (focus mode) and revert to grid view with another double-click.

## Features

1. **Folder-based camera layout**: Each subfolder is treated as a camera if it contains a `vdo.avi`.
2. **Time offsets**: Each camera can have a frame offset defined in `offsets.txt`.
3. **Bounding box overlay**: Toggle GT or other detection results via UI.
4. **Grid layout & focus mode**: Videos displayed in a grid; double-click on one to zoom in on that feed.
5. **Playback Control**: Single progress bar, play/pause controls all cameras.

## Installation Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME_HERE/multi_cam_player.git
cd multi_cam_player
```

### 2. Create a Python Virtual Environment

Depending on your system, you can create a virtual environment in different ways. One common method is:

```bash
python -m venv .venv
```

(On some systems, you might use python3 instead of python.)

### 3. Activate the Virtual Environment

On Linux/macOS:

```bash
source .venv/bin/activate
```

On Windows (Command Prompt):

```bash
.venv\Scripts\activate
```

### 4. Install Requirements

```bash
pip install -r requirements.txt
```

### 5. Run the Application

```bash
python main.py <sequence_folder>
```
