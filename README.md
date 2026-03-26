# My Dystopian Robot Girlfriend Chefbot

自动处理MDRG中的烹饪小游戏<br />
Auto-chef script for the cooking minigame in *My Dystopian Robot Girlfriend*.

## 特性 \ Features

-  自动识别萝卜（Z键）和茄子（X键） \ Auto-detect carrot (Z key) and eggplant (X key)
-  自动识别长条并进行对应操作 \ Auto-detect hold bars and release at the right time
-  高精确度的模板+颜色识别 \ Template matching + RGB color detection for high accuracy
-  自适应性的分辨率缩放（本fork修改） \ Adaptive full-resolution scaling based on reference layouts (by DrJason33564)
-  支持自定义识别阈值 `MATCH_TH` 以调整执行动作时机（本fork修改） \ Support customizing matching threshold `MATCH_TH` to adjust timing of action (by DrJason33564)

## 快速开始 \ Quick Start

### Option 1: 使用命令行运行（推荐） \ Run with command line (recommended)

1. 从 [Releases](https://github.com/DrJason33564/My-Dystopian-Robot-Girlfriend-ChefBot/releases) 下载 `ChefBot.zip` \ Download `ChefBot.zip` from [Releases](https://github.com/DrJason33564/My-Dystopian-Robot-Girlfriend-ChefBot/releases)
2. 双击 `start.bat`, 设置MATCH_TH，启动脚本 \ Double-click `start.bat`, set MATCH_TH, and run
3. 进入烹饪小游戏，按下 **F10** 键开始运行 \ Enter the cooking minigame, press **F10** to start
4. 关卡完成后，按下 **F11** 结束运行 \ Press **F11** to stop after the level ends
5. Ctrl+c 键以退出脚本 \ Crtl+c to quit

### Option 2: 使用UI运行 \ Run with UI

```bash
git clone https://github.com/DrJason33564/My-Dystopian-Robot-Girlfriend-ChefBot.git
cd My-Dystopian-Robot-Girlfriend-ChefBot
pip install -r requirements.txt
python main.py
```

## 快捷键 \ Hotkeys

| Key | Action |
|-----|--------|
| F10 | Start  |
| F11 | Stop   |

## 支持的分辨率 \ Supported Resolutions

理论上适用所有16:9和16:10的屏幕，在 `1366x768` 分辨率下测试成功<br />
Theoretically applicable to all 16:9 and 16:10 screens, and has been tested and working at `1366x768` resolution.


## Requirements

- Python 3.10+
- Windows (uses `keyboard` and `mss` which require Windows for full functionality)
- 如无法正常使用，以**管理员模式**运行 \ Run as **Administrator** if not functioning  properly.
- 游戏应为**全屏模式** \ Game should be in **borderless windowed** mode

## License

GPL3.0
