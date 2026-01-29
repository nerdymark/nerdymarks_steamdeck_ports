#!/usr/bin/env python3
"""
nerdymark's PS2 Downloader for ES-DE
Downloads games from Myrient's Redump PlayStation 2 collection
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
import time
from pathlib import Path

# Add shared module path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from gloomy_aesthetic import (
    GloomyBackground, draw_nerdymark_brand, draw_title_with_glow, create_panel,
    get_theme, VOID_BLACK, DEEP_GRAY, SMOKE_GRAY, MIST_GRAY, PALE_GRAY, FOG_WHITE,
    HOPE_BLUE, GLOOMY_BLUE
)
from git_update import UpdateChecker

BASE_URL = "https://myrient.erista.me/files/Redump/Sony%20-%20PlayStation%202/"
PS2_ROM_DIR = "/run/media/deck/SK256/Emulation/roms/ps2"
SOUND_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tada.mp3")

# Disk space thresholds (in GB)
DISK_SPACE_WARNING = 20  # Yellow when below 20GB
DISK_SPACE_CRITICAL = 10  # Red when below 10GB

# Colors - PS2 Blue theme
THEME = get_theme('ps2')
ACCENT = THEME['accent']
ACCENT_DIM = THEME['accent_dim']
HIGHLIGHT = THEME['highlight']

BLACK = VOID_BLACK
WHITE = FOG_WHITE
GREEN = (70, 150, 90)
DARK_GREEN = (40, 90, 50)
GRAY = MIST_GRAY
DARK_GRAY = DEEP_GRAY
LIGHT_GRAY = SMOKE_GRAY
YELLOW = (180, 170, 80)
RED = (180, 70, 70)
BLUE = ACCENT

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


class PS2DownloaderUI:
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
        pygame.display.set_caption("nerdymark's PS2 Downloader")

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
        # Git update checker
        self.update_checker = UpdateChecker()
        self.update_banner_visible = False

    def get_existing_games(self):
        """Get list of already downloaded games"""
        existing = set()
        rom_path = Path(PS2_ROM_DIR)
        if rom_path.exists():
            for f in rom_path.iterdir():
                if f.suffix.lower() in ['.zip', '.iso', '.chd', '.cso', '.zso']:
                    existing.add(f.stem)
        return existing

    def fetch_game_list(self):
        self.draw_message("Connecting to Myrient...", "Fetching PS2 game list, please wait")
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
        """Get free disk space in GB for the ROM directory"""
        try:
            stat = os.statvfs(PS2_ROM_DIR)
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
        """Play the completion sound if available"""
        if self.completion_sound:
            try:
                self.completion_sound.play()
            except:
                pass

    def draw_message(self, title, message):
        self.background.update()
        self.background.draw(self.screen)
        draw_title_with_glow(self.screen, self.font_large, title, ACCENT, self.height//2 - 50)
        msg_surf = self.font_medium.render(message, True, WHITE)
        self.screen.blit(msg_surf, (self.width//2 - msg_surf.get_width()//2, self.height//2 + 10))
        draw_nerdymark_brand(self.screen, self.font_brand, ACCENT_DIM)

    def draw_main_menu(self):
        self.background.update()
        self.background.draw(self.screen)
        self.draw_disk_space()

        draw_title_with_glow(self.screen, self.font_large, "NERDYMARK'S PS2 DOWNLOADER", ACCENT, 20)

        stats = f"{len(self.games)} games available | {len(self.existing_games)} downloaded | {len(self.filtered_games)} shown"
        stats_surf = self.font_small.render(stats, True, PALE_GRAY)
        self.screen.blit(stats_surf, (self.width//2 - stats_surf.get_width()//2, 70))

        search_panel = create_panel(self.width - 100, 40, border_color=ACCENT_DIM if self.keyboard_active else SMOKE_GRAY)
        self.screen.blit(search_panel, (50, 100))
        search_label = f"Search: {self.search_text}_" if not self.keyboard_active else f"Search: {self.search_text}"
        search_surf = self.font_medium.render(search_label, True, HIGHLIGHT if self.keyboard_active else WHITE)
        self.screen.blit(search_surf, (60, 108))

        list_panel = create_panel(self.width - 80, self.height - 230, border_color=SMOKE_GRAY)
        self.screen.blit(list_panel, (40, 155))

        list_top = 160
        for i in range(self.visible_items):
            idx = i + self.scroll_offset
            if idx >= len(self.filtered_games):
                break

            name, href, status = self.filtered_games[idx]
            y = list_top + i * 40

            if idx == self.selected_index:
                highlight_surface = pygame.Surface((self.width - 100, 38), pygame.SRCALPHA)
                pygame.draw.rect(highlight_surface, (*ACCENT_DIM, 120), (0, 0, self.width - 100, 38), border_radius=3)
                self.screen.blit(highlight_surface, (50, y))

            display_name = name[:60] + "..." if len(name) > 60 else name
            if status:
                display_name += f"  {status}"

            color = MIST_GRAY if status else PALE_GRAY
            if idx == self.selected_index:
                color = HIGHLIGHT if status else ACCENT

            text_surf = self.font_small.render(display_name, True, color)
            self.screen.blit(text_surf, (60, y + 8))

        if len(self.filtered_games) > self.visible_items:
            bar_height = self.height - 220
            handle_height = max(30, bar_height * self.visible_items // len(self.filtered_games))
            handle_pos = bar_height * self.scroll_offset // max(1, len(self.filtered_games) - self.visible_items)
            pygame.draw.rect(self.screen, DEEP_GRAY, (self.width - 30, 160, 10, bar_height), border_radius=5)
            pygame.draw.rect(self.screen, ACCENT_DIM, (self.width - 30, 160 + handle_pos, 10, handle_height), border_radius=5)

        controls = "[D-PAD] Navigate  [A] Download  [X] Download All  [Y] Search  [B] Quit"
        controls_surf = self.font_small.render(controls, True, MIST_GRAY)
        self.screen.blit(controls_surf, (self.width//2 - controls_surf.get_width()//2, self.height - 40))

        draw_nerdymark_brand(self.screen, self.font_brand, ACCENT_DIM)
        self.draw_update_banner()

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
                self.screen.blit(key_surf, (x + w//2 - key_surf.get_width()//2, y + key_size//2 - key_surf.get_height()//2))

    def draw_download_progress(self):
        self.background.update()
        self.background.draw(self.screen)
        self.draw_disk_space()

        draw_title_with_glow(self.screen, self.font_large, "DOWNLOADING", ACCENT, self.height//2 - 120)

        name_surf = self.font_medium.render(self.download_game_name[:50], True, PALE_GRAY)
        self.screen.blit(name_surf, (self.width//2 - name_surf.get_width()//2, self.height//2 - 60))

        bar_width = self.width - 200
        bar_height = 40
        bar_x = 100
        bar_y = self.height // 2
        pygame.draw.rect(self.screen, DEEP_GRAY, (bar_x, bar_y, bar_width, bar_height), border_radius=5)
        pygame.draw.rect(self.screen, SMOKE_GRAY, (bar_x, bar_y, bar_width, bar_height), width=1, border_radius=5)
        fill_width = int(bar_width * self.download_progress / 100)
        if fill_width > 0:
            pygame.draw.rect(self.screen, ACCENT_DIM, (bar_x, bar_y, fill_width, bar_height), border_radius=5)

        pct_surf = self.font_medium.render(f"{self.download_progress}%", True, WHITE)
        self.screen.blit(pct_surf, (self.width//2 - pct_surf.get_width()//2, bar_y + 8))

        if self.download_speed:
            speed_surf = self.font_small.render(self.download_speed, True, MIST_GRAY)
            self.screen.blit(speed_surf, (self.width//2 - speed_surf.get_width()//2, bar_y + 60))

        status_surf = self.font_small.render(self.download_status, True, HIGHLIGHT)
        self.screen.blit(status_surf, (self.width//2 - status_surf.get_width()//2, bar_y + 100))

        cancel_surf = self.font_small.render("[B] Cancel", True, (180, 70, 70))
        self.screen.blit(cancel_surf, (self.width//2 - cancel_surf.get_width()//2, self.height - 50))

        draw_nerdymark_brand(self.screen, self.font_brand, ACCENT_DIM)

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
        """Download a PS2 game - save the ZIP directly"""
        self.downloading = True
        self.download_game_name = game_name
        self.download_progress = 0
        self.download_speed = ""
        self.download_status = "Starting download..."

        download_url = BASE_URL + href
        filename = urllib.parse.unquote(href)
        dest_path = os.path.join(PS2_ROM_DIR, filename)

        try:
            # Get file size first
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

            # Start wget
            proc = subprocess.Popen(
                ['wget', '-O', dest_path, '-q', download_url],
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
                    if os.path.exists(dest_path):
                        os.remove(dest_path)
                    break

                if os.path.exists(dest_path):
                    size = os.path.getsize(dest_path)
                    size_mb = size / (1024 * 1024)
                    if total_mb > 0:
                        self.download_progress = int((size / total_size) * 100)
                        self.download_speed = f"{size_mb:.0f} / {total_mb:.0f} MB"
                    else:
                        self.download_speed = f"{size_mb:.0f} MB"

                self.download_status = "Downloading..."
                self.draw_download_progress()
                pygame.display.flip()
                self.clock.tick(5)

            if cancelled or proc.returncode != 0:
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                self.downloading = False
                return False

            self.download_progress = 100
            self.download_status = "Complete!"
            self.draw_download_progress()
            pygame.display.flip()

            self.play_completion_sound()
            pygame.time.wait(1000)

        except Exception as e:
            if os.path.exists(dest_path):
                os.remove(dest_path)
            self.downloading = False
            return False

        self.downloading = False
        self.existing_games = self.get_existing_games()
        self.filter_games()
        return True

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
        banner_surface.blit(text_surf, (self.width//2 - text_surf.get_width()//2, 6))
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
        """Show dialog offering to update. Returns True if user chose to update."""
        selected = 0
        options = ["Update Now", "Skip"]

        while True:
            self.background.update()
            self.background.draw(self.screen)
            draw_title_with_glow(self.screen, self.font_large, "UPDATE AVAILABLE", ACCENT, self.height//2 - 100)

            msg = f"{self.update_checker._status['behind']} new commits available"
            msg_surf = self.font_medium.render(msg, True, PALE_GRAY)
            self.screen.blit(msg_surf, (self.width//2 - msg_surf.get_width()//2, self.height//2 - 40))

            for i, opt in enumerate(options):
                y = self.height//2 + 20 + i * 50
                color = ACCENT if i == selected else MIST_GRAY
                opt_surf = self.font_medium.render(f"{'> ' if i == selected else '  '}{opt}", True, color)
                self.screen.blit(opt_surf, (self.width//2 - opt_surf.get_width()//2, y))

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
        os.makedirs(PS2_ROM_DIR, exist_ok=True)

        # Check for updates at startup
        self.check_for_updates()

        self.existing_games = self.get_existing_games()
        self.games = self.fetch_game_list()

        if not self.games:
            pygame.quit()
            return 1

        self.filter_games()

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
                    if event.button == 0:  # A button
                        if self.keyboard_active:
                            self.handle_keyboard_select()
                        elif self.filtered_games:
                            name, href, status = self.filtered_games[self.selected_index]
                            self.download_game(name, href)
                    elif event.button == 1:  # B button
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

            action = self.check_input()
            if action:
                if self.keyboard_active:
                    self.handle_keyboard_input(action)
                else:
                    self.handle_list_input(action)

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
    app = PS2DownloaderUI()
    return app.run()


if __name__ == '__main__':
    sys.exit(main())
