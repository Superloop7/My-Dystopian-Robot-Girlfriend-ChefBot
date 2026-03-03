import mss
import numpy as np
import cv2 as cv
import keyboard
import time
import os

"""
    判定框 (371, 1206, 483, 1318)
    屏幕分辨率 2560x1600
    
    short press: carrot -> Z, eggplant -> X
    hold press:  carrot+bar -> hold Z, eggplant+bar -> hold X
    hold release: bar color disappears -> release
    
    蓝色未变色:(27, 132, 242)  蓝色变色:(0, 204, 255)
    绿色未变色:(0, 145, 68)    绿色变色:(59, 179, 113)
"""

# judge box coordinate
JUDGE_BOX = (371, 1206, 483, 1318)

# extend area: right side of judge box, narrow strip
BAR_EXTEND_BOX = (485, 1230, 520, 1295)

# template paths
TEMPLATE_DIR = "assets"
TEMPLATES = {
    "carrot": os.path.join(TEMPLATE_DIR, "carrot.png"),
    "eggplant": os.path.join(TEMPLATE_DIR, "eggplant.png"),
}

# match threshold
MATCH_TH = 0.75

# bar color detection (RGB values)
BLUE_UNCHANGED_RGB = (27, 132, 242)
BLUE_CHANGED_RGB = (0, 204, 255)
GREEN_UNCHANGED_RGB = (0, 145, 68)
GREEN_CHANGED_RGB = (59, 179, 113)

# debug options
DEBUG = True
PRINT_EVERY_N_FRAMES = 20


