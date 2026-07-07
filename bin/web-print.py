#!/usr/bin/env python3
# SPDX-License-Identifier: BUSL-1.1 OR LicenseRef-MountainInformatik-Commercial
# SPDX-FileCopyrightText: 2026 Mountain Informatik GmbH — original software by John Buehrer
"""
web-print.py — turn a saved web page into a clean, paginated, printable PDF.

Usage:
    python3 web-print.py <source> [tempdir] [--just SPEC] [-o SPEC] [--width N]
                         [--suffix NAME] [--chromium] [--install] [--no-open]

Every run renders both image modes into a dated output folder and opens two of
them side by side:
  - audit/    images stripped, recoloured to ink-friendly black-on-white
  - wysiwyg/  images + brand colours kept, "what you see" (minus repeating junk)
Each holds four PDFs: {portrait,landscape}-{reflow,page}.  reflow stacks
multi-column layouts; page (scale-to-fit) keeps the on-screen columns, shrunk.
Working HTML lands in html/.  Default opens the original page, then both
portrait-page PDFs (a live before/after).

Arguments:
    source        A saved web page (.html), or an http(s):// URL.
    tempdir       Base output folder; a dated subfolder is created under it.
                  Defaults to a predictable per-OS scratch dir.
    --just SPEC   Render/open just a subset, by facet keyword(s): audit|wysiwyg,
                  portrait|landscape, reflow|page (comma/space separated; unnamed
                  facets mean 'all').  Reserved — not yet active.
    --width N     Render width in px for the 'page' scale-to-fit layout (dflt 1100).
    -o/--overlay SPEC
                  Also print the given overlay(s) as an appendix: numbers from
                  the detected list, CSS selectors, or 'all' (on-demand popups).
                  Repeatable and/or comma-separated.

Behaviour:
    1. Reads the source HTML (file or URL) and cleans/patches it.
    2. Creates a dated output folder; if today's exists, rotates it (+, ++ ...)
       so the bare date is always the latest run.
    3. Renders 8 PDFs with headless Chrome — audit/ and wysiwyg/, each with
       {portrait,landscape}-{reflow,page}; working HTML goes in html/.
    4. Prints the settings and the produced files; opens the original page,
       then both portrait-page PDFs (audit + wysiwyg), unless --no-open.

Two front doors:
  - local saved page  — pass a .html file (its _files/ assets resolve in place)
  - live fetch        — pass an http(s):// URL; the page is fetched and its
                        assets load from the live origin via <base href>.

Overlays & pop-ups:
  Fixed overlays and pop-ups (which otherwise repeat on every printed page and
  bury the content) are detected and stripped. Each run prints a table of what
  it found — index, selector, type, and name. Pass -o to also print chosen ones
  as an appendix at the end: the content itself for a pop-up or dialog, and for
  a nav bar its extracted links (the bar's visual form can't be reproduced, but
  its links can). Reference an overlay by its index, its selector, or 'all'.
"""

__version__ = "4.0.0"

import argparse
import functools
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import urllib.request
import webbrowser
from datetime import date
from html import escape as html_escape
from pathlib import Path
from urllib.parse import quote, urlparse

# Each run renders MODES x LAYOUTS: the two image modes, each in the four
# orientation/layout combos below. LAYOUTS: (orientation, scale?) where
# scale=True is the "page" (scale-to-fit) layout, False is "reflow".
MODES = ["audit", "wysiwyg"]
LAYOUTS = [("portrait", False), ("landscape", False),
           ("portrait", True), ("landscape", True)]


def variant_label(orientation: str, scale: bool) -> str:
    return orientation + ("-page" if scale else "-reflow")


def dated_output_dir(base: Path, suffix: str = "") -> Path:
    """Create today's dated output folder, e.g. <base>/2026-06-29[.suffix].

    If it already exists, rotate the existing ones down a '+' first
    (2026-06-29 -> 2026-06-29+, + -> ++, ...) so the bare date is always newest.
    Cascades deepest-first to avoid name collisions during the renames."""
    base.mkdir(parents=True, exist_ok=True)
    day = date.today().isoformat()
    if suffix:
        clean = "".join(c if c.isalnum() or c in "-._" else "-" for c in suffix)
        day = f"{day}.{clean}"
    bare = base / day
    if bare.exists():
        pat = re.compile(re.escape(day) + r"(\+*)$")
        counts = sorted(
            (len(m.group(1)) for p in base.iterdir() if p.is_dir()
             for m in [pat.fullmatch(p.name)] if m),
            reverse=True,
        )
        for c in counts:  # deepest '+' chain first
            (base / (day + "+" * c)).rename(base / (day + "+" * (c + 1)))
    bare.mkdir()
    return bare


def window_size(orientation: str, scale: bool, width: int) -> str:
    if scale:
        return f"{max(1400, width + 200)},1600"
    return "1400,1000" if orientation == "landscape" else "1200,1600"


