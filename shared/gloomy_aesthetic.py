#!/usr/bin/env python3
"""
Gloomy Aesthetic Module for nerdymark's Tools
Post-vaporwave aesthetic: dimly backlit skyline, fog, rain effects
"The party's over, but there's still hope..."
"""

import pygame
import random
import math

# Base dark palette
VOID_BLACK = (8, 8, 12)
DEEP_GRAY = (18, 20, 28)
SMOKE_GRAY = (35, 38, 48)
MIST_GRAY = (55, 60, 75)
PALE_GRAY = (90, 95, 110)
FOG_WHITE = (140, 145, 160)

# Accent colors (muted, gloomy versions)
GLOOMY_GREEN = (45, 120, 70)
GLOOMY_BLUE = (50, 90, 140)
GLOOMY_RED = (140, 55, 55)
GLOOMY_ORANGE = (160, 90, 40)
GLOOMY_YELLOW = (160, 150, 70)
GLOOMY_CYAN = (50, 120, 130)

# Highlight colors (for selected items, hope in the darkness)
HOPE_GREEN = (80, 180, 100)
HOPE_BLUE = (80, 140, 200)
HOPE_RED = (200, 90, 90)
HOPE_ORANGE = (220, 140, 60)
HOPE_YELLOW = (220, 210, 100)

# Rain/water colors
RAIN_COLOR = (100, 110, 130, 80)
PUDDLE_COLOR = (40, 45, 60)


class RainDrop:
    """A single rain drop particle"""
    def __init__(self, width, height):
        self.reset(width, height, start_top=False)

    def reset(self, width, height, start_top=True):
        self.x = random.randint(0, width)
        self.y = random.randint(-height, 0) if start_top else random.randint(0, height)
        self.speed = random.uniform(8, 15)
        self.length = random.randint(10, 25)
        self.alpha = random.randint(40, 100)
        self.width = width
        self.height = height

    def update(self):
        self.y += self.speed
        self.x += 1  # Slight wind
        if self.y > self.height:
            self.reset(self.width, self.height)

    def draw(self, surface):
        end_y = min(self.y + self.length, self.height)
        color = (100, 110, 130, self.alpha)
        pygame.draw.line(surface, color[:3], (self.x, self.y), (self.x + 2, end_y), 1)


