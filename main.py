import sys
import ctypes

# DPI awareness must be set before importing dxcam
# dxcam reads screen size on import, so DPI must be configured first
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # fallback
        except Exception:
            pass

import dxcam
import numpy as np
import cv2 as cv
import keyboard
import time
import os

if sys.platform == "win32":
    import winsound
import tkinter as tk
from tkinter import ttk
import threading

"""
    ChefBot v0.2.0 - My Dystopian Robot Girlfriend auto-chef

    short press: carrot -> Z, eggplant -> X
    hold press:  carrot+bar -> hold Z, eggplant+bar -> hold X
    hold release: bar color disappears -> release

    Uses dxcam (DXGI Desktop Duplication) for fast screen capture,
    merged region grabbing, and optimized bar color detection.
"""

# support pyinstaller bundled mode
if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TEMPLATE_DIR = os.path.join(BASE_DIR, "assets")

TEMPLATES = {
    "carrot": os.path.join(TEMPLATE_DIR, "carrot.png"),
    "eggplant": os.path.join(TEMPLATE_DIR, "eggplant.png"),
}

# resolution profiles: coordinates are physical pixels
# template_scale: scale factor relative to 2560-width templates
RESOLUTION_PROFILES = {
    "2560x1600": {
        "judge_box": (371, 1206, 483, 1318),
        "bar_extend_box": (485, 1230, 520, 1295),
        "template_scale": 1.0,
    },
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

# template match threshold
MATCH_TH = 0.65

# downsample ratio: both template and judge region are scaled by this
DOWNSAMPLE_RATIO = 1.0

# bar color detection constants (RGB)
BLUE_UNCHANGED_RGB = (27, 132, 242)
BLUE_CHANGED_RGB = (0, 204, 255)
GREEN_UNCHANGED_RGB = (0, 145, 68)
GREEN_CHANGED_RGB = (59, 179, 113)
BAR_COLOR_TH = 0.25
BAR_SAMPLE_RADIUS = 5


def load_templates_rgb(scale=1.0):
    """Load template images as RGB with resolution scaling and downsampling."""
    templates = {}
    for name, path in TEMPLATES.items():
        img = cv.imread(path, cv.IMREAD_COLOR)
        if img is None:
            raise FileNotFoundError(f"failed to load template: {path}")
        img = cv.cvtColor(img, cv.COLOR_BGR2RGB)
        # apply both resolution scale and downsample in one resize
        combined = scale * DOWNSAMPLE_RATIO
        if combined != 1.0:
            new_w = max(1, int(img.shape[1] * combined))
            new_h = max(1, int(img.shape[0] * combined))
            img = cv.resize(img, (new_w, new_h), interpolation=cv.INTER_AREA)
        templates[name] = img
    return templates


def match_template(region_rgb, template_rgb):
    """Run template matching, return max correlation score."""
    rh, rw = region_rgb.shape[:2]
    th, tw = template_rgb.shape[:2]
    if th > rh or tw > rw:
        return 0.0
    result = cv.matchTemplate(region_rgb, template_rgb, cv.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv.minMaxLoc(result)
    return max_val


def detect_bar_color_fast(region_rgb, tol=25):
    """Detect bar color by sampling center pixels only."""
    h, w = region_rgb.shape[:2]
    cy, cx = h // 2, w // 2
    r = BAR_SAMPLE_RADIUS
    sample = region_rgb[
        max(0, cy - r) : min(h, cy + r + 1), max(0, cx - r) : min(w, cx + r + 1)
    ]
    arr = sample.astype(np.int16)

    def check_color(target_rgb):
        target = np.array(target_rgb, dtype=np.int16)
        diff = np.abs(arr - target)
        return np.all(diff <= tol, axis=2).mean()

    blue_best = max(check_color(BLUE_UNCHANGED_RGB), check_color(BLUE_CHANGED_RGB))
    green_best = max(check_color(GREEN_UNCHANGED_RGB), check_color(GREEN_CHANGED_RGB))

    if blue_best >= BAR_COLOR_TH or green_best >= BAR_COLOR_TH:
        return "BLUE" if blue_best > green_best else "GREEN"
    return "NONE"


def compute_merged_region(judge_box, bar_box):
    """Compute bounding box that covers both regions for a single grab."""
    jx1, jy1, jx2, jy2 = judge_box
    bx1, by1, bx2, by2 = bar_box

    mx1 = min(jx1, bx1)
    my1 = min(jy1, by1)
    mx2 = max(jx2, bx2)
    my2 = max(jy2, by2)

    merged = (mx1, my1, mx2, my2)
    judge_slice = (jy1 - my1, jy2 - my1, jx1 - mx1, jx2 - mx1)
    bar_slice = (by1 - my1, by2 - my1, bx1 - mx1, bx2 - mx1)

    return merged, judge_slice, bar_slice


def detect_screen_resolution():
    """Auto-detect screen resolution via dxcam."""
    camera = dxcam.create()
    w = camera.width
    h = camera.height
    del camera
    return f"{w}x{h}"


def play_sound_async(sound_type):
    """Play a rising (start) or falling (stop) tone in a background thread."""
    if sys.platform != "win32":
        return

    def _play():
        if sound_type == "start":
            winsound.Beep(300, 150)
            winsound.Beep(500, 150)
        else:
            winsound.Beep(500, 150)
            winsound.Beep(300, 150)

    threading.Thread(target=_play, daemon=True).start()


class ChefBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ChefBot v0.2.0")
        self.root.geometry("540x460")
        self.root.resizable(False, False)

        self.running = False
        self.templates = None
        self.fps_text = tk.StringVar(value="FPS: --")

        tk.Label(root, text="ChefBot v0.2.0", font=("微软雅黑", 20, "bold")).pack(
            pady=(15, 5)
        )

        self.status_label = tk.Label(
            root, text="准备就绪", font=("微软雅黑", 20), fg="black"
        )
        self.status_label.pack(pady=5)

        tk.Label(
            root, textvariable=self.fps_text, font=("微软雅黑", 20), fg="gray"
        ).pack()

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

        detected = detect_screen_resolution()
        if detected in RESOLUTION_PROFILES:
            self.res_var.set(detected)
        elif RESOLUTION_PROFILES:
            self.res_var.set(list(RESOLUTION_PROFILES.keys())[0])

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

        tk.Label(
            root, text="开始: F10  |  停止: F11", fg="gray", font=("微软雅黑", 16)
        ).pack()

        threading.Thread(target=self._hotkey_listener, daemon=True).start()

    def _hotkey_listener(self):
        """Poll F10/F11 hotkeys in background thread."""
        while True:
            if keyboard.is_pressed("F10") and not self.running:
                self.root.after(0, self._start_bot)
                while keyboard.is_pressed("F10"):
                    time.sleep(0.01)
            if keyboard.is_pressed("F11") and self.running:
                self.root.after(0, self._stop_bot)
                while keyboard.is_pressed("F11"):
                    time.sleep(0.01)
            time.sleep(0.01)

    def toggle_bot(self):
        if not self.running:
            self._start_bot()
        else:
            self._stop_bot()

    def _start_bot(self):
        if self.running:
            return

        res_key = self.res_var.get()
        if res_key not in RESOLUTION_PROFILES:
            self.status_label.config(text="不支持当前分辨率", fg="red")
            return

        self.profile = RESOLUTION_PROFILES[res_key]

        try:
            self.templates = load_templates_rgb(self.profile["template_scale"])
        except FileNotFoundError as e:
            self.status_label.config(text=f"x {e}", fg="red")
            return

        self.running = True
        self.status_label.config(text="正在切菜中...", fg="green")
        self.btn.config(text="停止脚本 (F11)", bg="#cc3333", fg="white")
        self.res_combo.config(state="disabled")
        play_sound_async("start")

        threading.Thread(target=self._bot_worker, daemon=True).start()

    def _stop_bot(self):
        self.running = False
        self.status_label.config(text="脚本已停止", fg="black")
        self.btn.config(text="开始脚本 (F10)", bg="lightgray", fg="black")
        self.fps_text.set("FPS: --")
        self.res_combo.config(state="readonly")
        play_sound_async("stop")

        keyboard.release("z")
        keyboard.release("x")

    def _bot_worker(self):
        """Core detection loop using dxcam and merged region capture."""
        judge_box = self.profile["judge_box"]
        bar_box = self.profile["bar_extend_box"]

        # pre-compute merged capture region and sub-region slices
        merged_region, judge_slice, bar_slice = compute_merged_region(
            judge_box, bar_box
        )
        jr1, jr2, jc1, jc2 = judge_slice
        br1, br2, bc1, bc2 = bar_slice

        # pre-compute downsample target size for judge region
        judge_h = jr2 - jr1
        judge_w = jc2 - jc1
        small_h = max(1, int(judge_h * DOWNSAMPLE_RATIO))
        small_w = max(1, int(judge_w * DOWNSAMPLE_RATIO))

        hold_z_press = False
        hold_x_press = False
        prev_carrot_hit = False
        prev_eggplant_hit = False

        fps_count = 0
        fps_timer = time.perf_counter()

        camera = dxcam.create()

        # warm up: discard first few frames to let dxcam initialize the DXGI pipeline
        for _ in range(10):
            camera.grab(region=merged_region)
            time.sleep(0.01)

        try:
            while self.running:
                # single grab covering both judge and bar regions
                frame = camera.grab(region=merged_region)
                if frame is None:
                    continue

                # slice sub-regions from merged frame (zero-copy)
                judge_rgb = frame[jr1:jr2, jc1:jc2]
                bar_rgb = frame[br1:br2, bc1:bc2]

                # downsample judge region before matching
                if DOWNSAMPLE_RATIO < 1.0:
                    judge_rgb = cv.resize(
                        judge_rgb, (small_w, small_h), interpolation=cv.INTER_AREA
                    )

                # template matching
                carrot_score = match_template(judge_rgb, self.templates["carrot"])
                eggplant_score = match_template(judge_rgb, self.templates["eggplant"])

                carrot_hit = carrot_score >= MATCH_TH
                eggplant_hit = eggplant_score >= MATCH_TH

                # bar color detection (center sampling)
                bar_color = detect_bar_color_fast(bar_rgb)

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

                # fps counter
                fps_count += 1
                now = time.perf_counter()
                if now - fps_timer >= 1.0:
                    real_fps = fps_count / (now - fps_timer)
                    self.fps_text.set(f"FPS: {real_fps:.0f}")
                    fps_count = 0
                    fps_timer = now

        finally:
            if hold_z_press:
                keyboard.release("z")
            if hold_x_press:
                keyboard.release("x")
            del camera


if __name__ == "__main__":
    root = tk.Tk()
    app = ChefBotGUI(root)
    root.mainloop()