def serve_dir(directory: Path):
    """Serve a directory over http://127.0.0.1:<port>/ in a background thread.

    The browser fetches the page over HTTP instead of via a file:// path. This
    is the key portability move: sandboxed browsers (notably snap Chromium) are
    walled off from the filesystem — they cannot read file:///tmp/... — but they
    can always reach localhost. Returns (server, port); call .shutdown() when done."""
    handler = functools.partial(_QuietHandler, directory=str(directory))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # silence per-request logging
        pass


def is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def slug_from_url(url: str) -> str:
    """Filename stem from a URL, e.g. https://www.example.com/vacation/ -> example.com-vacation"""
    p = urlparse(url)
    host = p.netloc.replace("www.", "")
    path = p.path.strip("/").replace("/", "-")
    stem = f"{host}-{path}" if path else host
    return "".join(c if c.isalnum() or c in "-._" else "-" for c in stem) or "page"


def fetch_url(url: str) -> str:
    """GET the raw server HTML (browser-like UA so we get the real page, not a bot wall)."""
    # Defense-in-depth: only ever open http(s). Callers already gate via is_url(),
    # but assert it here too so this stays safe if a future caller forgets.
    if urlparse(url).scheme not in ("http", "https"):
        sys.exit(f"error: refusing non-http(s) URL: {url}\n")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # nosec B310  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001 — surface a clean message, not a traceback
        sys.exit(f"error: could not fetch {url}: {e}\n")


class NLParser(argparse.ArgumentParser):
    """ArgumentParser that shows the version on top and ends help with a blank line."""
    def format_help(self):
        return f"{self.prog} {__version__}\n" + super().format_help() + "\n"

    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: error: {message}\n\n")
        sys.exit(2)


class NLHelpFormatter(argparse.HelpFormatter):
    """Cap width so the usage line wraps; honour explicit newlines (and their indent)."""
    def __init__(self, prog):
        super().__init__(prog, max_help_position=22,
                         width=min(shutil.get_terminal_size().columns, 84))

    def _split_lines(self, text, width):
        lines = []
        for part in text.splitlines():
            body = part.lstrip(" ")
            indent = " " * (len(part) - len(body))
            wrapped = textwrap.wrap(body, max(1, width - len(indent))) or [""]
            lines.extend(indent + w for w in wrapped)
        return lines


# --------------------------------------------------------------------------- #
# Temp-dir convention: predictable /tmp/claude/web-print on POSIX; the OS
# temp dir elsewhere (Windows has no /tmp; %TEMP%\claude\web-print instead).
# Override by passing an explicit tempdir as the 3rd argument.
# --------------------------------------------------------------------------- #
def default_tempdir() -> str:
    if os.name == "posix" and os.path.isdir("/tmp"):
        prefix = "/tmp/claude"
    else:  # Windows / anything without /tmp
        prefix = os.path.join(tempfile.gettempdir(), "claude")
    return os.path.join(prefix, "web-print")


def find_chrome() -> str:
    """Locate a Chromium-family binary; honour $CHROME override first."""
    env = os.environ.get("CHROME")
    if env and os.path.exists(env):
        return env
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for name in ("google-chrome", "google-chrome-stable", "chrome", "chromium",
                 "chromium-browser", "brave-browser", "microsoft-edge"):
        found = shutil.which(name)
        if found:
            candidates.insert(0, found)
    for c in candidates:
        if os.path.exists(c):
            return c
    sys.exit("error: no Chrome/Chromium found.\n"
             "  Set $CHROME to the binary, or install one (Linux/WSL: "
             "`apt install chromium` or `chromium-browser`).\n")


