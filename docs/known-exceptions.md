# Known exceptions

These are continuing security, validation, and compatibility exceptions. Revisit
an entry when its assumptions change; remove it when resolved. This document is
not a record of completed work or a substitute for fresh validation.

## Security analysis

- **Local execution and filesystem access:** the CLI intentionally executes selected
  Java programs, installer commands, and operator-selected downloads, and reads or
  writes selected paths. The renderer is not a Java sandbox. Reassess these
  capabilities before accepting untrusted remote jobs or running with elevated
  privileges.
- **HTML findings:** CodeQL can flag assignment to an inert template before
  DOMPurify sanitizes it, and a checked `HTMLElement` or `null` passed to jQuery.
  Neither path inserts an unsanitized string into the live document. Revisit if
  sanitization order, allowed markup, or DOM argument checks change.
- **Property writes:** trace names and heap IDs intentionally permit names such as
  `__proto__`; their dictionaries and cloned objects have null prototypes.
  Revisit if ordinary objects are introduced at those boundaries.
- **Archive findings:** experimental queries can flag TAR extraction despite its
  explicit `data` filter and ZIP extraction despite shared path and symlink
  validation. Keep rejection tests and JDK extraction errors enforced. Revisit
  when extraction code or query support changes.
- **Runtime and audit findings:** type-checking-only imports can appear cyclic;
  `ExitStack` owns file lifetimes; unsupported-platform branches raise before use;
  timing findings concern public checksums, paths, versions, and test data.
  Callback timers, argument-list process launches, and intentional cleanup/probe
  fallbacks require contextual review. Reassess when the affected control flow
  or data sensitivity changes rather than suppressing whole query categories.
- **Scan scope:** generated bundles, dependencies, Java teaching fixtures, and the
  external tracer JAR were outside the Python/JavaScript CodeQL scan. Reviewed
  alerts do not certify those components. Revisit scope when dependencies,
  languages, or the execution trust model change.

## Validation

- **Nondeterministic references:** enum identity hash values may differ between
  otherwise equivalent tracer runs. Cross-version comparisons may normalize those
  values and expected source-metadata differences, but must retain raw output and
  investigate other differences. Revisit when tracer identity semantics change.
- **Connector geometry:** ordinary crossings through clear space are permitted;
  arbitrary graphs are not guaranteed to be crossing-free or independently
  traceable. Text remains protected. Fixed-position routing uses a bounded set of
  candidates before local spacing repair; externally constrained CSS can prevent
  repair and cause a diagnostic. Revisit when routing candidates, CSS layout, or
  attachment rules change. Reproduce reported failures against the current
  renderer using the [routing validation guidance](reference-routing/README.md#validation-and-performance).
- **Build advisories:** webpack emits bundle-size advisories. Successful builds do
  not resolve that performance concern; reassess when bundle contents or delivery
  requirements change.
- **Type-check scope:** the repository gate checks the production Python package,
  not every development script. Changes to helper scripts still need linting and
  direct execution; revisit if the type-check gate is expanded.
- **SVG acceptance:** font substitution can alter glyphs across applications.
  Browser checks and screenshots alone do not establish screen-reader acceptance.
  Follow the [SVG review guidance](svg-gallery.md) when changing export structure,
  accessible descriptions, fonts, or embedding behavior.

## Compatibility

- **Module-level name:** `DISABLE_HEADLESS_MODE` remains available despite having
  no internal reads. Removing it requires a deliberate compatibility decision,
  not merely an unused-variable cleanup. Revisit during API deprecation review.

- **Deprecated string option:** rendering accepts `inline_strings` with a warning
  during the current major version; specifying it together with `string_style`
  is an error. Trace-only APIs retain their existing argument. Revisit removal at
  the next major release; see the [migration guide](string-style/README.md).
- **Legacy traces:** strings inlined during tracing lack reference identity, so
  `default` and `compact` require regeneration with `inline_strings=False`.
  The renderer must not invent reference IDs. Revisit only if the trace format
  provides enough identity information.
- **Tracer source metadata:** metadata does not imply source-file navigation in
  the visualizer, and library frame paths may be absent from the submitted source
  map. Revisit when adding navigation or changing tracer versions.
- **Array metadata:** untyped arrays use the configured base orientation when rank
  is unavailable; collections retain their existing layout. Keep the documented
  [resolution rules](array-orientation/README.md) until introducing an explicit
  compatibility change.
