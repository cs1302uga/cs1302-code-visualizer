# CodeQL remediation

Validated on 2026-09-27 against the working tree, after the string-style feature.
All actionable findings identified in this review are fixed. Remaining scanner
alerts have explicit dispositions; this is not a zero-alert scan.

## Changes

- Sanitize computed legacy HTML with DOMPurify before insertion. Inert template
  fragments preserve table structure; HTML setters return sanitized strings for
  D3 callbacks. Ordinary reference labels use DOM text. Selector fallback escaping
  now handles backslashes, and connector inputs are checked as DOM elements.
- Use null-prototype dictionaries for trace names and heap IDs, including the
  cloned string-style trace. Names such as `__proto__` and `constructor` remain
  ordinary data, without changing object prototypes.
- Use explicit TAR `data` filters throughout the downloaders. JDK extraction
  raises on filter errors instead of ignoring them. ZIP extraction validates
  entry paths, resolved destinations, and symlink targets; executable permissions
  are preserved while special permission bits are removed.
- Replace the potentially slow headless-option regex with fixed token boundaries.
- Pin the two flagged third-party release actions to the commits behind their
  existing release tags. Remove unused frontend code and explain deliberate
  exception fallbacks.

The sanitizer follows the [DOMPurify API](https://github.com/cure53/DOMPurify).
Security regressions cover active HTML, table fragments, source-code rendering,
prototype-named variables, archive traversal, external symlinks, and the JDK
filter-error handling path on Linux and macOS.

## Verification

| Gate | Result |
| --- | --- |
| `make check` | Passed: Ruff, Markdown/local links, package Basedpyright, Python and frontend tests. |
| Python | 558 passed; 100% coverage of 2,024 statements. |
| Frontend | 94 passed across 10 files. |
| `make test-examples`, JDK 25 | 34 examples passed; 389 images rendered. |
| `make build` | Frontend bundles, wheel, and source distribution passed. |
| `make deptry` | Passed. |
| `git diff --check` | Passed. |

Existing webpack bundle-size advisories remain. Validation ran locally on macOS
with Python 3.14; the complete remote release CI matrix was not run.

## CodeQL results

Fresh Python and JavaScript/TypeScript databases passed extraction-quality checks
with no extractor errors. All 63 Python files and 32 JavaScript/TypeScript files
were extracted, along with HTML/configuration and the release workflow. Explicit
suites resolved 233 Python and 245 JavaScript queries: official security/quality
and experimental suites plus available GitHub Security Lab community packs.
Remote/default and local threat models were enabled.

Generated bundles, dependencies, analysis artifacts, Java teaching fixtures, and
the external tracer JAR are outside the scan scope. No query category was disabled
and no raw results were removed. No custom taint model was introduced to hide
remaining alerts; source/sink inventories and wrapper inspection informed triage.

| Non-debug alerts/audit candidates | Before | After |
| --- | ---: | ---: |
| Python | 193 | 166 |
| JavaScript/TypeScript | 225 | 83 |
| Total | 418 | 249 |

The final raw SARIF contains 912 results, including 663 source/sink debugging
outputs. Counts include overlapping stable/experimental queries and audit-only
checks; they are not counts of confirmed vulnerabilities.

The remaining 249 alerts were reviewed as follows:

| Disposition | Count | Rationale |
| --- | ---: | --- |
| False positive | 103 | Existing security checks or semantics are not understood by the query. |
| Intended capability | 34 | Local CLI filesystem paths, explicit installer commands, output templates, and selected downloads. |
| Audit reviewed | 102 | Safe external-library calls, callback timers, argument-list process launches, and deliberate cleanup/probe fallbacks. |
| Test intent | 4 | Explicit failure/destructor paths and assertions in tests. |
| Style only | 5 | Local/repeated test imports and module imports used alongside direct imports. |
| Compatibility | 1 | An existing module-level configuration name is retained. |

Specific residual security alerts:

- **HTML/XSS:** two stable alerts and their experimental counterparts remain.
  One points to assignment into an inert template that is sanitized before
  attachment. The other points to passing a checked `HTMLElement` or `null` to
  jQuery, where CodeQL retains trace taint through the DOM node. Neither inserts
  an unsanitized HTML string into the live document.
- **Property injection:** writes target null-prototype dictionaries or existing
  own properties on the null-prototype clone. Arbitrary variable names are an
  intended part of trace data, not prototype mutation.
- **Archive extraction:** the experimental TAR query still flags explicit
  `data` filters, including the rejection test. The ZIP query does not infer the
  path and symlink validation in the shared extractor. Regression tests exercise
  rejection rather than relying on suppression.
- **Python runtime warnings:** reported import cycles pass through a
  `TYPE_CHECKING` guard; the file lifetime is owned by `ExitStack`; unsupported
  platform branches raise before use; timing warnings concern public checksums,
  paths, versions, and test data, not secret authentication checks.

These dispositions assume the documented local CLI/library use: the application
intentionally runs selected Java programs and writes selected output paths. They
do not certify a privileged service accepting arbitrary remote jobs, and the
renderer is not a sandbox for executing Java code.

The ignored `static_analysis_codeql_2/` directory contains final SARIF, database
quality checks, query logs, diagnostics, and `triage.json`. Every non-debug SARIF
result has an individual disposition, rationale, and source excerpt. The prior
scan is retained in `static_analysis_codeql_1/` for comparison.
