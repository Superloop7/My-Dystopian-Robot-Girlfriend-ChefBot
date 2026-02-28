import tkinter as tk
import threading
import dxcam
import pydirectinput
import cv2
import numpy as np
import keyboard  # 需要 pip install keyboard

# 1. 配置参数（固定为你测得的分辨率）
REGION = (371, 1206, 483, 1318) 
THRESHOLD = 0.85 

class SimpleBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ChefBot 调试版")
        self.root.geometry("300x200")
        
        self.running = False
        
        # 界面显示
        self.label = tk.Label(root, text="ChefBot 准备就绪", font=("微软雅黑", 12))
        self.label.pack(pady=20)
        
        self.btn = tk.Button(root, text="开始脚本 (F11)", command=self.toggle_bot, width=20, height=2, bg="lightgray")
        self.btn.pack(pady=10)
        
        tk.Label(root, text="停止热键: F12", fg="gray").pack()

        # 在后台监听热键
        threading.Thread(target=self.hotkey_listener, daemon=True).start()

    def hotkey_listener(self):
        while True:
            if keyboard.is_pressed('f11'):
                self.root.after(0, self.start_logic)
            if keyboard.is_pressed('f12'):
                self.root.after(0, self.stop_logic)
            tk.sleep(0.1)

    def toggle_bot(self):
        if not self.running: self.start_logic()
        else: self.stop_logic()

    def start_logic(self):
        if not self.running:
            self.running = True
            self.label.config(text="● 正在切菜中...", fg="green")
            self.btn.config(text="停止脚本", bg="red", fg="white")
            threading.Thread(target=self.bot_worker, daemon=True).start()

    def stop_logic(self):
        self.running = False
        self.label.config(text="○ 脚本已停止", fg="black")
        self.btn.config(text="开始脚本 (F11)", bg="lightgray", fg="black")
        pydirectinput.keyUp('z')
        pydirectinput.keyUp('x')

    def bot_worker(self):
        # 初始化相机和模板
        carrot_img = cv2.imread('assets/carrot.png', 0)
        eggplant_img = cv2.imread('assets/eggplant.png', 0)
        camera = dxcam.create(region=REGION)
        camera.start(target_fps=120)
        
        is_z = False
        is_x = False

        try:
            while self.running:
                frame = camera.get_latest_frame()
                if frame is None: continue
                
                gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
                
                # 识别逻辑
                res_z = cv2.matchTemplate(gray, carrot_img, cv2.TM_CCOEFF_NORMED)
                res_x = cv2.matchTemplate(gray, eggplant_img, cv2.TM_CCOEFF_NORMED)
                
                # 简化判定逻辑
                has_z = np.max(res_z) > THRESHOLD or (np.sum((frame[:,:,2] > 200) & (frame[:,:,0] < 50)) > 50)
                has_x = np.max(res_x) > THRESHOLD or (np.sum((frame[:,:,1] > 100) & (frame[:,:,2] < 90)) > 50)

                # 按键触发
                if has_z and not is_z: pydirectinput.keyDown('z'); is_z = True
                elif not has_z and is_z: pydirectinput.keyUp('z'); is_z = False

                if has_x and not is_x: pydirectinput.keyDown('x'); is_x = True
                elif not has_x and is_x: pydirectinput.keyUp('x'); is_x = False
        finally:
            camera.stop()

if __name__ == "__main__":
    root = tk.Tk()
    app = SimpleBotGUI(root)
    root.mainloop()