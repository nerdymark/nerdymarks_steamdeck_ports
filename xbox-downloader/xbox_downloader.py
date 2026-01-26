#!/usr/bin/env python3
"""
nerdymark's Xbox Game Downloader for ES-DE
Downloads games from Myrient's Redump Xbox collection
Uses pygame for Steam Deck controller-friendly UI
"""

import pygame

import subprocess
import urllib.request
import urllib.parse
import html.parser
import os
import sys
import tempfile
import zipfile
import shutil
import signal
import atexit
import threading
import time
from pathlib import Path

# Add shared module path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from gloomy_aesthetic import (
    GloomyBackground, draw_nerdymark_brand, draw_title_with_glow, create_panel,
    get_theme, VOID_BLACK, DEEP_GRAY, SMOKE_GRAY, MIST_GRAY, PALE_GRAY, FOG_WHITE,
    HOPE_GREEN, GLOOMY_GREEN
)

BASE_URL = "https://myrient.erista.me/files/Redump/Microsoft%20-%20Xbox/"
XBOX_ROM_DIR = "/run/media/deck/SK256/Emulation/roms/xbox"
EXTRACT_XISO = "/run/media/deck/SK256/Emulation/tools/chdconv/extract-xiso"
SOUND_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tada.mp3")

# Disk space thresholds (in GB)
DISK_SPACE_WARNING = 20  # Yellow when below 20GB
DISK_SPACE_CRITICAL = 10  # Red when below 10GB

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
    try:
        subprocess.run(['pkill', '-f', 'wget.*myrient'], capture_output=True, timeout=5)
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
        self.games = []
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
                display_name = name[:-4]
                self.games.append((display_name, self.current_href))
            self.in_link = False
            self.current_href = None


