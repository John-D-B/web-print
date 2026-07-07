# Web-Print — SAST Scan and Security Assessment

**Author:** JohnB, with AI pair-programming support by Anthropic Claude<br/>
**Date:** 2026-07-02<br/>
**Target version:** `web-print.py` (and the identical copy bundled in `web-print.skill`)<br/>
**Methodology:** static analysis with Bandit and Semgrep, dependency audit with pip-audit,<br/>
&nbsp; &nbsp; and a documented triage framework (accept-by-design / false-positive / remediate / accept-risk).

## 1. Result

**PASS, with documented findings. No High-severity issues.**

- Bandit: 8 findings on `web-print.py` (0 High, 2 Medium, 6 Low) — all triaged below.
- pip-audit: **no known vulnerabilities** in dependencies.
- Semgrep: **no findings** (the one original finding was resolved in v3.7.0 — see §4).
- The one item deserving action is not a scanner finding at all:<br/>
&nbsp; &nbsp; the `--no-sandbox` Chrome flag in the opt-out `--chromium` engine (§5, item 1).

## 2. Trust model (the frame for every verdict)

**Web-Print** is a **single-user, local, command-line developer tool.**<br/>
The user runs it on their own machine, with their own privileges,<br/>
&nbsp; &nbsp; against a URL or `.html` file **they** chose.

There is no server, no multi-tenant surface, and no authentication to bypass.<br/>
The user is the trust boundary.

Consequences for triage:

- Classic web-app findings — path traversal, arbitrary file read, "SSRF" —<br/>
&nbsp; &nbsp; reframe as *"the user is driving their own tool against their own inputs."*<br/>
They are not privilege-boundary crossings here.

- The **one** place the tool ingests genuinely untrusted input is the **remote HTML**<br/>
&nbsp; &nbsp; it fetches and renders in a real browser engine. That is where the real<br/>
&nbsp; &nbsp; security attention belongs (§5), and it is mostly invisible to SAST.

## 3. Scope

### In scope

| Component | File | Tool |
|---|---|---|
| Main tool | `web-print.py` (847 lines) | Bandit, Semgrep |
| Skill bundle | `web-print.skill` (ZIP: `SKILL.md`, `version.txt`, `scripts/`) | manual + Bandit (bundled `.py`) |
| Dependencies | `requirements.txt` (`playwright>=1.40`) | pip-audit |

### Out of scope

| Item | Reason |
|---|---|
| Sample input pages and rendered output PDFs | Test/output artifacts, not tool code. |
| The injected in-page JS in `build_patch()` | Tool-generated, runs in the ephemeral render context; see §5 item 5. |

### Skill-bundle integrity check

`web-print.skill` is a ZIP archive. Its bundled `scripts/web-print.py` was extracted<br/>
&nbsp; &nbsp; and compared byte-for-byte against the top-level `web-print.py`:<br/>
&nbsp; &nbsp; **identical** (both v3.8.0). Scanning one covers both.

`SKILL.md` was inspected for risky invocation patterns (`curl|bash`, `sudo`, auto-eval):<br/>
&nbsp; &nbsp; none present. Its only install path is the opt-in `--install` flag.

## 4. Findings — `web-print.py`

Toolchain: Bandit 1.9.4, Semgrep (200 community rules), Python 3.13, on macOS.

```bash
$ bandit -f txt web-print.py
$ semgrep --config p/python --config p/security-audit --config p/command-injection web-print.py
```

### Active findings (all accept-by-design)

| # | Test | Sev | Line(s) | Verdict |
|---|---|---|---|---|
| 1 | B404 subprocess import | Low | 62 | Accept — by design |
| 2 | B108 hardcoded `/tmp` | Med | 199, 200 | Accept — by design (documented convention) |
| 3 | B603 subprocess without `shell=True` | Low | 588, 589, 690 | Accept — by design |
| 4 | B110 try/except/pass | Low | 606, 636 | Accept — by design |

### Triage detail

