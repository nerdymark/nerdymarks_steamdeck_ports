#!/usr/bin/env python3
"""
Git Self-Update Module for nerdymark's Tools
Checks for updates from the git remote and offers to update if behind.
Respects local changes - won't auto-update if there are uncommitted modifications.
"""

import subprocess
import os


# Path to the git repository root
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_git_command(args, cwd=None):
    """Run a git command and return (success, output)"""
    if cwd is None:
        cwd = REPO_ROOT
    try:
        result = subprocess.run(
            ['git'] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)


def is_git_repo():
    """Check if we're in a git repository"""
    success, _ = run_git_command(['rev-parse', '--git-dir'])
    return success


def get_current_branch():
    """Get the current branch name"""
    success, output = run_git_command(['rev-parse', '--abbrev-ref', 'HEAD'])
    return output if success else None


def has_local_changes():
    """Check if there are any uncommitted changes (staged or unstaged)"""
    # Check for staged changes
    success, output = run_git_command(['diff', '--cached', '--quiet'])
    if not success:
        return True

    # Check for unstaged changes
    success, output = run_git_command(['diff', '--quiet'])
    if not success:
        return True

    return False


def has_untracked_files():
    """Check if there are untracked files (excluding ignored)"""
    success, output = run_git_command(['ls-files', '--others', '--exclude-standard'])
    return bool(output.strip()) if success else False


def fetch_remote():
    """Fetch from origin to get latest refs"""
    success, _ = run_git_command(['fetch', 'origin', '--quiet'])
    return success


def get_commits_behind():
    """Get number of commits we're behind origin"""
    branch = get_current_branch()
    if not branch:
        return 0

    success, output = run_git_command([
        'rev-list', '--count', f'HEAD..origin/{branch}'
    ])

    if success and output.isdigit():
        return int(output)
    return 0


def get_commits_ahead():
    """Get number of commits we're ahead of origin"""
    branch = get_current_branch()
    if not branch:
        return 0

    success, output = run_git_command([
        'rev-list', '--count', f'origin/{branch}..HEAD'
    ])

    if success and output.isdigit():
        return int(output)
    return 0


def pull_updates():
    """Pull updates from origin (fast-forward only to be safe)"""
    success, output = run_git_command(['pull', '--ff-only', 'origin'])
    return success, output


def check_for_updates(fetch=True):
    """
    Check if updates are available.

    Returns a dict with:
        - update_available: bool - True if we can safely update
        - behind: int - Number of commits behind
        - ahead: int - Number of commits ahead
        - has_changes: bool - True if there are local modifications
        - message: str - Human-readable status message
        - can_update: bool - True if update is safe (no local changes, behind origin)
    """
    result = {
        'update_available': False,
        'behind': 0,
        'ahead': 0,
        'has_changes': False,
        'message': '',
        'can_update': False
    }

    if not is_git_repo():
        result['message'] = 'Not a git repository'
        return result

    # Fetch latest from remote
    if fetch:
        if not fetch_remote():
            result['message'] = 'Could not fetch from remote'
            return result

    # Check for local changes
    result['has_changes'] = has_local_changes()

    # Get commit counts
    result['behind'] = get_commits_behind()
    result['ahead'] = get_commits_ahead()

    # Determine if we can update
    if result['behind'] > 0:
        result['update_available'] = True
        if result['has_changes']:
            result['message'] = f"Update available ({result['behind']} commits) - local changes prevent auto-update"
            result['can_update'] = False
        elif result['ahead'] > 0:
            result['message'] = f"Update available ({result['behind']} behind, {result['ahead']} ahead) - diverged from origin"
            result['can_update'] = False
        else:
            result['message'] = f"Update available ({result['behind']} commits behind)"
            result['can_update'] = True
    elif result['ahead'] > 0:
        result['message'] = f"Ahead of origin by {result['ahead']} commits"
    else:
        result['message'] = 'Up to date'

    return result


def perform_update():
    """
    Attempt to update the repository.

    Returns (success, message)
    """
    # Double-check we can update
    status = check_for_updates(fetch=False)

    if not status['can_update']:
        return False, status['message']

    success, output = pull_updates()
    if success:
        return True, f"Updated successfully! Restart the tool to use the new version."
    else:
        return False, f"Update failed: {output}"


class UpdateChecker:
    """
    Helper class for UI integration.
    Caches update check results to avoid repeated git operations.
    """

    def __init__(self):
        self._status = None
        self._checked = False

    def check(self, force=False):
        """Check for updates (cached unless force=True)"""
        if not self._checked or force:
            self._status = check_for_updates()
            self._checked = True
        return self._status

    @property
    def update_available(self):
        """True if an update is available"""
        if self._status is None:
            self.check()
        return self._status.get('update_available', False)

    @property
    def can_update(self):
        """True if we can safely auto-update"""
        if self._status is None:
            self.check()
        return self._status.get('can_update', False)

    @property
    def message(self):
        """Human-readable status message"""
        if self._status is None:
            self.check()
        return self._status.get('message', '')

    @property
    def behind(self):
        """Number of commits behind"""
        if self._status is None:
            self.check()
        return self._status.get('behind', 0)

    def update(self):
        """Perform the update"""
        return perform_update()


