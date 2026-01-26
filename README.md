# nerdymark's Steam Deck Ports

A collection of controller-friendly download and utility tools for ES-DE on Steam Deck. All tools feature a unified "gloomy aesthetic" UI with animated cityscapes, fog, and rain effects.

![Python](https://img.shields.io/badge/Python-3.x-blue)
![Platform](https://img.shields.io/badge/Platform-Steam%20Deck-1a9fff)
![License](https://img.shields.io/badge/License-MIT-green)

## Features

- **Fullscreen pygame UI** optimized for Steam Deck's 1280x800 display
- **Full controller support** - navigate with D-pad/stick, select with face buttons
- **Gloomy aesthetic** - animated city skyline, drifting fog, falling rain
- **Batch downloads** - press X to download all missing games at once
- **Search/filter** - on-screen keyboard for searching game lists
- **Disk space indicator** - always know how much space you have left
- **Auto-setup** - first run creates Python venv and installs dependencies

## Tools Included

### Game Downloaders

All downloaders fetch from [Myrient](https://myrient.erista.me/), a free ROM archive.

| Tool | Source | Format | Theme |
|------|--------|--------|-------|
| **Xbox Downloader** | Redump | ZIP → XISO (auto-converts) | Green |
| **PS2 Downloader** | Redump | ZIP | Blue |
| **GameCube Downloader** | Redump | NKit RVZ (Dolphin-ready) | Purple |
| **Saturn Downloader** | Redump | ZIP (CUE/BIN) | Teal |
| **Neo Geo CD Downloader** | Redump | ZIP | Blue |
| **Atari Jaguar CD Downloader** | Redump | ZIP | Red |
| **Neo Geo Pocket Downloader** | No-Intro | ZIP | Gold |
| **Neo Geo Pocket Color Downloader** | No-Intro | ZIP | Gold |
| **Atari Jaguar Downloader** | No-Intro | ZIP (J64) | Red |
| **Vectrex Downloader** | No-Intro | ZIP | Vector Green |
| **Game.com Downloader** | No-Intro | ZIP | Tiger Yellow |
| **Pokemon Mini Downloader** | No-Intro | ZIP | Pikachu Yellow |

### Utilities

| Tool | Description |
|------|-------------|
| **MAME Romset Repairer** | Scans arcade ROMs for errors, downloads missing files from Myrient |
| **DOS Setup Tool** | Configure DOSBox-Pure autoboot executables for DOS games |
| **Xbox Extractor** | Batch extract Xbox ZIPs and convert ISOs to XISO format |

## Installation

### Prerequisites

- Steam Deck (or any Linux system with Python 3)
- ES-DE frontend (EmuDeck installs this)
- Python 3 with venv support (pre-installed on Steam Deck)

### Quick Install

1. Clone this repository into your ES-DE ports folder:
   ```bash
   cd ~/Emulation/roms/ports  # or your ES-DE ports path
   git clone git@github.com:nerdymark/nerdymarks_steamdeck_ports.git .
   ```

2. Rescan your games in ES-DE (Start → Scrape → Rescan)

3. Launch any tool from the Ports system - first run will auto-install pygame

### Manual Install

If you already have files in your ports folder:

```bash
cd /path/to/your/ports

# Download just the tools you want
wget https://raw.githubusercontent.com/nerdymark/nerdymarks_steamdeck_ports/main/shared/gloomy_aesthetic.py -P shared/
wget https://raw.githubusercontent.com/nerdymark/nerdymarks_steamdeck_ports/main/ps2-downloader/ps2_downloader.py -P ps2-downloader/
wget "https://raw.githubusercontent.com/nerdymark/nerdymarks_steamdeck_ports/main/nerdymark's%20PS2%20Downloader.sh"
chmod +x "nerdymark's PS2 Downloader.sh"
```

## Controls

All tools use the same controller layout:

| Button | Action |
|--------|--------|
| **D-Pad / Left Stick** | Navigate list |
| **A** | Select / Download |
| **B** | Back / Cancel / Quit |
| **X** | Download All (batch) |
| **Y** | Open search keyboard |
| **Start** | Special actions (varies by tool) |

### On-Screen Keyboard

When searching:
- **D-Pad** - Navigate keys
- **A** - Press key
- **B** - Close keyboard
- Select **DONE** to apply search filter

## Directory Structure

```
ports/
├── shared/
│   └── gloomy_aesthetic.py      # Shared UI theme module
├── xbox-downloader/
│   ├── xbox_downloader.py       # Main downloader
│   ├── xbox_extractor.py        # ZIP extraction + XISO conversion
│   └── venv/                    # Auto-created Python environment
├── ps2-downloader/
│   └── ps2_downloader.py
├── gamecube-downloader/
│   └── gamecube_downloader.py
├── saturn-downloader/
│   └── saturn_downloader.py
├── [other downloaders...]
├── mame-repair/
│   └── mame_repair.py
├── nerdymarks-dos_setup/
│   └── dos_setup.py
├── nerdymark's Xbox Downloader.sh    # ES-DE launcher
├── nerdymark's PS2 Downloader.sh
└── [other launchers...]
```

## ROM Destinations

Downloaded games go to these ES-DE ROM folders:

| Tool | Destination |
|------|-------------|
| Xbox | `roms/xbox/` |
| PS2 | `roms/ps2/` |
| GameCube | `roms/gc/` |
| Saturn | `roms/saturn/` |
| Neo Geo CD | `roms/neogeocd/` |
| Jaguar CD | `roms/atarijaguarcd/` |
| Neo Geo Pocket | `roms/ngp/` |
| Neo Geo Pocket Color | `roms/ngpc/` |
| Atari Jaguar | `roms/atarijaguar/` |
| Vectrex | `roms/vectrex/` |
| Game.com | `roms/gamecom/` |
| Pokemon Mini | `roms/pokemini/` |

## Configuration

### Changing ROM Paths

Edit the `ROM_DIR` constant at the top of each downloader:

```python
# In ps2_downloader.py
ROM_DIR = "/run/media/deck/SK256/Emulation/roms/ps2"  # Change this
```

### Xbox Extractor Requirements

The Xbox downloader requires `extract-xiso` for ISO conversion:

```python
# In xbox_downloader.py
EXTRACT_XISO = "/run/media/deck/SK256/Emulation/tools/chdconv/extract-xiso"
```

You can get extract-xiso from: https://github.com/XboxDev/extract-xiso

## The Gloomy Aesthetic

All tools share a unified visual theme defined in `shared/gloomy_aesthetic.py`:

- **Dark color palette** - Easy on the eyes for late-night gaming sessions
- **Animated skyline** - Procedurally generated city silhouette with glowing windows
- **Fog particles** - Slowly drifting atmospheric fog
- **Rain effect** - Gentle rain with slight wind
- **Accent colors** - Each tool has its own color scheme (green for Xbox, purple for GameCube, etc.)
- **nerdymark branding** - Subtle signature in the corner

### Using the Theme in Your Own Tools

```python
import sys
sys.path.insert(0, '/path/to/ports/shared')
from gloomy_aesthetic import (
    GloomyBackground, draw_nerdymark_brand, draw_title_with_glow,
    create_panel, get_theme
)

# Get a color theme
theme = get_theme('xbox')  # or 'ps2', 'gamecube', 'saturn', etc.
ACCENT = theme['accent']
ACCENT_DIM = theme['accent_dim']
HIGHLIGHT = theme['highlight']

# Create animated background
background = GloomyBackground(screen_width, screen_height, accent_color=ACCENT)

# In your game loop:
background.update()
background.draw(screen)
draw_title_with_glow(screen, font, "MY COOL TOOL", ACCENT, y_position)
draw_nerdymark_brand(screen, small_font, ACCENT_DIM)
```

## Troubleshooting

### "pygame not found" error
First run should auto-install pygame. If it fails:
```bash
cd /path/to/ports/xbox-downloader  # or whichever tool
python3 -m venv venv
./venv/bin/pip install pygame
```

### Tools don't appear in ES-DE
1. Make sure .sh files are executable: `chmod +x "nerdymark's"*.sh`
2. Rescan games in ES-DE: Start → Scrape → Rescan

### "Connection failed" when fetching game list
- Check your internet connection
- Myrient may be temporarily down - try again later
- Some corporate/school networks block these sites

### Xbox ISOs not working in xemu
- Make sure extract-xiso is installed and path is correct
- Check that the ISO was fully downloaded (not cancelled mid-download)
- Some games require specific BIOS versions

### Controller not working
- Make sure Steam Input is enabled for the game
- Try the Button Test utility to verify mappings
- Controllers are detected at startup - restart the tool if you connected after launch

## Contributing

Pull requests welcome! Please maintain the gloomy aesthetic and controller-friendly design.

### Adding a New Downloader

1. Copy an existing downloader as a template (ngp_downloader.py is simplest)
2. Change `BASE_URL`, `ROM_DIR`, and title strings
3. Add a color theme to `shared/gloomy_aesthetic.py`
4. Create a launcher .sh script
5. Test with controller and keyboard

## Credits

**Author:** [nerdymark](https://nerdymark.com)

**Built with:**
- [pygame](https://www.pygame.org/) - Game library for Python
- [Myrient](https://myrient.erista.me/) - ROM archive
- [ES-DE](https://es-de.org/) - Frontend for emulators

**AI Assistance:** Claude (Anthropic) helped write and refactor code

## License

MIT License - Use freely, modify freely, share freely.

---

*"The party's over, but there's still hope..."* - The Gloomy Aesthetic
