#!/usr/bin/env python3
"""
nerdymark's Xbox Game Extractor for ES-DE
Extracts ZIP files containing Xbox ISOs and converts them to xemu-compatible XISO format
Uses pygame for Steam Deck controller-friendly UI
"""

import pygame

import os
import sys
import zipfile
import shutil
import signal
import atexit
import subprocess
from pathlib import Path

# Add shared module path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from gloomy_aesthetic import (
    GloomyBackground, draw_nerdymark_brand, draw_title_with_glow, create_panel,
    get_theme, VOID_BLACK, DEEP_GRAY, SMOKE_GRAY, MIST_GRAY, PALE_GRAY, FOG_WHITE,
    HOPE_GREEN, GLOOMY_GREEN
)

XBOX_ROM_DIR = "/run/media/deck/SK256/Emulation/roms/xbox"
EXTRACT_XISO = "/run/media/deck/SK256/Emulation/tools/chdconv/extract-xiso"
DOWNLOADS_DIR = "/run/media/deck/SK256/Emulation/roms/ports/xbox-downloader/downloads"

# Colors - Gloomy Green theme for Xbox
THEME = get_theme('xbox')
ACCENT = THEME['accent']
ACCENT_DIM = THEME['accent_dim']
HIGHLIGHT = THEME['highlight']

BLACK = VOID_BLACK
WHITE = FOG_WHITE
GREEN = ACCENT
DARK_GREEN = ACCENT_DIM
GRAY = MIST_GRAY
DARK_GRAY = DEEP_GRAY
LIGHT_GRAY = SMOKE_GRAY
YELLOW = (180, 170, 80)
RED = (180, 70, 70)

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


