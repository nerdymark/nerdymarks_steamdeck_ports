#!/usr/bin/env python3
"""Quick button mapping test for Steam Deck"""
import pygame
pygame.init()
pygame.joystick.init()

screen = pygame.display.set_mode((800, 600))
pygame.display.set_caption("Button Test - Press A, B, X, Y")
font = pygame.font.Font(None, 48)

js = None
if pygame.joystick.get_count() > 0:
    js = pygame.joystick.Joystick(0)
    js.init()

last_buttons = []
running = True
clock = pygame.time.Clock()

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.JOYBUTTONDOWN:
            last_buttons.append(f"Button {event.button}")
            if len(last_buttons) > 8:
                last_buttons.pop(0)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            running = False

    screen.fill((0, 0, 0))

    title = font.render("Press A, B, X, Y buttons", True, (100, 200, 100))
    screen.blit(title, (150, 50))

    hint = font.render("Press ESC or close window to exit", True, (128, 128, 128))
    screen.blit(hint, (120, 100))

    y = 200
    for btn in last_buttons:
        text = font.render(btn, True, (255, 255, 255))
        screen.blit(text, (300, y))
        y += 45

    pygame.display.flip()
    clock.tick(30)

pygame.quit()
