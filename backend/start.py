#!/usr/bin/env python3
"""
SwachhNetra POC — One-Command Launcher
Run this file and everything starts automatically.

Usage:
    python start.py
    python start.py --port 8000
    python start.py --sim          # also start IoT simulator
    python start.py --sim --chaos  # simulator with random spikes
"""

import sys
import os

# Force UTF-8 encoding for stdout and stderr to prevent UnicodeEncodeErrors on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
import subprocess
import time
import webbrowser
import threading
import argparse
import shutil

# ── Colours for terminal output ──
GRN = "\033[92m"
YEL = "\033[93m"
RED = "\033[91m"
CYN = "\033[96m"
BLD = "\033[1m"
RST = "\033[0m"

BANNER = f"""
{CYN}{BLD}
╔══════════════════════════════════════════════════════╗
║         SwachhNetra IoT — POC Demo Launcher          ║
║   GVMC Visakhapatnam · Smart Sanitation Monitor      ║
╚══════════════════════════════════════════════════════╝
{RST}"""


def check_python():
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 9):
        print(f"{RED}✗ Python 3.9+ required. Found {v.major}.{v.minor}{RST}")
        sys.exit(1)
    print(f"{GRN}✓ Python {v.major}.{v.minor}.{v.micro}{RST}")


def check_pip_package(pkg):
    try:
        __import__(pkg.split("[")[0].replace("-", "_"))
        return True
    except ImportError:
        return False


def install_dependencies():
    print(f"\n{YEL}► Checking dependencies...{RST}")
    req_file = os.path.join(os.path.dirname(__file__), "requirements.txt")
    if not os.path.exists(req_file):
        print(f"{RED}✗ requirements.txt not found. Run from cleancity_backend/ folder.{RST}")
        sys.exit(1)

    missing = []
    core_packages = ["fastapi", "uvicorn", "aiosqlite", "PyJWT", "pydantic", "firebase-admin"]
    for pkg in core_packages:
        if not check_pip_package(pkg):
            missing.append(pkg)

    if missing:
        print(f"{YEL}  Installing: {', '.join(missing)}...{RST}")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", req_file,
            "--quiet", "--break-system-packages"
        ])
        print(f"{GRN}  ✓ Dependencies installed{RST}")
    else:
        print(f"{GRN}  ✓ All dependencies present{RST}")


def find_frontend():
    """Look for swachhnetra.html in common locations."""
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "swachhnetra.html"),
        os.path.join(os.path.dirname(__file__), "swachhnetra.html"),
        os.path.expanduser("~/swachhnetra.html"),
        os.path.expanduser("~/Downloads/swachhnetra.html"),
        os.path.expanduser("~/Desktop/swachhnetra.html"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)
    return None


def start_backend(port, ready_event):
    """Start uvicorn backend server."""
    env = os.environ.copy()
    env["DATABASE_URL"] = "cleancity.db"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    backend_dir = os.path.dirname(os.path.abspath(__file__))
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "app.main:app",
            "--host", "0.0.0.0",
            "--port", str(port),
            "--reload",
        ],
        cwd=backend_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        errors="ignore",
    )

    for line in proc.stdout:
        line = line.rstrip()
        if "Application startup complete" in line or "Uvicorn running" in line:
            print(f"{GRN}  ✓ Backend ready on http://localhost:{port}{RST}")
            ready_event.set()
        elif "ERROR" in line or "Error" in line:
            print(f"{RED}  Backend: {line}{RST}")
        elif "INFO" in line and ("GET" in line or "POST" in line):
            # API calls - print briefly
            pass
        # else:
        #     print(f"  {line}")  # uncomment for verbose logging

    return proc


