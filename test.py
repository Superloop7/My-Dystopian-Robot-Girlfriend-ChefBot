import mss
import numpy as np
import cv2 as cv
import keyboard
import time
import dataclasses
import collections

""" 
    敲击区域(371, 1206, 483, 1318) 
    长条显示上边缘 1242 下边缘 1216 额外探测长条右边缘(512, 1206) (512, 1318)
    萝卜/茄子 左侧上边缘1221 1307 右侧斜角下边缘 1293
"""

# define the screenshot range
left_edge = (371, 1221, 376, 1307)
right_edge = (478, 1221, 483, 1293)
bar_edge = (497, 1206, 512, 1318)

# define the button rgb
blue_rgb = (27, 132, 242)
green_rgb = (0, 145, 68)
blue_bar_rgb = (0, 204, 255)
green_bar_rgb = (59, 179, 113)

# debug options
DEBUG = True
PRINT_EVERY_N_FRAMES = 20


def convert_to_coord(arr_list) -> dict:
    x1, y1, x2, y2 = arr_list
    return {"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1}


def match_ratio_rgb(img_bgr, target_rgb, tol):
    """
    tol: color tolerance
    """
    # convert RGB to BGR
    tr, tg, tb = target_rgb
    target_bgr = np.array([tb, tg, tr], dtype=np.int16)

    arr = img_bgr.astype(np.int16)
    diff = np.abs(arr - target_bgr)
    ok = np.all(diff <= tol, axis=2)  # diff is less than tol
    ratio = ok.mean()
    return ratio  # correct colour pixel in all pixels


def detect_by_rgb_ratio(img_bgr, blue_rgb, green_rgb, ratio_th=0.65, tol=12):
    # if the colour is in the tolerance return the flag
    blue_ratio = match_ratio_rgb(img_bgr, blue_rgb, tol)
    green_ratio = match_ratio_rgb(img_bgr, green_rgb, tol)

    if blue_ratio >= ratio_th or green_ratio >= ratio_th:
        flag = "BLUE" if blue_ratio > green_ratio else "GREEN"
    else:
        flag = "NONE"

    return flag, blue_ratio, green_ratio


def run_capture_loop(target_fps=120):
    frame_interval = 1.0 / target_fps
    next_tick = time.perf_counter()

    fps_count = 0
    fps_timer = time.perf_counter()
    frame_idx = 0

    left_coord = convert_to_coord(left_edge)
    right_coord = convert_to_coord(right_edge)
    bar_coord = convert_to_coord(bar_edge)

    # initialize the hold_flag
    hold_z_press = False
    hold_x_press = False

    # edge trigger for short click
    prev_left_click_flag = "NONE"

    # hold stability counter
    hold_blue_stable = 0
    hold_green_stable = 0
    HOLD_STABLE_FRAMES = 2

    with mss.mss() as sct:
        while True:
            # stage timing: capture
            t_grab_0 = time.perf_counter()
            left_img = np.array(sct.grab(left_coord))
            right_img = np.array(sct.grab(right_coord))
            bar_img = np.array(sct.grab(bar_coord))
            t_grab_1 = time.perf_counter()

            # stage timing: convert BGRA to BGR
            t_cvt_0 = time.perf_counter()
            left_img = cv.cvtColor(left_img, cv.COLOR_BGRA2BGR)
            right_img = cv.cvtColor(right_img, cv.COLOR_BGRA2BGR)
            bar_img = cv.cvtColor(bar_img, cv.COLOR_BGRA2BGR)
            t_cvt_1 = time.perf_counter()

            # stage timing: detect
            t_det_0 = time.perf_counter()
            left_click_flag, left_blue_ratio, left_green_ratio = detect_by_rgb_ratio(
                left_img, blue_rgb, green_rgb, ratio_th=0.65, tol=12
            )
            right_click_flag, right_blue_ratio, right_green_ratio = detect_by_rgb_ratio(
                right_img, blue_rgb, green_rgb, ratio_th=0.65, tol=12
            )

            # bar uses independent color profile (very important)
            hold_click_flag, hold_blue_ratio, hold_green_ratio = detect_by_rgb_ratio(
                bar_img, blue_bar_rgb, green_bar_rgb, ratio_th=0.45, tol=18
            )
            t_det_1 = time.perf_counter()

            # update hold stability counter
            if hold_click_flag == "BLUE":
                hold_blue_stable += 1
            else:
                hold_blue_stable = 0

            if hold_click_flag == "GREEN":
                hold_green_stable += 1
            else:
                hold_green_stable = 0

            # hold logic
            if (
                left_click_flag == "BLUE"
                and right_click_flag == "BLUE"
                and hold_blue_stable >= HOLD_STABLE_FRAMES
            ):
                if not hold_z_press:
                    keyboard.press("z")
                    hold_z_press = True
            elif hold_z_press and hold_click_flag != "BLUE":
                keyboard.release("z")
                hold_z_press = False

            if (
                left_click_flag == "GREEN"
                and right_click_flag == "GREEN"
                and hold_green_stable >= HOLD_STABLE_FRAMES
            ):
                if not hold_x_press:
                    keyboard.press("x")
                    hold_x_press = True
            elif hold_x_press and hold_click_flag != "GREEN":
                keyboard.release("x")
                hold_x_press = False

            # click logic (edge trigger)
            if (
                left_click_flag == "BLUE"
                and prev_left_click_flag != "BLUE"
                and not hold_z_press
            ):
                keyboard.press_and_release("z")

            if (
                left_click_flag == "GREEN"
                and prev_left_click_flag != "GREEN"
                and not hold_x_press
            ):
                keyboard.press_and_release("x")

            prev_left_click_flag = left_click_flag

            # debug output
            frame_idx += 1
            if DEBUG and frame_idx % PRINT_EVERY_N_FRAMES == 0:
                grab_ms = (t_grab_1 - t_grab_0) * 1000
                cvt_ms = (t_cvt_1 - t_cvt_0) * 1000
                det_ms = (t_det_1 - t_det_0) * 1000

                print(
                    "[DEBUG] "
                    f"L={left_click_flag}(b={left_blue_ratio:.2f},g={left_green_ratio:.2f}) "
                    f"R={right_click_flag}(b={right_blue_ratio:.2f},g={right_green_ratio:.2f}) "
                    f"H={hold_click_flag}(b={hold_blue_ratio:.2f},g={hold_green_ratio:.2f}) "
                    f"| HS(b={hold_blue_stable},g={hold_green_stable}) "
                    f"| grab={grab_ms:.2f}ms cvt={cvt_ms:.2f}ms det={det_ms:.2f}ms"
                )

            # fps calculate
            fps_count += 1
            now = time.perf_counter()
            if now - fps_timer >= 1.0:
                real_fps = fps_count / (now - fps_timer)
                print(f"real_fps={real_fps:.1f}")
                fps_count = 0
                fps_timer = now

            # Scheduling by target fps
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

    # 1) 阻塞等待 F10
    keyboard.wait("F10")
    print("已开始运行...")

    # 2) 进入主循环（你在 run_capture_loop 里监听 F11）
    run_capture_loop(120)

    # 3) run_capture_loop 因 F11 break 后，程序直接结束
    print("程序已结束")
