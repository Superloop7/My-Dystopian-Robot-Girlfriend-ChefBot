import mss
import numpy as np
import cv2 as cv
import keyboard
import time
import os
import sys
import ctypes
import sys
import tkinter as tk
from tkinter import ttk
import threading

"""
    ChefBot - My Dystopian Robot Girlfriend auto-chef
    
    short press: carrot -> Z, eggplant -> X
    hold press:  carrot+bar -> hold Z, eggplant+bar -> hold X
    hold release: bar color disappears -> release
    
    coordinates are screen-specific and must be measured on real hardware.
    only verified resolution: 2560x1600
"""

# === DPI awareness: MUST be before tkinter import ===
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # fallback
        except Exception:
            pass

# support pyinstaller bundled mode
if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TEMPLATE_DIR = os.path.join(BASE_DIR, "assets")

# template paths
TEMPLATES = {
    "carrot": os.path.join(TEMPLATE_DIR, "carrot.png"),
    "eggplant": os.path.join(TEMPLATE_DIR, "eggplant.png"),
}

# verified resolution profiles (only add after real hardware testing)
# template_scale: scale factor relative to 2560 width templates
RESOLUTION_PROFILES = {
    "2560x1600": {
        "judge_box": (371, 1206, 483, 1318),
        "bar_extend_box": (485, 1230, 520, 1295),
        "template_scale": 1.0,
    },
    # add more resolutions here after real testing:
    "2560x1440": {
        "judge_box": (370, 1126, 482, 1238),
        "bar_extend_box": (484, 1150, 519, 1215),
        "template_scale": 1.0,
    },
    "1920x1200": {
        "judge_box": (280, 905, 364, 989),
        "bar_extend_box": (366, 923, 392, 971),
        "template_scale": 0.75,
    },
    "1920x1080": {
        "judge_box": (278, 845, 362, 929),
        "bar_extend_box": (364, 863, 390, 911),
        "template_scale": 0.75,
    },
}

# match threshold
MATCH_TH = 0.75

# bar color detection (RGB values)
BLUE_UNCHANGED_RGB = (27, 132, 242)
BLUE_CHANGED_RGB = (0, 204, 255)
GREEN_UNCHANGED_RGB = (0, 145, 68)
GREEN_CHANGED_RGB = (59, 179, 113)


