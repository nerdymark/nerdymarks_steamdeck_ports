#!/usr/bin/env python3
"""
nerdymark's MAME Romset Repairer for ES-DE
Browse, launch, and repair MAME ROMs - downloads replacements from Myrient
Uses pygame for Steam Deck controller-friendly UI
"""

import pygame
import subprocess
import urllib.request
import urllib.parse
import html.parser
import os
import sys
import signal
import atexit
import shutil
import re
import logging
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add shared module path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from gloomy_aesthetic import (
    GloomyBackground, draw_nerdymark_brand, draw_title_with_glow, create_panel,
    get_theme, VOID_BLACK, DEEP_GRAY, SMOKE_GRAY, MIST_GRAY, PALE_GRAY, FOG_WHITE,
    HOPE_ORANGE, GLOOMY_ORANGE
)

# Setup logging
LOG_FILE = "/tmp/mame_repair.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

BASE_URL = "https://myrient.erista.me/files/MAME/ROMs%20(merged)/"
BIOS_URL = "https://myrient.erista.me/files/MAME/ROMs%20(bios-devices)/"
MAME_ROM_DIR = "/run/media/deck/SK256/Emulation/roms/mame"

# Common BIOS/device files that games depend on
COMMON_BIOS = [
    # Neo Geo / SNK
    "neogeo",
    # Capcom
    "qsound", "qsound_hle",
    # DECO
    "decocass", "decobsmt",
    # PGM / IGS
    "pgm",
    # Sega
    "segasp", "segas32", "stvbios", "stv",
    # Seta
    "skns", "st0016",
    # NMK
    "nmk004",
    # Namco chips (critical for many Namco games)
    "namcoc65", "namcoc67", "namcoc68", "namcoc69", "namcoc70",
    "namcoc71", "namcoc74", "namcoc75", "namcoc76",
    "namco50", "namco51", "namco52", "namco53", "namco54", "namco62",
    "namco_amc", "sys246", "sys256",
    # Naomi / Atomiswave
    "naomi", "naomi2", "naomigd", "atomiswave", "awbios",
    # Sound chips
    "bsmt2000", "ym2608", "upd7759",
    # Taito
    "cchip", "taitosnd", "taito68705", "taitotz", "taitofx1",
    # Konami
    "konamigv", "konamigx", "ksys573", "sys573bios",
    # Irem
    "m72", "m90", "m92",
    # Nintendo
    "megaplay", "megatech", "nss", "playch10",
    # Misc
    "tms32031", "u87", "isgsm",
]

# Mapping of missing file patterns to their BIOS source
# Format: "missing_file_pattern": "bios_zip_name"
MISSING_FILE_TO_BIOS = {
    # Namco chips
    "c65.bin": "namcoc65",
    "c67.bin": "namcoc67",
    "c68.3d": "namcoc68",
    "sys2c68.3f": "namcoc68",
    "c69.bin": "namcoc69",
    "c70.bin": "namcoc70",
    "c71.bin": "namcoc71",
    "c74.bin": "namcoc74",
    "c75.bin": "namcoc75",
    "c76.bin": "namcoc76",
    # Namco System 2
    "sys2mcpu.bin": "namcoc68",
    "sys2c65c.bin": "namcoc65",
    "sys2c65b.bin": "namcoc65",
    # NMK
    "nmk004.bin": "nmk004",
    "nmk004_2.bin": "nmk004",
    # Sound chips
    "bsmt2000.bin": "bsmt2000",
    "ym2608.bin": "ym2608",
    "upd7759.bin": "upd7759",
    # Capcom
    "qsound.bin": "qsound",
    "qsound_hle.bin": "qsound_hle",
    "dl-1425.bin": "qsound",
    # DECO
    "v0c-.7e": "decocass",
    "dp-1100a.rom": "decocass",
    "dp-1100b.rom": "decocass",
    # Neo Geo
    "000-lo.lo": "neogeo",
    "sm1.sm1": "neogeo",
    "sfix.sfix": "neogeo",
    "sp-s2.sp1": "neogeo",
    # PGM
    "pgm_p01s.rom": "pgm",
    "pgm_t01s.rom": "pgm",
    "pgm_m01s.rom": "pgm",
    # Taito
    "cchip_data": "cchip",
    # Irem M72
    "m72_i8751": "m72",
}

FBNEO_CORE = "/home/deck/.var/app/org.libretro.RetroArch/config/retroarch/cores/fbneo_libretro.so"
RETROARCH = "/home/deck/.local/share/flatpak/exports/bin/org.libretro.RetroArch"
SOUND_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tada.mp3")

# Disk space thresholds (in GB)
DISK_SPACE_WARNING = 20
DISK_SPACE_CRITICAL = 10

# Colors - Gloomy Orange theme
THEME = get_theme('mame')
ACCENT = THEME['accent']
ACCENT_DIM = THEME['accent_dim']
HIGHLIGHT = THEME['highlight']

BLACK = VOID_BLACK
WHITE = FOG_WHITE
GRAY = MIST_GRAY
DARK_GRAY = DEEP_GRAY
LIGHT_GRAY = SMOKE_GRAY
YELLOW = (180, 170, 80)
RED = (180, 70, 70)
GREEN = (70, 150, 90)
ORANGE = ACCENT
DARK_ORANGE = ACCENT_DIM

# ROM status
STATUS_UNKNOWN = 0
STATUS_OK = 1
STATUS_BROKEN = 2
STATUS_NOT_IN_MYRIENT = 3

# Global tracking for cleanup
_child_processes = []
_cleanup_done = False

def cleanup():
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True
    for proc in _child_processes:
        try:
            proc.kill()
            proc.wait(timeout=2)
        except:
            pass

def signal_handler(signum, frame):
    cleanup()
    pygame.quit()
    sys.exit(1)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)

def track_process(proc):
    _child_processes.append(proc)
    return proc


class MyrientParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.files = set()
        self.in_link = False
        self.current_href = None

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            for name, value in attrs:
                if name == 'href' and value.endswith('.zip'):
                    self.in_link = True
                    self.current_href = value

    def handle_data(self, data):
        if self.in_link and self.current_href:
            name = data.strip()
            if name.endswith('.zip'):
                # Store without .zip extension for easier matching
                self.files.add(name[:-4])
            self.in_link = False
            self.current_href = None


