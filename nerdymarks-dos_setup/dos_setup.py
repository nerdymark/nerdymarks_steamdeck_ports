#!/usr/bin/env python3
"""
nerdymark's DOS Setup Tool for ES-DE
https://nerdymark.com

Helps configure DOSBox-Pure games by:
- Enumerating DOS game ZIPs
- Detecting games that need installation (DEICE/LZH installers)
- Pre-extracting LZH archives for easier setup
- Previewing executables in each game
- Launching games for interactive setup
- Creating AUTOBOOT.DBP files for auto-launch

Uses pygame for Steam Deck controller-friendly UI
"""

import pygame
import os
import sys
import zipfile
import subprocess
import shutil
import logging
import signal
import atexit
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime

# Add shared module path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from gloomy_aesthetic import (
    GloomyBackground, draw_nerdymark_brand, draw_title_with_glow, create_panel,
    get_theme, VOID_BLACK, DEEP_GRAY, SMOKE_GRAY, MIST_GRAY, PALE_GRAY, FOG_WHITE
)
from git_update import UpdateChecker

# Logging setup
LOG_FILE = "/tmp/dos_setup.log"
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Paths
DOS_ROM_DIR = "/run/media/deck/SK256/Emulation/roms/dos"
SAVES_DIR = "/run/media/deck/SK256/Emulation/saves/retroarch/saves"
RETROARCH_CMD = "flatpak run org.libretro.RetroArch"
DOSBOX_PURE_CORE = "/home/deck/.var/app/org.libretro.RetroArch/config/retroarch/cores/dosbox_pure_libretro.so"

# Theme - DOS gets a retro amber/green theme
THEME = get_theme('dos')
ACCENT = THEME['accent']
ACCENT_DIM = THEME['accent_dim']
HIGHLIGHT = THEME['highlight']

# Additional colors
GREEN = (100, 200, 100)
YELLOW = (255, 220, 100)
RED = (200, 80, 80)
BLUE = (100, 150, 255)
ORANGE = (255, 180, 100)
PURPLE = (180, 100, 255)
CYAN = (100, 200, 200)

# Executable patterns
SETUP_PATTERNS = ['setup', 'install', 'setsound', 'config', 'setblast']
SKIP_PATTERNS = ['setup.exe', 'install.exe', 'uninstall.exe', 'config.exe', 'readme.exe',
                 'help.exe', 'order.exe', 'register.exe', 'catalog.exe', 'vendor.exe']

# LZH/DEICE installer patterns
LZH_INSTALLER_FILES = ['deice.exe', 'de-ice.exe', 'ice.exe', 'lha.exe', 'lharc.exe']
LZH_ARCHIVE_EXTENSIONS = ['.1', '.2', '.3', '.4', '.5', '.6', '.7', '.8', '.9', '.dat', '.lzh', '.lha']

# Process tracking for cleanup
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


def check_lha_available() -> bool:
    """Check if lha/lhasa is available for LZH extraction"""
    try:
        result = subprocess.run(['which', 'lha'], capture_output=True, text=True)
        return result.returncode == 0
    except:
        return False


