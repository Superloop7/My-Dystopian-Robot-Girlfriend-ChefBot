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
    ChefBot v0.3.0 - My Dystopian Robot Girlfriend auto-chef

    short press: carrot -> Z, eggplant -> X
    hold press:  carrot+bar -> hold Z, eggplant+bar -> hold X
    hold release: bar color disappears -> release

    Uses dxcam (DXGI Desktop Duplication) for fast screen capture,
    merged region grabbing, and optimized bar color detection.

    v0.3.0 adds adaptive resolution support:
    - automatically detects current screen resolution
    - scales capture boxes using the closest reference aspect ratio
    - computes template scale from the current screen width
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

# Reference profiles in physical pixels.
# These are used as the calibration source for adaptive scaling.
REFERENCE_PROFILES = {
    "2560x1600": {
        "judge_box": (371, 1206, 483, 1318),
        "bar_extend_box": (485, 1230, 520, 1295),
        "template_scale": 1.0,
        "verified": True,
    },
    "2560x1440": {
        "judge_box": (370, 1126, 482, 1238),
        "bar_extend_box": (484, 1150, 519, 1215),
        "template_scale": 1.0,
        "verified": False,
    },
    "1920x1200": {
        "judge_box": (280, 905, 364, 989),
        "bar_extend_box": (366, 923, 392, 971),
        "template_scale": 0.75,
        "verified": True,
    },
    "1920x1080": {
        "judge_box": (278, 845, 362, 929),
        "bar_extend_box": (364, 863, 390, 911),
        "template_scale": 0.75,
        "verified": True,
    },
}