**B108 (Medium ×2) — hardcoded `/tmp`, `default_tempdir()`. ACCEPT — by design.**<br/>
`default_tempdir()` returns `/tmp/claude/web-print` on POSIX.<br/>
This is the tool's documented scratch-dir convention, and it is user-overridable<br/>
&nbsp; &nbsp; via the `tempdir` positional argument.

*Insight — the determinism is a requirement, not an accident.*<br/>
`/tmp/claude/...` is a shared, known location for AI-generated output delivered<br/>
&nbsp; &nbsp; back to the end user, and that output needs periodic garbage collection.<br/>
A fixed, predictable path is what makes both possible:<br/>
&nbsp; &nbsp; the user can find, inspect, and clean up what the tool produced.<br/>
As AI-assisted work is an ongoing and emerging area, a deterministic location<br/>
&nbsp; &nbsp; for human oversight is a deliberate governance choice.<br/>
A randomized per-run directory would defeat that purpose.

*Residual note:* a predictable path under a shared `/tmp` is a symlink-pre-placement<br/>
&nbsp; &nbsp; vector on multi-user hosts. Negligible for a single-user tool.<br/>
If hardening is ever wanted, create the base with a restrictive mode (e.g. `0700`) —<br/>
&nbsp; &nbsp; **not** `tempfile.mkdtemp`, which would randomize the path and break the<br/>
&nbsp; &nbsp; deterministic-oversight requirement above (§7, WP-SAST-04).

**B603 (Low ×3) / B404 (Low) — subprocess. ACCEPT — by design.**<br/>
No `shell=True` anywhere in the file.<br/>
Every call passes an argument **list**, not a shell string.<br/>
Executables are resolved safely: the browser via `find_chrome()` (absolute paths or<br/>
&nbsp; &nbsp; `shutil.which`), and pip/Playwright via `sys.executable`.<br/>
No user-controlled string reaches a shell.

**B110 (Low ×2) — try/except/pass. ACCEPT — by design.**<br/>
Best-effort rendering: a page-load network timeout and the lazy-load scroll helper<br/>
&nbsp; &nbsp; are intentionally non-fatal, so a slow or partial page still produces its PDFs<br/>
&nbsp; &nbsp; rather than aborting the run.

### Resolved in v3.7.0 — B310 / `dynamic-urllib-use-detected` (WP-SAST-02)

Bandit (B310) and Semgrep (`dynamic-urllib-use-detected`) both warned that `urllib`<br/>
&nbsp; &nbsp; accepts `file://` and custom schemes, so a malicious value could read local files.<br/>
This was a **false positive**: `fetch_url()` is only reached after `main()` gates the<br/>
&nbsp; &nbsp; source through `is_url()`, which admits only `http://` / `https://`; a file path<br/>
&nbsp; &nbsp; takes the other branch (`Path.read_text`, not `urllib`).

v3.7.0 closes it two ways:

- **Defense-in-depth guard:** an explicit `http`/`https` scheme check at the top of<br/>
&nbsp; &nbsp; `fetch_url()` — so the function stays safe even if a future caller forgets the<br/>
&nbsp; &nbsp; `is_url()` gate.

- **Justified inline suppression** on the `urlopen` line, for both scanners:<br/>
&nbsp; &nbsp; `# nosec B310` (Bandit) and<br/>
&nbsp; &nbsp; `# nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected`<br/>
&nbsp; &nbsp; (Semgrep — the id is the full doubled check-id Semgrep emits; the shorter form does not match).

Both scanners now report zero findings on that line.

## 5. Proactive disclosure (items SAST cannot flag)

These are the security-relevant design points a reviewer should know.<br/>
None is a scanner finding; the first is the most notable.

