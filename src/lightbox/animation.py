"""Animation utilities for Lightbox CLI.

Provides cassette tape animations, spinners, and progress bars
for a retro flight-recorder aesthetic.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager

# ANSI escape codes
CLEAR_LINE = "\033[2K\r"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"

# Colors
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Spinner characters
SPINNER_DOTS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
SPINNER_SIMPLE = ["─", "╲", "│", "╱"]

# Progress bar characters
PROGRESS_FILLED = "█"
PROGRESS_EMPTY = "░"
PROGRESS_PARTIAL = ["▏", "▎", "▍", "▌", "▋", "▊", "▉"]


def _colors_enabled() -> bool:
    """Check if colors/animations should be used."""
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def colorize(text: str, color: str) -> str:
    """Wrap text in ANSI color codes if colors are enabled."""
    if not _colors_enabled():
        return text
    return f"{color}{text}{RESET}"


@contextmanager
def hidden_cursor():
    """Context manager to hide cursor during animations."""
    if _colors_enabled():
        sys.stdout.write(HIDE_CURSOR)
        sys.stdout.flush()
    try:
        yield
    finally:
        if _colors_enabled():
            sys.stdout.write(SHOW_CURSOR)
            sys.stdout.flush()


# --- Cassette Tape Animation ---


def render_cassette_frame(frame_num: int, mode: str = "REC", label: str = "") -> str:
    """Render a single cassette animation frame.

    Args:
        frame_num: Animation frame number (for rotation)
        mode: "REC" (recording), "PLAY" (playback), or "STOP"
        label: Optional text to show below cassette
    """
    if not _colors_enabled():
        return f"[{mode}] {label}" if label else f"[{mode}]"

    # --- RESTORED LINE ---
    spoke = SPINNER_SIMPLE[frame_num % 4]

    # Mode indicator with blinking effect
    if mode == "REC":
        indicator = f"{RED}● REC{RESET}" if frame_num % 2 == 0 else f"{DIM}○ REC{RESET}"
    elif mode == "PLAY":
        indicator = f"{GREEN}▶ PLAY{RESET}"
    else:
        indicator = f"{DIM}■ STOP{RESET}"

    # VU meter animation
    vu_states = ["=  ", "== ", "===", "== ", "=  ", "== ", "===", "== "]
    vu = f"{GREEN}[{vu_states[frame_num % 8]}]{RESET}"

    # Tape progress (use simple ASCII)
    filled = frame_num % 9
    tape = "=" * filled + "-" * (8 - filled)

    # Build cassette with Unicode box drawing
    reel_line = f"  │ {CYAN}{spoke}{RESET} │  [{tape}]  │ {CYAN}{spoke}{RESET} │   "
    status_line = f"  {indicator}          {vu}       "

    # FIXED ALIGNMENT: 14 spaces in middle, 3 spaces on right
    output = f"""\
{DIM}┌─────────────────────────────┐
│  o───────────────────────o  │
│  ┌───┐              ┌───┐   │
│{RESET}{reel_line}{DIM}│
│  └───┘              └───┘   │
│{RESET}{status_line}{DIM}│
└─────────────────────────────┘{RESET}"""

    if label:
        output += f"\n  {DIM}{label}{RESET}"

    return output


def cassette_animation(duration: float = 2.0, mode: str = "REC", label: str = "") -> None:
    """Run the cassette tape animation.

    Args:
        duration: How long to animate (seconds)
        mode: "REC", "PLAY", or "STOP"
        label: Optional text below cassette
    """
    if not _colors_enabled():
        print(f"[{mode}] {label}" if label else f"[{mode}]")
        return

    start_time = time.time()
    frame = 0
    frame_height = 8 if label else 7

    with hidden_cursor():
        while time.time() - start_time < duration:
            # Clear previous frame
            if frame > 0:
                sys.stdout.write(f"\033[{frame_height}A")

            sys.stdout.write(render_cassette_frame(frame, mode, label))
            sys.stdout.write("\n")
            sys.stdout.flush()

            frame += 1
            time.sleep(0.12)


# --- Spinner ---


class Spinner:
    """Animated spinner for long-running operations."""

    def __init__(self, message: str = "Working", style: str = "dots"):
        self.message = message
        self.chars = {
            "dots": SPINNER_DOTS,
            "simple": SPINNER_SIMPLE,
        }.get(style, SPINNER_DOTS)
        self.frame = 0

    def _render(self) -> str:
        char = self.chars[self.frame % len(self.chars)]
        if _colors_enabled():
            return f"{CLEAR_LINE}{CYAN}{char}{RESET} {self.message}"
        return f"\r{char} {self.message}"

    def spin(self) -> None:
        """Advance spinner one frame."""
        sys.stdout.write(self._render())
        sys.stdout.flush()
        self.frame += 1

    def succeed(self, message: str | None = None) -> None:
        """Show success state."""
        msg = message or self.message
        if _colors_enabled():
            sys.stdout.write(f"{CLEAR_LINE}{GREEN}✓{RESET} {msg}\n")
        else:
            sys.stdout.write(f"\r[OK] {msg}\n")
        sys.stdout.flush()

    def fail(self, message: str | None = None) -> None:
        """Show failure state."""
        msg = message or self.message
        if _colors_enabled():
            sys.stdout.write(f"{CLEAR_LINE}{RED}✗{RESET} {msg}\n")
        else:
            sys.stdout.write(f"\r[FAIL] {msg}\n")
        sys.stdout.flush()

    def warn(self, message: str | None = None) -> None:
        """Show warning state."""
        msg = message or self.message
        if _colors_enabled():
            sys.stdout.write(f"{CLEAR_LINE}{YELLOW}⚠{RESET} {msg}\n")
        else:
            sys.stdout.write(f"\r[WARN] {msg}\n")
        sys.stdout.flush()


@contextmanager
def spinner(message: str = "Working", style: str = "dots"):
    """Context manager for spinner animation.

    Usage:
        with spinner("Loading") as s:
            do_work()
            s.succeed("Done!")
    """
    s = Spinner(message, style)
    with hidden_cursor():
        try:
            yield s
        except Exception:
            s.fail()
            raise


# --- Progress Bar ---


def progress_bar(
    current: int,
    total: int,
    width: int = 30,
    prefix: str = "",
    suffix: str = "",
) -> str:
    """Render a progress bar.

    Args:
        current: Current progress value
        total: Total value
        width: Bar width in characters
        prefix: Text before bar
        suffix: Text after bar
    """
    percent = 100 if total == 0 else int(100 * current / total)
    filled = int(width * current / total) if total > 0 else width

    if _colors_enabled():
        bar = f"{GREEN}{PROGRESS_FILLED * filled}{RESET}{DIM}{PROGRESS_EMPTY * (width - filled)}{RESET}"
        return f"{prefix}│{bar}│ {percent:3d}% {suffix}"
    else:
        bar = "#" * filled + "-" * (width - filled)
        return f"{prefix}[{bar}] {percent:3d}% {suffix}"


def animated_progress(
    iterable: Iterator,
    total: int,
    prefix: str = "",
    item_name: str = "items",
) -> Iterator:
    """Wrap an iterable with an animated progress bar.

    Usage:
        for event in animated_progress(events, len(events), "Verifying"):
            process(event)
    """
    with hidden_cursor():
        for i, item in enumerate(iterable):
            bar = progress_bar(i, total, prefix=prefix, suffix=f"{i}/{total} {item_name}")
            sys.stdout.write(f"{CLEAR_LINE}{bar}")
            sys.stdout.flush()
            yield item

        # Final state
        bar = progress_bar(total, total, prefix=prefix, suffix=f"{total}/{total} {item_name}")
        sys.stdout.write(f"{CLEAR_LINE}{bar}\n")
        sys.stdout.flush()


# --- Startup Animation ---

LIGHTBOX_LOGO = """\
   _    _ ___ _  _ _____ ___  _____  __
  | |  | |_ _| || |_   _| _ )/ _ \\ \\/ /
  | |__| || || __ | | | | _ \\ (_) >  <
  |____|_|___|_||_| |_| |___/\\___/_/\\_\\"""


def startup_animation(version: str = "", duration: float = 3.0) -> None:
    """Show a fun startup animation.

    Args:
        version: Version string to display
        duration: How long to run the cassette animation (seconds)
    """
    if not _colors_enabled():
        print(f"Lightbox v{version}" if version else "Lightbox")
        return

    with hidden_cursor():
        # Phase 1: Logo reveal (typing effect)
        lines = LIGHTBOX_LOGO.split("\n")
        for line in lines:
            for i, char in enumerate(line):
                if char != " ":
                    sys.stdout.write(colorize(char, CYAN))
                else:
                    sys.stdout.write(char)
                sys.stdout.flush()
                if i % 3 == 0:
                    time.sleep(0.01)
            sys.stdout.write("\n")

        # Tagline
        tagline = "  Flight Recorder for AI Agents"
        sys.stdout.write(f"\n{DIM}")
        for char in tagline:
            sys.stdout.write(char)
            sys.stdout.flush()
            time.sleep(0.02)
        sys.stdout.write(f"{RESET}\n")

        if version:
            sys.stdout.write(f"  {DIM}v{version}{RESET}\n")

        # Cassette animation
        time.sleep(0.3)
        sys.stdout.write("\n")

        # Run cassette for specified duration
        start_time = time.time()
        frame = 0
        while time.time() - start_time < duration:
            if frame > 0:
                sys.stdout.write("\033[7A")
            sys.stdout.write(render_cassette_frame(frame, "REC"))
            sys.stdout.write("\n")
            sys.stdout.flush()
            frame += 1
            time.sleep(0.12)

        sys.stdout.write("\n")


def replay_header(session_id: str, event_count: int) -> None:
    """Show replay header with cassette."""
    if not _colors_enabled():
        print(f">>> REPLAY: {session_id} ({event_count} events)")
        return

    with hidden_cursor():
        # Quick spin-up animation
        for frame in range(6):
            if frame > 0:
                sys.stdout.write("\033[8A")

            sys.stdout.write(
                render_cassette_frame(frame, "PLAY", f"{session_id} ({event_count} events)")
            )
            sys.stdout.write("\n")
            sys.stdout.flush()
            time.sleep(0.1)

        sys.stdout.write("\n")


def replay_event(
    index: int,
    total: int,
    tool: str,
    status: str,
    input_preview: str = "",
    output_preview: str = "",
    error_msg: str = "",
    animate: bool = True,
) -> None:
    """Display a single event during replay."""
    # Progress
    progress = f"[{index + 1}/{total}]"

    # Status icon
    if status == "complete":
        icon = colorize("✓", GREEN) if _colors_enabled() else "[OK]"
    elif status == "error":
        icon = colorize("✗", RED) if _colors_enabled() else "[ERR]"
    else:
        icon = colorize("◌", YELLOW) if _colors_enabled() else "[...]"

    # Tool name
    tool_styled = colorize(tool, CYAN + BOLD) if _colors_enabled() else tool

    print(f"{colorize(progress, DIM)} {icon} {tool_styled}")

    if input_preview:
        print(colorize(f"      → {input_preview}", DIM))

    if output_preview:
        print(colorize(f"      ← {output_preview}", DIM))

    if error_msg:
        print(colorize(f"      ✗ {error_msg}", RED))


def replay_footer() -> None:
    """Show replay completion."""
    if _colors_enabled():
        print(f"\n{MAGENTA}{BOLD}■ REPLAY COMPLETE{RESET}\n")
    else:
        print("\n>>> REPLAY COMPLETE\n")
