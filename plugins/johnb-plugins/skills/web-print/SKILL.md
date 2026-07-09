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

The renderer is `<skill-dir>/scripts/web-print.py`, where `<skill-dir>` is the<br/>
&nbsp; &nbsp; base directory announced when this skill loads.<br/>
Use that path; never search the filesystem for it.

## Commands

- `help` — print the two fenced blocks below (Quick reference, then Script<br/>
&nbsp; &nbsp; options) verbatim. No tool calls.

- `version` — print the VERSION line from the Quick reference. No tool calls.

- `license` — print the License block below verbatim.

- `run`, or an inline source — render; see Run below.

## Quick reference (help output)

`skill web-print help` prints the fenced block below, then the Script options
block — both verbatim, no tool calls, nothing added. Never paraphrase them.

```
NAME
    web-print — render a saved web page or a URL to clean, print-ready PDFs.

VERSION
    4.3.0

COMMANDS (strict — nothing else triggers this skill)
    skill web-print run              # render; parameters follow as field: value
    skill web-print SOURCE [opts]    # render; source + flags inline on one line
    skill web-print help             # this block + the Script options block
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
    The Script options block below is the script's own --help, embedded
    verbatim at build time — behaviour, defaults, modes (audit + wysiwyg
    x 4 layouts = 8 PDFs), engines, and overlays.

EXAMPLES
    skill web-print run
      source: https://en.wikipedia.org/wiki/PDF

    skill web-print https://en.wikipedia.org/wiki/PDF -o all

    # blank first page, title at the bottom? collapse the decorative banner:
    skill web-print run
      source: https://www.example.com/
      collapse-hero: true
```

## Script options (second half of the help output)

<!-- GENERATED:HELP — from `web-print.py --help`; edit the script, then run zDev/make-skill.py -->

```
web-print.py 4.3.0
usage: web-print.py [-h] [-V] [--just SPEC] [-o SPEC] [--width WIDTH]
                    [--suffix SUFFIX] [--collapse-hero] [-v] [--chromium]
                    [--install] [--no-open]
                    source [[tempdir]]

Make a printable PDF from a saved web page or URL.

positional arguments:
  source              saved .html file, or an http(s):// URL
  [tempdir]           output base dir for the dated run folder (default: per-OS
                      scratch)

options:
  -h, --help          show this help message and exit
  -V, --version       show program's version number and exit
  --just SPEC         audit|wysiwyg, portrait|landscape, page|reflow
                      Faster operation: render just one style combination, not
                      all.
                      Default '--just all' renders all combinations, and opens:
                          --just audit,portrait,page
                          --just wysiwyg,portrait,page
                      (reserved: not yet active)
  -o, --overlay SPEC  also print the given overlay(s) as an appendix.
                      SPEC: numbers, selectors, or 'all'. Comma-separated,
                      repeatable.
  --width WIDTH       render width in px for the 'page' (scale-to-fit) layout
                      (default 1100)
  --suffix SUFFIX     tag the dated folder, e.g. --suffix vacation ->
                      2026-06-29.vacation
  --collapse-hero     hide a decorative lead banner ("hero") that would print as
                      a page of blank paper, pulling the title back up to the
                      top of page 1. For page-builder sites; a run that would
                      benefit prints a note suggesting this flag.
                      default: OFF
  -v, --verbose       show untruncated detail (e.g. full overlay selectors)
  --chromium          use a Chromium-family browser already installed (no
                      Playwright)
  --install           install Playwright + its Chromium, then run
  --no-open           do not open the original page or the PDFs afterwards
```

## License (license output)

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

## Run

- Forms: `skill web-print run` with `field: value` lines below it;<br/>
&nbsp; &nbsp; `skill web-print SOURCE [flags]` inline; Claude Code: `/web-print SOURCE [flags]`.

- `source` is required — if missing, print a one-line error pointing at<br/>
&nbsp; &nbsp; `skill web-print help` and stop. Ignore unknown fields with a brief note.

- Build the command from the PARAMETERS map in the Quick reference. Pass inline<br/>
&nbsp; &nbsp; flags through unchanged, including the experimental capture flags<br/>
&nbsp; &nbsp; (`--raw`, `--wait`, `--scroll`, `--main`).

- Run it with Bash and relay the script's output. Surface any `error:` or<br/>
&nbsp; &nbsp; `note:` line (e.g. the `--collapse-hero` suggestion) — never bury them.

- If Playwright is missing, offer the two fixes: `install: true`, or<br/>
&nbsp; &nbsp; `engine: chromium` to drive a browser already on the machine.