class FogLayer:
    """Animated fog effect"""
    def __init__(self, width, height, density=0.3):
        self.width = width
        self.height = height
        self.density = density
        self.offset = 0
        self.blobs = []
        for _ in range(int(15 * density)):
            self.blobs.append({
                'x': random.randint(0, width),
                'y': random.randint(height // 2, height),
                'radius': random.randint(100, 300),
                'alpha': random.randint(10, 30),
                'speed': random.uniform(0.2, 0.8)
            })

    def update(self):
        self.offset += 0.3
        for blob in self.blobs:
            blob['x'] += blob['speed']
            if blob['x'] > self.width + blob['radius']:
                blob['x'] = -blob['radius']

    def draw(self, surface):
        fog_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        for blob in self.blobs:
            for r in range(0, blob['radius'], 20):
                alpha = int(blob['alpha'] * (1 - r / blob['radius']))
                if alpha > 0:
                    pygame.draw.circle(fog_surface, (100, 105, 120, alpha),
                                      (int(blob['x']), int(blob['y'])), blob['radius'] - r)
        surface.blit(fog_surface, (0, 0))


class Skyline:
    """Dimly backlit city skyline"""
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.buildings = self._generate_buildings()
        self.glow_offset = 0

    def _generate_buildings(self):
        buildings = []
        x = 0
        while x < self.width:
            w = random.randint(30, 80)
            h = random.randint(80, 250)
            buildings.append({
                'x': x,
                'width': w,
                'height': h,
                'windows': self._generate_windows(w, h)
            })
            x += w + random.randint(-5, 10)
        return buildings

    def _generate_windows(self, building_w, building_h):
        windows = []
        for wy in range(20, building_h - 10, 15):
            for wx in range(5, building_w - 8, 12):
                if random.random() < 0.15:  # 15% of windows lit
                    windows.append({
                        'x': wx,
                        'y': wy,
                        'brightness': random.uniform(0.3, 1.0),
                        'flicker': random.random() < 0.1
                    })
        return windows

    def update(self):
        self.glow_offset += 0.02
        # Flicker some windows
        for building in self.buildings:
            for window in building['windows']:
                if window['flicker'] and random.random() < 0.05:
                    window['brightness'] = random.uniform(0.2, 1.0)

    def draw(self, surface, accent_color):
        base_y = self.height - 100  # Skyline base position

        # Draw dim backlight glow
        glow_intensity = 0.3 + 0.1 * math.sin(self.glow_offset)
        glow_color = tuple(int(c * glow_intensity * 0.3) for c in accent_color)
        for i in range(60, 0, -2):
            alpha = int(15 * (i / 60))
            glow_surface = pygame.Surface((self.width, i * 2), pygame.SRCALPHA)
            pygame.draw.ellipse(glow_surface, (*glow_color, alpha),
                               (0, 0, self.width, i * 2))
            surface.blit(glow_surface, (0, base_y - i))

        # Draw buildings
        for building in self.buildings:
            bx = building['x']
            bw = building['width']
            bh = building['height']
            by = base_y - bh

            # Building silhouette
            pygame.draw.rect(surface, DEEP_GRAY, (bx, by, bw, bh))
            pygame.draw.rect(surface, SMOKE_GRAY, (bx, by, bw, bh), 1)

            # Lit windows
            for window in building['windows']:
                wx = bx + window['x']
                wy = by + window['y']
                brightness = window['brightness']
                window_color = tuple(int(c * brightness * 0.6) for c in accent_color)
                pygame.draw.rect(surface, window_color, (wx, wy, 6, 8))

        # Ground line with puddle reflections
        pygame.draw.rect(surface, PUDDLE_COLOR, (0, base_y, self.width, 100))
        pygame.draw.line(surface, SMOKE_GRAY, (0, base_y), (self.width, base_y), 2)


class GloomyBackground:
    """Complete gloomy background with all effects"""
    def __init__(self, width, height, accent_color=HOPE_GREEN, rain_intensity=0.5):
        self.width = width
        self.height = height
        self.accent_color = accent_color

        # Initialize effects
        self.skyline = Skyline(width, height)
        self.fog = FogLayer(width, height, density=0.4)

        # Rain particles
        num_drops = int(100 * rain_intensity)
        self.rain = [RainDrop(width, height) for _ in range(num_drops)]

        # Pre-render static elements
        self.static_surface = None
        self._render_static()

    def _render_static(self):
        """Pre-render elements that don't change much"""
        self.static_surface = pygame.Surface((self.width, self.height))
        self.static_surface.fill(VOID_BLACK)

    def update(self):
        self.skyline.update()
        self.fog.update()
        for drop in self.rain:
            drop.update()

    def draw(self, surface):
        # Base dark background
        surface.fill(VOID_BLACK)

        # Skyline with glow
        self.skyline.draw(surface, self.accent_color)

        # Fog layer
        self.fog.draw(surface)

        # Rain
        for drop in self.rain:
            drop.draw(surface)

    def set_accent_color(self, color):
        self.accent_color = color


def draw_nerdymark_brand(surface, font, accent_color, position="bottom_right"):
    """Draw the nerdymark branding"""
    width = surface.get_width()
    height = surface.get_height()

    # Create brand text with glow effect
    brand_text = "nerdymark"

    # Glow layer
    glow_color = tuple(max(0, c - 60) for c in accent_color)
    glow_surf = font.render(brand_text, True, glow_color)

    # Main text
    text_surf = font.render(brand_text, True, accent_color)

    # Position
    if position == "bottom_right":
        x = width - text_surf.get_width() - 20
        y = height - text_surf.get_height() - 15
    elif position == "bottom_left":
        x = 20
        y = height - text_surf.get_height() - 15
    elif position == "top_right":
        x = width - text_surf.get_width() - 20
        y = 15
    else:  # top_left
        x = 20
        y = 15

    # Draw glow (offset slightly)
    for ox, oy in [(-1, -1), (1, -1), (-1, 1), (1, 1), (0, -2), (0, 2), (-2, 0), (2, 0)]:
        surface.blit(glow_surf, (x + ox, y + oy))

    # Draw main text
    surface.blit(text_surf, (x, y))


def draw_title_with_glow(surface, font, text, accent_color, y_pos, center_x=None):
    """Draw a title with glow effect"""
    if center_x is None:
        center_x = surface.get_width() // 2

    # Glow layers
    for offset in range(4, 0, -1):
        glow_alpha = 60 - offset * 15
        glow_color = tuple(max(0, min(255, c - 40)) for c in accent_color)
        glow_surf = font.render(text, True, glow_color)
        glow_surf.set_alpha(glow_alpha)
        surface.blit(glow_surf, (center_x - glow_surf.get_width() // 2, y_pos))

    # Main text
    text_surf = font.render(text, True, accent_color)
    surface.blit(text_surf, (center_x - text_surf.get_width() // 2, y_pos))


def create_panel(width, height, border_color=SMOKE_GRAY, fill_color=None):
    """Create a semi-transparent panel with border"""
    if fill_color is None:
        fill_color = (*DEEP_GRAY, 180)

    panel = pygame.Surface((width, height), pygame.SRCALPHA)

    # Fill with semi-transparent dark
    pygame.draw.rect(panel, fill_color, (0, 0, width, height), border_radius=5)

    # Border
    pygame.draw.rect(panel, border_color, (0, 0, width, height), width=1, border_radius=5)

    return panel


# Additional accent colors for new systems
GLOOMY_PURPLE = (90, 60, 130)
HOPE_PURPLE = (140, 100, 200)
GLOOMY_TEAL = (40, 100, 110)
HOPE_TEAL = (70, 160, 180)
GLOOMY_PINK = (130, 60, 100)
HOPE_PINK = (200, 100, 150)

# Color schemes for different tools
TOOL_THEMES = {
    'xbox': {
        'accent': HOPE_GREEN,
        'accent_dim': GLOOMY_GREEN,
        'highlight': (100, 200, 120),
    },
    'neogeo': {
        'accent': HOPE_BLUE,
        'accent_dim': GLOOMY_BLUE,
        'highlight': (100, 160, 220),
    },
    'jaguar': {
        'accent': HOPE_RED,
        'accent_dim': GLOOMY_RED,
        'highlight': (220, 110, 110),
    },
    'mame': {
        'accent': HOPE_ORANGE,
        'accent_dim': GLOOMY_ORANGE,
        'highlight': (240, 160, 80),
    },
    'dos': {
        'accent': HOPE_YELLOW,
        'accent_dim': GLOOMY_YELLOW,
        'highlight': (240, 230, 120),
    },
    'ps2': {
        'accent': HOPE_BLUE,
        'accent_dim': GLOOMY_BLUE,
        'highlight': (100, 150, 230),
    },
    'gamecube': {
        'accent': HOPE_PURPLE,
        'accent_dim': GLOOMY_PURPLE,
        'highlight': (170, 130, 230),
    },
    'saturn': {
        'accent': HOPE_TEAL,
        'accent_dim': GLOOMY_TEAL,
        'highlight': (100, 190, 210),
    },
    'ngp': {
        'accent': (180, 160, 100),  # Gold/tan for Neo Geo Pocket
        'accent_dim': (120, 100, 60),
        'highlight': (220, 200, 140),
    },
    'jaguar': {
        'accent': HOPE_RED,
        'accent_dim': GLOOMY_RED,
        'highlight': (220, 110, 110),
    },
    'vectrex': {
        'accent': (100, 200, 100),  # Vector green
        'accent_dim': (50, 120, 50),
        'highlight': (140, 240, 140),
    },
    'gamecom': {
        'accent': (200, 180, 100),  # Tiger yellow/gold
        'accent_dim': (140, 120, 60),
        'highlight': (240, 220, 140),
    },
    'pokemini': {
        'accent': (255, 200, 80),  # Pikachu yellow
        'accent_dim': (180, 140, 50),
        'highlight': (255, 230, 120),
    },
}


def get_theme(tool_name):
    """Get color theme for a specific tool"""
    return TOOL_THEMES.get(tool_name, TOOL_THEMES['mame'])
