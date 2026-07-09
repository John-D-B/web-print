---
name: web-print
description: >
  Render a saved web page (.html) or a remote http(s) URL to clean, paginated,
  print-ready PDFs using headless Chromium. Strips popups/overlays, consent walls,
  fixed headers, and scroll animations that make pages print badly, then renders
  two image modes every run — audit (images stripped, ink-friendly black-on-white)
  and wysiwyg (images + brand colour kept) — each in four orientation/layout variants.

  STRICT INVOCATION (case-insensitive keywords `skill`, `run`, `help`, `version`,
  `license`). Act ONLY when a line is one of these: `skill web-print run` (render;
  parameters follow as `field: value` lines — required: source; optional: output,
  overlay, width, suffix, collapse-hero, verbose, engine, install, open);
  `skill web-print SOURCE [options]` (source + flags inline); `skill web-print help`;
  `skill web-print version`; `skill web-print license`. A reserved keyword after
  the name is a command, not a source.

  Otherwise do NOT trigger: casual mentions of web-to-PDF or the skill name are not
  triggers; ask for a proper `run` block.
---

# web-print — web page → printable PDF

Drives headless Chromium to turn a saved web page or a live URL into clean,
paginated PDFs. Strips popups, consent walls, fixed headers, and scroll
animations that make pages print badly, and renders two image modes every run:

- **audit** — images/backgrounds stripped, recoloured to ink-friendly
  black-on-white; the "just the facts" archival record.
- **wysiwyg** — images and brand colour kept; the page as it looks, minus the
  repeating overlays the browser leaves in.

