#!/usr/bin/env python3
"""Launch the Lightbox web dashboard.

Usage:
    python dashboard.py [--port 8780] [--no-browser]
"""

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch Lightbox web dashboard")
    parser.add_argument("--port", type=int, default=8780, help="Port to listen on (default: 8780)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser on launch")
    args = parser.parse_args()

    try:
        from lightbox.web.app import create_app
    except ImportError:
        print("Lightbox GUI requires Flask. Install with: pip install lightbox-rec[gui]",
              file=sys.stderr)
        sys.exit(1)

    import threading
    import webbrowser

    app = create_app()
    url = f"http://{args.host}:{args.port}"

    print(f"Lightbox Dashboard: {url}")

    if not args.no_browser:
        import time

        def open_browser() -> None:
            time.sleep(1.0)
            webbrowser.open(url)

        threading.Thread(target=open_browser, daemon=True).start()

    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
