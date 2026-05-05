"""
Set up macOS launchd jobs for automatic video production.

Creates two jobs:
  com.wealthvault.produce  — 9am + 6pm daily: build & upload 3 videos each run
  com.wealthvault.retry    — 12:05am daily: retry any queued YouTube uploads

Usage:
  python setup_scheduler.py install    # write plists + load into launchd
  python setup_scheduler.py uninstall  # unload + remove plists
  python setup_scheduler.py status     # show job status
  python setup_scheduler.py run-now    # trigger produce job immediately
"""

from __future__ import annotations
import os
import subprocess
import sys

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_VENV_PYTHON = os.path.join(_PROJECT_DIR, "venv", "bin", "python")
_PYTHON = _VENV_PYTHON if os.path.exists(_VENV_PYTHON) else sys.executable
_LAUNCH_AGENTS = os.path.expanduser("~/Library/LaunchAgents")
_LOG_DIR = os.path.join(_PROJECT_DIR, "output", "logs")

_JOBS = {
    "com.wealthvault.produce": {
        "args": [_PYTHON, "main.py", "--batch", "3", "--youtube", "--no-tiktok"],
        "schedule": [{"Hour": 9, "Minute": 0}, {"Hour": 18, "Minute": 0}],
        "log": "produce",
    },
    "com.wealthvault.retry": {
        "args": [_PYTHON, "main.py", "--retry-youtube"],
        "schedule": [{"Hour": 0, "Minute": 5}],
        "log": "retry",
    },
    "com.wealthvault.comment": {
        "args": [_PYTHON, "main.py", "--comment", "8"],
        "schedule": [{"Hour": 12, "Minute": 0}, {"Hour": 20, "Minute": 0}],
        "log": "comment",
    },
}


def _plist_path(label: str) -> str:
    return os.path.join(_LAUNCH_AGENTS, f"{label}.plist")


def _build_plist(label: str, job: dict) -> str:
    args_xml = "\n".join(f"        <string>{a}</string>" for a in job["args"])
    schedule_xml = "\n".join(
        "        <dict>\n" +
        "\n".join(f"            <key>{k}</key><integer>{v}</integer>" for k, v in s.items()) +
        "\n        </dict>"
        for s in job["schedule"]
    )
    log_out = os.path.join(_LOG_DIR, f"{job['log']}_stdout.log")
    log_err = os.path.join(_LOG_DIR, f"{job['log']}_stderr.log")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>

    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>

    <key>WorkingDirectory</key>
    <string>{_PROJECT_DIR}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>

    <key>StartCalendarInterval</key>
    <array>
{schedule_xml}
    </array>

    <key>StandardOutPath</key>
    <string>{log_out}</string>

    <key>StandardErrorPath</key>
    <string>{log_err}</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""


def install() -> None:
    os.makedirs(_LAUNCH_AGENTS, exist_ok=True)
    os.makedirs(_LOG_DIR, exist_ok=True)

    for label, job in _JOBS.items():
        path = _plist_path(label)
        with open(path, "w") as f:
            f.write(_build_plist(label, job))
        print(f"  Wrote: {path}")
        subprocess.run(["launchctl", "unload", path], capture_output=True)
        result = subprocess.run(["launchctl", "load", path], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  Loaded: {label}")
        else:
            print(f"  Load warning: {result.stderr.strip()}")

    print("\nActive schedule:")
    print("   9:00 AM — produce 3 videos + upload to YouTube")
    print("  12:00 PM — comment on 8 TikTok videos")
    print("   6:00 PM — produce 3 videos + upload to YouTube")
    print("   8:00 PM — comment on 8 TikTok videos")
    print("  12:05 AM — retry any queued YouTube uploads")
    print(f"\nLogs → {_LOG_DIR}")
    print(f"Python → {_PYTHON}")


def uninstall() -> None:
    for label in _JOBS:
        path = _plist_path(label)
        if os.path.exists(path):
            subprocess.run(["launchctl", "unload", path], capture_output=True)
            os.unlink(path)
            print(f"  Removed: {path}")
        else:
            print(f"  Not installed: {label}")


def status() -> None:
    for label in _JOBS:
        result = subprocess.run(["launchctl", "list", label], capture_output=True, text=True)
        path = _plist_path(label)
        if result.returncode == 0:
            print(f"  ACTIVE    {label}")
            for line in result.stdout.strip().splitlines():
                if "LastExitStatus" in line or "PID" in line:
                    print(f"            {line.strip()}")
        elif os.path.exists(path):
            print(f"  INSTALLED {label}  (not loaded)")
        else:
            print(f"  MISSING   {label}")


def run_now() -> None:
    label = "com.wealthvault.produce"
    subprocess.run(["launchctl", "start", label])
    print(f"Triggered {label}. Logs → {_LOG_DIR}/produce_stdout.log")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    actions = {"install": install, "uninstall": uninstall, "status": status, "run-now": run_now}
    if cmd in actions:
        actions[cmd]()
    else:
        print(__doc__)
