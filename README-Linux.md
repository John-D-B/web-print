# web-print on Linux (Debian / Ubuntu / WSL)

Supplement to **Section 4: Alternate Script-Only Installation** in the main README.

The base Section 4 instructions assume a "just works" Bash environment.<br/>
On Debian-family systems (Debian, Ubuntu, Ubuntu-under-WSL),<br/>
&nbsp; &nbsp; two Debian-specific issues bite that the generic steps don't mention:

1. **PEP 668:**<br/>
Modern `pip` refuses to install into the system Python.

2. **Missing browser libraries:**<br/>
Playwright downloads Chromium, but not the system shared libraries it links against.

Each command unit below has its own ID (e.g. `L2.C`), so it can be referenced and checked off individually.

Where a section says *choose one*, do exactly one of the lettered variants.

**Install order:** `L1` → `L2` → `L3` → `L4`.

---

## Order of operations (at a glance)

The recommended path: apt for system libraries, a venv for Python.<br/>
Each block is labelled with the section that documents it in full; jump there if a step fails.

```bash
# L1.A — system libraries (root, once per machine)
$ sudo apt-get update && sudo apt-get install -y \
    libnss3 libnspr4 libatk1.0-0t64 libatk-bridge2.0-0t64 libcups2t64 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2t64

# (README 4B) — clone the repo
$ git clone https://github.com/John-D-B/web-print.git
$ cd web-print

# L2.A — python packages in a venv   (or L2.B for a system-wide /usr/local install)
$ python3 -m venv .venv && source .venv/bin/activate
$ pip install -r bin/requirements.txt

# L3 — browser binary
$ python3 -m playwright install chromium

# L4 — test
$ python3 bin/web-print.py --help
$ python3 bin/web-print.py ./tests/bad-print-testcase.html
$ python3 bin/web-print.py https://en.wikipedia.org/wiki/PDF
```

The sections below also document the `L2.B` / `L2.C` variants, the `L1.B` wrapper, and the `L1.C` fallback.

---

## L1. System libraries — root, once per machine

This is the step most people miss.

`playwright install chromium` (L3) fetches the browser binary into your user cache.<br/>
But a fresh Debian/Ubuntu/WSL install does **not** ship the libraries Chromium needs (`libnspr4`, `libnss3`, …).

Without them, the browser fails to launch:

```
error while loading shared libraries: libnspr4.so: cannot open shared object file
```

**Choose one of L1.A or L1.B.**<br/>
L1.C is troubleshooting only.

### L1.A — Install via apt (recommended)

```bash
$ sudo apt-get update
$ sudo apt-get install -y \
    libnss3 libnspr4 libatk1.0-0t64 libatk-bridge2.0-0t64 libcups2t64 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2t64
```

This is exactly the set `playwright install-deps` would install.<br/>
Running apt directly works regardless of how you installed the Python packages in L2.

The `t64` suffixes are Ubuntu's 64-bit `time_t` transition (24.04 onward);<br/>
&nbsp; &nbsp; `libasound2t64` in particular must be named explicitly, since bare `libasound2`<br/>
&nbsp; &nbsp; is now a virtual package with two providers and apt refuses to guess.

### L1.B — Install via `playwright install-deps` (alternative)

The "official" convenience wrapper.<br/>
It tracks library-name changes for you across Playwright versions.

But it only works when Playwright sits where `root`'s Python can see it —<br/>
&nbsp; &nbsp; i.e. the system-wide install (L2.B), **not** a venv (L2.A) or a `--user` install (L2.C).

```bash
$ sudo python3 -m playwright install-deps chromium
```

If it reports `No module named playwright`, you have a venv (L2.A) or `--user` (L2.C) install; use **L1.A** instead.

There is no clean way to hand a venv or per-user Playwright to a `root` process,<br/>
&nbsp; &nbsp; so on those two paths (L2.A venv, L2.C user-local), the apt install (L1.A) is the answer.

### L1.C — Troubleshooting: find a missing library

