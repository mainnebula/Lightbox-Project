#!/usr/bin/env python3
"""
Lightbox CLI Animation - Compact Cassette Style
"""

import time
import sys

# ANSI escape codes
CLEAR = "\033[2J\033[H"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
RED = "\033[91m"
GREEN = "\033[92m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"

# Spinner characters for reel rotation
SPINNER = ["─", "╲", "│", "╱"]


def render_frame(frame_num, mode="REC"):
    """Render a single animation frame"""
    
    # Reel rotation
    spoke = SPINNER[frame_num % 4]
    
    # Recording indicator
    if mode == "REC":
        rec = f"{RED}● REC{RESET}" if frame_num % 2 == 0 else f"{DIM}○ REC{RESET}"
    else:
        rec = f"{GREEN}▶ PLAY{RESET}"
    
    # VU meter
    vu_states = ["[I  ]", "[II ]", "[III]", "[II ]"]
    vu = vu_states[frame_num % 4]
    
    output = f"""\
┌─────────────────────────┐
│  ◓───────────────────◒  │
│  ╭───╮           ╭───╮  │
│  │ {spoke} │ ▮▮▮▮▮▮▮▮▮ │ {spoke} │  │
│  ╰───╯           ╰───╯  │
│  {rec}          {vu}   │
└─────────────────────────┘"""
    return output


def run_animation(duration=10, mode="REC"):
    """Run the animation"""
    start_time = time.time()
    frame = 0
    
    sys.stdout.write(HIDE_CURSOR)
    
    try:
        while True:
            elapsed = time.time() - start_time
            if elapsed > duration:
                break
            
            sys.stdout.write(CLEAR)
            sys.stdout.write(render_frame(frame, mode))
            sys.stdout.flush()
            
            frame += 1
            time.sleep(0.15)
            
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(SHOW_CURSOR)
    
    print(f"\n{GREEN}✓ Complete{RESET}\n")


def show_frames():
    """Show all 4 frames"""
    for i in range(4):
        print(f"Frame {i+1}:")
        print(render_frame(i, "REC"))
        print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--frames":
        show_frames()
    else:
        print(f"\n{BOLD}Lightbox{RESET}")
        print("Press Ctrl+C to stop\n")
        time.sleep(0.5)
        run_animation(duration=10, mode="REC")