def extract_lzh_file(lzh_path: str, dest_dir: str) -> Tuple[bool, str]:
    """Extract an LZH file using lha command"""
    try:
        result = subprocess.run(
            ['lha', '-xfw=' + dest_dir, lzh_path],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            return True, "Extraction successful"
        else:
            return False, result.stderr or "Unknown error"
    except subprocess.TimeoutExpired:
        return False, "Extraction timed out"
    except FileNotFoundError:
        return False, "lha command not found - install lhasa package"
    except Exception as e:
        return False, str(e)


class DOSGame:
    """Represents a DOS game ZIP file"""

    def __init__(self, zip_path: Path):
        self.zip_path = zip_path
        self.name = zip_path.stem
        self.executables: List[str] = []
        self.setup_exes: List[str] = []
        self.game_exes: List[str] = []
        self.autoboot_exe: Optional[str] = None
        self.is_configured = False

        # LZH installer detection
        self.has_lzh_installer = False
        self.lzh_decompressor: Optional[str] = None
        self.lzh_archives: List[str] = []

        # Save data detection
        self.has_save_data = False
        self.save_file_count = 0
        self.save_size_kb = 0

        self._scan_contents()
        self._check_configured()
        self._check_save_data()

        logger.debug(f"Loaded: {self.name} - {len(self.executables)} exes, "
                     f"lzh={self.has_lzh_installer}, configured={self.is_configured}, "
                     f"save_data={self.has_save_data}")

    def _scan_contents(self):
        """Scan ZIP for executable files and LZH installers"""
        try:
            with zipfile.ZipFile(self.zip_path, 'r') as zf:
                for name in zf.namelist():
                    lower = name.lower()
                    basename = os.path.basename(name)
                    basename_lower = basename.lower()

                    # Check for executables
                    if lower.endswith(('.exe', '.bat', '.com')):
                        if basename:
                            self.executables.append(basename)
                            if any(p in lower for p in SETUP_PATTERNS):
                                self.setup_exes.append(basename)
                            elif basename_lower not in [p.lower() for p in SKIP_PATTERNS]:
                                self.game_exes.append(basename)

                            # Check for LZH decompressor
                            if basename_lower in LZH_INSTALLER_FILES:
                                self.has_lzh_installer = True
                                self.lzh_decompressor = basename

                    # Check for LZH archives
                    ext = os.path.splitext(lower)[1]
                    if ext in LZH_ARCHIVE_EXTENSIONS:
                        self.lzh_archives.append(basename)

                # If we have LZH archives but no decompressor detected, still flag it
                if self.lzh_archives and not self.has_lzh_installer:
                    # Check if there's an install.bat that might use deice
                    if any('install' in e.lower() for e in self.executables):
                        self.has_lzh_installer = True

        except Exception as e:
            logger.error(f"Error scanning {self.zip_path}: {e}")

    def _check_configured(self):
        """Check if game has an AUTOBOOT.DBP configured"""
        save_path = Path(SAVES_DIR) / f"{self.name}.pure.zip"
        if save_path.exists():
            try:
                with zipfile.ZipFile(save_path, 'r') as zf:
                    if 'AUTOBOOT.DBP' in zf.namelist():
                        content = zf.read('AUTOBOOT.DBP').decode('utf-8', errors='ignore').strip()
                        if content:
                            self.autoboot_exe = content
                            self.is_configured = True
            except Exception as e:
                logger.error(f"Error checking config for {self.name}: {e}")

    def _check_save_data(self):
        """Check if game has persistent save data (installed files)"""
        save_path = Path(SAVES_DIR) / f"{self.name}.pure.zip"
        if save_path.exists():
            try:
                self.save_size_kb = save_path.stat().st_size // 1024
                with zipfile.ZipFile(save_path, 'r') as zf:
                    # Count files excluding AUTOBOOT.DBP
                    files = [n for n in zf.namelist() if n != 'AUTOBOOT.DBP']
                    self.save_file_count = len(files)
                    self.has_save_data = self.save_file_count > 0
            except Exception as e:
                logger.error(f"Error checking save data for {self.name}: {e}")

    def get_likely_game_exe(self) -> Optional[str]:
        """Guess the most likely main game executable"""
        if len(self.executables) == 1:
            return self.executables[0]

        non_setup = [e for e in self.executables
                     if e.lower() not in [p.lower() for p in SKIP_PATTERNS]
                     and e.lower() not in LZH_INSTALLER_FILES]
        if len(non_setup) == 1:
            return non_setup[0]

        # Check if game name is in executable name
        for exe in non_setup or self.executables:
            lower = exe.lower()
            game_words = self.name.lower().split()[0:2]
            for word in game_words:
                if len(word) > 3 and word in lower:
                    return exe

        if non_setup:
            return non_setup[0]
        return self.executables[0] if self.executables else None

    def get_install_status(self) -> Tuple[str, Tuple[int, int, int]]:
        """Get installation status label and color"""
        if self.is_configured and self.has_save_data:
            return "[READY]", GREEN
        elif self.is_configured:
            return "[CFG]", CYAN
        elif self.has_save_data:
            return "[DATA]", BLUE
        elif self.has_lzh_installer:
            return "[LZH]", ORANGE
        elif self.setup_exes:
            return "[SETUP]", YELLOW
        elif self.executables:
            return f"[{len(self.executables)}]", MIST_GRAY
        else:
            return "[?]", RED

    def set_autoboot(self, exe_name: str) -> bool:
        """Create/update AUTOBOOT.DBP in save file"""
        save_path = Path(SAVES_DIR) / f"{self.name}.pure.zip"
        autoboot_content = f"C:\\{exe_name.upper()}"

        logger.info(f"Setting autoboot for {self.name}: {autoboot_content}")

        try:
            existing_files = {}
            if save_path.exists():
                with zipfile.ZipFile(save_path, 'r') as zf:
                    for name in zf.namelist():
                        if name != 'AUTOBOOT.DBP':
                            existing_files[name] = zf.read(name)

            with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('AUTOBOOT.DBP', autoboot_content)
                for name, data in existing_files.items():
                    zf.writestr(name, data)

            self.autoboot_exe = autoboot_content
            self.is_configured = True
            return True
        except Exception as e:
            logger.error(f"Error setting autoboot for {self.name}: {e}")
            return False

    def clear_autoboot(self) -> bool:
        """Remove AUTOBOOT.DBP from save file"""
        save_path = Path(SAVES_DIR) / f"{self.name}.pure.zip"

        if not save_path.exists():
            self.autoboot_exe = None
            self.is_configured = False
            return True

        try:
            existing_files = {}
            with zipfile.ZipFile(save_path, 'r') as zf:
                for name in zf.namelist():
                    if name != 'AUTOBOOT.DBP':
                        existing_files[name] = zf.read(name)

            if existing_files:
                with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for name, data in existing_files.items():
                        zf.writestr(name, data)
            else:
                save_path.unlink()

            self.autoboot_exe = None
            self.is_configured = False
            return True
        except Exception as e:
            logger.error(f"Error clearing autoboot for {self.name}: {e}")
            return False

    def clear_save_data(self) -> bool:
        """Remove all save data for this game"""
        save_path = Path(SAVES_DIR) / f"{self.name}.pure.zip"

        if save_path.exists():
            try:
                save_path.unlink()
                self.autoboot_exe = None
                self.is_configured = False
                self.has_save_data = False
                self.save_file_count = 0
                self.save_size_kb = 0
                return True
            except Exception as e:
                logger.error(f"Error clearing save data for {self.name}: {e}")
                return False
        return True


class DOSSetupUI:
    def __init__(self):
        pygame.init()
        pygame.joystick.init()

        info = pygame.display.Info()
        self.width = info.current_w
        self.height = info.current_h
        self.screen = pygame.display.set_mode((self.width, self.height), pygame.FULLSCREEN)
        pygame.display.set_caption("nerdymark's DOS Setup Tool")

        self.font_large = pygame.font.Font(None, 48)
        self.font_medium = pygame.font.Font(None, 36)
        self.font_small = pygame.font.Font(None, 28)
        self.font_tiny = pygame.font.Font(None, 22)
        self.font_brand = pygame.font.Font(None, 24)

        self.joystick = None
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()

        self.games: List[DOSGame] = []
        self.filtered_games: List[DOSGame] = []
        self.selected_index = 0
        self.scroll_offset = 0
        self.visible_items = (self.height - 280) // 35

        self.view_mode = "list"
        self.selected_game: Optional[DOSGame] = None
        self.exe_select_index = 0

        self.filter_mode = "all"
        self.search_text = ""
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

        self.status_message = ""
        self.status_time = 0
        self.last_input_time = 0
        self.input_delay = 150
        self.clock = pygame.time.Clock()

        # Gloomy background
        self.background = GloomyBackground(self.width, self.height, accent_color=ACCENT)

        # Git update checker
        self.update_checker = UpdateChecker()
        self.update_banner_visible = False

        # LHA availability
        self.lha_available = check_lha_available()
        if not self.lha_available:
            logger.warning("lha command not found - LZH pre-extraction disabled")

    def load_games(self):
        """Load all DOS game ZIPs"""
        self.games = []
        dos_path = Path(DOS_ROM_DIR)
        logger.info(f"Loading games from {dos_path}")

        if dos_path.exists():
            zips = sorted(dos_path.glob("*.zip"), key=lambda x: x.name.lower())
            total = len(zips)
            logger.info(f"Found {total} DOS game ZIPs")

            for i, zip_path in enumerate(zips):
                if i % 100 == 0:
                    self.draw_loading(f"Loading games... {i}/{total}")
                    pygame.display.flip()
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            return
                self.games.append(DOSGame(zip_path))

            configured = sum(1 for g in self.games if g.is_configured)
            lzh_games = sum(1 for g in self.games if g.has_lzh_installer)
            logger.info(f"Loaded {len(self.games)} games, {configured} configured, {lzh_games} with LZH installers")
        else:
            logger.warning(f"DOS ROM directory not found: {dos_path}")

        self.apply_filter()

    def apply_filter(self):
        search = self.search_text.lower()
        self.filtered_games = []
        for game in self.games:
            if search and search not in game.name.lower():
                continue
            if self.filter_mode == "unconfigured" and game.is_configured:
                continue
            if self.filter_mode == "configured" and not game.is_configured:
                continue
            if self.filter_mode == "needs_setup" and not game.setup_exes:
                continue
            if self.filter_mode == "needs_install" and not game.has_lzh_installer:
                continue
            if self.filter_mode == "has_data" and not game.has_save_data:
                continue
            self.filtered_games.append(game)
        self.selected_index = 0
        self.scroll_offset = 0

    def draw_loading(self, message: str):
        self.background.update()
        self.background.draw(self.screen)
        draw_title_with_glow(self.screen, self.font_large, "NERDYMARK'S DOS SETUP", ACCENT, self.height // 2 - 50)
        msg_surf = self.font_medium.render(message, True, PALE_GRAY)
        self.screen.blit(msg_surf, (self.width // 2 - msg_surf.get_width() // 2, self.height // 2 + 10))
        draw_nerdymark_brand(self.screen, self.font_brand, ACCENT_DIM)

    def draw_message(self, title: str, message: str):
        self.background.update()
        self.background.draw(self.screen)
        draw_title_with_glow(self.screen, self.font_large, title, ACCENT, self.height // 2 - 50)
        msg_surf = self.font_medium.render(message, True, PALE_GRAY)
        self.screen.blit(msg_surf, (self.width // 2 - msg_surf.get_width() // 2, self.height // 2 + 10))
        draw_nerdymark_brand(self.screen, self.font_brand, ACCENT_DIM)

    def draw_status(self):
        if self.status_message and pygame.time.get_ticks() - self.status_time < 4000:
            surf = self.font_medium.render(self.status_message, True, YELLOW)
            panel = create_panel(surf.get_width() + 40, 40, border_color=ACCENT_DIM)
            self.screen.blit(panel, (self.width // 2 - surf.get_width() // 2 - 20, self.height - 95))
            self.screen.blit(surf, (self.width // 2 - surf.get_width() // 2, self.height - 90))

    def set_status(self, message: str):
        self.status_message = message
        self.status_time = pygame.time.get_ticks()

    def draw_update_banner(self):
        """Draw update available notification banner at top of screen"""
        if not self.update_banner_visible:
            return
        banner_height = 30
        banner_surface = pygame.Surface((self.width, banner_height), pygame.SRCALPHA)
        pygame.draw.rect(banner_surface, (80, 60, 20, 200), (0, 0, self.width, banner_height))
        msg = self.update_checker.message
        if self.update_checker.can_update:
            msg += " - Press SELECT to update"
        text_surf = self.font_tiny.render(msg, True, (255, 220, 100))
        banner_surface.blit(text_surf, (self.width // 2 - text_surf.get_width() // 2, 6))
        self.screen.blit(banner_surface, (0, 0))

    def check_for_updates(self):
        """Check for updates and show dialog if update can be applied"""
        self.draw_message("Checking for updates...", "Please wait")
        pygame.display.flip()

        status = self.update_checker.check()
        if status['update_available']:
            self.update_banner_visible = True
            if status['can_update']:
                return self.offer_update_dialog()
        return False

    def offer_update_dialog(self):
        """Show dialog offering to update."""
        selected = 0
        options = ["Update Now", "Skip"]

        while True:
            self.background.update()
            self.background.draw(self.screen)
            draw_title_with_glow(self.screen, self.font_large, "UPDATE AVAILABLE", ACCENT, self.height // 2 - 100)

            msg = f"{self.update_checker._status['behind']} new commits available"
            msg_surf = self.font_medium.render(msg, True, PALE_GRAY)
            self.screen.blit(msg_surf, (self.width // 2 - msg_surf.get_width() // 2, self.height // 2 - 40))

            for i, opt in enumerate(options):
                y = self.height // 2 + 20 + i * 50
                color = ACCENT if i == selected else MIST_GRAY
                opt_surf = self.font_medium.render(f"{'> ' if i == selected else '  '}{opt}", True, color)
                self.screen.blit(opt_surf, (self.width // 2 - opt_surf.get_width() // 2, y))

            draw_nerdymark_brand(self.screen, self.font_brand, ACCENT_DIM)
            pygame.display.flip()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_UP:
                        selected = max(0, selected - 1)
                    elif event.key == pygame.K_DOWN:
                        selected = min(len(options) - 1, selected + 1)
                    elif event.key == pygame.K_RETURN:
                        if selected == 0:
                            return self.perform_update()
                        return False
                    elif event.key == pygame.K_ESCAPE:
                        return False
                if event.type == pygame.JOYBUTTONDOWN:
                    if event.button == 0:
                        if selected == 0:
                            return self.perform_update()
                        return False
                    elif event.button == 1:
                        return False

            if self.joystick and self.joystick.get_numhats() > 0:
                hat = self.joystick.get_hat(0)
                if hat[1] == 1:
                    selected = max(0, selected - 1)
                    pygame.time.wait(150)
                elif hat[1] == -1:
                    selected = min(len(options) - 1, selected + 1)
                    pygame.time.wait(150)

            self.clock.tick(30)

    def perform_update(self):
        """Perform the git update and show result"""
        self.draw_message("Updating...", "Pulling latest changes from git")
        pygame.display.flip()

        success, message = self.update_checker.update()

        if success:
            self.draw_message("Update Complete!", "Please restart the tool")
            pygame.display.flip()
            pygame.time.wait(3000)
            pygame.quit()
            sys.exit(0)
        else:
            self.draw_message("Update Failed", message[:50])
            pygame.display.flip()
            pygame.time.wait(3000)
            return False

    def draw_main_list(self):
        self.background.update()
        self.background.draw(self.screen)

        draw_title_with_glow(self.screen, self.font_large, "NERDYMARK'S DOS SETUP", ACCENT, 15)

        # Stats
        configured = sum(1 for g in self.games if g.is_configured)
        lzh_count = sum(1 for g in self.games if g.has_lzh_installer)
        stats = f"{len(self.games)} games | {configured} configured | {lzh_count} need install | {len(self.filtered_games)} shown"
        stats_surf = self.font_small.render(stats, True, MIST_GRAY)
        self.screen.blit(stats_surf, (self.width // 2 - stats_surf.get_width() // 2, 60))

        # Filter indicator
        filter_labels = {
            "all": "ALL",
            "unconfigured": "UNCONFIGURED",
            "configured": "CONFIGURED",
            "needs_setup": "HAS SETUP.EXE",
            "needs_install": "NEEDS INSTALL (LZH)",
            "has_data": "HAS SAVE DATA"
        }
        filter_text = f"Filter: {filter_labels.get(self.filter_mode, self.filter_mode.upper())}"
        filter_color = YELLOW if self.filter_mode != "all" else MIST_GRAY
        filter_surf = self.font_small.render(filter_text, True, filter_color)
        self.screen.blit(filter_surf, (50, 95))

        # Search box
        search_panel = create_panel(self.width - 300, 30, border_color=ACCENT_DIM if self.keyboard_active else SMOKE_GRAY)
        self.screen.blit(search_panel, (250, 90))
        search_label = f"Search: {self.search_text}" + ("_" if not self.keyboard_active else "")
        search_surf = self.font_small.render(search_label, True, HIGHLIGHT if self.search_text else PALE_GRAY)
        self.screen.blit(search_surf, (260, 95))

        # Game list panel
        list_panel = create_panel(self.width - 80, self.height - 260, border_color=SMOKE_GRAY)
        self.screen.blit(list_panel, (40, 130))

        list_top = 138
        for i in range(self.visible_items):
            idx = i + self.scroll_offset
            if idx >= len(self.filtered_games):
                break

            game = self.filtered_games[idx]
            y = list_top + i * 35

            if idx == self.selected_index:
                highlight = pygame.Surface((self.width - 100, 33), pygame.SRCALPHA)
                pygame.draw.rect(highlight, (*ACCENT_DIM, 120), (0, 0, self.width - 100, 33), border_radius=3)
                self.screen.blit(highlight, (50, y))

            # Status indicator
            indicator, ind_color = game.get_install_status()
            ind_surf = self.font_tiny.render(indicator, True, ind_color)
            self.screen.blit(ind_surf, (60, y + 8))

            # Game name
            name = game.name[:70] + "..." if len(game.name) > 70 else game.name
            color = HIGHLIGHT if idx == self.selected_index else PALE_GRAY
            name_surf = self.font_small.render(name, True, color)
            self.screen.blit(name_surf, (130, y + 6))

        # Scrollbar
        if len(self.filtered_games) > self.visible_items:
            bar_height = self.height - 270
            handle_height = max(30, bar_height * self.visible_items // len(self.filtered_games))
            handle_pos = bar_height * self.scroll_offset // max(1, len(self.filtered_games) - self.visible_items)
            pygame.draw.rect(self.screen, DEEP_GRAY, (self.width - 30, 135, 10, bar_height), border_radius=5)
            pygame.draw.rect(self.screen, ACCENT_DIM, (self.width - 30, 135 + handle_pos, 10, handle_height), border_radius=5)

        # Legend
        legend_y = self.height - 120
        legend_items = [
            ("[READY]", "Configured + Installed", GREEN),
            ("[CFG]", "Autoboot Set", CYAN),
            ("[DATA]", "Has Save Data", BLUE),
            ("[LZH]", "Needs Install", ORANGE),
            ("[SETUP]", "Has Setup.exe", YELLOW),
        ]
        x = 50
        for indicator, desc, color in legend_items:
            ind_surf = self.font_tiny.render(indicator, True, color)
            self.screen.blit(ind_surf, (x, legend_y))
            desc_surf = self.font_tiny.render(desc, True, MIST_GRAY)
            self.screen.blit(desc_surf, (x + ind_surf.get_width() + 5, legend_y))
            x += ind_surf.get_width() + desc_surf.get_width() + 25

        # Controls
        controls = "[A] Details  [X] Quick Config  [Y] Search  [LB/RB] Filter  [B] Quit"
        controls_surf = self.font_small.render(controls, True, MIST_GRAY)
        self.screen.blit(controls_surf, (self.width // 2 - controls_surf.get_width() // 2, self.height - 40))

        draw_nerdymark_brand(self.screen, self.font_brand, ACCENT_DIM)
        self.draw_update_banner()
        self.draw_status()

    def draw_detail_view(self):
        if not self.selected_game:
            return

        self.background.update()
        self.background.draw(self.screen)
        game = self.selected_game

        draw_title_with_glow(self.screen, self.font_large, "GAME DETAILS", ACCENT, 15)

        # Game name
        name_surf = self.font_medium.render(game.name[:55], True, FOG_WHITE)
        self.screen.blit(name_surf, (50, 70))

        # Status panel
        status_panel = create_panel(self.width - 100, 80, border_color=SMOKE_GRAY)
        self.screen.blit(status_panel, (50, 105))

        y = 115
        if game.is_configured:
            status = f"Autoboot: {game.autoboot_exe}"
            status_color = GREEN
        else:
            status = "Not configured - needs autoboot executable set"
            status_color = ORANGE
        status_surf = self.font_small.render(status, True, status_color)
        self.screen.blit(status_surf, (60, y))

        y += 25
        if game.has_save_data:
            save_info = f"Save Data: {game.save_file_count} files ({game.save_size_kb} KB) - Game is installed!"
            save_color = GREEN
        else:
            save_info = "No save data - Game may need installation first"
            save_color = MIST_GRAY
        save_surf = self.font_small.render(save_info, True, save_color)
        self.screen.blit(save_surf, (60, y))

        y += 25
        if game.has_lzh_installer:
            lzh_info = f"LZH Installer: {game.lzh_decompressor or 'detected'} ({len(game.lzh_archives)} archives)"
            lzh_surf = self.font_small.render(lzh_info, True, ORANGE)
            self.screen.blit(lzh_surf, (60, y))
            y += 25

        # Executables section
        y = 200
        exe_title = self.font_medium.render("Executables:", True, YELLOW)
        self.screen.blit(exe_title, (50, y))
        y += 35

        if game.setup_exes:
            setup_label = self.font_small.render("Setup/Install:", True, BLUE)
            self.screen.blit(setup_label, (70, y))
            y += 22
            for exe in game.setup_exes[:4]:
                exe_surf = self.font_small.render(f"  {exe}", True, MIST_GRAY)
                self.screen.blit(exe_surf, (70, y))
                y += 20
            y += 8

        if game.game_exes:
            game_label = self.font_small.render("Game:", True, GREEN)
            self.screen.blit(game_label, (70, y))
            y += 22
            for exe in game.game_exes[:6]:
                exe_surf = self.font_small.render(f"  {exe}", True, PALE_GRAY)
                self.screen.blit(exe_surf, (70, y))
                y += 20

        # Suggested executable
        suggested = game.get_likely_game_exe()
        if suggested:
            y += 15
            suggest_surf = self.font_small.render(f"Suggested autoboot: {suggested}", True, YELLOW)
            self.screen.blit(suggest_surf, (50, y))

        # Help text panel
        help_panel = create_panel(self.width - 100, 130, border_color=SMOKE_GRAY)
        self.screen.blit(help_panel, (50, self.height - 220))

        help_y = self.height - 210
        help_title = self.font_small.render("DOSBox-Pure Keyboard Tips:", True, CYAN)
        self.screen.blit(help_title, (60, help_y))

        help_lines = [
            "L3 (click left stick) = On-screen keyboard",
            "Scroll Lock = Game Focus mode (direct keyboard input)",
            "PAD MAPPER = Bind keys to controller buttons",
            "SoundBlaster: Port 220, IRQ 7, DMA 1, High DMA 5"
        ]
        for i, line in enumerate(help_lines):
            line_surf = self.font_tiny.render(line, True, MIST_GRAY)
            self.screen.blit(line_surf, (70, help_y + 25 + i * 20))

        # Controls
        if game.is_configured:
            controls = "[A] Change Autoboot  [X] Launch  [Y] Launch  [R1] Clear Data  [B] Back"
        else:
            controls = "[A] Set Autoboot  [X] Launch (Setup)  [Y] Launch (Play)  [B] Back"
        controls_surf = self.font_small.render(controls, True, MIST_GRAY)
        self.screen.blit(controls_surf, (self.width // 2 - controls_surf.get_width() // 2, self.height - 40))

        draw_nerdymark_brand(self.screen, self.font_brand, ACCENT_DIM)
        self.draw_status()

    def draw_exe_select(self):
        if not self.selected_game:
            return

        self.background.update()
        self.background.draw(self.screen)
        game = self.selected_game

        draw_title_with_glow(self.screen, self.font_large, "SELECT EXECUTABLE", ACCENT, 15)

        subtitle = self.font_medium.render(f"For: {game.name[:50]}", True, PALE_GRAY)
        self.screen.blit(subtitle, (self.width // 2 - subtitle.get_width() // 2, 60))

        # List panel
        list_panel = create_panel(self.width - 200, self.height - 180, border_color=SMOKE_GRAY)
        self.screen.blit(list_panel, (100, 100))

        y = 115
        for i, exe in enumerate(game.executables):
            if y > self.height - 130:
                break

            if i == self.exe_select_index:
                highlight = pygame.Surface((self.width - 220, 35), pygame.SRCALPHA)
                pygame.draw.rect(highlight, (*ACCENT_DIM, 120), (0, 0, self.width - 220, 35), border_radius=3)
                self.screen.blit(highlight, (110, y))

            lower = exe.lower()
            if lower in LZH_INSTALLER_FILES:
                prefix = "[LZH]"
                color = ORANGE
            elif any(p in lower for p in SETUP_PATTERNS):
                prefix = "[SETUP]"
                color = BLUE
            else:
                prefix = "[GAME]"
                color = GREEN

            prefix_surf = self.font_small.render(prefix, True, color)
            self.screen.blit(prefix_surf, (120, y + 6))

            exe_color = HIGHLIGHT if i == self.exe_select_index else PALE_GRAY
            exe_surf = self.font_medium.render(exe, True, exe_color)
            self.screen.blit(exe_surf, (210, y + 4))

            y += 38

        controls = "[A] Select  [B] Cancel"
        controls_surf = self.font_small.render(controls, True, MIST_GRAY)
        self.screen.blit(controls_surf, (self.width // 2 - controls_surf.get_width() // 2, self.height - 40))

        draw_nerdymark_brand(self.screen, self.font_brand, ACCENT_DIM)

    def draw_keyboard(self):
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((*VOID_BLACK, 220))
        self.screen.blit(overlay, (0, 0))

        kb_width = 600
        kb_height = 300
        kb_x = (self.width - kb_width) // 2
        kb_y = (self.height - kb_height) // 2

        kb_panel = create_panel(kb_width, kb_height, border_color=ACCENT_DIM)
        self.screen.blit(kb_panel, (kb_x, kb_y))

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

                label = " " if key == "SPACE" else key
                key_surf = self.font_small.render(label, True, VOID_BLACK if selected else PALE_GRAY)
                self.screen.blit(key_surf, (x + w // 2 - key_surf.get_width() // 2,
                                            y + key_size // 2 - key_surf.get_height() // 2))

    def launch_game(self, game: DOSGame):
        """Launch game in DOSBox-Pure via RetroArch"""
        # Show keyboard tips before launching
        self.draw_message("LAUNCHING GAME", "L3=On-Screen Keyboard | Scroll Lock=Game Focus")
        pygame.display.flip()
        pygame.time.wait(2000)

        cmd = f'{RETROARCH_CMD} -L "{DOSBOX_PURE_CORE}" "{game.zip_path}"'
        logger.info(f"Launching game: {game.name}")
        logger.info(f"Command: {cmd}")

        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            logger.debug(f"RetroArch exit code: {result.returncode}")

            # Refresh game state
            game._check_configured()
            game._check_save_data()

            if game.is_configured:
                self.set_status(f"Configured: {game.autoboot_exe}")
            elif game.has_save_data:
                self.set_status(f"Game has save data ({game.save_file_count} files)")
            else:
                self.set_status("Game exited - no changes detected")

        except Exception as e:
            logger.error(f"Launch failed for {game.name}: {e}")
            self.set_status(f"Launch failed: {e}")

    def quick_config(self, game: DOSGame):
        """Auto-configure game with best-guess executable"""
        exe = game.get_likely_game_exe()
        if exe:
            if game.set_autoboot(exe):
                self.set_status(f"Set autoboot: {exe}")
            else:
                self.set_status("Failed to set autoboot")
        else:
            self.set_status("No executable found!")

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
            self.apply_filter()
        elif key == "DEL":
            self.search_text = self.search_text[:-1]
        elif key == "SPACE":
            self.search_text += " "
        else:
            self.search_text += key.lower()

    def handle_list_input(self, action):
        if action == "UP":
            if self.selected_index > 0:
                self.selected_index -= 1
                if self.selected_index < self.scroll_offset:
                    self.scroll_offset = self.selected_index
        elif action == "DOWN":
            if self.selected_index < len(self.filtered_games) - 1:
                self.selected_index += 1
                if self.selected_index >= self.scroll_offset + self.visible_items:
                    self.scroll_offset = self.selected_index - self.visible_items + 1

    def handle_exe_select_input(self, action):
        if not self.selected_game:
            return
        if action == "UP":
            self.exe_select_index = max(0, self.exe_select_index - 1)
        elif action == "DOWN":
            self.exe_select_index = min(len(self.selected_game.executables) - 1,
                                        self.exe_select_index + 1)

    def cycle_filter(self, direction: int):
        modes = ["all", "unconfigured", "configured", "needs_setup", "needs_install", "has_data"]
        idx = modes.index(self.filter_mode)
        idx = (idx + direction) % len(modes)
        self.filter_mode = modes[idx]
        logger.info(f"Filter changed to: {self.filter_mode}")
        self.apply_filter()

    def run(self):
        os.makedirs(DOS_ROM_DIR, exist_ok=True)
        os.makedirs(SAVES_DIR, exist_ok=True)

        # Check for updates at startup
        self.check_for_updates()

        self.draw_loading("Starting up...")
        pygame.display.flip()
        self.load_games()

        if not self.games:
            self.draw_loading("No DOS games found in roms/dos/")
            pygame.display.flip()
            pygame.time.wait(3000)
            pygame.quit()
            return 1

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
                    elif self.view_mode == "list":
                        if event.key == pygame.K_ESCAPE:
                            running = False
                        elif event.key == pygame.K_RETURN and self.filtered_games:
                            self.selected_game = self.filtered_games[self.selected_index]
                            self.view_mode = "detail"
                        elif event.key == pygame.K_y:
                            self.keyboard_active = True
                    elif self.view_mode == "detail":
                        if event.key == pygame.K_ESCAPE:
                            self.view_mode = "list"
                    elif self.view_mode == "exe_select":
                        if event.key == pygame.K_ESCAPE:
                            self.view_mode = "detail"
                        elif event.key == pygame.K_RETURN and self.selected_game:
                            exe = self.selected_game.executables[self.exe_select_index]
                            self.selected_game.set_autoboot(exe)
                            self.set_status(f"Set autoboot: {exe}")
                            self.view_mode = "detail"

                if event.type == pygame.JOYBUTTONDOWN:
                    if self.keyboard_active:
                        if event.button == 0:
                            self.handle_keyboard_select()
                        elif event.button == 1:
                            self.keyboard_active = False
                    elif self.view_mode == "list":
                        if event.button == 0 and self.filtered_games:
                            self.selected_game = self.filtered_games[self.selected_index]
                            self.view_mode = "detail"
                        elif event.button == 1:
                            running = False
                        elif event.button == 2 and self.filtered_games:
                            game = self.filtered_games[self.selected_index]
                            self.quick_config(game)
                        elif event.button == 3:
                            self.keyboard_active = True
                            self.key_row = 0
                            self.key_col = 0
                        elif event.button == 4:
                            self.cycle_filter(-1)
                        elif event.button == 5:
                            self.cycle_filter(1)
                        elif event.button == 6:  # SELECT - update
                            if self.update_banner_visible and self.update_checker.can_update:
                                self.perform_update()
                    elif self.view_mode == "detail":
                        if event.button == 0 and self.selected_game:
                            self.exe_select_index = 0
                            self.view_mode = "exe_select"
                        elif event.button == 1:
                            self.view_mode = "list"
                        elif event.button == 2 and self.selected_game:
                            self.launch_game(self.selected_game)
                        elif event.button == 3 and self.selected_game:
                            self.launch_game(self.selected_game)
                        elif event.button == 5 and self.selected_game:  # R1 - clear save data
                            if self.selected_game.clear_save_data():
                                self.set_status("Save data cleared")
                            else:
                                self.set_status("Failed to clear save data")
                    elif self.view_mode == "exe_select":
                        if event.button == 0 and self.selected_game:
                            exe = self.selected_game.executables[self.exe_select_index]
                            self.selected_game.set_autoboot(exe)
                            self.set_status(f"Set autoboot: {exe}")
                            self.view_mode = "detail"
                        elif event.button == 1:
                            self.view_mode = "detail"

            action = self.check_input()
            if action:
                if self.keyboard_active:
                    self.handle_keyboard_input(action)
                elif self.view_mode == "list":
                    self.handle_list_input(action)
                elif self.view_mode == "exe_select":
                    self.handle_exe_select_input(action)

            if self.view_mode == "list":
                self.draw_main_list()
                if self.keyboard_active:
                    self.draw_keyboard()
            elif self.view_mode == "detail":
                self.draw_detail_view()
            elif self.view_mode == "exe_select":
                self.draw_exe_select()

            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()
        return 0


def main():
    logger.info("=" * 60)
    logger.info("nerdymark's DOS Setup Tool starting")
    logger.info(f"Log file: {LOG_FILE}")
    logger.info(f"DOS ROM dir: {DOS_ROM_DIR}")
    logger.info(f"Saves dir: {SAVES_DIR}")
    logger.info("=" * 60)

    app = DOSSetupUI()
    result = app.run()

    logger.info(f"DOS Setup Tool exiting with code {result}")
    return result


if __name__ == '__main__':
    sys.exit(main())