def start_simulator(chaos=False):
    """Start IoT sensor simulator."""
    sim_file = os.path.join(os.path.dirname(__file__), "iot_simulator.py")
    if not os.path.exists(sim_file):
        print(f"{YEL}  ⚠ iot_simulator.py not found — skipping simulator{RST}")
        return None

    args = [sys.executable, sim_file, "--interval", "5"]
    if chaos:
        args.append("--chaos")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    proc = subprocess.Popen(
        args,
        cwd=os.path.dirname(__file__),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        errors="ignore",
    )

    def stream():
        for line in proc.stdout:
            l = line.rstrip()
            if "SPIKE" in l:
                print(f"{RED}  [SIM] {l}{RST}")
            elif "✅" in l or "🟢" in l:
                print(f"{GRN}  [SIM] {l}{RST}")
            elif "🟡" in l:
                print(f"{YEL}  [SIM] {l}{RST}")

    t = threading.Thread(target=stream, daemon=True)
    t.start()
    return proc


def main():
    parser = argparse.ArgumentParser(description="SwachhNetra POC Launcher")
    parser.add_argument("--port", type=int, default=8000, help="Backend port (default: 8000)")
    parser.add_argument("--sim",   action="store_true", help="Start IoT simulator")
    parser.add_argument("--chaos", action="store_true", help="Simulator chaos mode (random spikes)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser automatically")
    args = parser.parse_args()

    print(BANNER)

    # 1. Python version
    check_python()

    # 2. Install deps
    install_dependencies()

    # 3. Start backend
    print(f"\n{YEL}► Starting backend on port {args.port}...{RST}")
    ready = threading.Event()
    backend_thread = threading.Thread(
        target=start_backend, args=(args.port, ready), daemon=True
    )
    backend_thread.start()

    # Wait up to 15 seconds for backend to be ready
    if not ready.wait(timeout=15):
        print(f"{YEL}  ⚠ Backend taking longer than expected. Continuing anyway...{RST}")
    else:
        time.sleep(0.5)  # give it a moment after ready signal

    # 4. Start IoT simulator if requested
    sim_proc = None
    if args.sim or args.chaos:
        print(f"\n{YEL}► Starting IoT simulator {'(CHAOS MODE)' if args.chaos else ''}...{RST}")
        time.sleep(2)  # let DB seed first
        sim_proc = start_simulator(chaos=args.chaos)
        if sim_proc:
            print(f"{GRN}  ✓ IoT simulator running{RST}")

    # 5. Find and open frontend
    frontend = find_frontend()
    print(f"\n{CYN}{BLD}══════════════════════════════════════{RST}")
    print(f"{GRN}{BLD}  SwachhNetra is RUNNING!{RST}")
    print(f"{CYN}══════════════════════════════════════{RST}")
    print(f"\n  Backend API  : {BLD}http://localhost:{args.port}{RST}")
    print(f"  Swagger docs : {BLD}http://localhost:{args.port}/api/docs{RST}")
    print(f"  Health check : {BLD}http://localhost:{args.port}/api/health{RST}")

    if frontend:
        frontend_url = f"http://localhost:{args.port}/dashboard"
        print(f"\n  Frontend     : {BLD}{frontend_url}{RST}")
        if not args.no_browser:
            time.sleep(1)
            print(f"\n{YEL}  Opening browser...{RST}")
            webbrowser.open(frontend_url)
    else:
        print(f"\n{YEL}  Frontend (swachhnetra.html) not found automatically.")
        print(f"  Open it manually in your browser.")
        print(f"  Or place it in the same folder as this script.{RST}")

    print(f"\n{YEL}  Login credentials:")
    print(f"    Admin  : admin   / admin123")
    print(f"    Worker : worker  / work123")
    print(f"    Citizen: citizen / citi123{RST}")

    if args.sim or args.chaos:
        print(f"\n{GRN}  IoT Simulator: RUNNING — sensor data flowing live{RST}")
        print(f"  Watch facility scores change on the dashboard!")

    print(f"\n{RED}  Press Ctrl+C to stop all services{RST}\n")

    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n{YEL}Shutting down...{RST}")
        if sim_proc:
            sim_proc.terminate()
        print(f"{GRN}Done. Goodbye!{RST}")


if __name__ == "__main__":
    main()
