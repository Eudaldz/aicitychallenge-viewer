import sys
import os
import cv2
import numpy as np

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QWidget, 
    QGridLayout, QLabel, QPushButton, QSlider, QHBoxLayout, 
    QVBoxLayout, QCheckBox, QComboBox, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap, QImage

def load_bounding_boxes(txt_file):
    """
    Loads bounding boxes from a text file with lines of format:
    [frame, ID, left, top, width, height, 1, -1, -1, -1]
    Returns a dictionary:
        boxes[frame] = list of (id, left, top, width, height)
    """
    boxes = {}
    if not os.path.isfile(txt_file):
        return boxes  # Return empty if file doesn't exist

    with open(txt_file, 'r') as f:
        for line in f:
            parts = line.strip().split(',')
            if len(parts) < 6:
                continue
            frame_idx = int(parts[0])
            obj_id    = int(parts[1])
            left      = float(parts[2])
            top       = float(parts[3])
            width     = float(parts[4])
            height    = float(parts[5])

            if frame_idx not in boxes:
                boxes[frame_idx] = []
            boxes[frame_idx].append((obj_id, left, top, width, height))
    return boxes

class VideoWidget(QLabel):
    """
    A widget that displays frames. 
    We handle double-click to toggle enlarged/focused view vs. grid view.
    """
    def __init__(self, parent=None, cam_index=-1):
        super().__init__(parent)
        self.cam_index = cam_index
        self.setScaledContents(True)
        self.setStyleSheet("background-color: black;")
        self.focused = False

    def mouseDoubleClickEvent(self, event):
        # Signal the parent that we want to toggle focus on this video.
        if self.parent() and hasattr(self.parent(), "toggle_focus"):
            self.parent().toggle_focus(self)


