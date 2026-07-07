#!/usr/bin/env python3
"""
web-print plugin bootstrap — installs the Python + Chromium dependencies the
skill needs, the SAME way the direct "ask Claude to install it" path (README
section 2) does: into the Python interpreter that runs the skill. This keeps the
plugin and direct-install paths behaving identically, with no changes to the
shared SKILL.md.

Idempotent: it does the work once, then skips until requirements.txt changes.
Called automatically by the SessionStart hook (hooks/hooks.json).

Cross-platform: this one Python file replaces OS-specific shell, so the hook line
stays simple. (See the note in README section 3 about the Windows `python` name.)
"""

__version__ = "1.0.0"

import os
import sys
import subprocess
import pathlib

root = pathlib.Path(os.environ["CLAUDE_PLUGIN_ROOT"])   # installed plugin dir
data = pathlib.Path(os.environ["CLAUDE_PLUGIN_DATA"])   # persists across updates

req = root / "skills" / "web-print" / "scripts" / "requirements.txt"
stamp = data / "requirements.stamp"                     # what we last installed

want = req.read_bytes() if req.exists() else b""

# Fast path: already installed for this exact requirements.txt.
if stamp.exists() and stamp.read_bytes() == want:
    sys.exit(0)


def pip_install(pkg_args):
    """Run `pip install`, retrying into an externally-managed environment
    (PEP 668) ONLY if the normal install is refused. This spares the user the
    raw "externally-managed-environment" error on newer Debian/Ubuntu, while
    leaving ordinary systems completely unaffected."""
    cmd = [sys.executable, "-m", "pip", "install", *pkg_args]
    if subprocess.run(cmd).returncode != 0:
        subprocess.run([*cmd, "--break-system-packages"], check=True)


# 1. Python dependencies, into the running interpreter (mirrors section 2).
pip_install(["-r", str(req)])
# 2. The Chromium browser Playwright drives.
subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)

data.mkdir(parents=True, exist_ok=True)
stamp.write_bytes(want)
print(f"web-print: dependencies installed for {sys.executable}")
