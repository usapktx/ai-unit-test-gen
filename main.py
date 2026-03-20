#!/usr/bin/env python3
"""Entry point — starts Flask server and opens the UI in the default browser."""

import threading
import time
import webbrowser

PORT = 5000


def _open_browser():
    time.sleep(1.2)
    webbrowser.open(f"http://127.0.0.1:{PORT}")


if __name__ == "__main__":
    from app import app

    print(f"\n  .NET Unit Test Generator")
    print(f"  Opening browser at http://127.0.0.1:{PORT}")
    print(f"  Press Ctrl+C to quit.\n")

    threading.Thread(target=_open_browser, daemon=True).start()
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