class MyrientSizeParser(html.parser.HTMLParser):
    """Parser that extracts file names and sizes from Myrient listing"""
    def __init__(self):
        super().__init__()
        self.files = {}  # name -> size in bytes
        self.in_link = False
        self.current_href = None
        self.in_size = False
        self.current_name = None

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            for name, value in attrs:
                if name == 'href' and value.endswith('.zip'):
                    self.in_link = True
                    self.current_href = value
        elif tag == 'td':
            attr_dict = dict(attrs)
            if attr_dict.get('class') == 'size':
                self.in_size = True

    def handle_data(self, data):
        if self.in_link and self.current_href:
            name = data.strip()
            if name.endswith('.zip'):
                self.current_name = name[:-4]
            self.in_link = False
        elif self.in_size and self.current_name:
            # Parse size like "1.8 MiB" or "22.4 KiB"
            size_str = data.strip()
            try:
                if 'MiB' in size_str:
                    size = float(size_str.replace('MiB', '').strip()) * 1024 * 1024
                elif 'KiB' in size_str:
                    size = float(size_str.replace('KiB', '').strip()) * 1024
                elif 'GiB' in size_str:
                    size = float(size_str.replace('GiB', '').strip()) * 1024 * 1024 * 1024
                else:
                    size = float(size_str)
                self.files[self.current_name] = int(size)
            except:
                pass
            self.current_name = None
            self.in_size = False

    def handle_endtag(self, tag):
        if tag == 'td':
            self.in_size = False


