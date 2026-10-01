import cv2
import numpy as np
import time
import math
import os
import urllib.request
import ctypes
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# Fast Windows Win32 API Ctypes Mouse Control (< 0.005ms latency)
user32 = ctypes.windll.user32

def set_mouse_pos(x, y):
    user32.SetCursorPos(int(x), int(y))

def mouse_left_down():
    user32.mouse_event(0x0002, 0, 0, 0, 0) # MOUSEEVENTF_LEFTDOWN

def mouse_left_up():
    user32.mouse_event(0x0004, 0, 0, 0, 0) # MOUSEEVENTF_LEFTUP

def mouse_right_click():
    user32.mouse_event(0x0008, 0, 0, 0, 0) # MOUSEEVENTF_RIGHTDOWN
    user32.mouse_event(0x0010, 0, 0, 0, 0) # MOUSEEVENTF_RIGHTUP

def mouse_scroll(amount):
    user32.mouse_event(0x0800, 0, 0, amount, 0) # MOUSEEVENTF_WHEEL

MODEL_PATH = "hand_landmarker.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"

def ensure_model_exists():
    if not os.path.exists(MODEL_PATH):
        print(f"[+] Downloading MediaPipe Hand Landmarker model file ({MODEL_PATH})...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print("[OK] Model downloaded successfully.")

class OneEuroFilter:
    """1 Euro Filter: Zero-lag adaptive low-pass filter for high-speed tracking."""
    def __init__(self, min_cutoff=1.2, beta=0.08, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = None

    def alpha(self, cutoff, dt):
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def filter(self, x, t):
        if self.t_prev is None:
            self.x_prev = x
            self.dx_prev = 0.0
            self.t_prev = t
            return x

        dt = max(t - self.t_prev, 0.0001)
        self.t_prev = t

        dx = (x - self.x_prev) / dt
        dx_hat = self.dx_prev + self.alpha(self.d_cutoff, dt) * (dx - self.dx_prev)

        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        x_hat = self.x_prev + self.alpha(cutoff, dt) * (x - self.x_prev)

        self.x_prev = x_hat
        self.dx_prev = dx_hat
        return x_hat

class KeyButton:
    def __init__(self, pos, text, size=(45, 45)):
        self.pos = pos
        self.size = size
        self.text = text

class VirtualKeyboard:
    def __init__(self):
        self.keys = []
        self.layout = [
            ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
            ["A", "S", "D", "F", "G", "H", "J", "K", "L"],
            ["Z", "X", "C", "V", "B", "N", "M"]
        ]
        self.create_layout()

    def create_layout(self):
        start_x = 25
        start_y = 210

        for row_idx, row in enumerate(self.layout):
            row_start_x = start_x + (row_idx * 15)
            for col_idx, char in enumerate(row):
                x = row_start_x + col_idx * 50
                y = start_y + row_idx * 52
                self.keys.append(KeyButton((x, y), char, (44, 46)))

        y_bot = start_y + 3 * 52
        self.keys.append(KeyButton((start_x, y_bot), "BACK", (100, 46)))
        self.keys.append(KeyButton((start_x + 110, y_bot), "SPACE", (210, 46)))
        self.keys.append(KeyButton((start_x + 330, y_bot), "ENTER", (100, 46)))

    def draw(self, frame, hovered_key=None, active_key=None, dwell_ratio=0.0):
        cv2.rectangle(frame, (10, 195), (630, 430), (15, 20, 32), cv2.FILLED)
        cv2.rectangle(frame, (10, 195), (630, 430), (0, 242, 254), 1)

        cv2.putText(frame, "AIR VIRTUAL KEYBOARD [Press K to Toggle]", (20, 208),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 242, 254), 1)

        for key in self.keys:
            x, y = key.pos
            w, h = key.size

            bg_color = (35, 45, 65)
            border_color = (80, 95, 120)
            text_color = (240, 240, 240)

            if active_key == key.text:
                bg_color = (0, 230, 118)
                border_color = (255, 255, 255)
                text_color = (0, 0, 0)
            elif hovered_key == key.text:
                bg_color = (0, 180, 220)
                border_color = (0, 242, 254)
                text_color = (255, 255, 255)

            cv2.rectangle(frame, (x, y), (x + w, y + h), bg_color, cv2.FILLED)
            cv2.rectangle(frame, (x, y), (x + w, y + h), border_color, 2)

            font_scale = 0.5 if len(key.text) == 1 else 0.4
            text_size = cv2.getTextSize(key.text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2)[0]
            text_x = x + (w - text_size[0]) // 2
            text_y = y + (h + text_size[1]) // 2
            cv2.putText(frame, key.text, (text_x, text_y),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, text_color, 2)

            if hovered_key == key.text and dwell_ratio > 0.0:
                fill_w = int(w * min(1.0, dwell_ratio))
                cv2.rectangle(frame, (x, y + h - 5), (x + fill_w, y + h), (0, 255, 0), cv2.FILLED)

class VirtualCursor:
    def __init__(self):
        ensure_model_exists()

        self.screen_w = user32.GetSystemMetrics(0)
        self.screen_h = user32.GetSystemMetrics(1)

        self.cam_w = 640
        self.cam_h = 480
        
        self.margin_x = 90
        self.margin_y = 65

        # 1 Euro Filters for zero-lag smooth X and Y cursor motion
        self.filter_x = OneEuroFilter(min_cutoff=1.5, beta=0.1)
        self.filter_y = OneEuroFilter(min_cutoff=1.5, beta=0.1)

        # MediaPipe HandLandmarker Detector
        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            num_hands=1,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.detector = vision.HandLandmarker.create_from_options(options)

        self.keyboard = VirtualKeyboard()
        self.show_keyboard = False
        self.hover_key = None
        self.hover_start_time = 0
        self.dwell_time_required = 0.3  # 300ms dwell time
        self.active_key_flash = None
        self.flash_start_time = 0

        self.control_enabled = True
        self.is_dragging = False
        self.last_click_time = 0
        self.click_cooldown = 0.3  # seconds

        self.pinch_click_ratio = 0.28
        self.pinch_release_ratio = 0.38
        self.pinch_right_ratio = 0.28

    def init_camera(self):
        print("[+] Initializing zero-latency webcam feed...")
        backends = [cv2.CAP_DSHOW, cv2.CAP_ANY]
        indices = [0, 1, 2]

        for backend in backends:
            for idx in indices:
                cap = cv2.VideoCapture(idx, backend)
                if cap.isOpened():
                    # Set buffer size to 1 to eliminate camera frame queue lag!
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cam_w)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cam_h)
                    cap.set(cv2.CAP_PROP_FPS, 60)
                    success, test_frame = cap.read()
                    if success and test_frame is not None:
                        print(f"[OK] High-Speed Webcam connected (Index: {idx})")
                        return cap
                    cap.release()

        print("[!] ERROR: No accessible webcam found!")
        return None

    def get_distance(self, pt1, pt2):
        return math.hypot(pt1[0] - pt2[0], pt1[1] - pt2[1])

    def map_coords(self, x, y):
        min_x = self.margin_x
        max_x = self.cam_w - self.margin_x
        min_y = self.margin_y
        max_y = self.cam_h - self.margin_y

        norm_x = (x - min_x) / (max_x - min_x) if max_x > min_x else 0.5
        norm_y = (y - min_y) / (max_y - min_y) if max_y > min_y else 0.5

        norm_x = max(0.0, min(1.0, norm_x))
        norm_y = max(0.0, min(1.0, norm_y))

        screen_x = norm_x * self.screen_w
        screen_y = norm_y * self.screen_h

        return screen_x, screen_y

    def draw_hand_skeleton(self, frame, landmarks_px):
        connections = [
            (0, 1), (1, 2), (2, 3), (3, 4),
            (0, 5), (5, 6), (6, 7), (7, 8),
            (5, 9), (9, 10), (10, 11), (11, 12),
            (9, 13), (13, 14), (14, 15), (15, 16),
            (13, 17), (0, 17), (17, 18), (18, 19), (19, 20)
        ]

        for p1, p2 in connections:
            cv2.line(frame, landmarks_px[p1], landmarks_px[p2], (0, 242, 254), 2)

        for idx, (x, y) in enumerate(landmarks_px):
            color = (255, 0, 128) if idx in [4, 8, 12] else (124, 77, 255)
            cv2.circle(frame, (x, y), 4, color, cv2.FILLED)

    def trigger_key_press(self, key_text):
        self.active_key_flash = key_text
        self.flash_start_time = time.time()

        # Direct win32 keypress
        if key_text == "SPACE":
            user32.keybd_event(0x20, 0, 0, 0)
            user32.keybd_event(0x20, 0, 2, 0)
        elif key_text == "BACK":
            user32.keybd_event(0x08, 0, 0, 0)
            user32.keybd_event(0x08, 0, 2, 0)
        elif key_text == "ENTER":
            user32.keybd_event(0x0D, 0, 0, 0)
            user32.keybd_event(0x0D, 0, 2, 0)
        else:
            vk_code = ord(key_text.upper())
            user32.keybd_event(vk_code, 0, 0, 0)
            user32.keybd_event(vk_code, 0, 2, 0)

    def run(self):
        cap = self.init_camera()
        if cap is None:
            input("Press Enter to exit...")
            return

        p_time = time.time()

        print("\n" + "=" * 62)
        print("    ULTRA-SMOOTH ZERO-LAG VIRTUAL CURSOR (1 EURO FILTER)")
        print("=" * 62)

        while cap.isOpened():
            # Grab latest frame buffer to eliminate lag
            cap.grab()
            success, frame = cap.retrieve()

            if not success or frame is None:
                time.sleep(0.005)
                continue

            frame = cv2.flip(frame, 1)
            h, w, _ = frame.shape
            current_time = time.time()

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

            result = self.detector.detect(mp_image)

            cv2.rectangle(
                frame,
                (self.margin_x, self.margin_y),
                (w - self.margin_x, h - self.margin_y),
                (255, 0, 128), 2
            )
            cv2.putText(
                frame, "Active Tracking Box",
                (self.margin_x + 5, self.margin_y - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 0, 128), 1
            )

            status_str = "Status: Searching for hand..."
            status_color = (180, 180, 180)

            if self.active_key_flash and current_time - self.flash_start_time > 0.18:
                self.active_key_flash = None

            hovered_key_obj = None
            dwell_ratio = 0.0

            if result.hand_landmarks:
                hand_landmarks = result.hand_landmarks[0]
                landmarks_px = [(int(lm.x * w), int(lm.y * h)) for lm in hand_landmarks]

                self.draw_hand_skeleton(frame, landmarks_px)

                wrist = landmarks_px[0]
                thumb_tip = landmarks_px[4]
                index_mcp = landmarks_px[5]
                index_tip = landmarks_px[8]
                middle_tip = landmarks_px[12]

                hand_scale = self.get_distance(wrist, index_mcp)
                if hand_scale < 1.0:
                    hand_scale = 1.0

                d_index_thumb = self.get_distance(index_tip, thumb_tip)
                d_middle_thumb = self.get_distance(middle_tip, thumb_tip)
                d_index_middle = self.get_distance(index_tip, middle_tip)

                ratio_index_thumb = d_index_thumb / hand_scale
                ratio_middle_thumb = d_middle_thumb / hand_scale
                ratio_index_middle = d_index_middle / hand_scale

                raw_screen_x, raw_screen_y = self.map_coords(index_tip[0], index_tip[1])

                # Apply 1 Euro Filter for zero-lag smooth mouse tracking
                smooth_screen_x = self.filter_x.filter(raw_screen_x, current_time)
                smooth_screen_y = self.filter_y.filter(raw_screen_y, current_time)

                if self.show_keyboard:
                    ix, iy = index_tip[0], index_tip[1]
                    for key in self.keyboard.keys:
                        kx, ky = key.pos
                        kw, kh = key.size
                        if kx <= ix <= kx + kw and ky <= iy <= ky + kh:
                            hovered_key_obj = key
                            break

                    if hovered_key_obj:
                        if self.hover_key != hovered_key_obj.text:
                            self.hover_key = hovered_key_obj.text
                            self.hover_start_time = current_time
                        else:
                            dwell_duration = current_time - self.hover_start_time
                            dwell_ratio = dwell_duration / self.dwell_time_required

                            if dwell_duration >= self.dwell_time_required:
                                self.trigger_key_press(hovered_key_obj.text)
                                self.hover_start_time = current_time + 0.25

                        if ratio_index_thumb < self.pinch_click_ratio:
                            if current_time - self.last_click_time > self.click_cooldown:
                                self.trigger_key_press(hovered_key_obj.text)
                                self.last_click_time = current_time

                        status_str = f"Air Keyboard: Hover '{hovered_key_obj.text}'"
                        status_color = (0, 242, 254)
                    else:
                        self.hover_key = None
                        self.hover_start_time = 0

                if self.control_enabled and not hovered_key_obj:
                    index_up = hand_landmarks[8].y < hand_landmarks[6].y
                    middle_up = hand_landmarks[12].y < hand_landmarks[10].y
                    ring_down = hand_landmarks[16].y > hand_landmarks[14].y

                    if index_up and middle_up and ring_down and ratio_index_middle < 0.45:
                        status_str = "Gesture: SCROLLING"
                        status_color = (255, 255, 0)
                        scroll_val = int((self.filter_y.x_prev - raw_screen_y) / 4.0)
                        if abs(scroll_val) > 0:
                            mouse_scroll(scroll_val * 40)

                        cv2.line(frame, index_tip, middle_tip, (255, 255, 0), 3)

                    elif ratio_index_thumb < self.pinch_click_ratio or (self.is_dragging and ratio_index_thumb < self.pinch_release_ratio):
                        if not self.is_dragging:
                            self.is_dragging = True
                            mouse_left_down()
                            status_str = "Gesture: LEFT CLICK / DRAG HOLD"
                            status_color = (0, 255, 0)
                        else:
                            set_mouse_pos(smooth_screen_x, smooth_screen_y)
                            status_str = "Gesture: DRAGGING MOUSE"
                            status_color = (0, 255, 0)

                        cv2.line(frame, index_tip, thumb_tip, (0, 255, 0), 4)
                        cv2.circle(frame, index_tip, 14, (0, 255, 0), cv2.FILLED)

                    elif ratio_middle_thumb < self.pinch_right_ratio:
                        if self.is_dragging:
                            mouse_left_up()
                            self.is_dragging = False

                        if current_time - self.last_click_time > self.click_cooldown:
                            mouse_right_click()
                            self.last_click_time = current_time

                        status_str = "Gesture: RIGHT CLICK"
                        status_color = (0, 165, 255)
                        cv2.line(frame, middle_tip, thumb_tip, (0, 165, 255), 4)

                    else:
                        if self.is_dragging:
                            mouse_left_up()
                            self.is_dragging = False

                        # Instant Ctypes mouse movement (zero-latency SetCursorPos)
                        set_mouse_pos(smooth_screen_x, smooth_screen_y)
                        status_str = "Gesture: MOVING CURSOR (ZERO LAG)"
                        status_color = (255, 0, 255)

                        cv2.circle(frame, index_tip, 8, (255, 0, 255), cv2.FILLED)
                        cv2.circle(frame, index_tip, 16, (255, 0, 255), 2)

            else:
                if self.is_dragging:
                    mouse_left_up()
                    self.is_dragging = False

            if self.show_keyboard:
                self.keyboard.draw(
                    frame,
                    hovered_key=self.hover_key,
                    active_key=self.active_key_flash,
                    dwell_ratio=dwell_ratio
                )

            fps = 1.0 / (current_time - p_time) if (current_time - p_time) > 0 else 0
            p_time = current_time

            cv2.rectangle(frame, (10, 10), (360, 95), (0, 0, 0), cv2.FILLED)
            cv2.rectangle(frame, (10, 10), (360, 95), (80, 80, 80), 1)

            cv2.putText(frame, f"FPS: {int(fps)}", (20, 32),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)

            ctrl_status = "ACTIVE [S]" if self.control_enabled else "PAUSED [S]"
            ctrl_color = (0, 255, 0) if self.control_enabled else (0, 0, 255)
            cv2.putText(frame, f"Control: {ctrl_status}", (130, 32),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, ctrl_color, 2)

            kbd_status = "ON [K]" if self.show_keyboard else "OFF [K]"
            kbd_color = (0, 242, 254) if self.show_keyboard else (150, 150, 150)
            cv2.putText(frame, f"Keyboard: {kbd_status}", (265, 32),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, kbd_color, 1)

            cv2.putText(frame, status_str, (20, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, status_color, 2)

            cv2.putText(frame, "Press 'K' Keyboard | 'S' Toggle | 'Q' Quit", (20, 84),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 180, 180), 1)

            cv2.imshow("AI Virtual Cursor - Index Finger", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == ord('Q') or key == 27:
                break
            elif key == ord('s') or key == ord('S'):
                self.control_enabled = not self.control_enabled
                if not self.control_enabled and self.is_dragging:
                    mouse_left_up()
                    self.is_dragging = False
            elif key == ord('k') or key == ord('K'):
                self.show_keyboard = not self.show_keyboard

        cap.release()
        cv2.destroyAllWindows()
        print("[+] Virtual Cursor exited cleanly.")

if __name__ == "__main__":
    app = VirtualCursor()
    app.run()