# --------------------------------------------------------------------------- #
# The patch. Identical defang/reveal/light-mode core for both orientations;
# only the @page rule and column handling differ.
# --------------------------------------------------------------------------- #
def build_patch(orientation: str, scale: bool = False, mode: str = "audit",
                width: int = 1100, keep=None) -> str:
    landscape = orientation == "landscape"
    audit = mode != "wysiwyg"       # audit strips imagery + recolours; wysiwyg keeps them
    page_size = "A4 landscape" if landscape else "A4"
    # The 'page' (scale-to-fit) layout uses tight uniform margins for max room.
    margin = "10mm" if scale else ("12mm" if landscape else "16mm 14mm")
    page_rule = f"@page {{ size: {page_size}; margin: {margin}; }}"

    # Keep page-builder rows as side-by-side flex columns whenever the target is
    # wide enough to hold them: landscape paper, or any 'page' render. In plain
    # portrait, let multi-column layouts stack naturally.
    column_rule = """
  .et_pb_row, .et_pb_row_inner {
    display: flex !important; flex-direction: row !important;
    flex-wrap: nowrap !important; align-items: flex-start !important;
    width: 100% !important; max-width: 100% !important;
  }
  .et_pb_column { float: none !important; flex: 1 1 0 !important;
                  width: auto !important; margin: 0 1.5% !important; }
  .et_pb_row { break-inside: avoid; page-break-inside: avoid; }""" if (scale or landscape) else ""

    # 'page' layout: lay the page out at a fixed "screen" width so the on-screen
    # layout survives, then CSS-zoom it down to fit the paper. (zoom shrinks the
    # layout box — unlike transform:scale — so pagination stays correct.)
    if scale:
        printable_mm = (297 if landscape else 210) - 20  # A4 dim minus 2 x 10mm
        zoom = min(1.0, printable_mm * 96 / 25.4 / width)
        scale_rule = (f"\n  html {{ zoom: {zoom:.3f}; }}"
                      f"\n  body {{ width: {width}px !important; }}")
    else:
        scale_rule = ""

    # audit mode only: strip imagery + recolour to ink-friendly black-on-white.
    ink_rule = ("""
  *, *::before, *::after { background-image: none !important;
    box-shadow: none !important; text-shadow: none !important; }
  html, body { background: #fff !important; }""" if audit else "")

    # --overlay selection + mode, handed to the in-page patch as a tiny JS config.
    keep_all, keep_nums, keep_sels = keep or (False, [], [])
    keep_all_js = "true" if keep_all else "false"
    keep_nums_js = json.dumps(keep_nums)
    keep_sels_js = json.dumps(keep_sels)
    audit_js = "true" if audit else "false"

    return rf"""
<!-- ===== Claude web-print patch ({orientation}) ===== -->
<style id="claude-web-print">
/* (A) defang the broken bits (generic; the JS classifier below catches the rest) */
[aria-modal="true"], [role="dialog"],
iframe, ins.adsbygoogle {{ display: none !important; }}
html, body {{ overflow: visible !important; height: auto !important;
              position: static !important; }}

/* (B) reveal content suppressed by scroll/motion-effect animations */
[class*="et_pb_"], .fadeIn, .et_animated, [data-animation],
[class*="wow"], [class*="aos"], [data-aos] {{
  opacity: 1 !important; visibility: visible !important;
  transform: none !important; filter: none !important;
  animation: none !important; transition: none !important;
}}

@media print {{
  {page_rule}{scale_rule}
  header, nav, #main-header, #top-header, #et-top-navigation, .et_menu_container,
  .et-fixed-header, .et_pb_section--fixed,
  [class*="cookie"], [class*="consent"], [class*="social"], [class*="-share"] {{
    display: none !important;
  }}
  img, figure, table, pre, blockquote, li {{ break-inside: avoid; }}
  h1, h2, h3, h4 {{ break-after: avoid; }}
  a {{ text-decoration: none; }}{ink_rule}{column_rule}
}}
/* --overlay appendix: kept overlays rendered in flow at the end */
#wp-appendix {{ break-before: page; margin: 8px 2px 0; }}
#wp-appendix .wp-appendix-h {{ font: 700 18px/1.3 sans-serif; margin: 0 0 4px;
  padding-bottom: 6px; border-bottom: 2px solid #333; }}
#wp-appendix .wp-item {{ break-inside: avoid; padding-top: 12px; margin-top: 16px;
  border-top: 1px solid #bbb; }}
#wp-appendix .wp-item:first-of-type {{ border-top: 0; }}
#wp-appendix .wp-item-h {{ font: 600 13px/1.4 sans-serif; margin: 0 0 8px; }}
#wp-appendix .wp-item-sel {{ font: 400 11px/1 ui-monospace, monospace; color: #666; }}
#wp-appendix .wp-note {{ font: italic 400 12px/1.4 sans-serif; color: #999; margin-top: 2px; }}
#wp-appendix .wp-links {{ margin: 4px 0 0; padding-left: 18px; font: 400 13px/1.7 sans-serif; }}
#wp-appendix .wp-links .wp-links-url {{ color: #888; font: 400 11px/1 ui-monospace, monospace; }}
</style>
<script id="claude-web-print-js">
(function () {{
  // --overlay selection (numbers from the detected list / selectors / all):
  var KEEPALL = {keep_all_js}, KEEPNUMS = {keep_nums_js}, KEEPSELS = {keep_sels_js};
  var AUDIT = {audit_js};   // audit: strip imagery + recolour. wysiwyg: keep them.
  // --- overlay classifier (read-only; feeds the run's "overlays detected"
  //     summary). Deterministic decision tree over ARIA + geometry + backdrop. ---
  function _rgba(s) {{
    var m = /rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/.exec(s || '');
    return m ? {{ r:+m[1], g:+m[2], b:+m[3], a: m[4] === undefined ? 1 : +m[4] }} : null;
  }}
  function _cssEsc(s) {{ return (window.CSS && CSS.escape) ? CSS.escape(s) : String(s); }}
  function _uniq(sel) {{
    try {{ return document.querySelectorAll(sel).length === 1; }} catch (e) {{ return false; }}
  }}
  function _sel(el) {{                            // shortest selector that matches only el
    if (el.id) {{ var s = '#' + _cssEsc(el.id); if (_uniq(s)) return s; }}
    var c = el.className;
    c = (c && c.baseVal !== undefined) ? c.baseVal : c;        // SVG className is an object
    var list = (c || '').toString().trim().split(/\s+/).filter(Boolean).map(_cssEsc);
    if (list.length) {{
      var s2 = el.tagName.toLowerCase() + '.' + list.join('.');
      if (_uniq(s2)) return s2;
    }}
    // structural fallback: nth-of-type path up to the nearest unique id (or body)
    var parts = [], node = el;
    while (node && node.nodeType === 1 && node !== document.body) {{
      if (node.id && _uniq('#' + _cssEsc(node.id))) {{ parts.unshift('#' + _cssEsc(node.id)); break; }}
      var i = 1, sib = node;
      while ((sib = sib.previousElementSibling)) if (sib.tagName === node.tagName) i++;
      parts.unshift(node.tagName.toLowerCase() + ':nth-of-type(' + i + ')');
      node = node.parentElement;
    }}
    return parts.join(' > ');
  }}
  function _label(el) {{
    var a = el.getAttribute('aria-label'); if (a) return a.trim();
    var h = el.querySelector('h1,h2,h3,h4,h5,h6');
    if (h && h.textContent.trim()) return h.textContent.trim().replace(/\s+/g, ' ').slice(0, 40);
    return el.id || _sel(el);
  }}
  function _classify(el, cs, pos, isDialog) {{
    var r = el.getBoundingClientRect(), vw = innerWidth, vh = innerHeight;
    // full-viewport, robust to display:none (rect 0x0) via size/inset keywords
    var full = /^(100%|100vw)$/.test(cs.width) &&
               (/^(100%|100vh)$/.test(cs.height) || /^(100%|100vh)$/.test(cs.minHeight));
    var inset = cs.top === '0px' && cs.left === '0px' && cs.right === '0px' && cs.bottom === '0px';
    var coversW = full || inset || r.width  > vw * 0.6;
    var coversH = full || inset || r.height > vh * 0.6;
    var bg = _rgba(cs.backgroundColor);
    var lum = bg ? (0.299 * bg.r + 0.587 * bg.g + 0.114 * bg.b) : 255;
    var backdrop = !!bg && bg.a > 0.15 && bg.a < 0.98 && lum < 90;   // dim scrim
    var narrow = r.width > 0 && r.width < vw * 0.33;
    var tall = r.height > 150;   // absolute px — render viewport height is arbitrary
    var side = (cs.left === '0px' || cs.right === '0px') && (cs.top !== 'auto' || cs.bottom !== 'auto');
    var t;
    if (isDialog)                                              t = 'modal dialog';
    else if (pos === 'fixed' && coversW && coversH && backdrop) t = 'modal popup';
    else if (pos === 'fixed' && coversW && coversH)            t = 'full overlay';
    else if (pos === 'fixed' && coversW)                       t = 'bar / banner';
    else if (pos === 'fixed' && narrow && tall && side)        t = 'side rail';
    else if (pos === 'sticky')                                 t = 'sticky bar';
    else                                                       t = 'floating panel';
    return {{ sel: _sel(el), label: _label(el), type: t,
             z: parseInt(cs.zIndex, 10) || 0 }};
  }}
  function _nestedOverlay(el) {{                  // inside another fixed/sticky/dialog?
    for (var p = el.parentElement; p && p !== document.body; p = p.parentElement) {{
      var pp = getComputedStyle(p).position, pr = p.getAttribute('role');
      if (pp === 'fixed' || pp === 'sticky' ||
          p.getAttribute('aria-modal') === 'true' || pr === 'dialog' || pr === 'alertdialog')
        return true;
    }}
    return false;
  }}
  function _matchSel(el, sels) {{
    for (var k = 0; k < sels.length; k++) {{ try {{ if (el.matches(sels[k])) return true; }} catch (e) {{}} }}
    return false;
  }}
  function _itemHead(info) {{                      // appendix item shell + heading
    var item = document.createElement('div'); item.className = 'wp-item';
    var h = document.createElement('div'); h.className = 'wp-item-h';
    h.appendChild(document.createTextNode(info.n + ' · ' + info.label + '  '));
    var cap = document.createElement('span'); cap.className = 'wp-item-sel';
    cap.textContent = info.sel; h.appendChild(cap);
    item.appendChild(h);
    return item;
  }}
  function _capture(appendix, el, info) {{        // move a kept overlay into the appendix
    var item = _itemHead(info);
    el.style.setProperty('display', 'block', 'important');   // reveal on-demand ones
    ['width', 'height', 'min-height', 'max-height'].forEach(function (p) {{
      el.style.setProperty(p, p === 'min-height' ? '0' : (p === 'max-height' ? 'none' : 'auto'), 'important');
    }});
    item.appendChild(el);                        // relocates el out of body flow
    appendix.appendChild(item);
  }}
  function _forceLazy() {{                         // wysiwyg: coax lazy images to load
    var imgs = document.getElementsByTagName('img');
    for (var i = 0; i < imgs.length; i++) {{
      var im = imgs[i];
      if (im.loading === 'lazy') im.loading = 'eager';
      var ds = im.getAttribute('data-src');
      if (ds && !im.getAttribute('src')) im.setAttribute('src', ds);
      var dss = im.getAttribute('data-srcset');
      if (dss && !im.getAttribute('srcset')) im.setAttribute('srcset', dss);
    }}
  }}
  function _captureBar(appendix, el, info) {{     // a nav bar: extract its real links
    var item = _itemHead(info), seen = {{}};
    var ul = document.createElement('ul'); ul.className = 'wp-links';
    var as = el.getElementsByTagName('a');
    for (var i = 0; i < as.length; i++) {{
      var t = (as[i].textContent || '').replace(/\s+/g, ' ').trim();
      if (!t || seen[t]) continue;               // skip icon-only anchors + duplicates
      seen[t] = 1;
      var li = document.createElement('li'); li.textContent = t;
      var href = as[i].getAttribute('href') || '';
      if (href && href.charAt(0) !== '#') {{
        var sp = document.createElement('span'); sp.className = 'wp-links-url';
        sp.textContent = '  ' + href; li.appendChild(sp);
      }}
      ul.appendChild(li);
    }}
    if (ul.children.length) item.appendChild(ul);
    else {{
      var note = document.createElement('div'); note.className = 'wp-note';
      note.textContent = 'no text content (icon-only bar)';
      item.appendChild(note);
    }}
    appendix.appendChild(item);
  }}
  function normalize() {{
    [document.documentElement, document.body].forEach(function (el) {{
      if (!el) return;
      el.style.setProperty('overflow', 'visible', 'important');
      el.style.setProperty('height', 'auto', 'important');
      el.style.setProperty('position', 'static', 'important');
    }});
    var mods = document.querySelectorAll('[class*="et_pb_"]');
    for (var i = 0; i < mods.length; i++) {{
      var s = mods[i].style;
      ['opacity','visibility','transform','filter','animation','transition']
        .forEach(function (p) {{ s.removeProperty(p); }});
    }}
    if (!AUDIT) _forceLazy();
    if (AUDIT && document.body) document.body.style.setProperty('background', '#fff', 'important');
    // Classify overlays only on the FIRST run, from pristine (screen) state —
    // later runs re-read a DOM this function has already recoloured and hidden.
    var collect = !window.__wp_collected, OV = [], n = 0;
    var wantKeep = KEEPALL || KEEPNUMS.length || KEEPSELS.length;
    var appendix = (collect && wantKeep) ? document.createElement('section') : null;
    if (appendix) appendix.id = 'wp-appendix';
    // Snapshot the node list — capturing a kept overlay MOVES nodes, which would
    // disturb a live HTMLCollection mid-iteration.
    var nodes = document.body
      ? Array.prototype.slice.call(document.body.getElementsByTagName('*')) : [];
    for (var j = 0; j < nodes.length; j++) {{
      var el = nodes[j];
      var inApp = el.closest && el.closest('#wp-appendix');   // already-kept content
      var cs = getComputedStyle(el), pos = cs.position;
      var role = el.getAttribute('role') || '';
      var isDialog = el.getAttribute('aria-modal') === 'true' ||
                     role === 'dialog' || role === 'alertdialog';
      var kept = false;
      // Record overlays here — BEFORE the recolour below zeroes backgroundColor,
      // which the backdrop test needs. Skip a plain container that merely wraps a
      // dialog, so the modal is listed once (as the dialog, not its scrim).
      if (collect && !inApp && (pos === 'fixed' || pos === 'sticky' || isDialog)) {{
        var skip = isDialog ? false
                 : ((el.querySelector && el.querySelector("[role='dialog'],[aria-modal='true']"))
                    || _nestedOverlay(el));
        if (!skip) {{
          var info = _classify(el, cs, pos, isDialog);
          info.n = ++n;
          info.kept = KEEPALL ? true                            // 'all' = every detected overlay
                    : (KEEPNUMS.indexOf(n) >= 0 || _matchSel(el, KEEPSELS));
          OV.push(info);
          if (info.kept && appendix) {{
            if (info.type === 'bar / banner') {{ _captureBar(appendix, el, info); }}  // links only
            else {{ _capture(appendix, el, info); kept = true; }}
          }}
        }}
      }}
      if (AUDIT) {{
        el.style.setProperty('background-color', 'transparent', 'important');
        el.style.setProperty('background-image', 'none', 'important');
        el.style.setProperty('color', '#1a1a1a', 'important');
      }}
      if (pos === 'fixed' || pos === 'sticky') {{
        if (inApp || kept) {{
          // kept content: pull into normal flow, but never hide or repeat it
          el.style.setProperty('position', 'static', 'important');
          el.style.setProperty('transform', 'none', 'important');
          ['top','left','right','bottom'].forEach(function (p) {{
            el.style.setProperty(p, 'auto', 'important');
          }});
        }} else {{
          var r = el.getBoundingClientRect();
          var coversMost = r.width > innerWidth * 0.6 && r.height > innerHeight * 0.6;
          // Also catch full-viewport overlays that are display:none in *screen*
          // media (so their rect is 0x0 here) but reappear in print — detect via
          // the computed size keywords, which survive display:none.
          var full = /^(100%|100vw)$/.test(cs.width) &&
                     (/^(100%|100vh)$/.test(cs.height) || /^(100%|100vh)$/.test(cs.minHeight));
          var z = parseInt(cs.zIndex, 10) || 0;
          if (coversMost || full || z > 900) {{
            el.style.setProperty('display', 'none', 'important');
          }} else {{
            // Demote to flow — cancel any centring transform / insets, or a
            // width:100% block with translate(-50%) is thrown off the page edge.
            el.style.setProperty('position', 'static', 'important');
            el.style.setProperty('transform', 'none', 'important');
            ['top','left','right','bottom'].forEach(function (p) {{
              el.style.setProperty(p, 'auto', 'important');
            }});
          }}
        }}
      }}
    }}
    if (appendix && appendix.querySelector('.wp-item')) {{
      var title = document.createElement('div'); title.className = 'wp-appendix-h';
      title.textContent = 'Captured overlays';
      appendix.insertBefore(title, appendix.firstChild);
      document.body.appendChild(appendix);
    }}
    if (collect) {{ window.__wp_overlays = OV; window.__wp_collected = true; }}
  }}
  if (document.readyState === 'complete') normalize();
  window.addEventListener('load', normalize);
  window.addEventListener('beforeprint', normalize);
}})();
</script>
<!-- ===== end Claude web-print patch ===== -->
"""