def convert_to_coord(box) -> dict:
    x1, y1, x2, y2 = box
    return {"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1}


def load_templates(scale=1.0):
    """load all template images as BGR, optionally scale"""
    templates = {}
    for name, path in TEMPLATES.items():
        img = cv.imread(path, cv.IMREAD_COLOR)
        if img is None:
            raise FileNotFoundError(f"failed to load template: {path}")
        if scale != 1.0:
            new_w = int(img.shape[1] * scale)
            new_h = int(img.shape[0] * scale)
            img = cv.resize(img, (new_w, new_h), interpolation=cv.INTER_AREA)
        templates[name] = img
    return templates


def match_template(region_bgr, template_bgr):
    rh, rw = region_bgr.shape[:2]
    th, tw = template_bgr.shape[:2]
    if th > rh or tw > rw:
        return 0.0
    result = cv.matchTemplate(region_bgr, template_bgr, cv.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv.minMaxLoc(result)
    return max_val


def match_rgb_ratio(img_bgr, target_rgb, tol=15):
    tr, tg, tb = target_rgb
    target_bgr = np.array([tb, tg, tr], dtype=np.int16)
    arr = img_bgr.astype(np.int16)
    diff = np.abs(arr - target_bgr)
    ok = np.all(diff <= tol, axis=2)
    return ok.mean()


def detect_bar_color_rgb(region_bgr):
    blue_r1 = match_rgb_ratio(region_bgr, BLUE_UNCHANGED_RGB, tol=20)
    blue_r2 = match_rgb_ratio(region_bgr, BLUE_CHANGED_RGB, tol=20)
    blue_total = max(blue_r1, blue_r2)

    green_r1 = match_rgb_ratio(region_bgr, GREEN_UNCHANGED_RGB, tol=20)
    green_r2 = match_rgb_ratio(region_bgr, GREEN_CHANGED_RGB, tol=20)
    green_total = max(green_r1, green_r2)

    BAR_COLOR_TH = 0.25
    if blue_total >= BAR_COLOR_TH or green_total >= BAR_COLOR_TH:
        if blue_total > green_total:
            return "BLUE"
        else:
            return "GREEN"
    return "NONE"


def detect_screen_resolution():
    """auto detect current screen resolution"""
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        w = monitor["width"]
        h = monitor["height"]
        return f"{w}x{h}"


class ChefBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ChefBot")
        self.root.geometry("540x460")
        self.root.resizable(False, False)

        self.running = False
        self.templates = None
        self.fps_text = tk.StringVar(value="FPS: --")

        # title
        tk.Label(root, text="ChefBot", font=("微软雅黑", 20, "bold")).pack(pady=(15, 5))

        # status label
        self.status_label = tk.Label(
            root, text="○ 准备就绪", font=("微软雅黑", 20), fg="black"
        )
        self.status_label.pack(pady=5)

        # fps label
        tk.Label(
            root, textvariable=self.fps_text, font=("微软雅黑", 20), fg="gray"
        ).pack()

        # resolution selector
        res_frame = tk.Frame(root)
        res_frame.pack(pady=8)
        tk.Label(res_frame, text="分辨率:", font=("微软雅黑", 18)).pack(side=tk.LEFT)

        self.res_var = tk.StringVar()
        self.res_combo = ttk.Combobox(
            res_frame,
            textvariable=self.res_var,
            values=list(RESOLUTION_PROFILES.keys()),
            state="readonly",
            width=16,
        )
        self.res_combo.pack(side=tk.LEFT, padx=10)

        # auto detect resolution
        detected = detect_screen_resolution()
        if detected in RESOLUTION_PROFILES:
            self.res_var.set(detected)
        elif RESOLUTION_PROFILES:
            self.res_var.set(list(RESOLUTION_PROFILES.keys())[0])

        # start/stop button
        self.btn = tk.Button(
            root,
            text="开始脚本 (F10)",
            command=self.toggle_bot,
            width=14,
            height=2,
            bg="lightgray",
            font=("微软雅黑", 16),
        )
        self.btn.pack(pady=10)

        # hotkey hint
        tk.Label(
            root, text="开始: F10  |  停止: F11", fg="gray", font=("微软雅黑", 16)
        ).pack()

        # hotkey listener thread
        threading.Thread(target=self._hotkey_listener, daemon=True).start()

    def _hotkey_listener(self):
        while True:
            if keyboard.is_pressed("F10") and not self.running:
                self.root.after(0, self._start_bot)
                while keyboard.is_pressed("F10"):
                    time.sleep(0.01)

            if keyboard.is_pressed("F11") and self.running:
                self.root.after(0, self._stop_bot)
                while keyboard.is_pressed("F11"):
                    time.sleep(0.01)

            time.sleep(0.05)

    def toggle_bot(self):
        if not self.running:
            self._start_bot()
        else:
            self._stop_bot()

    def _start_bot(self):
        if self.running:
            return

        # get selected resolution profile
        res_key = self.res_var.get()
        if res_key not in RESOLUTION_PROFILES:
            self.status_label.config(text="✗ 不支持当前分辨率", fg="red")
            return

        self.profile = RESOLUTION_PROFILES[res_key]

        # load templates with correct scale
        try:
            self.templates = load_templates(self.profile["template_scale"])
        except FileNotFoundError as e:
            self.status_label.config(text=f"✗ {e}", fg="red")
            return

        self.running = True
        self.status_label.config(text="● 正在切菜中...", fg="green")
        self.btn.config(text="停止脚本 (F11)", bg="#cc3333", fg="white")
        self.res_combo.config(state="disabled")

        threading.Thread(target=self._bot_worker, daemon=True).start()

    def _stop_bot(self):
        self.running = False
        self.status_label.config(text="○ 脚本已停止", fg="black")
        self.btn.config(text="开始脚本 (F10)", bg="lightgray", fg="black")
        self.fps_text.set("FPS: --")
        self.res_combo.config(state="readonly")

        keyboard.release("z")
        keyboard.release("x")

    def _bot_worker(self):
        frame_interval = 1.0 / 120
        next_tick = time.perf_counter()

        fps_count = 0
        fps_timer = time.perf_counter()

        judge_coord = convert_to_coord(self.profile["judge_box"])
        extend_coord = convert_to_coord(self.profile["bar_extend_box"])

        hold_z_press = False
        hold_x_press = False
        prev_carrot_hit = False
        prev_eggplant_hit = False

        with mss.mss() as sct:
            while self.running:
                # capture
                judge_img = np.array(sct.grab(judge_coord))
                extend_img = np.array(sct.grab(extend_coord))

                # convert BGRA -> BGR
                judge_bgr = cv.cvtColor(judge_img, cv.COLOR_BGRA2BGR)
                extend_bgr = cv.cvtColor(extend_img, cv.COLOR_BGRA2BGR)

                # template matching
                carrot_score = match_template(judge_bgr, self.templates["carrot"])
                eggplant_score = match_template(judge_bgr, self.templates["eggplant"])

                # detect bar color
                bar_color = detect_bar_color_rgb(extend_bgr)

                carrot_hit = carrot_score >= MATCH_TH
                eggplant_hit = eggplant_score >= MATCH_TH

                # === carrot (Z): press logic ===
                if carrot_hit and not prev_carrot_hit:
                    if bar_color == "BLUE":
                        if not hold_z_press:
                            keyboard.press("z")
                            hold_z_press = True
                    else:
                        if not hold_z_press:
                            keyboard.press_and_release("z")

                # === carrot (Z): release logic ===
                if hold_z_press and bar_color != "BLUE":
                    keyboard.release("z")
                    hold_z_press = False

                # === eggplant (X): press logic ===
                if eggplant_hit and not prev_eggplant_hit:
                    if bar_color == "GREEN":
                        if not hold_x_press:
                            keyboard.press("x")
                            hold_x_press = True
                    else:
                        if not hold_x_press:
                            keyboard.press_and_release("x")

                # === eggplant (X): release logic ===
                if hold_x_press and bar_color != "GREEN":
                    keyboard.release("x")
                    hold_x_press = False

                # update edge trigger
                prev_carrot_hit = carrot_hit
                prev_eggplant_hit = eggplant_hit

                # fps calculate
                fps_count += 1
                now = time.perf_counter()
                if now - fps_timer >= 1.0:
                    real_fps = fps_count / (now - fps_timer)
                    self.fps_text.set(f"FPS: {real_fps:.0f}")
                    fps_count = 0
                    fps_timer = now

                # scheduling
                next_tick += frame_interval
                sleep_time = next_tick - time.perf_counter()
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    next_tick = time.perf_counter()

        # cleanup
        if hold_z_press:
            keyboard.release("z")
        if hold_x_press:
            keyboard.release("x")


if __name__ == "__main__":
    root = tk.Tk()
    app = ChefBotGUI(root)
    root.mainloop()