1. **`--no-sandbox` on Linux, `--chromium` engine only.**<br/>
The opt-out `--chromium` engine adds `--no-sandbox --disable-dev-shm-usage`<br/>
&nbsp; &nbsp; when `sys.platform` is Linux — disabling Chrome's sandbox while it renders<br/>
&nbsp; &nbsp; fetched (possibly hostile) HTML.<br/>
The **default** Playwright engine does **not** do this — it launches Chromium with<br/>
&nbsp; &nbsp; the sandbox intact.<br/>
`--no-sandbox` is a common necessity for headless Chrome in containers, but it<br/>
&nbsp; &nbsp; weakens isolation. This section is that disclosure;<br/>
&nbsp; &nbsp; the one open question is whether to gate the flag behind an explicit opt-in<br/>
&nbsp; &nbsp; rather than auto-adding it on Linux (§7, WP-SAST-01).

2. **Rendering untrusted remote HTML.**<br/>
`fetch_url()` GETs an arbitrary user-supplied URL and the engine renders it in a real<br/>
&nbsp; &nbsp; browser. The mitigation is headless operation plus Chromium's sandbox<br/>
&nbsp; &nbsp; (intact under the default engine; weakened under item 1). This is inherent to any<br/>
&nbsp; &nbsp; web-render tool and is acceptable given the trust model (§2).

3. **Local HTTP server, `--chromium` mode (`serve_dir`).**<br/>
Binds `127.0.0.1:0` — **localhost only, ephemeral port**, serving the `html/` working<br/>
&nbsp; &nbsp; directory for the duration of the render, then `shutdown()` in a `finally`.<br/>
It is **not** bound to `0.0.0.0`. Low risk: localhost-scoped, short-lived,<br/>
&nbsp; &nbsp; and it serves only the tool's own patched HTML.

4. **`<base href>` construction (`inject_base`) — resolved in v3.8.0.**<br/>
The tag value is now passed through `html.escape()`, so a double-quote in the URL is<br/>
&nbsp; &nbsp; encoded (`&quot;`) rather than breaking out of the attribute.<br/>
Legitimate URLs are unaffected: an `&` becomes `&amp;`, the correct HTML representation,<br/>
&nbsp; &nbsp; which the browser decodes back to `&`.

5. **Injected in-page JS (`build_patch`, ~230 lines).**<br/>
Tool-generated JavaScript that classifies and neutralizes print-breaking overlays.<br/>
It runs in the ephemeral render context, controlling print layout — it is the tool's<br/>
&nbsp; &nbsp; own trusted code, not a user-facing web-app surface.<br/>
Reviewed manually rather than with a JavaScript linter; low priority given where it runs.

## 6. Dependencies

**pip-audit — PASS.**

```bash
$ pip-audit -r requirements.txt
No known vulnerabilities found
```

The sole runtime dependency is `playwright>=1.40`, which manages its own pinned<br/>
&nbsp; &nbsp; Chromium build. No known-vulnerable versions.

## 7. Recommended actions

**Resolved:**<br/>
&nbsp; &nbsp; WP-SAST-02 — explicit scheme guard in `fetch_url()` (v3.7.0, §4).<br/>
&nbsp; &nbsp; WP-SAST-05 — `<base href>` value escaped via `html.escape()` (v3.8.0, §5.4).

Remaining, all optional hardening (no defect fixes required):

| ID | Action | Priority | Effort |
|---|---|---|---|
| WP-SAST-01 | Consider gating the Linux `--no-sandbox` behind an explicit opt-in flag,<br/>&nbsp; &nbsp; rather than auto-adding it (§5.1).<br/>The behaviour is already disclosed in §5.1. | Medium | Low |
| WP-SAST-04 | Harden the `/tmp` base dir with a restrictive mode (e.g. `0700`) on creation.<br/>Keep the path deterministic — do not randomize it (§4, B108). | Low | Low |

## 8. Triage framework

Verdicts used above: **Accept — by design** (intentional, not a gap),<br/>
&nbsp; &nbsp; **False positive** (tool flagged a non-issue), **Remediate** (genuine, fix before release),<br/>
&nbsp; &nbsp; **Accept risk** (genuine, understood, accepted).<br/>
No finding required a *Remediate* verdict.<br/>
The §7 actions are hardening and documentation, not defect fixes.