def inject_base(html: str, base_href: str) -> str:
    """Insert <base href> right after <head> so the page's relative _files/
    asset links resolve from the original folder even when the patched copy
    lives in the temp dir (sidesteps the broken-_files problem)."""
    tag = f'<base href="{html_escape(base_href)}">'
    low = html.lower()
    h = low.find("<head")
    if h == -1:
        return tag + html
    gt = low.find(">", h)
    return html[: gt + 1] + tag + html[gt + 1 :]


def ensure_playwright() -> None:
    """The default engine needs the Playwright package; fail loud if it's absent."""
    import importlib.util
    if importlib.util.find_spec("playwright") is None:
        sys.exit(
            "error: the default engine needs Playwright, which isn't installed.\n"
            "  install:  $ pip install -r requirements.txt\n"
            "            $ playwright install chromium\n"
            "  or:       re-run with --install\n"
            "  or:       use --chromium to drive a browser already on your machine\n")


def install_playwright() -> None:
    """--install: fetch the Playwright package and its Chromium, then continue."""
    print("  installing Playwright + Chromium ...")
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)


def _scroll_to_load(page):
    """wysiwyg: scroll through the page so IntersectionObserver lazy-loaders fire,
    then wait for the network to settle so images are present before printing."""
    try:
        page.evaluate("""() => new Promise(res => {
            let y = 0;
            const step = () => {
                window.scrollTo(0, y); y += Math.max(200, window.innerHeight);
                if (y < document.body.scrollHeight) setTimeout(step, 50);
                else { window.scrollTo(0, 0); setTimeout(res, 200); }
            };
            step();
        })""")
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass


