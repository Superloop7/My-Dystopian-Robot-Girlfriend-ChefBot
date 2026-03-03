# My Dystopian Robot Girlfriend chefbot

**My Dystopian Robot Girlfriend chefbot**

Auto-chef script for the cooking minigame in *My Dystopian Robot Girlfriend*.

## Features

-  Auto-detect carrot (Z key) and eggplant (X key)
-  Auto-detect hold bars and release at the right time
-  Template matching + RGB color detection for high accuracy
-  Resolution profile system (easy to add new resolutions)

## Quick Start

### Option 1: Run the exe (recommended)

1. Download `ChefBot.exe` from [Releases]
2. Double-click to run (run as Administrator if needed)
3. Select your screen resolution
4. Enter the cooking minigame, press **F10** to start
5. Press **F11** to stop after the level ends

### Option 2: Run from source

```bash
git clone https://github.com/Superloop7/My-Dystopian-Robot-Girlfriend-ChefBot.git
cd My-Dystopian-Robot-Girlfriend-ChefBot
pip install -r requirements.txt
python main.py
```

## Hotkeys

| Key | Action |
|-----|--------|
| F10 | Start  |
| F11 | Stop   |

## Supported Resolutions

| Resolution | Aspect Ratio| Status     |
|------------|-------------|------------|
| 2560x1600  | 16:10       |Verified    |
| 2560x1440  | 16:9        |Not verified|
| 1920x1200  | 16:10       |Verified    |
| 1920x1080  | 16:9        |Verified    |


## Requirements

- Python 3.10+
- Windows (uses `keyboard` and `mss` which require Windows for full functionality)
- Run as **Administrator** (keyboard library requires elevated privileges)
- Game should be in **windowed** or **borderless windowed** mode

## License

MIT