class MameRepairUI:
    def __init__(self):
        pygame.init()
        pygame.joystick.init()
        pygame.mixer.init()

        # Load completion sound
        self.completion_sound = None
        if os.path.exists(SOUND_FILE):
            try:
                self.completion_sound = pygame.mixer.Sound(SOUND_FILE)
            except:
                pass

        # Fullscreen
        info = pygame.display.Info()
        self.width = info.current_w
        self.height = info.current_h
        self.screen = pygame.display.set_mode((self.width, self.height), pygame.FULLSCREEN)
        pygame.display.set_caption("nerdymark's MAME Romset Repairer")

        # Fonts
        self.font_large = pygame.font.Font(None, 48)
        self.font_medium = pygame.font.Font(None, 36)
        self.font_small = pygame.font.Font(None, 28)
        self.font_tiny = pygame.font.Font(None, 22)
        self.font_brand = pygame.font.Font(None, 24)

        # Gloomy background
        self.background = GloomyBackground(self.width, self.height, accent_color=ACCENT)

        # Controller
        self.joystick = None
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()

        # State
        self.local_roms = []  # List of (name, path, status, error_msg)
        self.myrient_roms = set()
        self.selected_index = 0
        self.scroll_offset = 0
        self.visible_items = (self.height - 250) // 35

        # Filter state
        self.show_filter = "all"  # "all", "broken", "ok"
        self.search_text = ""

        # Keyboard for search
        self.keyboard_active = False
        self.keyboard_rows = [
            list("1234567890"),
            list("QWERTYUIOP"),
            list("ASDFGHJKL"),
            list("ZXCVBNM"),
            ["SPACE", "DEL", "DONE"]
        ]
        self.key_row = 0
        self.key_col = 0

        # Scan state
        self.scanning = False
        self.scan_progress = 0
        self.scan_total = 0
        self.scan_current = ""

        # Download state
        self.downloading = False
        self.download_progress = 0
        self.download_game = ""
        self.download_status = ""

        # Input timing
        self.last_input_time = 0
        self.input_delay = 150

        self.clock = pygame.time.Clock()

    def get_disk_space(self):
        try:
            stat = os.statvfs(MAME_ROM_DIR)
            free_bytes = stat.f_bavail * stat.f_frsize
            total_bytes = stat.f_blocks * stat.f_frsize
            free_gb = free_bytes / (1024 ** 3)
            total_gb = total_bytes / (1024 ** 3)
            return free_gb, total_gb
        except:
            return 0, 0

    def draw_disk_space(self):
        free_gb, total_gb = self.get_disk_space()
        if total_gb == 0:
            return

        bar_width = 120
        bar_height = 16
        padding = 15
        x = self.width - bar_width - padding
        y = padding

        used_gb = total_gb - free_gb
        fill_pct = used_gb / total_gb if total_gb > 0 else 0

        if free_gb < DISK_SPACE_CRITICAL:
            fill_color = RED
        elif free_gb < DISK_SPACE_WARNING:
            fill_color = YELLOW
        else:
            fill_color = GREEN

        pygame.draw.rect(self.screen, DARK_GRAY, (x, y, bar_width, bar_height), border_radius=3)
        fill_width = int(bar_width * fill_pct)
        if fill_width > 0:
            pygame.draw.rect(self.screen, fill_color, (x, y, fill_width, bar_height), border_radius=3)
        pygame.draw.rect(self.screen, GRAY, (x, y, bar_width, bar_height), width=1, border_radius=3)

        label = f"{free_gb:.0f}GB free"
        label_surf = self.font_tiny.render(label, True, WHITE if free_gb >= DISK_SPACE_CRITICAL else fill_color)
        self.screen.blit(label_surf, (x, y + bar_height + 3))

    def play_completion_sound(self):
        if self.completion_sound:
            try:
                self.completion_sound.play()
            except:
                pass

    def draw_message(self, title, message, subtitle=""):
        self.background.update()
        self.background.draw(self.screen)

        # Central message panel
        panel = create_panel(500, 180)
        panel_x = (self.width - 500) // 2
        panel_y = (self.height - 180) // 2
        self.screen.blit(panel, (panel_x, panel_y))

        draw_title_with_glow(self.screen, self.font_large, title, ACCENT, panel_y + 30)
        msg_surf = self.font_medium.render(message, True, WHITE)
        self.screen.blit(msg_surf, (self.width//2 - msg_surf.get_width()//2, panel_y + 80))
        if subtitle:
            sub_surf = self.font_small.render(subtitle, True, GRAY)
            self.screen.blit(sub_surf, (self.width//2 - sub_surf.get_width()//2, panel_y + 120))

        draw_nerdymark_brand(self.screen, self.font_brand, ACCENT_DIM, "bottom_left")

    def fetch_myrient_list(self):
        self.draw_message("Connecting to Myrient...", "Fetching available ROMs list", "This may take a moment")
        pygame.display.flip()

        try:
            req = urllib.request.Request(BASE_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=60) as response:
                html_content = response.read().decode('utf-8')

            parser = MyrientParser()
            parser.feed(html_content)
            return parser.files
        except Exception as e:
            self.draw_message("Error", f"Failed to fetch Myrient list: {str(e)[:50]}")
            pygame.display.flip()
            pygame.time.wait(3000)
            return set()

    def get_local_roms(self):
        """Get list of local ROM files"""
        roms = []
        rom_path = Path(MAME_ROM_DIR)
        if rom_path.exists():
            for f in sorted(rom_path.iterdir()):
                if f.suffix.lower() == '.zip':
                    roms.append((f.stem, f, STATUS_UNKNOWN, ""))
        return roms

    def test_rom(self, rom_path):
        """Test a ROM with FBNeo and return (status, error_message)"""
        rom_name = rom_path.stem if hasattr(rom_path, 'stem') else os.path.basename(rom_path)
        logging.info(f"Testing ROM: {rom_name}")

        try:
            # Run RetroArch with FBNeo in test mode (will fail fast if ROM is bad)
            proc = subprocess.run(
                [RETROARCH, '-L', FBNEO_CORE, str(rom_path), '--verbose', '--max-frames=1'],
                capture_output=True,
                text=True,
                timeout=10,
                env={**os.environ, 'DISPLAY': ''}  # Prevent display issues
            )

            output = proc.stdout + proc.stderr

            # Check for specific error patterns
            if 'is required' in output.lower():
                # Extract ALL missing file info
                missing_files = re.findall(r'ROM.*?name (\S+).*?is required', output)
                if missing_files:
                    error_msg = f"Missing: {', '.join(missing_files[:5])}"
                    if len(missing_files) > 5:
                        error_msg += f" (+{len(missing_files)-5} more)"
                    logging.warning(f"{rom_name}: {error_msg}")
                    logging.debug(f"{rom_name} full output:\n{output}")
                    return STATUS_BROKEN, error_msg
                return STATUS_BROKEN, "Missing required files"

            if 'failed to load' in output.lower():
                logging.warning(f"{rom_name}: Failed to load")
                return STATUS_BROKEN, "Failed to load"

            if 'not found' in output.lower() and 'romset' in output.lower():
                logging.warning(f"{rom_name}: ROM not supported by FBNeo")
                return STATUS_BROKEN, "ROM not supported"

            # If we got here without errors, ROM is probably OK
            logging.info(f"{rom_name}: OK")
            return STATUS_OK, ""

        except subprocess.TimeoutExpired:
            logging.info(f"{rom_name}: OK (timeout = loaded successfully)")
            return STATUS_OK, ""  # Timeout likely means it started loading
        except Exception as e:
            logging.error(f"{rom_name}: Exception - {e}")
            return STATUS_UNKNOWN, str(e)[:30]

    def scan_roms(self):
        """Scan all local ROMs and test them"""
        self.scanning = True
        self.local_roms = self.get_local_roms()
        self.scan_total = len(self.local_roms)
        self.scan_progress = 0

        updated_roms = []

        for i, (name, path, _, _) in enumerate(self.local_roms):
            self.scan_progress = i + 1
            self.scan_current = name

            # Update display
            self.draw_scan_progress()
            pygame.display.flip()

            # Process events to allow cancellation
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.scanning = False
                    return
                if event.type == pygame.JOYBUTTONDOWN and event.button == 1:
                    self.scanning = False
                    return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.scanning = False
                    return

            # Check if ROM exists in Myrient
            in_myrient = name in self.myrient_roms

            # Test the ROM
            status, error = self.test_rom(path)

            if not in_myrient and status == STATUS_BROKEN:
                status = STATUS_NOT_IN_MYRIENT
                error = "Not in Myrient (can't repair)"

            updated_roms.append((name, path, status, error))

        self.local_roms = updated_roms
        self.scanning = False

    def draw_scan_progress(self):
        self.background.update()
        self.background.draw(self.screen)

        draw_title_with_glow(self.screen, self.font_large, "SCANNING ROMS", ACCENT, self.height//2 - 100)

        # Current ROM
        current_surf = self.font_medium.render(self.scan_current[:40], True, WHITE)
        self.screen.blit(current_surf, (self.width//2 - current_surf.get_width()//2, self.height//2 - 40))

        # Progress bar
        bar_width = self.width - 200
        bar_height = 40
        bar_x = 100
        bar_y = self.height // 2 + 20

        pygame.draw.rect(self.screen, DEEP_GRAY, (bar_x, bar_y, bar_width, bar_height), border_radius=5)
        pygame.draw.rect(self.screen, SMOKE_GRAY, (bar_x, bar_y, bar_width, bar_height), width=1, border_radius=5)

        if self.scan_total > 0:
            fill_width = int(bar_width * self.scan_progress / self.scan_total)
            if fill_width > 0:
                pygame.draw.rect(self.screen, ACCENT, (bar_x, bar_y, fill_width, bar_height), border_radius=5)

        # Progress text
        pct = (self.scan_progress * 100 // self.scan_total) if self.scan_total > 0 else 0
        progress_text = f"{self.scan_progress} / {self.scan_total} ({pct}%)"
        pct_surf = self.font_medium.render(progress_text, True, WHITE)
        self.screen.blit(pct_surf, (self.width//2 - pct_surf.get_width()//2, bar_y + 8))

        # Cancel hint
        cancel_surf = self.font_small.render("[B] Cancel Scan", True, RED)
        self.screen.blit(cancel_surf, (self.width//2 - cancel_surf.get_width()//2, self.height - 50))

        draw_nerdymark_brand(self.screen, self.font_brand, ACCENT_DIM, "bottom_left")

    def get_filtered_roms(self):
        """Get ROMs based on current filter and search"""
        roms = self.local_roms

        # Apply search filter
        if self.search_text:
            search = self.search_text.lower()
            roms = [r for r in roms if search in r[0].lower()]

        # Apply status filter
        if self.show_filter == "broken":
            roms = [r for r in roms if r[2] == STATUS_BROKEN]
        elif self.show_filter == "ok":
            roms = [r for r in roms if r[2] == STATUS_OK]

        return roms

    def draw_keyboard(self):
        # Dark overlay
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((8, 8, 12, 220))
        self.screen.blit(overlay, (0, 0))

        # Keyboard panel
        kb_width = 600
        kb_height = 300
        kb_x = (self.width - kb_width) // 2
        kb_y = (self.height - kb_height) // 2

        panel = create_panel(kb_width, kb_height)
        self.screen.blit(panel, (kb_x, kb_y))

        search_surf = self.font_medium.render(f"Search: {self.search_text}_", True, ACCENT)
        self.screen.blit(search_surf, (kb_x + 20, kb_y + 20))

        key_size = 50
        for row_idx, row in enumerate(self.keyboard_rows):
            row_width = len(row) * (key_size + 5)
            start_x = kb_x + (kb_width - row_width) // 2
            y = kb_y + 70 + row_idx * (key_size + 5)

            for col_idx, key in enumerate(row):
                x = start_x + col_idx * (key_size + 5)
                w = key_size
                if key in ["SPACE", "DEL", "DONE"]:
                    w = 80
                    x = start_x + col_idx * 85

                selected = (row_idx == self.key_row and col_idx == self.key_col)
                color = ACCENT if selected else SMOKE_GRAY
                pygame.draw.rect(self.screen, color, (x, y, w, key_size), border_radius=5)
                if not selected:
                    pygame.draw.rect(self.screen, MIST_GRAY, (x, y, w, key_size), width=1, border_radius=5)

                label = " " if key == "SPACE" else key
                key_surf = self.font_small.render(label, True, VOID_BLACK if selected else WHITE)
                self.screen.blit(key_surf, (x + w//2 - key_surf.get_width()//2, y + key_size//2 - key_surf.get_height()//2))

    def handle_keyboard_input(self, action):
        if action == "UP":
            self.key_row = max(0, self.key_row - 1)
            self.key_col = min(self.key_col, len(self.keyboard_rows[self.key_row]) - 1)
        elif action == "DOWN":
            self.key_row = min(len(self.keyboard_rows) - 1, self.key_row + 1)
            self.key_col = min(self.key_col, len(self.keyboard_rows[self.key_row]) - 1)
        elif action == "LEFT":
            self.key_col = max(0, self.key_col - 1)
        elif action == "RIGHT":
            self.key_col = min(len(self.keyboard_rows[self.key_row]) - 1, self.key_col + 1)

    def handle_keyboard_select(self):
        key = self.keyboard_rows[self.key_row][self.key_col]
        if key == "DONE":
            self.keyboard_active = False
            self.selected_index = 0
            self.scroll_offset = 0
        elif key == "DEL":
            self.search_text = self.search_text[:-1]
        elif key == "SPACE":
            self.search_text += " "
        else:
            self.search_text += key.lower()

    def draw_main_menu(self):
        # Gloomy background with rain and fog
        self.background.update()
        self.background.draw(self.screen)

        self.draw_disk_space()

        # Header with glow effect
        draw_title_with_glow(self.screen, self.font_large, "MAME ROMSET REPAIRER", ACCENT, 15)

        # nerdymark branding
        draw_nerdymark_brand(self.screen, self.font_brand, ACCENT_DIM, "bottom_left")

        # Stats
        total = len(self.local_roms)
        ok_count = sum(1 for r in self.local_roms if r[2] == STATUS_OK)
        broken_count = sum(1 for r in self.local_roms if r[2] == STATUS_BROKEN)
        unknown_count = sum(1 for r in self.local_roms if r[2] == STATUS_UNKNOWN)

        stats = f"Total: {total} | OK: {ok_count} | Broken: {broken_count} | Not scanned: {unknown_count}"
        stats_surf = self.font_small.render(stats, True, GRAY)
        self.screen.blit(stats_surf, (self.width//2 - stats_surf.get_width()//2, 55))

        # Log file hint
        log_hint = f"Log: {LOG_FILE}"
        log_surf = self.font_tiny.render(log_hint, True, DARK_GRAY)
        self.screen.blit(log_surf, (self.width//2 - log_surf.get_width()//2, 75))

        # Search and filter row
        search_text = f"Search: {self.search_text}_" if self.search_text else "Search: [press SELECT]"
        search_surf = self.font_small.render(search_text, True, YELLOW if self.search_text else GRAY)
        self.screen.blit(search_surf, (50, 95))

        filter_text = f"Filter: {self.show_filter.upper()}"
        filter_surf = self.font_small.render(filter_text, True, YELLOW)
        self.screen.blit(filter_surf, (400, 95))

        filtered_roms = self.get_filtered_roms()

        # ROM list
        list_top = 130
        for i in range(self.visible_items):
            idx = i + self.scroll_offset
            if idx >= len(filtered_roms):
                break

            name, path, status, error = filtered_roms[idx]
            y = list_top + i * 35

            # Highlight selected
            if idx == self.selected_index:
                pygame.draw.rect(self.screen, DARK_ORANGE, (50, y, self.width - 100, 33))

            # Status indicator
            if status == STATUS_OK:
                status_text = "[OK]"
                status_color = GREEN
            elif status == STATUS_BROKEN:
                status_text = "[BROKEN]"
                status_color = RED
            elif status == STATUS_NOT_IN_MYRIENT:
                status_text = "[N/A]"
                status_color = GRAY
            else:
                status_text = "[?]"
                status_color = GRAY

            # ROM name
            display_name = name[:45] + "..." if len(name) > 45 else name

            color = WHITE
            if idx == self.selected_index:
                color = YELLOW if status != STATUS_OK else GREEN

            status_surf = self.font_small.render(status_text, True, status_color)
            name_surf = self.font_small.render(display_name, True, color)

            self.screen.blit(status_surf, (60, y + 6))
            self.screen.blit(name_surf, (160, y + 6))

            # Error message for selected item
            if idx == self.selected_index and error:
                error_surf = self.font_tiny.render(error[:50], True, YELLOW)
                self.screen.blit(error_surf, (self.width - 400, y + 8))

        # Scrollbar
        if len(filtered_roms) > self.visible_items:
            bar_height = self.height - 280
            handle_height = max(30, bar_height * self.visible_items // len(filtered_roms))
            handle_pos = bar_height * self.scroll_offset // max(1, len(filtered_roms) - self.visible_items)
            pygame.draw.rect(self.screen, DARK_GRAY, (self.width - 30, 130, 10, bar_height))
            pygame.draw.rect(self.screen, ORANGE, (self.width - 30, 130 + handle_pos, 10, handle_height))

        # Controls help
        if self.show_filter == "broken":
            controls = "[A] Repair  [Y] Search  [X] Filter  [SELECT] Fix All  [START] Scan  [L1] BIOS Check  [R1] BIOS Scan  [B] Quit"
        else:
            controls = "[A] Launch/Repair  [Y] Search  [X] Filter  [START] Scan  [L1] BIOS Check  [R1] BIOS Scan  [B] Quit"
        controls_surf = self.font_small.render(controls, True, GRAY)
        self.screen.blit(controls_surf, (self.width//2 - controls_surf.get_width()//2, self.height - 40))

    def draw_download_progress(self):
        self.background.update()
        self.background.draw(self.screen)
        self.draw_disk_space()

        draw_title_with_glow(self.screen, self.font_large, "DOWNLOADING", ACCENT, self.height//2 - 120)

        name_surf = self.font_medium.render(self.download_game[:50], True, WHITE)
        self.screen.blit(name_surf, (self.width//2 - name_surf.get_width()//2, self.height//2 - 60))

        bar_width = self.width - 200
        bar_height = 40
        bar_x = 100
        bar_y = self.height // 2

        pygame.draw.rect(self.screen, DEEP_GRAY, (bar_x, bar_y, bar_width, bar_height), border_radius=5)
        pygame.draw.rect(self.screen, SMOKE_GRAY, (bar_x, bar_y, bar_width, bar_height), width=1, border_radius=5)
        fill_width = int(bar_width * self.download_progress / 100)
        if fill_width > 0:
            pygame.draw.rect(self.screen, ACCENT, (bar_x, bar_y, fill_width, bar_height), border_radius=5)

        pct_surf = self.font_medium.render(f"{self.download_progress}%", True, WHITE)
        self.screen.blit(pct_surf, (self.width//2 - pct_surf.get_width()//2, bar_y + 8))

        status_surf = self.font_small.render(self.download_status, True, YELLOW)
        self.screen.blit(status_surf, (self.width//2 - status_surf.get_width()//2, bar_y + 60))

        cancel_surf = self.font_small.render("[B] Cancel", True, RED)
        self.screen.blit(cancel_surf, (self.width//2 - cancel_surf.get_width()//2, self.height - 50))

        draw_nerdymark_brand(self.screen, self.font_brand, ACCENT_DIM, "bottom_left")

    def check_input(self):
        current_time = pygame.time.get_ticks()
        if current_time - self.last_input_time < self.input_delay:
            return None

        keys = pygame.key.get_pressed()
        if keys[pygame.K_UP]:
            self.last_input_time = current_time
            return "UP"
        if keys[pygame.K_DOWN]:
            self.last_input_time = current_time
            return "DOWN"
        if keys[pygame.K_LEFT]:
            self.last_input_time = current_time
            return "LEFT"
        if keys[pygame.K_RIGHT]:
            self.last_input_time = current_time
            return "RIGHT"

        if self.joystick:
            hat = self.joystick.get_hat(0) if self.joystick.get_numhats() > 0 else (0, 0)
            if hat[1] == 1:
                self.last_input_time = current_time
                return "UP"
            if hat[1] == -1:
                self.last_input_time = current_time
                return "DOWN"
            if hat[0] == -1:
                self.last_input_time = current_time
                return "LEFT"
            if hat[0] == 1:
                self.last_input_time = current_time
                return "RIGHT"

            axis_y = self.joystick.get_axis(1)
            axis_x = self.joystick.get_axis(0)
            if axis_y < -0.5:
                self.last_input_time = current_time
                return "UP"
            if axis_y > 0.5:
                self.last_input_time = current_time
                return "DOWN"
            if axis_x < -0.5:
                self.last_input_time = current_time
                return "LEFT"
            if axis_x > 0.5:
                self.last_input_time = current_time
                return "RIGHT"

        return None

    def handle_list_input(self, action):
        filtered_roms = self.get_filtered_roms()
        if action == "UP":
            if self.selected_index > 0:
                self.selected_index -= 1
                if self.selected_index < self.scroll_offset:
                    self.scroll_offset = self.selected_index
        elif action == "DOWN":
            if self.selected_index < len(filtered_roms) - 1:
                self.selected_index += 1
                if self.selected_index >= self.scroll_offset + self.visible_items:
                    self.scroll_offset = self.selected_index - self.visible_items + 1

    def cycle_filter(self):
        filters = ["broken", "all", "ok"]
        current_idx = filters.index(self.show_filter)
        self.show_filter = filters[(current_idx + 1) % len(filters)]
        self.selected_index = 0
        self.scroll_offset = 0

    def launch_game(self, rom_name, rom_path):
        """Launch a game with FBNeo and check if it works"""
        self.draw_message("Launching...", rom_name, "Game will start shortly")
        pygame.display.flip()

        # Hide pygame window
        pygame.display.iconify()

        try:
            # Launch with FBNeo (full launch, not test mode)
            proc = subprocess.Popen(
                [RETROARCH, '-L', FBNEO_CORE, str(rom_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            track_process(proc)

            # Wait for it to finish
            stdout, stderr = proc.communicate()
            output = stdout.decode() + stderr.decode()

            # Restore pygame
            pygame.display.set_mode((self.width, self.height), pygame.FULLSCREEN)

            # Check if it failed due to missing ROMs
            if 'is required' in output.lower() or 'failed to load' in output.lower():
                # Extract error
                match = re.search(r'ROM.*?name (\S+).*?is required', output)
                error_msg = f"Missing: {match.group(1)}" if match else "Missing required files"

                # Update ROM status
                for i, (name, path, status, _) in enumerate(self.local_roms):
                    if name == rom_name:
                        in_myrient = name in self.myrient_roms
                        new_status = STATUS_BROKEN if in_myrient else STATUS_NOT_IN_MYRIENT
                        self.local_roms[i] = (name, path, new_status, error_msg)
                        break

                # Offer to repair
                if rom_name in self.myrient_roms:
                    self.draw_message("Game Failed to Load", error_msg, "Press [A] to repair or [B] to cancel")
                    pygame.display.flip()

                    waiting = True
                    while waiting:
                        for event in pygame.event.get():
                            if event.type == pygame.JOYBUTTONDOWN:
                                if event.button == 0:  # A - Repair
                                    self.repair_rom(rom_name)
                                    waiting = False
                                elif event.button == 1:  # B - Cancel
                                    waiting = False
                            if event.type == pygame.KEYDOWN:
                                if event.key == pygame.K_RETURN:
                                    self.repair_rom(rom_name)
                                    waiting = False
                                elif event.key == pygame.K_ESCAPE:
                                    waiting = False
                        self.clock.tick(30)
                else:
                    self.draw_message("Game Failed to Load", error_msg, "ROM not available on Myrient - cannot repair")
                    pygame.display.flip()
                    pygame.time.wait(3000)
            else:
                # Game ran successfully, mark as OK
                for i, (name, path, status, _) in enumerate(self.local_roms):
                    if name == rom_name:
                        self.local_roms[i] = (name, path, STATUS_OK, "")
                        break

        except Exception as e:
            pygame.display.set_mode((self.width, self.height), pygame.FULLSCREEN)
            self.draw_message("Error", str(e)[:50])
            pygame.display.flip()
            pygame.time.wait(2000)

    def fetch_bios_sizes(self):
        """Fetch BIOS file sizes from Myrient"""
        self.draw_message("Checking BIOS Files...", "Fetching Myrient BIOS list")
        pygame.display.flip()

        try:
            req = urllib.request.Request(BIOS_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=60) as response:
                html_content = response.read().decode('utf-8')

            parser = MyrientSizeParser()
            parser.feed(html_content)
            return parser.files
        except Exception as e:
            logging.error(f"Failed to fetch BIOS list: {e}")
            return {}

    def check_and_repair_bios(self):
        """Check all common BIOS files and offer to repair outdated ones"""
        logging.info("=" * 40)
        logging.info("Starting BIOS check")

        # Fetch Myrient BIOS sizes
        myrient_bios = self.fetch_bios_sizes()
        if not myrient_bios:
            self.draw_message("Error", "Could not fetch BIOS list from Myrient")
            pygame.display.flip()
            pygame.time.wait(2000)
            return

        # Check local BIOS files
        outdated = []
        missing = []
        ok = []

        for bios_name in COMMON_BIOS:
            local_path = os.path.join(MAME_ROM_DIR, bios_name + ".zip")

            if bios_name not in myrient_bios:
                continue  # Not available on Myrient

            myrient_size = myrient_bios[bios_name]

            if os.path.exists(local_path):
                local_size = os.path.getsize(local_path)
                # If local is significantly smaller, it's likely outdated
                if local_size < myrient_size * 0.9:  # More than 10% smaller
                    outdated.append((bios_name, local_size, myrient_size))
                    logging.info(f"BIOS {bios_name}: OUTDATED (local: {local_size}, myrient: {myrient_size})")
                else:
                    ok.append(bios_name)
                    logging.info(f"BIOS {bios_name}: OK")
            else:
                # Check if any games might need this BIOS
                missing.append((bios_name, myrient_size))
                logging.info(f"BIOS {bios_name}: MISSING")

        # Show results
        if not outdated and not missing:
            self.draw_message("BIOS Check Complete", f"All {len(ok)} BIOS files are up to date!")
            pygame.display.flip()
            pygame.time.wait(2000)
            return

        # Show what needs updating
        total_repairs = len(outdated)
        if total_repairs == 0:
            self.draw_message("BIOS Check Complete", f"{len(missing)} BIOS files not installed (optional)")
            pygame.display.flip()
            pygame.time.wait(2000)
            return

        self.draw_message("Outdated BIOS Found",
                         f"{total_repairs} BIOS files need updating",
                         "Press [A] to repair all or [B] to cancel")
        pygame.display.flip()

        # Wait for user input
        waiting = True
        while waiting:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.JOYBUTTONDOWN:
                    if event.button == 0:  # A - Repair
                        waiting = False
                    elif event.button == 1:  # B - Cancel
                        return
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        waiting = False
                    elif event.key == pygame.K_ESCAPE:
                        return
            self.clock.tick(30)

        # Repair outdated BIOS files
        fixed = 0
        failed = 0

        for i, (bios_name, local_size, myrient_size) in enumerate(outdated):
            self.draw_message(f"Updating BIOS ({i+1}/{total_repairs})",
                             bios_name,
                             f"Fixed: {fixed} | Failed: {failed}")
            pygame.display.flip()

            # Check for cancel
            for event in pygame.event.get():
                if event.type == pygame.JOYBUTTONDOWN and event.button == 1:
                    return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return

            if self.download_bios(bios_name):
                fixed += 1
            else:
                failed += 1

        self.play_completion_sound()
        self.draw_message("BIOS Update Complete", f"Fixed: {fixed} | Failed: {failed}")
        pygame.display.flip()
        logging.info(f"BIOS update complete: {fixed} fixed, {failed} failed")
        pygame.time.wait(3000)

    def download_bios(self, bios_name):
        """Download a BIOS file from Myrient"""
        logging.info(f"Downloading BIOS: {bios_name}")

        download_url = BIOS_URL + urllib.parse.quote(bios_name + ".zip")
        dest_path = os.path.join(MAME_ROM_DIR, bios_name + ".zip")
        backup_path = dest_path + ".old"

        try:
            # Backup existing
            if os.path.exists(dest_path):
                shutil.copy2(dest_path, backup_path)

            # Download
            temp_path = dest_path + ".tmp"
            proc = subprocess.run(
                ['wget', '-q', '-O', temp_path, download_url],
                capture_output=True,
                timeout=120
            )

            if proc.returncode != 0:
                logging.error(f"Failed to download {bios_name}")
                if os.path.exists(backup_path):
                    shutil.move(backup_path, dest_path)
                return False

            # Replace
            shutil.move(temp_path, dest_path)

            # Remove backup on success
            if os.path.exists(backup_path):
                os.remove(backup_path)

            logging.info(f"BIOS {bios_name}: Updated successfully")
            return True

        except Exception as e:
            logging.error(f"Error updating BIOS {bios_name}: {e}")
            if os.path.exists(backup_path):
                shutil.move(backup_path, dest_path)
            return False

    def scan_for_needed_bios(self):
        """Scan broken ROMs to identify which BIOS files are needed"""
        logging.info("=" * 40)
        logging.info("Scanning for needed BIOS files")

        self.draw_message("Scanning ROMs...", "Identifying missing BIOS files")
        pygame.display.flip()

        # Collect all error messages from broken ROMs
        broken_roms = [r for r in self.local_roms if r[2] == STATUS_BROKEN]
        if not broken_roms:
            self.draw_message("No Broken ROMs", "Nothing to scan")
            pygame.display.flip()
            pygame.time.wait(2000)
            return

        # Find needed BIOS from error messages
        needed_bios = {}  # bios_name -> list of games needing it
        unmatched_files = set()

        for name, path, status, error in broken_roms:
            if error and "Missing:" in error:
                # Parse missing files from error
                missing_part = error.split("Missing:")[1].strip()
                missing_files = [f.strip() for f in missing_part.split(",")]

                for mf in missing_files:
                    # Check if we know which BIOS provides this file
                    bios_found = False
                    for pattern, bios_name in MISSING_FILE_TO_BIOS.items():
                        if pattern in mf or mf == pattern:
                            if bios_name not in needed_bios:
                                needed_bios[bios_name] = []
                            needed_bios[bios_name].append(name)
                            bios_found = True
                            break
                    if not bios_found:
                        unmatched_files.add(mf)

        if not needed_bios:
            msg = "No matching BIOS files found"
            if unmatched_files:
                msg += f" ({len(unmatched_files)} unknown files)"
            self.draw_message("Scan Complete", msg)
            pygame.display.flip()
            logging.info(f"Unmatched missing files: {unmatched_files}")
            pygame.time.wait(3000)
            return

        # Check which needed BIOS are missing or outdated
        myrient_bios = self.fetch_bios_sizes()
        to_download = []

        for bios_name, games in needed_bios.items():
            local_path = os.path.join(MAME_ROM_DIR, bios_name + ".zip")
            if bios_name in myrient_bios:
                myrient_size = myrient_bios[bios_name]
                if not os.path.exists(local_path):
                    to_download.append((bios_name, len(games), "MISSING"))
                    logging.info(f"BIOS {bios_name}: MISSING (needed by {len(games)} games)")
                else:
                    local_size = os.path.getsize(local_path)
                    if local_size < myrient_size * 0.9:
                        to_download.append((bios_name, len(games), "OUTDATED"))
                        logging.info(f"BIOS {bios_name}: OUTDATED (needed by {len(games)} games)")

        if not to_download:
            self.draw_message("Scan Complete", "All identified BIOS files present")
            pygame.display.flip()
            pygame.time.wait(2000)
            return

        # Log unmatched files
        if unmatched_files:
            logging.info(f"Unmatched missing files (no known BIOS): {unmatched_files}")

        # Show results and offer to download
        total = len(to_download)
        self.draw_message(f"Found {total} BIOS Files Needed",
                         f"{sum(g for _, g, _ in to_download)} games affected",
                         "Press [A] to download all or [B] to cancel")
        pygame.display.flip()

        # Wait for user input
        waiting = True
        while waiting:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.JOYBUTTONDOWN:
                    if event.button == 0:  # A - Download
                        waiting = False
                    elif event.button == 1:  # B - Cancel
                        return
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        waiting = False
                    elif event.key == pygame.K_ESCAPE:
                        return
            self.clock.tick(30)

        # Download needed BIOS
        fixed = 0
        failed = 0

        for i, (bios_name, game_count, status) in enumerate(to_download):
            self.draw_message(f"Downloading BIOS ({i+1}/{total})",
                             f"{bios_name} ({status})",
                             f"Downloaded: {fixed} | Failed: {failed}")
            pygame.display.flip()

            # Check for cancel
            for event in pygame.event.get():
                if event.type == pygame.JOYBUTTONDOWN and event.button == 1:
                    return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return

            if self.download_bios(bios_name):
                fixed += 1
            else:
                failed += 1

        self.play_completion_sound()
        self.draw_message("BIOS Download Complete",
                         f"Downloaded: {fixed} | Failed: {failed}",
                         "Re-scan ROMs to verify fixes")
        pygame.display.flip()
        logging.info(f"BIOS scan/download complete: {fixed} downloaded, {failed} failed")
        pygame.time.wait(3000)

    def repair_all_broken(self):
        """Repair all broken ROMs that are available on Myrient"""
        broken_roms = [r for r in self.local_roms if r[2] == STATUS_BROKEN and r[0] in self.myrient_roms]

        if not broken_roms:
            self.draw_message("Nothing to Fix", "No repairable broken ROMs found")
            pygame.display.flip()
            pygame.time.wait(2000)
            return

        total = len(broken_roms)
        fixed = 0
        failed = 0

        for i, (name, path, status, error) in enumerate(broken_roms):
            # Check for cancel
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.JOYBUTTONDOWN and event.button == 1:
                    self.draw_message("Cancelled", f"Fixed {fixed} of {total} ROMs")
                    pygame.display.flip()
                    pygame.time.wait(2000)
                    return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.draw_message("Cancelled", f"Fixed {fixed} of {total} ROMs")
                    pygame.display.flip()
                    pygame.time.wait(2000)
                    return

            self.draw_message(f"Fixing All Broken ({i+1}/{total})", name, f"Fixed: {fixed} | Failed: {failed} | [B] Cancel")
            pygame.display.flip()

            if self.repair_rom(name):
                fixed += 1
            else:
                failed += 1

        self.play_completion_sound()
        self.draw_message("Fix All Complete", f"Fixed: {fixed} | Failed: {failed}")
        pygame.display.flip()
        pygame.time.wait(3000)

    def repair_rom(self, rom_name):
        """Download replacement ROM from Myrient"""
        logging.info(f"Attempting to repair: {rom_name}")

        if rom_name not in self.myrient_roms:
            logging.warning(f"{rom_name}: Not available on Myrient")
            return False

        self.downloading = True
        self.download_game = rom_name
        self.download_progress = 0
        self.download_status = "Starting download..."

        download_url = BASE_URL + urllib.parse.quote(rom_name + ".zip")
        dest_path = os.path.join(MAME_ROM_DIR, rom_name + ".zip")
        backup_path = os.path.join(MAME_ROM_DIR, rom_name + ".zip.bak")

        try:
            # Backup original
            if os.path.exists(dest_path):
                shutil.copy2(dest_path, backup_path)
                self.download_status = "Backed up original..."

            # Get file size
            total_size = 0
            try:
                result = subprocess.run(
                    ['curl', '-sI', '-L', download_url],
                    capture_output=True, text=True, timeout=30
                )
                for line in result.stdout.split('\n'):
                    if line.lower().startswith('content-length:'):
                        total_size = int(line.split(':')[1].strip())
            except:
                pass

            # Download
            temp_path = dest_path + ".tmp"
            proc = subprocess.Popen(
                ['wget', '-O', temp_path, '-q', download_url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            track_process(proc)

            cancelled = False
            total_mb = total_size / (1024 * 1024) if total_size > 0 else 0

            while proc.poll() is None:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        proc.kill()
                        return False
                    if event.type == pygame.JOYBUTTONDOWN and event.button == 1:
                        proc.kill()
                        cancelled = True
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        proc.kill()
                        cancelled = True

                if cancelled:
                    self.download_status = "Cancelled"
                    break

                if os.path.exists(temp_path):
                    size = os.path.getsize(temp_path)
                    size_mb = size / (1024 * 1024)
                    if total_mb > 0:
                        self.download_progress = int((size / total_size) * 100)
                        self.download_status = f"Downloading... {size_mb:.1f} / {total_mb:.1f} MB"
                    else:
                        self.download_status = f"Downloading... {size_mb:.1f} MB"

                self.draw_download_progress()
                pygame.display.flip()
                self.clock.tick(5)

            if cancelled or proc.returncode != 0:
                # Restore backup
                if os.path.exists(backup_path):
                    shutil.move(backup_path, dest_path)
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                self.downloading = False
                return False

            # Replace original with new
            if os.path.exists(temp_path):
                shutil.move(temp_path, dest_path)

            # Remove backup on success
            if os.path.exists(backup_path):
                os.remove(backup_path)

            self.download_progress = 100
            self.download_status = "Complete! Testing..."
            self.draw_download_progress()
            pygame.display.flip()

            # Test the new ROM
            status, error = self.test_rom(Path(dest_path))

            if status == STATUS_OK:
                self.download_status = "Repair successful!"
                logging.info(f"{rom_name}: Repair successful!")
                self.play_completion_sound()
            else:
                self.download_status = f"Still broken: {error}"
                logging.warning(f"{rom_name}: Still broken after repair - {error}")
                logging.info(f"{rom_name}: This may require a BIOS file (neogeo.zip, qsound.zip, etc.)")

            self.draw_download_progress()
            pygame.display.flip()
            pygame.time.wait(2000)

            # Update local ROM status
            for i, (name, path, _, _) in enumerate(self.local_roms):
                if name == rom_name:
                    self.local_roms[i] = (name, path, status, error)
                    break

        except Exception as e:
            # Restore backup on error
            if os.path.exists(backup_path):
                shutil.move(backup_path, dest_path)
            self.downloading = False
            return False

        self.downloading = False
        return True

    def run(self):
        os.makedirs(MAME_ROM_DIR, exist_ok=True)

        logging.info("=" * 60)
        logging.info("MAME Romset Repairer started")
        logging.info(f"ROM directory: {MAME_ROM_DIR}")
        logging.info("=" * 60)

        # Check for FBNeo core
        if not os.path.exists(FBNEO_CORE):
            self.draw_message("Error", "FBNeo core not found", "Please install FBNeo in RetroArch")
            pygame.display.flip()
            pygame.time.wait(3000)
            pygame.quit()
            return 1

        # Fetch Myrient ROM list
        self.myrient_roms = self.fetch_myrient_list()
        if not self.myrient_roms:
            pygame.quit()
            return 1

        # Get local ROMs (without scanning yet)
        self.local_roms = self.get_local_roms()

        self.draw_message("Ready", f"Found {len(self.local_roms)} local ROMs",
                         f"{len(self.myrient_roms)} ROMs available on Myrient. Press [Y] to scan.")
        pygame.display.flip()
        pygame.time.wait(2000)

        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                if event.type == pygame.KEYDOWN:
                    if self.keyboard_active:
                        if event.key == pygame.K_ESCAPE:
                            self.keyboard_active = False
                        elif event.key == pygame.K_RETURN:
                            self.handle_keyboard_select()
                    else:
                        if event.key == pygame.K_ESCAPE:
                            running = False
                        elif event.key == pygame.K_RETURN:
                            filtered = self.get_filtered_roms()
                            if filtered and self.selected_index < len(filtered):
                                name, path, status, _ = filtered[self.selected_index]
                                if status == STATUS_BROKEN:
                                    self.repair_rom(name)
                                else:
                                    self.launch_game(name, path)
                        elif event.key == pygame.K_y:
                            self.keyboard_active = True
                            self.key_row = 0
                            self.key_col = 0
                        elif event.key == pygame.K_x:
                            self.cycle_filter()
                        elif event.key == pygame.K_s:
                            self.scan_roms()
                        elif event.key == pygame.K_b:
                            self.check_and_repair_bios()
                        elif event.key == pygame.K_n:
                            self.scan_for_needed_bios()

                if event.type == pygame.JOYBUTTONDOWN:
                    if self.keyboard_active:
                        if event.button == 0:  # A - Select key
                            self.handle_keyboard_select()
                        elif event.button == 1:  # B - Close keyboard
                            self.keyboard_active = False
                    else:
                        if event.button == 0:  # A - Launch or Repair
                            filtered = self.get_filtered_roms()
                            if filtered and self.selected_index < len(filtered):
                                name, path, status, _ = filtered[self.selected_index]
                                if status == STATUS_BROKEN:
                                    self.repair_rom(name)
                                else:
                                    self.launch_game(name, path)
                        elif event.button == 1:  # B - Quit
                            running = False
                        elif event.button == 2:  # X - Filter
                            self.cycle_filter()
                        elif event.button == 3:  # Y - Search
                            self.keyboard_active = True
                            self.key_row = 0
                            self.key_col = 0
                        elif event.button == 4 or event.button == 6:  # Select - Fix all broken
                            self.repair_all_broken()
                        elif event.button == 5 or event.button == 7:  # Start - Scan all
                            self.scan_roms()
                        elif event.button == 9:  # L1 - BIOS check (common BIOS)
                            self.check_and_repair_bios()
                        elif event.button == 10:  # R1 - BIOS scan (scan ROMs for needed BIOS)
                            self.scan_for_needed_bios()

            action = self.check_input()
            if action:
                if self.keyboard_active:
                    self.handle_keyboard_input(action)
                else:
                    self.handle_list_input(action)

            if self.scanning:
                self.draw_scan_progress()
            elif self.downloading:
                self.draw_download_progress()
            else:
                self.draw_main_menu()
                if self.keyboard_active:
                    self.draw_keyboard()

            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()
        return 0


def main():
    app = MameRepairUI()
    return app.run()


if __name__ == '__main__':
    sys.exit(main())