def render_playwright(raw_html, items, width, src, source, chosen_labels, keep=None):
    """Default engine. Drives Playwright's own Chromium; page.pdf() returns the
    bytes over the protocol, so the script writes every file — no localhost, no
    /dev/stdout, no sandbox or quarantine concerns. Assets resolve via <base
    href>: the live origin for a URL, the original folder (file://) for a file."""
    from playwright.sync_api import sync_playwright
    base_href = source if src is None else (src.parent.as_uri() + "/")
    html = inject_base(raw_html, base_href)
    idx = html.lower().rfind("</body>")
    if idx == -1:
        sys.exit("error: no </body> in source\n")
    chosen_pdfs = []
    overlays = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            sys.exit("error: Playwright's Chromium isn't installed.\n"
                     "  run:  playwright install chromium   (or re-run with --install)\n")
        for mode, orientation, scale, label, patched, pdf in items:
            patched.write_text(html[:idx] + build_patch(orientation, scale, mode, width, keep) + html[idx:],
                               encoding="utf-8", errors="surrogatepass")
            vw = max(1400, width + 200) if scale else 1280
            page = browser.new_page(viewport={"width": vw, "height": 1600})
            try:
                page.goto(patched.as_uri(), wait_until="networkidle", timeout=15000)
            except Exception:
                pass  # assets may still be loading; render best-effort
            if mode == "wysiwyg":
                _scroll_to_load(page)     # coax lazy images into loading before print
            pdf.write_bytes(page.pdf(prefer_css_page_size=True, print_background=True))
            if not overlays:  # the patch's classifier stashes what it found
                try:
                    overlays = page.evaluate("() => window.__wp_overlays || []") or []
                except Exception:
                    overlays = []
            page.close()
            print(f"    {'*' if label in chosen_labels else ' '} {label}")
            if label in chosen_labels:
                chosen_pdfs.append(pdf)
        browser.close()
    return chosen_pdfs, overlays