The L1.A list is hand-picked: the core set headless Chromium links against,<br/>
&nbsp; &nbsp; and it matches the launch failures seen on a fresh Ubuntu 24.04 / 26.04 install.

A future Chromium bump could add a dependency the list doesn't cover.<br/>
If the browser still won't launch (`cannot open shared object file`), ask the binary what it's missing:

```bash
$ ldd ~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell \
    | grep "not found"
```

Each `=> not found` line names a library.<br/>
Find the apt package that provides it (`apt-file search libfoo.so`), install it, and re-run.

---

## L2. Python packages — choose L2.A, L2.B, or L2.C

Modern Debian/Ubuntu mark the system Python as *externally managed* (PEP 668), so a plain `pip install` fails:

```
error: externally-managed-environment
```

Three ways past it — pick the one that suits you, do exactly one:

- **L2.A — venv:**<br/>
Self-contained, no root, no PATH questions.

- **L2.B — system-wide:**<br/>
Installs into `/usr/local`, already on everyone's PATH. The convenient standard install.

- **L2.C — user-local:**<br/>
No root, lands in `~/.local` — for a shared box where you can't install system-wide.

### L2.A — Virtual environment

A venv is its own environment, so PEP 668 doesn't apply:

```bash
$ python3 -m venv .venv
$ source .venv/bin/activate
$ pip install -r bin/requirements.txt
```

Re-activate with `source .venv/bin/activate` in any new shell before running L3 or the script itself.

### L2.B — System-wide, into `/usr/local`

Drop `--user` and let pip install for the whole machine:

```bash
$ sudo pip install --break-system-packages -r bin/requirements.txt
```

Libraries go to `/usr/local/lib/python3.14/dist-packages`, scripts to `/usr/local/bin` —<br/>
&nbsp; &nbsp; a tree apt never manages, which is where locally-installed software belongs.

To stop typing the flag, disable the PEP 668 guard once, system-wide:

```bash
$ sudo pip config set --global global.break-system-packages true
```

After that, a plain `sudo pip install ...` just works.

### L2.C — User-local, into `~/.local`

No root, per-user — for a shared box where you can't (or won't) install system-wide:

```bash
$ pip install --user --break-system-packages -r bin/requirements.txt
```

On stock Ubuntu, `~/.profile` already adds `~/.local/bin` to PATH once it exists;<br/>
&nbsp; &nbsp; a fresh login (or `source ~/.profile`) picks it up without any edit from you.

---

## L3. Browser binary — once, any path

Downloads Chromium into `~/.cache/ms-playwright/`, a cache owned by the user who runs it:

```bash
$ python3 -m playwright install chromium
```

Run this as the user who will run the script (venv activated, if you used L2.A),<br/>
&nbsp; &nbsp; so the browser lands in that user's cache and its version matches the installed Playwright.

---

## L4. Test the script

```bash
$ python3 bin/web-print.py --help
$ python3 bin/web-print.py ./tests/bad-print-testcase.html
$ python3 bin/web-print.py https://en.wikipedia.org/wiki/PDF
```

The script produces two editions of "fixed" PDFs and launches a viewer.

---

## Quick reference (troubleshooting)

| Symptom | Cause | Fix |
|---|---|---|
|*error: externally-managed-environment* | PEP 668 blocks system-Python installs | Pick one:<br/>L2.A (venv)<br/>L2.B (system-wide)<br/>L2.C (user-local) |
| *libnspr4.so: cannot open shared object file* | Chromium's system libraries not installed | L1.A (apt) |
| *No module named playwright* under *sudo* | root's Python can't see a venv<br/>`--user` install | Use L1.A, not L1.B |
| some other<br/> *cannot open shared object file* | L1.A list missing a newer dependency | L1.C (*ldd* diagnostic) |
| *script 'playwright' … not on PATH* | *~/.local/bin* not yet on PATH (L2.C only) | Re-login;<br/>*~/.profile adds it |