class XboxDownloaderUI:
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
        pygame.display.set_caption("nerdymark's Xbox Game Downloader")

        # Fonts
        self.font_large = pygame.font.Font(None, 48)
        self.font_medium = pygame.font.Font(None, 36)
        self.font_small = pygame.font.Font(None, 28)
        self.font_tiny = pygame.font.Font(None, 22)

        # Controller
        self.joystick = None
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()

        # State
        self.games = []
        self.filtered_games = []
        self.existing_games = set()
        self.selected_index = 0
        self.scroll_offset = 0
        self.search_text = ""
        self.visible_items = (self.height - 200) // 40

        # Download state
        self.downloading = False
        self.download_progress = 0
        self.download_size = 0
        self.download_speed = ""
        self.download_game_name = ""
        self.download_status = ""

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

    def fetch_game_list(self):
        self.draw_message("Connecting to Myrient...", "Fetching game list, please wait")
        pygame.display.flip()

        try:
            req = urllib.request.Request(BASE_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                html_content = response.read().decode('utf-8')

            parser = MyrientParser()
            parser.feed(html_content)
            return parser.games
        except Exception as e:
            self.draw_message("Error", f"Failed to fetch game list: {str(e)}")
            pygame.display.flip()
            pygame.time.wait(3000)
            return None

    def filter_games(self):
        search = self.search_text.lower()
        self.filtered_games = []
        for name, href in self.games:
            if search in name.lower():
                status = "[DOWNLOADED]" if name in self.existing_games else ""
                self.filtered_games.append((name, href, status))
        self.selected_index = 0
        self.scroll_offset = 0

    def get_disk_space(self):
        """Get free disk space in GB for the Xbox ROM directory"""
        try:
            stat = os.statvfs(XBOX_ROM_DIR)
            free_bytes = stat.f_bavail * stat.f_frsize
            total_bytes = stat.f_blocks * stat.f_frsize
            free_gb = free_bytes / (1024 ** 3)
            total_gb = total_bytes / (1024 ** 3)
            return free_gb, total_gb
        except:
            return 0, 0

    def draw_disk_space(self):
        """Draw disk space indicator in top-right corner"""
        free_gb, total_gb = self.get_disk_space()
        if total_gb == 0:
            return

        # Dimensions
        bar_width = 120
        bar_height = 16
        padding = 15
        x = self.width - bar_width - padding
        y = padding

        # Calculate fill percentage
        used_gb = total_gb - free_gb
        fill_pct = used_gb / total_gb if total_gb > 0 else 0

        # Determine color based on free space
        if free_gb < DISK_SPACE_CRITICAL:
            fill_color = RED
        elif free_gb < DISK_SPACE_WARNING:
            fill_color = YELLOW
        else:
            fill_color = GREEN

        # Draw background
        pygame.draw.rect(self.screen, DARK_GRAY, (x, y, bar_width, bar_height), border_radius=3)

        # Draw fill (shows used space)
        fill_width = int(bar_width * fill_pct)
        if fill_width > 0:
            pygame.draw.rect(self.screen, fill_color, (x, y, fill_width, bar_height), border_radius=3)

        # Draw border
        pygame.draw.rect(self.screen, GRAY, (x, y, bar_width, bar_height), width=1, border_radius=3)

        # Draw label
        label = f"{free_gb:.0f}GB free"
        label_surf = self.font_tiny.render(label, True, WHITE if free_gb >= DISK_SPACE_CRITICAL else fill_color)
        self.screen.blit(label_surf, (x, y + bar_height + 3))

    def play_completion_sound(self):
        """Play the completion sound if available"""
        if self.completion_sound:
            try:
                self.completion_sound.play()
            except:
                pass

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

        # Disk space indicator
        self.draw_disk_space()

        # Header with glow
        draw_title_with_glow(self.screen, self.font_large, "NERDYMARK'S XBOX GAME DOWNLOADER", ACCENT, 20)

        # Stats
        stats = f"{len(self.games)} games available | {len(self.existing_games)} downloaded | {len(self.filtered_games)} shown"
        stats_surf = self.font_small.render(stats, True, PALE_GRAY)
        self.screen.blit(stats_surf, (self.width//2 - stats_surf.get_width()//2, 70))

        # Search box with panel
        search_panel = create_panel(self.width - 100, 40, border_color=ACCENT_DIM if self.keyboard_active else SMOKE_GRAY)
        self.screen.blit(search_panel, (50, 100))
        search_label = f"Search: {self.search_text}_" if not self.keyboard_active else f"Search: {self.search_text}"
        search_surf = self.font_medium.render(search_label, True, HIGHLIGHT if self.keyboard_active else WHITE)
        self.screen.blit(search_surf, (60, 108))

        # Game list panel
        list_panel = create_panel(self.width - 80, self.height - 230, border_color=SMOKE_GRAY)
        self.screen.blit(list_panel, (40, 155))

        list_top = 160
        for i in range(self.visible_items):
            idx = i + self.scroll_offset
            if idx >= len(self.filtered_games):
                break

            name, href, status = self.filtered_games[idx]
            y = list_top + i * 40

            # Highlight selected
            if idx == self.selected_index:
                highlight_surface = pygame.Surface((self.width - 100, 38), pygame.SRCALPHA)
                pygame.draw.rect(highlight_surface, (*ACCENT_DIM, 120), (0, 0, self.width - 100, 38), border_radius=3)
                self.screen.blit(highlight_surface, (50, y))

            # Truncate name
            display_name = name[:60] + "..." if len(name) > 60 else name
            if status:
                display_name += f"  {status}"

            color = MIST_GRAY if status else PALE_GRAY
            if idx == self.selected_index:
                color = HIGHLIGHT if status else ACCENT

            text_surf = self.font_small.render(display_name, True, color)
            self.screen.blit(text_surf, (60, y + 8))

        # Scrollbar
        if len(self.filtered_games) > self.visible_items:
            bar_height = self.height - 220
            handle_height = max(30, bar_height * self.visible_items // len(self.filtered_games))
            handle_pos = bar_height * self.scroll_offset // max(1, len(self.filtered_games) - self.visible_items)
            pygame.draw.rect(self.screen, DEEP_GRAY, (self.width - 30, 160, 10, bar_height), border_radius=5)
            pygame.draw.rect(self.screen, ACCENT_DIM, (self.width - 30, 160 + handle_pos, 10, handle_height), border_radius=5)

        # Controls help
        controls = "[D-PAD] Navigate  [A] Download  [X] Download All  [Y] Search  [B] Quit"
        controls_surf = self.font_small.render(controls, True, MIST_GRAY)
        self.screen.blit(controls_surf, (self.width//2 - controls_surf.get_width()//2, self.height - 40))

        # Branding
        draw_nerdymark_brand(self.screen, self.font_brand, ACCENT_DIM)

    def draw_keyboard(self):
        # Darken background
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((*VOID_BLACK, 220))
        self.screen.blit(overlay, (0, 0))

        # Keyboard panel
        kb_width = 600
        kb_height = 300
        kb_x = (self.width - kb_width) // 2
        kb_y = (self.height - kb_height) // 2
        kb_panel = create_panel(kb_width, kb_height, border_color=ACCENT_DIM)
        self.screen.blit(kb_panel, (kb_x, kb_y))

        # Search text with glow
        search_surf = self.font_medium.render(f"Search: {self.search_text}_", True, ACCENT)
        self.screen.blit(search_surf, (kb_x + 20, kb_y + 20))

        # Keys
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
                self.screen.blit(key_surf, (x + w//2 - key_surf.get_width()//2, y + key_size//2 - key_surf.get_height()//2))

    def draw_download_progress(self):
        # Update and draw gloomy background
        self.background.update()
        self.background.draw(self.screen)

        # Disk space indicator
        self.draw_disk_space()

        # Title with glow
        draw_title_with_glow(self.screen, self.font_large, "DOWNLOADING", ACCENT, self.height//2 - 120)

        # Game name
        name_surf = self.font_medium.render(self.download_game_name[:50], True, PALE_GRAY)
        self.screen.blit(name_surf, (self.width//2 - name_surf.get_width()//2, self.height//2 - 60))

        # Progress bar panel
        bar_width = self.width - 200
        bar_height = 40
        bar_x = 100
        bar_y = self.height // 2
        pygame.draw.rect(self.screen, DEEP_GRAY, (bar_x, bar_y, bar_width, bar_height), border_radius=5)
        pygame.draw.rect(self.screen, SMOKE_GRAY, (bar_x, bar_y, bar_width, bar_height), width=1, border_radius=5)
        fill_width = int(bar_width * self.download_progress / 100)
        if fill_width > 0:
            pygame.draw.rect(self.screen, ACCENT_DIM, (bar_x, bar_y, fill_width, bar_height), border_radius=5)

        # Percentage
        pct_surf = self.font_medium.render(f"{self.download_progress}%", True, WHITE)
        self.screen.blit(pct_surf, (self.width//2 - pct_surf.get_width()//2, bar_y + 8))

        # Speed/size
        if self.download_speed:
            speed_surf = self.font_small.render(self.download_speed, True, MIST_GRAY)
            self.screen.blit(speed_surf, (self.width//2 - speed_surf.get_width()//2, bar_y + 60))

        # Status
        status_surf = self.font_small.render(self.download_status, True, HIGHLIGHT)
        self.screen.blit(status_surf, (self.width//2 - status_surf.get_width()//2, bar_y + 100))

        # Cancel hint
        cancel_surf = self.font_small.render("[B] Cancel", True, (180, 70, 70))
        self.screen.blit(cancel_surf, (self.width//2 - cancel_surf.get_width()//2, self.height - 50))

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
            # D-pad
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

            # Left stick
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
            self.filter_games()
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

    def download_game(self, game_name, href):
        # Debug log
        debug = open('/tmp/xbox_dl_debug.log', 'a')
        debug.write(f"download_game called: {game_name}\n")
        debug.flush()

        self.downloading = True
        self.download_game_name = game_name
        self.download_progress = 0
        self.download_speed = ""
        self.download_status = "Starting download..."

        download_url = BASE_URL + href
        debug.write(f"URL: {download_url}\n")
        debug.flush()

        try:
            # Use SD card for temp storage (system /tmp is RAM-limited)
            temp_base = os.path.dirname(XBOX_ROM_DIR)  # /run/media/deck/SK256/Emulation/roms
            with tempfile.TemporaryDirectory(dir=temp_base) as tmpdir:
                debug.write(f"Temp dir: {tmpdir}\n")
                debug.flush()

                zip_path = os.path.join(tmpdir, "game.zip")

                # Get file size first
                debug.write("Getting file size...\n")
                debug.flush()
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
                debug.write(f"Total size: {total_size}\n")
                debug.flush()

                # Start wget - no pipe capture to avoid buffer issues
                debug.write(f"Starting wget to {zip_path}\n")
                debug.flush()

                proc = subprocess.Popen(
                    ['wget', '-O', zip_path, '-q', download_url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                track_process(proc)

                # Monitor progress
                cancelled = False
                total_mb = total_size / (1024 * 1024) if total_size > 0 else 0

                while proc.poll() is None:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            proc.kill()
                            debug.write("QUIT event\n")
                            debug.close()
                            return False
                        if event.type == pygame.JOYBUTTONDOWN:
                            if event.button == 1:  # B button - cancel
                                proc.kill()
                                cancelled = True
                        if event.type == pygame.KEYDOWN:
                            if event.key == pygame.K_ESCAPE:
                                proc.kill()
                                cancelled = True

                    if cancelled:
                        self.download_status = "Cancelled"
                        debug.write("Download cancelled\n")
                        break

                    # Check file size for progress
                    if os.path.exists(zip_path):
                        size = os.path.getsize(zip_path)
                        size_mb = size / (1024 * 1024)
                        if total_mb > 0:
                            self.download_progress = int((size / total_size) * 50)
                            self.download_speed = f"{size_mb:.0f} / {total_mb:.0f} MB"
                        else:
                            self.download_speed = f"{size_mb:.0f} MB"

                    self.draw_download_progress()
                    pygame.display.flip()
                    self.clock.tick(5)  # Check less frequently

                debug.write(f"wget finished, returncode={proc.returncode}\n")
                debug.flush()

                if cancelled or proc.returncode != 0:
                    self.downloading = False
                    debug.close()
                    return False

                # Extract and convert
                self.download_status = "Extracting..."
                self.download_progress = 50
                self.draw_download_progress()
                pygame.display.flip()

                debug.write("Starting extract_and_convert\n")
                debug.flush()

                if not self.extract_and_convert(zip_path, XBOX_ROM_DIR, game_name):
                    self.downloading = False
                    debug.write("extract_and_convert failed\n")
                    debug.close()
                    return False

                debug.write("Download complete!\n")
                debug.flush()

                # Play completion sound
                self.play_completion_sound()

        except Exception as e:
            debug.write(f"Exception: {e}\n")
            debug.flush()
            debug.close()
            self.downloading = False
            return False

        self.downloading = False
        self.existing_games = self.get_existing_games()
        self.filter_games()
        debug.close()
        return True

    def extract_and_convert(self, zip_path, dest_dir, game_name):
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                iso_files = [f for f in zf.namelist() if f.lower().endswith('.iso')]
                if not iso_files:
                    return False

                self.download_status = "Extracting ISO..."
                self.download_progress = 60
                self.draw_download_progress()
                pygame.display.flip()

                for iso_file in iso_files:
                    final_path = os.path.join(dest_dir, os.path.basename(iso_file))
                    with zf.open(iso_file) as src, open(final_path, 'wb') as dst:
                        shutil.copyfileobj(src, dst)

                    self.download_status = "Converting to XISO..."
                    self.download_progress = 80
                    self.draw_download_progress()
                    pygame.display.flip()

                    # Convert with extract-xiso (-D deletes original after conversion)
                    if os.path.exists(EXTRACT_XISO):
                        proc = subprocess.run([EXTRACT_XISO, '-r', '-D', '-d', dest_dir, final_path], capture_output=True)
                        if proc.returncode != 0:
                            os.remove(final_path)
                            return False

            self.download_progress = 100
            self.download_status = "Complete!"
            self.draw_download_progress()
            pygame.display.flip()
            pygame.time.wait(1000)
            return True

        except Exception as e:
            return False

    def download_all(self):
        """Download all missing games from the filtered list"""
        missing_games = [(name, href) for name, href, status in self.filtered_games if not status]
        if not missing_games:
            self.draw_message("Download All", "No missing games to download!")
            pygame.display.flip()
            pygame.time.wait(1500)
            return

        total = len(missing_games)
        for i, (name, href) in enumerate(missing_games):
            self.download_status = f"Batch: {i+1}/{total}"
            if not self.download_game(name, href):
                # Check if user cancelled
                for event in pygame.event.get():
                    if event.type == pygame.JOYBUTTONDOWN and event.button == 1:
                        return
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        return

        self.draw_message("Download All", f"Completed! Downloaded {total} games.")
        pygame.display.flip()
        pygame.time.wait(2000)

    def run(self):
        os.makedirs(XBOX_ROM_DIR, exist_ok=True)

        # Check for extract-xiso
        if not os.path.exists(EXTRACT_XISO):
            self.draw_message("Error", f"extract-xiso not found at {EXTRACT_XISO}")
            pygame.display.flip()
            pygame.time.wait(3000)
            pygame.quit()
            return 1

        self.existing_games = self.get_existing_games()
        self.games = self.fetch_game_list()

        if not self.games:
            pygame.quit()
            return 1

        self.filter_games()

        # Debug log
        debug_log = open('/tmp/xbox_dl_debug.log', 'w')
        debug_log.write(f"Games loaded: {len(self.games)}\n")
        debug_log.write(f"Filtered games: {len(self.filtered_games)}\n")
        debug_log.flush()

        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.keyboard_active:
                            self.keyboard_active = False
                        else:
                            running = False
                    elif event.key == pygame.K_RETURN:
                        if self.keyboard_active:
                            self.handle_keyboard_select()
                        elif self.filtered_games:
                            name, href, status = self.filtered_games[self.selected_index]
                            self.download_game(name, href)
                    elif event.key == pygame.K_y:
                        self.keyboard_active = True
                        self.key_row = 0
                        self.key_col = 0

                if event.type == pygame.JOYBUTTONDOWN:
                    debug_log.write(f"JOYBUTTONDOWN: button={event.button}, keyboard_active={self.keyboard_active}, filtered={len(self.filtered_games)}\n")
                    debug_log.flush()
                    if event.button == 0:  # A button
                        if self.keyboard_active:
                            self.handle_keyboard_select()
                        elif self.filtered_games:
                            name, href, status = self.filtered_games[self.selected_index]
                            debug_log.write(f"Downloading: {name}\n")
                            debug_log.flush()
                            self.download_game(name, href)
                    elif event.button == 1:  # B button
                        debug_log.write("B button - exiting\n")
                        debug_log.flush()
                        if self.keyboard_active:
                            self.keyboard_active = False
                        else:
                            running = False
                    elif event.button == 2:  # X button - Download All
                        if not self.keyboard_active:
                            self.download_all()
                    elif event.button == 3:  # Y button
                        self.keyboard_active = True
                        self.key_row = 0
                        self.key_col = 0

            # Handle held directions
            action = self.check_input()
            if action:
                if self.keyboard_active:
                    self.handle_keyboard_input(action)
                else:
                    self.handle_list_input(action)

            # Draw
            if self.downloading:
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
    app = XboxDownloaderUI()
    return app.run()


if __name__ == '__main__':
    sys.exit(main())