def render_chromium(raw_html, items, width, src, source, chosen_labels, keep=None):
    """Opt-out engine (--chromium). Drives a Chromium-family browser already on
    the machine, with no Python dependency. Serves the page over localhost and
    captures /dev/stdout so it works even under a sandbox (snap) — see serve_dir."""
    chrome = find_chrome()
    linux_flags = (["--no-sandbox", "--disable-dev-shm-usage"]
                   if sys.platform.startswith("linux") else [])
    capture = os.name == "posix"
    outdir = items[0][4].parent          # the html/ working dir (patched pages live here)
    httpd, port = serve_dir(outdir)
    try:
        if src is None:
            base_href = source                       # URL: assets load from the origin
        else:
            assets = src.parent / f"{src.stem}_files"
            if assets.is_dir():
                link = outdir / assets.name
                if not link.exists():
                    try:
                        link.symlink_to(assets)
                    except OSError:
                        shutil.copytree(assets, link)
            base_href = f"http://127.0.0.1:{port}/"
        html = inject_base(raw_html, base_href)
        idx = html.lower().rfind("</body>")
        if idx == -1:
            sys.exit("error: no </body> in source\n")
        chosen_pdfs = []
        for mode, orientation, scale, label, patched, pdf in items:
            patched.write_text(html[:idx] + build_patch(orientation, scale, mode, width, keep) + html[idx:],
                               encoding="utf-8", errors="surrogatepass")
            cmd = [chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                   *linux_flags, f"--window-size={window_size(orientation, scale, width)}",
                   "--virtual-time-budget=9000",
                   f"--print-to-pdf={'/dev/stdout' if capture else pdf}",
                   f"http://127.0.0.1:{port}/{quote(patched.name)}"]
            result = subprocess.run(
                cmd, stdout=(subprocess.PIPE if capture else subprocess.DEVNULL),
                stderr=subprocess.PIPE)
            if capture and result.returncode == 0:
                start = result.stdout.find(b"%PDF-")  # ignore any leading noise on stdout
                if start >= 0:
                    pdf.write_bytes(result.stdout[start:])
            if result.returncode != 0 or not pdf.exists() or pdf.stat().st_size == 0:
                tail = "\n    ".join(
                    result.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]) or "(no output)"
                sys.exit(f"error: Chrome failed to render {pdf.name} (exit {result.returncode}).\n"
                         f"    chrome: {chrome}\n    {tail}\n")
            print(f"    {'*' if label in chosen_labels else ' '} {label}")
            if label in chosen_labels:
                chosen_pdfs.append(pdf)
        return chosen_pdfs, []   # (overlay summary is a default-engine feature)
    finally:
        httpd.shutdown()