def convert_to_coord(box) -> dict:
    x1, y1, x2, y2 = box
    return {"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1}


def load_templates():
    """load all template images as BGR"""
    templates = {}
    for name, path in TEMPLATES.items():
        img = cv.imread(path, cv.IMREAD_COLOR)
        if img is None:
            print(f"[ERROR] failed to load template: {path}")
            exit(1)
        templates[name] = img
        print(f"[INFO] loaded template '{name}': {img.shape[1]}x{img.shape[0]}")
    return templates


def match_template(region_bgr, template_bgr):
    """
    return best match score (0~1)
    if template is bigger than region, return 0
    """
    rh, rw = region_bgr.shape[:2]
    th, tw = template_bgr.shape[:2]

    if th > rh or tw > rw:
        return 0.0

    result = cv.matchTemplate(region_bgr, template_bgr, cv.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv.minMaxLoc(result)
    return max_val


def match_rgb_ratio(img_bgr, target_rgb, tol=15):
    """check how much of the region matches a specific RGB color"""
    tr, tg, tb = target_rgb
    target_bgr = np.array([tb, tg, tr], dtype=np.int16)
    arr = img_bgr.astype(np.int16)
    diff = np.abs(arr - target_bgr)
    ok = np.all(diff <= tol, axis=2)
    return ok.mean()


def detect_bar_color_rgb(region_bgr):
    """
    use exact RGB values to detect bar color
    check both changed and unchanged versions
    """
    blue_r1 = match_rgb_ratio(region_bgr, BLUE_UNCHANGED_RGB, tol=20)
    blue_r2 = match_rgb_ratio(region_bgr, BLUE_CHANGED_RGB, tol=20)
    blue_total = max(blue_r1, blue_r2)

    green_r1 = match_rgb_ratio(region_bgr, GREEN_UNCHANGED_RGB, tol=20)
    green_r2 = match_rgb_ratio(region_bgr, GREEN_CHANGED_RGB, tol=20)
    green_total = max(green_r1, green_r2)

    BAR_COLOR_TH = 0.25

    if blue_total >= BAR_COLOR_TH or green_total >= BAR_COLOR_TH:
        if blue_total > green_total:
            return "BLUE", blue_total, green_total
        else:
            return "GREEN", blue_total, green_total

    return "NONE", blue_total, green_total


def run_capture_loop(target_fps=120):
    frame_interval = 1.0 / target_fps
    next_tick = time.perf_counter()

    fps_count = 0
    fps_timer = time.perf_counter()
    frame_idx = 0

    judge_coord = convert_to_coord(JUDGE_BOX)
    extend_coord = convert_to_coord(BAR_EXTEND_BOX)

    templates = load_templates()

    # hold state
    hold_z_press = False
    hold_x_press = False

    # edge trigger for short click
    prev_carrot_hit = False
    prev_eggplant_hit = False

    with mss.mss() as sct:
        while True:
            # capture
            t_grab_0 = time.perf_counter()
            judge_img = np.array(sct.grab(judge_coord))
            extend_img = np.array(sct.grab(extend_coord))
            t_grab_1 = time.perf_counter()

            # convert BGRA -> BGR
            judge_bgr = cv.cvtColor(judge_img, cv.COLOR_BGRA2BGR)
            extend_bgr = cv.cvtColor(extend_img, cv.COLOR_BGRA2BGR)

            # template matching (only carrot and eggplant)
            t_det_0 = time.perf_counter()
            carrot_score = match_template(judge_bgr, templates["carrot"])
            eggplant_score = match_template(judge_bgr, templates["eggplant"])
            t_det_1 = time.perf_counter()

            # detect bar color using RGB
            bar_color, bar_blue_r, bar_green_r = detect_bar_color_rgb(extend_bgr)

            carrot_hit = carrot_score >= MATCH_TH
            eggplant_hit = eggplant_score >= MATCH_TH

            # === carrot (Z): press logic ===
            if carrot_hit and not prev_carrot_hit:
                if bar_color == "BLUE":
                    # hold note
                    if not hold_z_press:
                        keyboard.press("z")
                        hold_z_press = True
                else:
                    # short note
                    if not hold_z_press:
                        keyboard.press_and_release("z")

            # === carrot (Z): release logic ===
            # bar is no longer blue -> release (same as v1)
            if hold_z_press and bar_color != "BLUE":
                keyboard.release("z")
                hold_z_press = False

            # === eggplant (X): press logic ===
            if eggplant_hit and not prev_eggplant_hit:
                if bar_color == "GREEN":
                    # hold note
                    if not hold_x_press:
                        keyboard.press("x")
                        hold_x_press = True
                else:
                    # short note
                    if not hold_x_press:
                        keyboard.press_and_release("x")

            # === eggplant (X): release logic ===
            # bar is no longer green -> release (same as v1)
            if hold_x_press and bar_color != "GREEN":
                keyboard.release("x")
                hold_x_press = False

            # update edge trigger state
            prev_carrot_hit = carrot_hit
            prev_eggplant_hit = eggplant_hit

            # debug output
            frame_idx += 1
            if DEBUG and frame_idx % PRINT_EVERY_N_FRAMES == 0:
                grab_ms = (t_grab_1 - t_grab_0) * 1000
                det_ms = (t_det_1 - t_det_0) * 1000

                print(
                    f"[DEBUG] "
                    f"carrot={carrot_score:.2f} eggplant={eggplant_score:.2f} "
                    f"bar={bar_color}(b={bar_blue_r:.2f},g={bar_green_r:.2f}) "
                    f"hold_z={hold_z_press} hold_x={hold_x_press} "
                    f"| grab={grab_ms:.1f}ms det={det_ms:.1f}ms"
                )

            # fps calculate
            fps_count += 1
            now = time.perf_counter()
            if now - fps_timer >= 1.0:
                real_fps = fps_count / (now - fps_timer)
                print(f"real_fps={real_fps:.1f}")
                fps_count = 0
                fps_timer = now

            # scheduling by target fps
            next_tick += frame_interval
            sleep_time = next_tick - time.perf_counter()
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                next_tick = time.perf_counter()

            # stop key
            if keyboard.is_pressed("F11"):
                while keyboard.is_pressed("F11"):
                    time.sleep(0.01)
                break


if __name__ == "__main__":

    print("程序已启动：按 F10 开始，按 F11 结束程序")

    keyboard.wait("F10")
    print("已开始运行...")

    run_capture_loop(120)

    print("程序已结束")