class UpdateUI:
    """
    Pygame UI helper for git updates.
    Provides reusable methods for update banner and dialogs.
    """

    def __init__(self, screen, fonts, colors, background, checker=None):
        """
        Initialize UpdateUI.

        Args:
            screen: Pygame screen surface
            fonts: Dict with 'tiny', 'small', 'medium', 'large', 'brand' fonts
            colors: Dict with 'accent', 'accent_dim', 'mist_gray', 'pale_gray' colors
            background: GloomyBackground instance
            checker: Optional UpdateChecker instance (creates one if not provided)
        """
        self.screen = screen
        self.fonts = fonts
        self.colors = colors
        self.background = background
        self.checker = checker or UpdateChecker()
        self.banner_visible = False
        self.width = screen.get_width()
        self.height = screen.get_height()

    def check_for_updates(self, draw_message_fn):
        """
        Check for updates and show dialog if update can be applied.

        Args:
            draw_message_fn: Function to draw a message (title, subtitle)

        Returns:
            True if tool should restart after update
        """
        draw_message_fn("Checking for updates...", "Please wait")
        import pygame
        pygame.display.flip()

        status = self.checker.check()
        if status['update_available']:
            self.banner_visible = True
            if status['can_update']:
                return self.offer_update_dialog()
        return False

    def draw_banner(self):
        """Draw update available notification banner at top of screen"""
        if not self.banner_visible:
            return

        import pygame
        banner_height = 30
        banner_surface = pygame.Surface((self.width, banner_height), pygame.SRCALPHA)
        pygame.draw.rect(banner_surface, (80, 60, 20, 200), (0, 0, self.width, banner_height))

        msg = self.checker.message
        if self.checker.can_update:
            msg += " - Press SELECT to update"

        text_surf = self.fonts['tiny'].render(msg, True, (255, 220, 100))
        banner_surface.blit(text_surf, (self.width//2 - text_surf.get_width()//2, 6))
        self.screen.blit(banner_surface, (0, 0))

    def offer_update_dialog(self, joystick=None):
        """
        Show dialog offering to update.

        Args:
            joystick: Optional pygame joystick for navigation

        Returns:
            True if update was performed and tool should restart
        """
        import pygame
        from gloomy_aesthetic import draw_title_with_glow, draw_nerdymark_brand

        selected = 0
        options = ["Update Now", "Skip"]
        clock = pygame.time.Clock()

        while True:
            self.background.update()
            self.background.draw(self.screen)

            draw_title_with_glow(
                self.screen, self.fonts['large'], "UPDATE AVAILABLE",
                self.colors['accent'], self.height//2 - 100
            )

            msg = f"{self.checker.behind} new commits available"
            msg_surf = self.fonts['medium'].render(msg, True, self.colors['pale_gray'])
            self.screen.blit(msg_surf, (self.width//2 - msg_surf.get_width()//2, self.height//2 - 40))

            for i, opt in enumerate(options):
                y = self.height//2 + 20 + i * 50
                color = self.colors['accent'] if i == selected else self.colors['mist_gray']
                prefix = "> " if i == selected else "  "
                opt_surf = self.fonts['medium'].render(f"{prefix}{opt}", True, color)
                self.screen.blit(opt_surf, (self.width//2 - opt_surf.get_width()//2, y))

            draw_nerdymark_brand(self.screen, self.fonts['brand'], self.colors['accent_dim'])
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
                    if event.button == 0:  # A
                        if selected == 0:
                            return self.perform_update()
                        return False
                    elif event.button == 1:  # B
                        return False

            if joystick and joystick.get_numhats() > 0:
                hat = joystick.get_hat(0)
                if hat[1] == 1:
                    selected = max(0, selected - 1)
                    pygame.time.wait(150)
                elif hat[1] == -1:
                    selected = min(len(options) - 1, selected + 1)
                    pygame.time.wait(150)

            clock.tick(30)

    def perform_update(self):
        """Perform the git update and show result. Returns True if successful."""
        import pygame
        import sys
        from gloomy_aesthetic import draw_title_with_glow, draw_nerdymark_brand

        self.background.update()
        self.background.draw(self.screen)
        draw_title_with_glow(
            self.screen, self.fonts['large'], "UPDATING...",
            self.colors['accent'], self.height//2 - 50
        )
        msg_surf = self.fonts['medium'].render("Pulling latest changes from git", True, self.colors['pale_gray'])
        self.screen.blit(msg_surf, (self.width//2 - msg_surf.get_width()//2, self.height//2 + 10))
        pygame.display.flip()

        success, message = self.checker.update()

        self.background.update()
        self.background.draw(self.screen)

        if success:
            draw_title_with_glow(
                self.screen, self.fonts['large'], "UPDATE COMPLETE!",
                self.colors['accent'], self.height//2 - 50
            )
            msg_surf = self.fonts['medium'].render("Please restart the tool", True, self.colors['pale_gray'])
            self.screen.blit(msg_surf, (self.width//2 - msg_surf.get_width()//2, self.height//2 + 10))
            pygame.display.flip()
            pygame.time.wait(3000)
            pygame.quit()
            sys.exit(0)
        else:
            draw_title_with_glow(
                self.screen, self.fonts['large'], "UPDATE FAILED",
                self.colors['accent'], self.height//2 - 50
            )
            msg_surf = self.fonts['medium'].render(message[:60], True, self.colors['pale_gray'])
            self.screen.blit(msg_surf, (self.width//2 - msg_surf.get_width()//2, self.height//2 + 10))
            pygame.display.flip()
            pygame.time.wait(3000)
            return False

    def handle_select_button(self):
        """Handle SELECT button press - trigger update if available and can update"""
        if self.banner_visible and self.checker.can_update:
            return self.perform_update()
        return False
