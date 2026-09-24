# Tracer v3.1.2 upgrade

The visualizer pins `code-tracer.jar` from v3.1.2 with SHA-256
`02fd7a05bba1448155865264dba7be6852f1caff9f44aeb6b4a2796e7e13a132`.
The downloaded bytes matched GitHub's release-asset digest and the JAR reported
version `3.1.2`. The installer checksum fix is a separate commit, `7306e87`.

## Compatibility scope

This upgrade preserves current visualizer behavior. It does not add source-file
navigation. Upstream added `sources` and `entryFile` metadata and populated file
paths in trace steps and stack frames; v3.1.2 also fixes a redundant worker-close
warning. Submitted sources appear in the source map; library frames can name
files outside that map.

Sources: [release](https://github.com/cs1302uga/cs1302-tracer/releases/tag/v3.1.2),
[changes since v3.1.0](https://github.com/cs1302uga/cs1302-tracer/compare/v3.1.0...v3.1.2).

## Validation

Both JARs were evaluated in separate temporary caches using the same local
OpenJDK 21 installation. The final full suite passed: **400 tests, 100% coverage**.
The new test file passed Ruff formatting/lint and BasedPyright checks.
Validation covered:

- 36 single-execution comparisons: 18 inputs in PythonTutor and modern formats.
  Inputs included records, enums, references, arrays, recursion, packages,
  exceptions, empty programs, stdin, multiple source files, selected breakpoints,
  and accumulated breakpoint occurrences.
- 14 batch comparisons using two workers and recycling workers after three jobs.
  The matrix included failed jobs from uncaught exceptions and subsequent
  successful jobs.
- Eight rendered image comparisons. Seven were pixel-identical. The enum image
  differed only in identity hash values; a repeat on v3.1.0 confirmed that those
  values also change between runs of the same version. After normalizing the
  actual enum hash values, that image was pixel-identical too.
- All 50 trace pairs were equal after excluding the expected source metadata
  differences and normalizing enum identity hash values. Raw outputs were
  retained during comparison; other output differences were not ignored.
- Compilation failures, batch execution timeouts, and a successful job after
  those failures were verified on both versions.
- A wheel built from the source distribution was installed in a clean virtual
  environment outside the checkout. Fresh downloads, cached upgrades, offline
  rejection/reuse, persistent trace-cache invalidation, and rollback passed.
- Eight new real-JAR regression tests cover exact source text, entry-file and
  step-file mappings, selected and accumulated breakpoint results, both formats,
  and persistent batch worker reuse.

Validation artifacts from this session are in `/tmp/tracer-312-validation`.
That temporary directory is not required at runtime and is not a permanent
artifact store. The regression tests are in `tests/test_tracer_source_metadata.py`.

## Rollback

Revert the upgrade commit while retaining installer commit `7306e87`, then
rebuild and reinstall the package. The previous pin is:

- URL: `https://github.com/cs1302uga/cs1302-tracer/releases/download/v3.1.0/code-tracer.jar`
- SHA-256: `b9acfe85478ecdaed06fc7bc575283dac04ea1af67ab3fffe3c2babedebf4734`

Close existing rendering sessions and batch workers before switching versions.
The installer verifies or replaces the cached JAR against the restored pin.
Persistent trace cache keys include the pin, so traces from the upgraded version
are not reused under the older pin. A rollback needs network access unless the
matching older JAR is already in the cache; an incompatible offline cache is
rejected. Never bypass checksum verification to roll back.