# One high-width reference per aspect ratio.
# We prefer the 2560-width layouts because the template images were captured there.
ASPECT_REFERENCE_KEYS = {
    "16:10": "2560x1600",
    "16:9": "2560x1440",
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


def imread_unicode(path, flags=cv.IMREAD_COLOR):
    """
    Read an image from any filesystem path, including non-ASCII paths on Windows.

    OpenCV's cv.imread can fail on Unicode paths depending on build/runtime locale.
    Using np.fromfile + cv.imdecode avoids that limitation.
    """
    data = np.fromfile(path, dtype=np.uint8)
    if data.size == 0:
        return None
    return cv.imdecode(data, flags)


def load_templates_rgb(scale=1.0):
    """Load template images as RGB with resolution scaling and downsampling."""
    templates = {}
    for name, path in TEMPLATES.items():
        img = imread_unicode(path, cv.IMREAD_COLOR)
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


def parse_resolution(resolution_text):
    """Parse a resolution string like '1920x1080' into integers."""
    w_str, h_str = resolution_text.lower().split("x")
    return int(w_str), int(h_str)



def detect_screen_resolution():
    """Auto-detect screen resolution without creating a temporary dxcam object."""
    if sys.platform == "win32":
        try:
            user32 = ctypes.windll.user32
            w = user32.GetSystemMetrics(0)
            h = user32.GetSystemMetrics(1)
            if w > 0 and h > 0:
                return f"{w}x{h}"
        except Exception:
            pass

    camera = dxcam.create()
    w = camera.width
    h = camera.height
    del camera
    return f"{w}x{h}"



def aspect_ratio_key(width, height):
    """Choose the closest known aspect ratio profile for the current resolution."""
    current_ratio = width / height
    options = {}
    for name, ref_key in ASPECT_REFERENCE_KEYS.items():
        ref_w, ref_h = parse_resolution(ref_key)
        options[name] = abs(current_ratio - (ref_w / ref_h))
    return min(options, key=options.get)



def scale_box(box, sx, sy):
    """Scale a capture box by x/y factors and clamp to integer pixels."""
    x1, y1, x2, y2 = box
    scaled = (
        int(round(x1 * sx)),
        int(round(y1 * sy)),
        int(round(x2 * sx)),
        int(round(y2 * sy)),
    )

    # Ensure a positive box even on very small resolutions.
    nx1, ny1, nx2, ny2 = scaled
    nx2 = max(nx2, nx1 + 1)
    ny2 = max(ny2, ny1 + 1)
    return (nx1, ny1, nx2, ny2)



def build_adaptive_profile(width, height):
    """Create a runtime profile for any resolution from the closest reference layout."""
    aspect_key = aspect_ratio_key(width, height)
    ref_key = ASPECT_REFERENCE_KEYS[aspect_key]
    ref_w, ref_h = parse_resolution(ref_key)
    ref_profile = REFERENCE_PROFILES[ref_key]

    sx = width / ref_w
    sy = height / ref_h
    template_scale = width / ref_w

    return {
        "resolution": f"{width}x{height}",
        "aspect_key": aspect_key,
        "reference_key": ref_key,
        "judge_box": scale_box(ref_profile["judge_box"], sx, sy),
        "bar_extend_box": scale_box(ref_profile["bar_extend_box"], sx, sy),
        "template_scale": template_scale,
        "verified_reference": ref_profile.get("verified", False),
    }



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
        self.root.title("ChefBot v0.3.0")
        self.root.geometry("620x520")
        self.root.resizable(False, False)

        self.running = False
        self.templates = None
        self.profile = None
        self.camera = None
        self.worker_thread = None
        self.fps_text = tk.StringVar(value="FPS: --")
        self.res_var = tk.StringVar()
        self.aspect_var = tk.StringVar(value="参考布局: --")
        self.ref_var = tk.StringVar(value="参考分辨率: --")

        tk.Label(root, text="ChefBot v0.3.0", font=("微软雅黑", 20, "bold")).pack(
            pady=(15, 5)
        )

        self.status_label = tk.Label(
            root, text="准备就绪", font=("微软雅黑", 20), fg="black"
        )
        self.status_label.pack(pady=5)

        tk.Label(
            root, textvariable=self.fps_text, font=("微软雅黑", 20), fg="gray"
        ).pack()

        info_frame = tk.Frame(root)
        info_frame.pack(pady=10)

        tk.Label(info_frame, text="当前分辨率:", font=("微软雅黑", 18)).grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        tk.Label(info_frame, textvariable=self.res_var, font=("微软雅黑", 18)).grid(
            row=0, column=1, sticky="w"
        )

        tk.Label(info_frame, textvariable=self.aspect_var, font=("微软雅黑", 16), fg="gray").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        tk.Label(info_frame, textvariable=self.ref_var, font=("微软雅黑", 16), fg="gray").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(2, 0)
        )

        self.detected_resolution = detect_screen_resolution()
        self.res_var.set(self.detected_resolution)
        self._refresh_profile_info(self.detected_resolution)

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
            root,
            text="开始: F10  |  停止: F11",
            fg="gray",
            font=("微软雅黑", 16),
        ).pack()

        tk.Label(
            root,
            text="已启用全分辨率自适应。程序会按当前分辨率自动缩放识别区域",
            fg="gray",
            font=("微软雅黑", 14),
            wraplength=560,
            justify="center",
        ).pack(pady=(14, 0))

        tk.Label(
            root,
            text="提示：非常规纵横比（如 4:3、21:9）会自动套用最接近的参考布局，可靠性未知",
            fg="gray",
            font=("微软雅黑", 12),
            wraplength=560,
            justify="center",
        ).pack(pady=(8, 0))

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        threading.Thread(target=self._hotkey_listener, daemon=True).start()

    def _refresh_profile_info(self, resolution_text):
        width, height = parse_resolution(resolution_text)
        profile = build_adaptive_profile(width, height)
        self.aspect_var.set(f"参考布局: {profile['aspect_key']} 自适应")
        self.ref_var.set(f"参考分辨率: {profile['reference_key']}")

    def _on_close(self):
        self._stop_bot()
        if self.camera is not None:
            try:
                del self.camera
            except Exception:
                pass
            self.camera = None
        self.root.destroy()

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

        current_resolution = detect_screen_resolution()
        self.res_var.set(current_resolution)
        self._refresh_profile_info(current_resolution)

        width, height = parse_resolution(current_resolution)
        self.profile = build_adaptive_profile(width, height)

        try:
            self.templates = load_templates_rgb(self.profile["template_scale"])
        except FileNotFoundError as e:
            self.status_label.config(text=f"x {e}", fg="red")
            return

        if self.camera is None:
            try:
                self.camera = dxcam.create()
            except Exception as e:
                self.status_label.config(text=f"x dxcam 初始化失败: {e}", fg="red")
                return

        self.running = True
        self.status_label.config(text="正在切菜中...", fg="green")
        self.btn.config(text="停止脚本 (F11)", bg="#cc3333", fg="white")
        play_sound_async("start")

        self.worker_thread = threading.Thread(target=self._bot_worker, daemon=True)
        self.worker_thread.start()

    def _stop_bot(self):
        if not self.running:
            return

        self.running = False
        self.status_label.config(text="脚本已停止", fg="black")
        self.btn.config(text="开始脚本 (F10)", bg="lightgray", fg="black")
        self.fps_text.set("FPS: --")
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

        camera = self.camera
        if camera is None:
            self.root.after(0, lambda: self.status_label.config(text="x dxcam 未初始化", fg="red"))
            return

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


if __name__ == "__main__":
    root = tk.Tk()
    app = ChefBotGUI(root)
    root.mainloop()
