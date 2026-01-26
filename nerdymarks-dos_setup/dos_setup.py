#!/usr/bin/env python3
"""
nerdymark's DOS Setup Tool for ES-DE
https://nerdymark.com

Helps configure DOSBox-Pure games by:
- Enumerating DOS game ZIPs
- Previewing executables in each game
- Launching games for interactive setup (SETUP.EXE)
- Creating AUTOBOOT.DBP files for auto-launch

Uses pygame for Steam Deck controller-friendly UI
"""

import pygame
import os
import sys
import zipfile
import subprocess
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime

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

# Executable patterns
SETUP_PATTERNS = ['setup', 'install', 'setsound', 'config', 'setblast']
SKIP_PATTERNS = ['setup.exe', 'install.exe', 'uninstall.exe', 'config.exe', 'readme.exe',
                 'help.exe', 'order.exe', 'register.exe', 'catalog.exe', 'vendor.exe']

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (100, 200, 100)
DARK_GREEN = (0, 100, 0)
GRAY = (128, 128, 128)
DARK_GRAY = (40, 40, 40)
LIGHT_GRAY = (60, 60, 60)
YELLOW = (255, 255, 100)
RED = (255, 100, 100)
BLUE = (100, 150, 255)
ORANGE = (255, 180, 100)
PURPLE = (180, 100, 255)


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
        self._scan_executables()
        self._check_configured()
        logger.debug(f"Loaded game: {self.name} - {len(self.executables)} exes, configured={self.is_configured}")

    def _scan_executables(self):
        """Scan ZIP for executable files"""
        try:
            with zipfile.ZipFile(self.zip_path, 'r') as zf:
                for name in zf.namelist():
                    lower = name.lower()
                    if lower.endswith(('.exe', '.bat', '.com')):
                        basename = os.path.basename(name)
                        if basename:
                            self.executables.append(basename)
                            if any(p in lower for p in SETUP_PATTERNS):
                                self.setup_exes.append(basename)
                            elif basename.lower() not in [p.lower() for p in SKIP_PATTERNS]:
                                self.game_exes.append(basename)
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
                            logger.debug(f"Found autoboot for {self.name}: {content}")
            except Exception as e:
                logger.error(f"Error checking config for {self.name}: {e}")

    def get_likely_game_exe(self) -> Optional[str]:
        """Guess the most likely main game executable"""
        if len(self.executables) == 1:
            return self.executables[0]

        non_setup = [e for e in self.executables
                     if e.lower() not in [p.lower() for p in SKIP_PATTERNS]]
        if len(non_setup) == 1:
            return non_setup[0]

        # Check if game name is in executable name
        for exe in self.executables:
            lower = exe.lower()
            game_words = self.name.lower().split()[0:2]
            for word in game_words:
                if len(word) > 3 and word in lower:
                    return exe

        if non_setup:
            return non_setup[0]
        return self.executables[0] if self.executables else None

    def set_autoboot(self, exe_name: str) -> bool:
        """Create/update AUTOBOOT.DBP in save file"""
        save_path = Path(SAVES_DIR) / f"{self.name}.pure.zip"
        autoboot_content = f"C:\\{exe_name.upper()}"

        logger.info(f"Setting autoboot for {self.name}: {autoboot_content}")
        logger.info(f"Save path: {save_path}")

        try:
            existing_files = {}
            if save_path.exists():
                with zipfile.ZipFile(save_path, 'r') as zf:
                    for name in zf.namelist():
                        if name != 'AUTOBOOT.DBP':
                            existing_files[name] = zf.read(name)
                logger.debug(f"Preserving {len(existing_files)} existing files in save")

            with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('AUTOBOOT.DBP', autoboot_content)
                for name, data in existing_files.items():
                    zf.writestr(name, data)

            self.autoboot_exe = autoboot_content
            self.is_configured = True
            logger.info(f"Successfully set autoboot for {self.name}")
            return True
        except Exception as e:
            logger.error(f"Error setting autoboot for {self.name}: {e}")
            return False

    def clear_autoboot(self) -> bool:
        """Remove AUTOBOOT.DBP from save file"""
        save_path = Path(SAVES_DIR) / f"{self.name}.pure.zip"
        logger.info(f"Clearing autoboot for {self.name}")

        if not save_path.exists():
            logger.debug(f"No save file exists for {self.name}")
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
                logger.debug(f"Removed AUTOBOOT.DBP, kept {len(existing_files)} other files")
            else:
                save_path.unlink()
                logger.debug(f"Deleted empty save file for {self.name}")

            self.autoboot_exe = None
            self.is_configured = False
            logger.info(f"Successfully cleared autoboot for {self.name}")
            return True
        except Exception as e:
            logger.error(f"Error clearing autoboot for {self.name}: {e}")
            return False


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

        self.joystick = None
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()

        self.games: List[DOSGame] = []
        self.filtered_games: List[DOSGame] = []
        self.selected_index = 0
        self.scroll_offset = 0
        self.visible_items = (self.height - 250) // 35

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
            logger.info(f"Loaded {len(self.games)} games, {configured} configured")
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
            self.filtered_games.append(game)
        self.selected_index = 0
        self.scroll_offset = 0
        logger.debug(f"Filter applied: mode={self.filter_mode}, search='{self.search_text}', results={len(self.filtered_games)}")

    def draw_loading(self, message: str):
        self.screen.fill(BLACK)
        title = self.font_large.render("NERDYMARK'S DOS SETUP", True, PURPLE)
        msg = self.font_medium.render(message, True, WHITE)
        self.screen.blit(title, (self.width//2 - title.get_width()//2, self.height//2 - 50))
        self.screen.blit(msg, (self.width//2 - msg.get_width()//2, self.height//2 + 10))

    def draw_status(self):
        if self.status_message and pygame.time.get_ticks() - self.status_time < 3000:
            surf = self.font_medium.render(self.status_message, True, YELLOW)
            pygame.draw.rect(self.screen, DARK_GRAY,
                           (self.width//2 - surf.get_width()//2 - 20, self.height - 90,
                            surf.get_width() + 40, 40), border_radius=5)
            self.screen.blit(surf, (self.width//2 - surf.get_width()//2, self.height - 85))

    def set_status(self, message: str):
        self.status_message = message
        self.status_time = pygame.time.get_ticks()

    def draw_main_list(self):
        self.screen.fill(BLACK)

        title = self.font_large.render("NERDYMARK'S DOS SETUP", True, PURPLE)
        self.screen.blit(title, (self.width//2 - title.get_width()//2, 15))

        configured = sum(1 for g in self.games if g.is_configured)
        stats = f"{len(self.games)} games | {configured} configured | {len(self.filtered_games)} shown"
        stats_surf = self.font_small.render(stats, True, GRAY)
        self.screen.blit(stats_surf, (self.width//2 - stats_surf.get_width()//2, 60))

        filter_labels = {
            "all": "ALL",
            "unconfigured": "UNCONFIGURED",
            "configured": "CONFIGURED",
            "needs_setup": "NEEDS SETUP"
        }
        filter_text = f"Filter: {filter_labels.get(self.filter_mode, self.filter_mode.upper())}"
        filter_color = YELLOW if self.filter_mode != "all" else GRAY
        filter_surf = self.font_small.render(filter_text, True, filter_color)
        self.screen.blit(filter_surf, (50, 95))

        search_label = f"Search: {self.search_text}" + ("_" if not self.keyboard_active else "")
        search_surf = self.font_small.render(search_label, True, YELLOW if self.search_text else WHITE)
        pygame.draw.rect(self.screen, DARK_GRAY, (200, 90, self.width - 250, 30))
        self.screen.blit(search_surf, (210, 95))

        list_top = 130
        for i in range(self.visible_items):
            idx = i + self.scroll_offset
            if idx >= len(self.filtered_games):
                break

            game = self.filtered_games[idx]
            y = list_top + i * 35

            if idx == self.selected_index:
                pygame.draw.rect(self.screen, DARK_GREEN, (50, y, self.width - 100, 33))

            if game.is_configured:
                indicator = "[OK]"
                ind_color = GREEN
            elif game.setup_exes:
                # Has setup/install exes - may need configuration
                indicator = "[CFG]"
                ind_color = BLUE
            elif game.executables:
                indicator = f"[{len(game.executables)}]"
                ind_color = ORANGE
            else:
                indicator = "[?]"
                ind_color = RED

            ind_surf = self.font_tiny.render(indicator, True, ind_color)
            self.screen.blit(ind_surf, (60, y + 8))

            name = game.name[:70] + "..." if len(game.name) > 70 else game.name
            color = WHITE if idx != self.selected_index else GREEN
            name_surf = self.font_small.render(name, True, color)
            self.screen.blit(name_surf, (120, y + 6))

        if len(self.filtered_games) > self.visible_items:
            bar_height = self.height - 250
            handle_height = max(30, bar_height * self.visible_items // len(self.filtered_games))
            handle_pos = bar_height * self.scroll_offset // max(1, len(self.filtered_games) - self.visible_items)
            pygame.draw.rect(self.screen, DARK_GRAY, (self.width - 30, 130, 10, bar_height))
            pygame.draw.rect(self.screen, PURPLE, (self.width - 30, 130 + handle_pos, 10, handle_height))

        controls = "[A] Details  [X] Quick Config  [Y] Search  [LB/RB] Filter  [B] Quit"
        controls_surf = self.font_small.render(controls, True, GRAY)
        self.screen.blit(controls_surf, (self.width//2 - controls_surf.get_width()//2, self.height - 40))

        self.draw_status()

    def draw_detail_view(self):
        if not self.selected_game:
            return

        self.screen.fill(BLACK)
        game = self.selected_game

        title = self.font_large.render("GAME DETAILS", True, PURPLE)
        self.screen.blit(title, (self.width//2 - title.get_width()//2, 15))

        name_surf = self.font_medium.render(game.name[:60], True, WHITE)
        self.screen.blit(name_surf, (50, 70))

        if game.is_configured:
            status = f"Configured: {game.autoboot_exe}"
            status_color = GREEN
        else:
            status = "Not configured"
            status_color = ORANGE
        status_surf = self.font_small.render(status, True, status_color)
        self.screen.blit(status_surf, (50, 110))

        exe_title = self.font_medium.render("Executables:", True, YELLOW)
        self.screen.blit(exe_title, (50, 160))

        y = 200
        if game.setup_exes:
            setup_label = self.font_small.render("Setup/Install:", True, BLUE)
            self.screen.blit(setup_label, (70, y))
            y += 25
            for exe in game.setup_exes[:5]:
                exe_surf = self.font_small.render(f"  {exe}", True, GRAY)
                self.screen.blit(exe_surf, (70, y))
                y += 22
            y += 10

        if game.game_exes:
            game_label = self.font_small.render("Game:", True, GREEN)
            self.screen.blit(game_label, (70, y))
            y += 25
            for exe in game.game_exes[:8]:
                exe_surf = self.font_small.render(f"  {exe}", True, WHITE)
                self.screen.blit(exe_surf, (70, y))
                y += 22

        suggested = game.get_likely_game_exe()
        if suggested:
            y += 20
            suggest_surf = self.font_small.render(f"Suggested: {suggested}", True, YELLOW)
            self.screen.blit(suggest_surf, (50, y))

        # Show potential issues/requirements
        y += 35
        issues = []
        has_install = any('install' in e.lower() for e in game.executables)
        has_setup = any('setup' in e.lower() or 'setsound' in e.lower() for e in game.executables)

        if has_install and not game.is_configured:
            issues.append("May need INSTALL first")
        if has_setup:
            issues.append("Has sound SETUP")

        if issues:
            issue_surf = self.font_small.render("Notes: " + " | ".join(issues), True, ORANGE)
            self.screen.blit(issue_surf, (50, y))
            y += 25

        # SoundBlaster help text
        y += 10
        sb_help = "SoundBlaster: Port 220, IRQ 7, DMA 1, High DMA 5"
        sb_surf = self.font_tiny.render(sb_help, True, GRAY)
        self.screen.blit(sb_surf, (50, y))

        controls = "[A] Set Autoboot  [X] Launch (Setup)  [Y] Launch (Play)  [B] Back"
        if game.is_configured:
            controls = "[A] Change  [X] Setup  [Y] Play  [SELECT] Clear  [B] Back"
        controls_surf = self.font_small.render(controls, True, GRAY)
        self.screen.blit(controls_surf, (self.width//2 - controls_surf.get_width()//2, self.height - 40))

        self.draw_status()

    def draw_exe_select(self):
        if not self.selected_game:
            return

        self.screen.fill(BLACK)
        game = self.selected_game

        title = self.font_large.render("SELECT EXECUTABLE", True, PURPLE)
        self.screen.blit(title, (self.width//2 - title.get_width()//2, 15))

        subtitle = self.font_medium.render(f"For: {game.name[:50]}", True, WHITE)
        self.screen.blit(subtitle, (self.width//2 - subtitle.get_width()//2, 60))

        y = 120
        for i, exe in enumerate(game.executables):
            if i == self.exe_select_index:
                pygame.draw.rect(self.screen, DARK_GREEN, (100, y, self.width - 200, 35))

            lower = exe.lower()
            if any(p in lower for p in SETUP_PATTERNS):
                prefix = "[SETUP]"
                color = BLUE
            else:
                prefix = "[GAME]"
                color = GREEN

            prefix_surf = self.font_small.render(prefix, True, color)
            self.screen.blit(prefix_surf, (110, y + 6))

            exe_color = WHITE if i != self.exe_select_index else GREEN
            exe_surf = self.font_medium.render(exe, True, exe_color)
            self.screen.blit(exe_surf, (200, y + 4))

            y += 38
            if y > self.height - 100:
                break

        controls = "[A] Select  [B] Cancel"
        controls_surf = self.font_small.render(controls, True, GRAY)
        self.screen.blit(controls_surf, (self.width//2 - controls_surf.get_width()//2, self.height - 40))

    def draw_keyboard(self):
        overlay = pygame.Surface((self.width, self.height))
        overlay.set_alpha(200)
        overlay.fill(BLACK)
        self.screen.blit(overlay, (0, 0))

        kb_width = 600
        kb_height = 300
        kb_x = (self.width - kb_width) // 2
        kb_y = (self.height - kb_height) // 2
        pygame.draw.rect(self.screen, DARK_GRAY, (kb_x, kb_y, kb_width, kb_height), border_radius=10)

        search_surf = self.font_medium.render(f"Search: {self.search_text}_", True, PURPLE)
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
                color = PURPLE if selected else LIGHT_GRAY
                pygame.draw.rect(self.screen, color, (x, y, w, key_size), border_radius=5)

                label = " " if key == "SPACE" else key
                key_surf = self.font_small.render(label, True, BLACK if selected else WHITE)
                self.screen.blit(key_surf, (x + w//2 - key_surf.get_width()//2,
                                           y + key_size//2 - key_surf.get_height()//2))

    def launch_game(self, game: DOSGame):
        """Launch game in DOSBox-Pure via RetroArch"""
        cmd = f'{RETROARCH_CMD} -L "{DOSBOX_PURE_CORE}" "{game.zip_path}"'
        logger.info(f"Launching game: {game.name}")
        logger.info(f"Command: {cmd}")
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            logger.debug(f"RetroArch exit code: {result.returncode}")
            if result.stderr:
                logger.debug(f"RetroArch stderr: {result.stderr[:500]}")
            game._check_configured()
            if game.is_configured:
                self.set_status(f"Configured: {game.autoboot_exe}")
                logger.info(f"Game now configured with: {game.autoboot_exe}")
            else:
                logger.info(f"Game exited but no autoboot set")
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
        modes = ["all", "unconfigured", "configured", "needs_setup"]
        idx = modes.index(self.filter_mode)
        idx = (idx + direction) % len(modes)
        self.filter_mode = modes[idx]
        logger.info(f"Filter changed to: {self.filter_mode}")
        self.apply_filter()

    def run(self):
        os.makedirs(DOS_ROM_DIR, exist_ok=True)
        os.makedirs(SAVES_DIR, exist_ok=True)

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
                        elif event.button == 6 and self.selected_game:
                            self.selected_game.clear_autoboot()
                            self.set_status("Autoboot cleared")
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