class MultiVideoPlayer(QMainWindow):
    INTERNAL_WIDTH = 360
    INTERNAL_HEIGHT = 360

    def __init__(self, folder_path=None):
        super().__init__()
        self.setWindowTitle("Multi-Camera Video Player")

        # Global frame index
        self.current_frame_index = 0
        self.is_playing = False

        # Store references to each camera
        self.cameras = []
        self.num_cameras = 0

        # Store the "raw" last frame read for each camera (dict: cam_index -> np.array)
        self.last_frames = {}

        # UI Setup
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout()
        self.central_widget.setLayout(self.main_layout)

        # Control bar
        self.play_pause_button = QPushButton("Play")
        self.show_gt_checkbox = QCheckBox("Show GT")
        self.show_gt_checkbox.setChecked(True)
        self.pred_combo = QComboBox()
        self.pred_combo.addItem("Ground Truth")
        self.pred_combo.addItem("det")

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)

        top_layout = QHBoxLayout()
        top_layout.addWidget(self.play_pause_button)
        top_layout.addWidget(self.show_gt_checkbox)
        top_layout.addWidget(self.pred_combo)
        top_layout.addWidget(self.slider)

        self.main_layout.addLayout(top_layout)

        # Grid layout for video widgets
        self.grid_layout = QGridLayout()
        self.main_layout.addLayout(self.grid_layout)

        # Connect signals
        self.play_pause_button.clicked.connect(self.toggle_play_pause)
        self.slider.sliderReleased.connect(self.on_slider_released)
        self.show_gt_checkbox.stateChanged.connect(self.on_show_gt_toggled)
        self.pred_combo.currentIndexChanged.connect(self.on_pred_combo_changed)

        # Timer
        self.timer = QTimer()
        self.timer.setInterval(100)  # ~10 FPS
        self.timer.timeout.connect(self.next_frame)

        # Setup folder if argument provided
        if folder_path and os.path.isdir(folder_path):
            self.setup_folder(folder_path)
        else:
            self.ask_folder()

    def ask_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Main Folder", "")
        if folder_path:
            self.setup_folder(folder_path)

    def setup_folder(self, folder_path):
        # Clear old data
        self.cameras.clear()
        self.num_cameras = 0
        self.current_frame_index = 0
        self.last_frames.clear()

        # Read subfolders
        subfolders = [f for f in os.listdir(folder_path) 
                      if os.path.isdir(os.path.join(folder_path, f))]

        # Load offsets
        offsets_map = {}
        offsets_file = os.path.join(folder_path, "offsets.txt")
        if os.path.isfile(offsets_file):
            with open(offsets_file, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) == 2:
                        offsets_map[parts[0]] = int(parts[1])

        for sub in sorted(subfolders):
            cam_path = os.path.join(folder_path, sub)
            video_file = os.path.join(cam_path, "vdo.avi")
            if os.path.isfile(video_file):
                cap = cv2.VideoCapture(video_file)
                if not cap.isOpened():
                    continue

                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

                gt_txt_file = os.path.join(cam_path, "gt", "gt.txt")
                gt_boxes = load_bounding_boxes(gt_txt_file)
                det_txt_file = os.path.join(cam_path, "det", "det.txt")
                det_boxes = load_bounding_boxes(det_txt_file)

                camera_info = {
                    'name': sub,
                    'cap': cap,
                    'frame_count': frame_count,
                    'offset': offsets_map.get(sub, 0),
                    'gt_boxes': gt_boxes,
                    'det_boxes': det_boxes,
                    'current_boxes': gt_boxes
                }
                self.cameras.append(camera_info)

        self.num_cameras = len(self.cameras)
        if self.num_cameras == 0:
            QMessageBox.warning(self, "No Cameras", "No valid camera subfolders found.")
            return

        self.create_camera_grid()

        # Update slider range
        max_frames = max(cam['frame_count'] for cam in self.cameras)
        self.slider.setRange(0, max_frames - 1)
        self.slider.setValue(0)

    def create_camera_grid(self):
        # Clear existing
        for i in reversed(range(self.grid_layout.count())):
            widget_to_remove = self.grid_layout.itemAt(i).widget()
            self.grid_layout.removeWidget(widget_to_remove)
            widget_to_remove.setParent(None)

        self.video_widgets = []

        import math
        rows = int(math.ceil(math.sqrt(self.num_cameras)))
        cols = rows if (rows * (rows - 1)) < self.num_cameras else rows

        idx = 0
        for cam_idx in range(self.num_cameras):
            vw = VideoWidget(self.central_widget, cam_index=cam_idx)
            self.video_widgets.append(vw)
            r = idx // cols
            c = idx % cols
            self.grid_layout.addWidget(vw, r, c)
            idx += 1

        self.resize(1000, 800)

    def toggle_focus(self, video_widget):
        if not video_widget.focused:
            for w in self.video_widgets:
                if w is not video_widget:
                    w.hide()
            self.grid_layout.addWidget(video_widget, 0, 0)
            self.grid_layout.setRowStretch(0, 1)
            self.grid_layout.setColumnStretch(0, 1)
            video_widget.focused = True
        else:
            video_widget.focused = False
            for w in self.video_widgets:
                w.show()
            self.create_camera_grid()

    # ---------- Play/Pause Logic ----------

    def toggle_play_pause(self):
        if self.is_playing:
            self.timer.stop()
            self.is_playing = False
            self.play_pause_button.setText("Play")
        else:
            self.timer.start()
            self.is_playing = True
            self.play_pause_button.setText("Pause")

    # ---------- Slider Logic ----------

    def on_slider_released(self):
        """
        Called when user finishes dragging the slider.
        We jump to that frame index, seeking each camera.
        """
        slider_value = self.slider.value()
        self.jump_to_frame(slider_value)

    def jump_to_frame(self, index):
        self.current_frame_index = index
        for cam_info in self.cameras:
            frame_idx = index - cam_info['offset']
            if frame_idx < 0:
                frame_idx = 0
            if frame_idx >= cam_info['frame_count']:
                frame_idx = cam_info['frame_count'] - 1
            cam_info['cap'].set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        # Because we called set(...), we will do a fresh read from each camera
        # on update_frames(...) with advance=True
        self.update_frames(self.current_frame_index, advance=True)

    # ---------- GT / Combo Toggling ----------

    def on_show_gt_toggled(self, state):
        # We do NOT advance to a new frame; just re-draw the last frames
        self.update_frames(self.current_frame_index, advance=False)

    def on_pred_combo_changed(self, index):
        choice = self.pred_combo.currentText()
        for cam_info in self.cameras:
            if choice == "Ground Truth":
                cam_info['current_boxes'] = cam_info['gt_boxes']
            elif choice == "det":
                cam_info['current_boxes'] = cam_info['det_boxes']
            else:
                cam_info['current_boxes'] = cam_info['gt_boxes']
        # Re-draw the last frames, do not advance
        self.update_frames(self.current_frame_index, advance=False)

    # ---------- Timer-Driven Playback ----------

    def next_frame(self):
        self.current_frame_index += 1
        if self.current_frame_index > self.slider.maximum():
            self.current_frame_index = 0

        # Update slider without triggering sliderReleased
        self.slider.blockSignals(True)
        self.slider.setValue(self.current_frame_index)
        self.slider.blockSignals(False)

        # Move forward by 1 frame
        self.update_frames(self.current_frame_index, advance=True)

    # ---------- The Key Method: update_frames with advance=True/False ----------

    def update_frames(self, global_frame_idx, advance=True):
        """
        If advance=True, read a new frame from each capture.
        If advance=False, re-draw bounding boxes on the last stored frames.
        """
        for i, cam_info in enumerate(self.cameras):
            offset_frame_idx = global_frame_idx - cam_info['offset']

            # If out of range, black image
            if offset_frame_idx < 0 or offset_frame_idx >= cam_info['frame_count']:
                self.video_widgets[i].setPixmap(QPixmap())
                continue

            frame = None
            if advance:
                # Read next frame from capture
                ret, f = cam_info['cap'].read()
                if not ret:
                    self.video_widgets[i].setPixmap(QPixmap())
                    continue
                # Store the raw frame
                self.last_frames[i] = f
                frame = f
            else:
                # Re-use the last stored frame
                frame = self.last_frames.get(i, None)
                if frame is None:
                    # No stored frame yet, maybe we're at start?
                    self.video_widgets[i].setPixmap(QPixmap())
                    continue

            # We'll overlay bounding boxes on a COPY so we don't permanently draw them.
            display_frame = frame.copy()

            # If "Show GT" is checked, we overlay bounding boxes from current_boxes
            if self.show_gt_checkbox.isChecked():
                boxes_dict = cam_info['current_boxes']
                if offset_frame_idx in boxes_dict:
                    for (obj_id, left, top, w, h) in boxes_dict[offset_frame_idx]:
                        left = int(left)
                        top = int(top)
                        w = int(w)
                        h = int(h)
                        cv2.rectangle(display_frame, (left, top), (left + w, top + h),
                                      (0, 255, 0), 2)
                        cv2.putText(display_frame, str(obj_id), (left, top - 5),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 2)

            # Downscale for performance
            resized_frame = cv2.resize(display_frame, 
                                       (self.INTERNAL_WIDTH, self.INTERNAL_HEIGHT),
                                       interpolation=cv2.INTER_AREA)

            # Convert to QPixmap
            rgb_image = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w
            qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_image)

            self.video_widgets[i].setPixmap(pixmap)

def main():
    app = QApplication(sys.argv)

    folder_path = None
    if len(sys.argv) > 1:
        candidate = sys.argv[1]
        if os.path.isdir(candidate):
            folder_path = candidate
        else:
            print(f"Warning: '{candidate}' is not a valid directory. Will open dialog instead.")

    player = MultiVideoPlayer(folder_path=folder_path)
    player.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