Each mode is rendered in four orientation/layout variants, so you can pick the
best fit after the fact. The bundled, engine-verified script lives at
`scripts/web-print.py` (relative to this skill's directory). It runs on macOS,
Windows, and Linux/WSL-class systems.

## Quick reference (help output)

When the user runs `skill web-print help`: show the fenced block below verbatim,
then run `<skill-dir>/scripts/web-print.py --help` and show ITS output verbatim
beneath it. The script's `--help` is the single source of truth for behaviour,
defaults, modes, and engines — never paraphrase or summarise it. The block below
only covers what the script cannot know: the skill grammar and the field->flag map.

```
NAME
    web-print — render a saved web page or a URL to clean, print-ready PDFs.

COMMANDS (strict — nothing else triggers this skill)
    skill web-print run              # render; parameters follow as field: value
    skill web-print SOURCE [opts]    # render; source + flags inline on one line
    skill web-print help             # this block, then the script's own --help
    skill web-print version          # print the version and stop
    skill web-print license          # show the license and stop

PARAMETERS — each maps 1:1 onto a script option:
    source: X            ->  X               (required; .html or http(s) URL)
    output: DIR          ->  [tempdir]        (2nd positional)
    overlay: SPEC        ->  -o SPEC
    width: N             ->  --width N
    suffix: NAME         ->  --suffix NAME
    collapse-hero: true  ->  --collapse-hero
    verbose: true        ->  -v
    engine: chromium     ->  --chromium       (default: playwright)
    install: true        ->  --install
    open: false          ->  --no-open

EVERYTHING ELSE
    The script's --help is the authority on behaviour, defaults, modes
    (audit + wysiwyg x 4 layouts = 8 PDFs), engines, and overlays.
    `skill web-print help` shows it verbatim below this block.

EXAMPLES
    skill web-print run
      source: https://en.wikipedia.org/wiki/PDF

    skill web-print https://en.wikipedia.org/wiki/PDF -o all

    # blank first page, title at the bottom? collapse the decorative banner:
    skill web-print run
      source: https://www.example.com/
      collapse-hero: true
```

## License (`skill web-print license` output)

Show this fenced block verbatim when the user runs `skill web-print license` —
nothing added above or below. It is embedded here on purpose: no file read, so it
never triggers a permission prompt. The same text ships as `LICENSE.txt` in the
skill bundle.

```
Web-Print — Skill License

(c) 2026 Mountain Informatik GmbH. Original software by John Buehrer.

SPDX-License-Identifier: BUSL-1.1 OR LicenseRef-MountainInformatik-Commercial

This Skill -- SKILL.md, the bundled web-print.py script, and all accompanying
files -- is source-available under the Business Source License 1.1 (BSL), with
a commercial license available from Mountain Informatik GmbH.

Under the BSL you may use Web-Print freely -- including for your own paid client
work -- modify it, and self-host it. A commercial license is required only to
offer Web-Print itself as a commercial product or service (hosted, embedded, or
resold). Each released version converts to an open-source license (GPL v2.0 or
later) on the Change Date stated in the repository LICENSE.

Full terms are in the project repository -- this file does not reproduce them:

  https://github.com/John-D-B/web-print

    LICENSE          complete Business Source License 1.1 text + parameters
    LICENSING.md     plain-English summary + commercial terms
    CONTRIBUTING.md  contribution (inbound-license) policy

The software is provided WITHOUT WARRANTY of any kind, to the extent permitted
by applicable law. See the LICENSE file for the full disclaimer.

"Web-Print" is a trademark of Mountain Informatik GmbH. The license grants no
trademark rights; redistributed modified versions should use a different name.

Commercial licensing enquiries: sales <at> mountain-informatik.ch
```

## Finding this skill's files (do NOT search for them)

When this skill is invoked, the harness provides its base directory (shown as
"Base directory for this skill: ...") — call it `<skill-dir>`. The renderer is at
`<skill-dir>/scripts/web-print.py`; run it at that path. **Never run a filesystem
search** (`find`, `ls` across `~`, etc.) to locate the skill — the path is already
known, and searching only triggers needless permission prompts.

For `skill web-print version`: run `<skill-dir>/scripts/web-print.py -V` and show
its output — the version reported is always the script that will actually execute,
so it can never drift from reality. Stop.

For `skill web-print license`: show the fenced block under "## License" above,
verbatim. It is already in context — do NOT read `LICENSE.txt` or any file. Stop.

## Running it (the `run` command)

**Invocation forms** (all explicit — casual prose still never triggers):
- `skill web-print run`, then `field: value` lines below it (Cowork-style).
- `skill web-print <source> [options]` — the source and the script's own flags
  inline on the same line (this is the script's own CLI syntax). A reserved
  keyword (`run`/`help`/`version`/`license`) right after the name is that command,
  never a source.
- Claude Code: `/web-print <source> [options]` — the same inline form with a slash.

For the run-block form, map `field: value` lines with the table below. For the
inline forms, pass the source and any flags (`-o all`, `--width N`, `--suffix`,
`--collapse-hero`, `-v`, `--chromium`, `--install`, `--no-open`, and the
experimental capture flags `--raw`/`--wait`/`--scroll`/`--main`) straight through
to the script unchanged; treat an inline `--install` as equivalent to
`install: true`. Then:

1. Parse the parameters. `source` is required — if it is missing, show a
   one-line error pointing at `skill web-print help` and stop. Ignore unknown
   fields with a brief note.

2. Resolve this skill's directory and build the command against the bundled
   script. Map fields to the script's CLI exactly as below:

   | field    | becomes                                             |
   |----------|-----------------------------------------------------|
   | source   | first positional argument                           |
   | output   | second positional (the tempdir / base folder)       |
   | overlay  | `-o SPEC` (repeatable / comma-separated)            |
   | width    | `--width N`                                          |
   | suffix   | `--suffix NAME`                                      |
   | engine   | `chromium` -> `--chromium`; `playwright` -> nothing  |
   | install  | `true` -> `--install`                                |
   | open     | `false` -> `--no-open`                               |
   | collapse-hero | `true` -> `--collapse-hero`                     |
   | verbose  | `true` -> `-v`                                       |

   There is no orientation/layout field: every run renders both modes and all
   four orientation/layout variants. (Selecting a single one is the reserved
   `--just` flag, not yet active.)

   Example resulting invocation:

   ```
   python3 <skill-dir>/scripts/web-print.py "https://example.com/" ~/pdfs -o all
   ```

3. Run it with the Bash tool. The script prints its settings, the eight produced
   files grouped under `audit/` and `wysiwyg/` (the two opened marked `*`), the
   overlay table, and the paths it opened. Relay that output; surface any
   `error:` line the script emits (missing Playwright, no Chromium found, source
   not found) rather than burying it. If it prints a `note:` suggesting
   `--collapse-hero` (a page opening with a large blank banner), pass that along.

4. If the default engine reports Playwright is missing, offer the two documented
   fixes: re-run with `install: true`, or `engine: chromium` to drive a browser
   already on the machine.