def main() -> None:
    ap = NLParser(description="Make a printable PDF from a saved web page or URL.",
                  formatter_class=NLHelpFormatter)
    ap.add_argument("-V", "--version", action="version",
                    version=f"%(prog)s {__version__}\n")
    ap.add_argument("source", help="saved .html file, or an http(s):// URL")
    ap.add_argument("tempdir", nargs="?", metavar="[tempdir]",
                    help="output base dir for the dated run folder (default: per-OS scratch)")
    ap.add_argument("--just", metavar="SPEC",
                    help="audit|wysiwyg, portrait|landscape, page|reflow\n"
                         "Faster operation: render just one style combination, not all.\n"
                         "Default '--just all' renders all combinations, and opens:\n"
                         "    --just audit,portrait,page\n"
                         "    --just wysiwyg,portrait,page\n"
                         "(reserved: not yet active)")
    ap.add_argument("-o", "--overlay", action="append", default=[], metavar="SPEC",
                    help="also print the given overlay(s) as an appendix.\n"
                         "SPEC: numbers, selectors, or 'all'. Comma-separated, repeatable.")
    ap.add_argument("--width", type=int, default=1100,
                    help="render width in px for the 'page' (scale-to-fit) layout (default 1100)")
    ap.add_argument("--suffix", default="",
                    help="tag the dated folder, e.g. --suffix vacation -> 2026-06-29.vacation")
    ap.add_argument("--chromium", action="store_true",
                    help="use a Chromium-family browser already installed (no Playwright)")
    ap.add_argument("--install", action="store_true",
                    help="install Playwright + its Chromium, then run")
    ap.add_argument("--no-open", action="store_true",
                    help="do not open the original page or the PDFs afterwards")
    args = ap.parse_args()

    # Parse --overlay into (all?, [numbers], [selectors]) for the patch.
    keep_all, keep_nums, keep_sels = False, [], []
    for chunk in args.overlay:
        for tok in (t.strip() for t in chunk.split(",")):
            if not tok:
                continue
            if tok.lower() == "all":
                keep_all = True
            elif tok.isdigit():
                keep_nums.append(int(tok))
            else:
                keep_sels.append(tok)
    keep = (keep_all, keep_nums, keep_sels)

    tempdir_arg = args.tempdir

    # --just is reserved: validate its facet keywords now; wire up behaviour later.
    if args.just:
        allowed = {"audit", "wysiwyg", "portrait", "landscape", "reflow", "page"}
        bad = [t for t in re.split(r"[,\s]+", args.just.strip()) if t and t.lower() not in allowed]
        if bad:
            sys.exit(f"error: --just: unknown facet(s): {', '.join(bad)}\n"
                     f"       choose from: {', '.join(sorted(allowed))}\n")
        print("  note: --just is reserved and not yet active — rendering the full set.")

    base_dir = Path(tempdir_arg).expanduser() if tempdir_arg else Path(default_tempdir())

    # Read the source HTML. For a saved file, remember its folder so the sibling
    # <name>_files/ assets can be served alongside the patched copy below.
    src = None
    if is_url(args.source):
        html = fetch_url(args.source)
        stem = slug_from_url(args.source)
    else:
        src = Path(args.source).expanduser().resolve()
        if not src.is_file():
            sys.exit(f"error: source not found: {src}\n")
        html = src.read_text(encoding="utf-8", errors="surrogatepass")
        stem = src.stem
    html = html.replace("&amp;shy", "").replace("­", "")  # site's own broken soft hyphens

    outdir = dated_output_dir(base_dir, args.suffix)
    html_dir = outdir / "html"
    html_dir.mkdir()
    for m in MODES:
        (outdir / m).mkdir()
    chosen_labels = {f"{m}/portrait-page" for m in MODES}   # default: open both portrait-page
    items = []
    for m in MODES:
        for o, scale in LAYOUTS:
            lab = variant_label(o, scale)
            items.append((m, o, scale, f"{m}/{lab}",
                          html_dir / f"{stem}_{m}.{lab}.html",
                          outdir / m / f"{stem}_{m}.{lab}.pdf"))

    print(f"{ap.prog} {__version__}")
    print(f"  engine:      {'system Chromium' if args.chromium else 'Playwright'}")
    print(f"  source:      {args.source}")
    print(f"  width:       {args.width}px  (for the 'page' scale-to-fit layout)")
    print(f"  output dir:  {outdir}{os.sep}")
    print(f"  opens:       {', '.join(sorted(chosen_labels))}")
    print("  variants:")

    if args.chromium:
        chosen_pdfs, overlays = render_chromium(html, items, args.width, src, args.source, chosen_labels, keep)
    else:
        install_playwright() if args.install else ensure_playwright()
        chosen_pdfs, overlays = render_playwright(html, items, args.width, src, args.source, chosen_labels, keep)

    # FYI page-snoop: overlays the patch found and neutralised for print.
    seen, uniq = set(), []
    for o in overlays:
        if o["sel"] in seen:            # selectors are unique, so one row per overlay
            continue
        seen.add(o["sel"])
        uniq.append(o)
    if uniq:
        # #0 is a fixed reference row: the page body itself, which always prints.
        rows = [{"n": 0, "sel": "html body", "type": "document",
                 "print": "always", "label": "the page itself", "kept": False}]
        rows += [{**o, "print": "on-demand"} for o in uniq]
        w = min(max(len("selector"), *(len(r["sel"]) for r in rows)), 48)
        nw = max(1, len(str(max(r["n"] for r in rows))))   # index column width
        kept = [o for o in uniq if o.get("kept")]
        head = f"  overlays & popups detected ({len(uniq)})"
        if kept:
            head += "   [kept -> appendix: " + ", ".join(f"#{o['n']}" for o in kept) + "]"
        print()
        print(head + ":")
        print(f"      {'#':>{nw}}  {'selector':<{w}} {'type':<13} {'print?':<9} name")
        print(f"      {'-'*nw}  {'-'*w} {'-'*13} {'-'*9} {'-'*28}")
        for r in rows:
            mark = "*" if r.get("kept") else " "
            print(f"    {mark} {r['n']:>{nw}}  {r['sel']:<{w}} {r['type']:<13} {r['print']:<9} {r['label'][:28]}")
        print()

    if args.no_open:
        print("  opening:     no (--no-open)")
    else:
        print("  opening:")
        # Original page first, so it sits alongside the clean PDFs — a live
        # before/after. On Windows the PDFs open as Edge tabs, so the original
        # becomes the first tab next to the two Web-Print results.
        original = args.source if is_url(args.source) else Path(args.source).resolve().as_uri()
        print(f"  {args.source}   (original page)")
        webbrowser.open(original)
        for cp in chosen_pdfs:
            print(f"  {cp}")
            webbrowser.open(cp.as_uri())
    print()


if __name__ == "__main__":
    main()
