# My Dystopian Robot Girlfriend Chefbot

Auto-chef script for the cooking minigame in *My Dystopian Robot Girlfriend*.

## Features

-  Auto-detect carrot (Z key) and eggplant (X key)
-  Auto-detect hold bars and release at the right time
-  Template matching + RGB color detection for high accuracy
-  Adaptive full-resolution scaling based on reference layouts (by DrJason33564)

## Quick Start

### Option 1: Run with command line (recommended)

1. Download `ChefBot.zip` from [Releases]
2. Double-click start.bat, set MATCH_TH, and run
3. Enter the cooking minigame, press **F10** to start
4. Press **F11** to stop after the level ends
5. Crtl+c to quit

### Option 2: Run with UI

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

Theoretically applicable to all 16:9 and 16:10 screens, and has been tested and working at 1366x768 resolution.


## Requirements

- Python 3.10+
- Windows (uses `keyboard` and `mss` which require Windows for full functionality)
- Run as **Administrator** (keyboard library requires elevated privileges)
- Game should be in **borderless windowed** mode

## License

GPL3.0