class XboxExtractorUI:
    def __init__(self):
        pygame.init()
        pygame.joystick.init()

        # Fullscreen
        info = pygame.display.Info()
        self.width = info.current_w
        self.height = info.current_h
        self.screen = pygame.display.set_mode((self.width, self.height), pygame.FULLSCREEN)
        pygame.display.set_caption("nerdymark's Xbox Game Extractor")

        # Fonts
        self.font_large = pygame.font.Font(None, 48)
        self.font_medium = pygame.font.Font(None, 36)
        self.font_small = pygame.font.Font(None, 28)

        # Controller
        self.joystick = None
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()

        # State
        self.zip_files = []
        self.existing_games = set()
        self.selected_index = 0
        self.scroll_offset = 0
        self.visible_items = (self.height - 200) // 40

        # Extract state
        self.extracting = False
        self.extract_progress = 0
        self.extract_game = ""
        self.extract_status = ""

        # Confirmation dialog
        self.confirm_active = False
        self.confirm_message = ""
        self.confirm_callback = None
        self.confirm_selected = 0  # 0 = Yes, 1 = No

        # Input timing
        self.last_input_time = 0
        self.input_delay = 150  # ms

        # Gloomy background
        self.font_brand = pygame.font.Font(None, 24)
        self.background = GloomyBackground(self.width, self.height, accent_color=ACCENT)

        self.clock = pygame.time.Clock()

    def get_existing_games(self):
        existing = set()
        xbox_path = Path(XBOX_ROM_DIR)
        if xbox_path.exists():
            for f in xbox_path.iterdir():
                if f.suffix.lower() == '.iso':
                    existing.add(f.stem)
        return existing

    def find_zip_files(self):
        zip_files = []
        search_path = Path(DOWNLOADS_DIR)
        if search_path.exists():
            for f in search_path.iterdir():
                if f.is_file() and f.suffix.lower() == '.zip':
                    zip_files.append(f)
        return sorted(zip_files, key=lambda x: x.name.lower())

    def draw_message(self, title, message):
        # Update and draw gloomy background
        self.background.update()
        self.background.draw(self.screen)

        # Title with glow
        draw_title_with_glow(self.screen, self.font_large, title, ACCENT, self.height//2 - 50)

        # Message
        msg_surf = self.font_medium.render(message, True, WHITE)
        self.screen.blit(msg_surf, (self.width//2 - msg_surf.get_width()//2, self.height//2 + 10))

        # Branding
        draw_nerdymark_brand(self.screen, self.font_brand, ACCENT_DIM)

    def draw_main_menu(self):
        # Update and draw gloomy background
        self.background.update()
        self.background.draw(self.screen)

        # Header with glow
        draw_title_with_glow(self.screen, self.font_large, "NERDYMARK'S XBOX GAME EXTRACTOR", ACCENT, 20)

        # Stats
        pending = sum(1 for z in self.zip_files if z.stem not in self.existing_games)
        stats = f"{len(self.zip_files)} ZIP files | {len(self.existing_games)} games extracted | {pending} pending"
        stats_surf = self.font_small.render(stats, True, PALE_GRAY)
        self.screen.blit(stats_surf, (self.width//2 - stats_surf.get_width()//2, 70))

        # Downloads folder info
        folder_surf = self.font_small.render(f"Folder: {DOWNLOADS_DIR}", True, SMOKE_GRAY)
        self.screen.blit(folder_surf, (50, 100))

        if not self.zip_files:
            # No files message
            msg = "No ZIP files found!"
            msg_surf = self.font_medium.render(msg, True, HIGHLIGHT)
            self.screen.blit(msg_surf, (self.width//2 - msg_surf.get_width()//2, self.height//2 - 50))

            hint = "Place Xbox game ZIP files in the downloads folder"
            hint_surf = self.font_small.render(hint, True, MIST_GRAY)
            self.screen.blit(hint_surf, (self.width//2 - hint_surf.get_width()//2, self.height//2 + 10))
        else:
            # File list panel
            list_panel = create_panel(self.width - 80, self.height - 230, border_color=SMOKE_GRAY)
            self.screen.blit(list_panel, (40, 135))

            list_top = 140
            for i in range(self.visible_items):
                idx = i + self.scroll_offset
                if idx >= len(self.zip_files):
                    break

                zip_path = self.zip_files[idx]
                y = list_top + i * 40

                # Highlight selected
                if idx == self.selected_index:
                    highlight_surface = pygame.Surface((self.width - 100, 38), pygame.SRCALPHA)
                    pygame.draw.rect(highlight_surface, (*ACCENT_DIM, 120), (0, 0, self.width - 100, 38), border_radius=3)
                    self.screen.blit(highlight_surface, (50, y))

                # File info
                name = zip_path.stem
                size_mb = zip_path.stat().st_size / (1024 * 1024)
                is_extracted = name in self.existing_games

                display_name = name[:50] + "..." if len(name) > 50 else name
                status = "[EXTRACTED]" if is_extracted else f"({size_mb:.0f} MB)"

                color = MIST_GRAY if is_extracted else PALE_GRAY
                if idx == self.selected_index:
                    color = HIGHLIGHT if is_extracted else ACCENT

                text_surf = self.font_small.render(f"{display_name}  {status}", True, color)
                self.screen.blit(text_surf, (60, y + 8))

            # Scrollbar
            if len(self.zip_files) > self.visible_items:
                bar_height = self.height - 220
                handle_height = max(30, bar_height * self.visible_items // len(self.zip_files))
                handle_pos = bar_height * self.scroll_offset // max(1, len(self.zip_files) - self.visible_items)
                pygame.draw.rect(self.screen, DEEP_GRAY, (self.width - 30, 140, 10, bar_height), border_radius=5)
                pygame.draw.rect(self.screen, ACCENT_DIM, (self.width - 30, 140 + handle_pos, 10, handle_height), border_radius=5)

        # Controls help
        controls = "[D-PAD] Navigate  [A] Extract  [X] Extract All  [Y] Delete ZIP  [B] Quit"
        controls_surf = self.font_small.render(controls, True, MIST_GRAY)
        self.screen.blit(controls_surf, (self.width//2 - controls_surf.get_width()//2, self.height - 40))

        # Branding
        draw_nerdymark_brand(self.screen, self.font_brand, ACCENT_DIM)

    def draw_confirm_dialog(self):
        # Darken background
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((*VOID_BLACK, 220))
        self.screen.blit(overlay, (0, 0))

        # Dialog panel
        box_width = 500
        box_height = 200
        box_x = (self.width - box_width) // 2
        box_y = (self.height - box_height) // 2
        dialog_panel = create_panel(box_width, box_height, border_color=ACCENT_DIM)
        self.screen.blit(dialog_panel, (box_x, box_y))

        # Message
        lines = self.confirm_message.split('\n')
        for i, line in enumerate(lines):
            msg_surf = self.font_medium.render(line, True, PALE_GRAY)
            self.screen.blit(msg_surf, (self.width//2 - msg_surf.get_width()//2, box_y + 30 + i * 35))

        # Buttons
        btn_y = box_y + box_height - 60
        btn_width = 100
        spacing = 50

        # Yes button
        yes_color = ACCENT if self.confirm_selected == 0 else SMOKE_GRAY
        yes_x = self.width//2 - btn_width - spacing//2
        pygame.draw.rect(self.screen, yes_color, (yes_x, btn_y, btn_width, 40), border_radius=5)
        yes_surf = self.font_medium.render("Yes", True, VOID_BLACK if self.confirm_selected == 0 else PALE_GRAY)
        self.screen.blit(yes_surf, (yes_x + btn_width//2 - yes_surf.get_width()//2, btn_y + 8))

        # No button
        no_color = ACCENT if self.confirm_selected == 1 else SMOKE_GRAY
        no_x = self.width//2 + spacing//2
        pygame.draw.rect(self.screen, no_color, (no_x, btn_y, btn_width, 40), border_radius=5)
        no_surf = self.font_medium.render("No", True, VOID_BLACK if self.confirm_selected == 1 else PALE_GRAY)
        self.screen.blit(no_surf, (no_x + btn_width//2 - no_surf.get_width()//2, btn_y + 8))

    def draw_extract_progress(self):
        # Update and draw gloomy background
        self.background.update()
        self.background.draw(self.screen)

        # Title with glow
        draw_title_with_glow(self.screen, self.font_large, "EXTRACTING", ACCENT, self.height//2 - 120)

        # Game name
        name_surf = self.font_medium.render(self.extract_game[:50], True, PALE_GRAY)
        self.screen.blit(name_surf, (self.width//2 - name_surf.get_width()//2, self.height//2 - 60))

        # Progress bar panel
        bar_width = self.width - 200
        bar_height = 40
        bar_x = 100
        bar_y = self.height // 2
        pygame.draw.rect(self.screen, DEEP_GRAY, (bar_x, bar_y, bar_width, bar_height), border_radius=5)
        pygame.draw.rect(self.screen, SMOKE_GRAY, (bar_x, bar_y, bar_width, bar_height), width=1, border_radius=5)
        fill_width = int(bar_width * self.extract_progress / 100)
        if fill_width > 0:
            pygame.draw.rect(self.screen, ACCENT_DIM, (bar_x, bar_y, fill_width, bar_height), border_radius=5)

        # Percentage
        pct_surf = self.font_medium.render(f"{self.extract_progress}%", True, WHITE)
        self.screen.blit(pct_surf, (self.width//2 - pct_surf.get_width()//2, bar_y + 8))

        # Status
        status_surf = self.font_small.render(self.extract_status, True, HIGHLIGHT)
        self.screen.blit(status_surf, (self.width//2 - status_surf.get_width()//2, bar_y + 60))

        # Branding
        draw_nerdymark_brand(self.screen, self.font_brand, ACCENT_DIM)

    def check_input(self):
        current_time = pygame.time.get_ticks()
        if current_time - self.last_input_time < self.input_delay:
            return None

        # Keyboard input
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

        # Controller input
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
        if action == "UP":
            if self.selected_index > 0:
                self.selected_index -= 1
                if self.selected_index < self.scroll_offset:
                    self.scroll_offset = self.selected_index
        elif action == "DOWN":
            if self.selected_index < len(self.zip_files) - 1:
                self.selected_index += 1
                if self.selected_index >= self.scroll_offset + self.visible_items:
                    self.scroll_offset = self.selected_index - self.visible_items + 1

    def handle_confirm_input(self, action):
        if action == "LEFT":
            self.confirm_selected = 0
        elif action == "RIGHT":
            self.confirm_selected = 1

    def show_confirm(self, message, callback):
        self.confirm_active = True
        self.confirm_message = message
        self.confirm_callback = callback
        self.confirm_selected = 0

    def extract_zip(self, zip_path):
        self.extracting = True
        self.extract_game = zip_path.stem
        self.extract_progress = 0
        self.extract_status = "Starting extraction..."

        self.draw_extract_progress()
        pygame.display.flip()

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                iso_files = [f for f in zf.namelist() if f.lower().endswith('.iso')]
                if not iso_files:
                    self.extracting = False
                    return False

                total_size = sum(zf.getinfo(f).file_size for f in iso_files)
                extracted_size = 0

                for iso_file in iso_files:
                    self.extract_status = f"Extracting: {os.path.basename(iso_file)}"
                    self.draw_extract_progress()
                    pygame.display.flip()

                    final_path = os.path.join(XBOX_ROM_DIR, os.path.basename(iso_file))

                    with zf.open(iso_file) as src, open(final_path, 'wb') as dst:
                        chunk_size = 1024 * 1024  # 1MB
                        while True:
                            # Check for cancel
                            for event in pygame.event.get():
                                if event.type == pygame.QUIT:
                                    self.extracting = False
                                    return False

                            chunk = src.read(chunk_size)
                            if not chunk:
                                break
                            dst.write(chunk)
                            extracted_size += len(chunk)

                            self.extract_progress = int((extracted_size / total_size) * 70)
                            self.draw_extract_progress()
                            pygame.display.flip()

                    # Convert with extract-xiso
                    self.extract_status = "Converting to XISO format..."
                    self.extract_progress = 80
                    self.draw_extract_progress()
                    pygame.display.flip()

                    if os.path.exists(EXTRACT_XISO):
                        proc = subprocess.run([EXTRACT_XISO, '-r', '-D', '-d', XBOX_ROM_DIR, final_path], capture_output=True)
                        if proc.returncode != 0:
                            os.remove(final_path)
                            self.extracting = False
                            return False

            self.extract_progress = 100
            self.extract_status = "Complete!"
            self.draw_extract_progress()
            pygame.display.flip()
            pygame.time.wait(1000)

            self.extracting = False
            self.existing_games = self.get_existing_games()
            return True

        except Exception as e:
            self.extracting = False
            return False

    def extract_all_pending(self):
        pending = [z for z in self.zip_files if z.stem not in self.existing_games]
        if not pending:
            return

        success = 0
        for zip_path in pending:
            if self.extract_zip(zip_path):
                success += 1
            else:
                break

        # Show summary
        self.draw_message("Batch Complete", f"Extracted {success}/{len(pending)} games")
        pygame.display.flip()
        pygame.time.wait(2000)

    def delete_zip(self, zip_path):
        try:
            zip_path.unlink()
            self.zip_files = self.find_zip_files()
            if self.selected_index >= len(self.zip_files):
                self.selected_index = max(0, len(self.zip_files) - 1)
            return True
        except:
            return False

    def run(self):
        os.makedirs(XBOX_ROM_DIR, exist_ok=True)
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)

        # Check for extract-xiso
        if not os.path.exists(EXTRACT_XISO):
            self.draw_message("Error", f"extract-xiso not found at {EXTRACT_XISO}")
            pygame.display.flip()
            pygame.time.wait(3000)
            pygame.quit()
            return 1

        self.existing_games = self.get_existing_games()
        self.zip_files = self.find_zip_files()

        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                if event.type == pygame.KEYDOWN:
                    if self.confirm_active:
                        if event.key == pygame.K_RETURN:
                            self.confirm_active = False
                            if self.confirm_selected == 0 and self.confirm_callback:
                                self.confirm_callback()
                        elif event.key == pygame.K_ESCAPE:
                            self.confirm_active = False
                    else:
                        if event.key == pygame.K_ESCAPE:
                            running = False
                        elif event.key == pygame.K_RETURN and self.zip_files:
                            zip_path = self.zip_files[self.selected_index]
                            self.extract_zip(zip_path)
                        elif event.key == pygame.K_x:
                            self.extract_all_pending()
                        elif event.key == pygame.K_y and self.zip_files:
                            zip_path = self.zip_files[self.selected_index]
                            self.show_confirm(f"Delete ZIP file?\n{zip_path.name[:40]}", lambda: self.delete_zip(zip_path))

                if event.type == pygame.JOYBUTTONDOWN:
                    if self.confirm_active:
                        if event.button == 0:  # A button
                            self.confirm_active = False
                            if self.confirm_selected == 0 and self.confirm_callback:
                                self.confirm_callback()
                        elif event.button == 1:  # B button
                            self.confirm_active = False
                    else:
                        if event.button == 0 and self.zip_files:  # A button - extract
                            zip_path = self.zip_files[self.selected_index]
                            self.extract_zip(zip_path)
                        elif event.button == 1:  # B button - quit
                            running = False
                        elif event.button == 2:  # X button - extract all
                            self.extract_all_pending()
                        elif event.button == 3 and self.zip_files:  # Y button - delete
                            zip_path = self.zip_files[self.selected_index]
                            self.show_confirm(f"Delete ZIP file?\n{zip_path.name[:40]}", lambda zp=zip_path: self.delete_zip(zp))

            # Handle held directions
            action = self.check_input()
            if action:
                if self.confirm_active:
                    self.handle_confirm_input(action)
                else:
                    self.handle_list_input(action)

            # Draw
            if self.extracting:
                self.draw_extract_progress()
            else:
                self.draw_main_menu()
                if self.confirm_active:
                    self.draw_confirm_dialog()

            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()
        return 0


def main():
    app = XboxExtractorUI()
    return app.run()


if __name__ == '__main__':
    sys.exit(main())
