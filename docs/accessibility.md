# Accessibility and WCAG scope

The renderer supplies contrast-tested default palettes and descriptive SVG
exports. These are specific accessibility features, not a declaration that the
application, every exported diagram, or an embedding page conforms to a complete
WCAG level. This guide uses WCAG 2.2 success criteria.

## Verified features and compliance levels

| Feature | WCAG 2.2 criterion and level | What is established |
| --- | --- | --- |
| Default text colors | [1.4.3 Contrast (Minimum), AA](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html); [1.4.6 Contrast (Enhanced), AAA](https://www.w3.org/WAI/WCAG22/Understanding/contrast-enhanced.html) | Palette tests require at least 7:1 for primary, secondary, and special text against all five default surfaces in both themes. This satisfies the normal-text contrast thresholds of 4.5:1 and 7:1 for those combinations. |
| Default borders and reference colors | [1.4.11 Non-text Contrast, AA](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html) | Palette tests require at least 3:1 against each default surface, including muted references from inactive frames. These color comparisons meet the criterion's contrast threshold; they do not evaluate every possible overlapping graphic. |
| SVG text alternatives | [1.1.1 Non-text Content, A](https://www.w3.org/WAI/WCAG22/Understanding/non-text-content.html) | Exports contain a summary and structured state description. This supports providing an equivalent text alternative; usefulness and exposure in the actual embedding/browser/assistive-technology combination still need review. |

A complete Level AA claim requires all applicable Level A and AA criteria; Level
AAA additionally requires all applicable AAA criteria. Contrast results alone do
not establish either. Full-page behavior, complete processes, and accessibility
support also matter. See the [WCAG conformance requirements](https://www.w3.org/TR/WCAG22/#conformance-reqs).

The [palette tests](../cs1302_code_visualizer/frontend/tests/theme.test.ts),
[description tests](../cs1302_code_visualizer/frontend/tests/svgDescription.test.ts),
and [SVG export tests](../cs1302_code_visualizer/frontend/tests/svgExport.test.ts)
provide automated evidence for these implementation features. They do not replace
keyboard, zoom, or screen-reader acceptance testing of the final content.

## Default light and dark colors

These values come from the [shared palette](../cs1302_code_visualizer/frontend/js/theme.ts).
Both themes use the same semantic roles and contrast thresholds.

| Role | Light | Dark |
| --- | --- | --- |
| Canvas | `#ffffff` | `#131416` |
| Inactive stack frame | `#f8f9fb` | `#1a1c1e` |
| Active stack frame | `#eff3fa` | `#1c2736` |
| Object surface | `#e9edf3` | `#252b34` |
| Value surface | `#e6efff` | `#233754` |
| Primary text | `#1e1e1e` | `#cfd0d0` |
| Secondary/type text | `#454950` | `#c9cdd3` |
| Special labels (`this`, return values) | `#8a1c3a` | `#ffd0dc` |
| Borders | `#718096` | `#8b98aa` |
| Active-frame and heap references | `#2757dd` | `#5ca5ff` |
| Inactive-frame references | `#788496` | `#758397` |

Choose `--theme light` or `--theme dark` for predictable exports. Standalone SVG
uses light when the theme is omitted; adaptive inline SVG can follow the host's
`data-theme`. Explicit `auto` follows the viewing system preference. PNG colors
are fixed when rendered. The [theme guide](themes.md) covers embedding, overrides,
printing, and visual examples.

Inline SVG has a transparent canvas, so contrast depends on the host background.
Changing public CSS colors or backgrounds requires a fresh contrast check.
Literal Java `Color` swatches deliberately retain the program's colors and are
outside the default-palette guarantees. Antialiasing, thin strokes, and reducing
a diagram's displayed size can also affect practical readability even when the
specified color pair passes a contrast calculation.

## What an SVG includes

The root SVG has `role="img"`, `aria-labelledby="state-title"`, and
`aria-describedby="state-description"`. It contains:

- A `<title>` with a concise summary and frame/object counts.
- A `<desc>` listing stack frames and visible variables before heap objects,
  including fields, array elements, values, and named reference targets.
- A `<metadata data-description="1">` element containing the description as JSON
  for applications that present it as structured HTML. Metadata alone is not a
  user-facing text alternative.

The description follows the selected state and visible content: hidden fields
are omitted, shared objects appear once, and cycles are described as references
rather than expanded recursively. Review the result for the lesson's purpose;
a state inventory does not automatically explain an algorithm or its significance.

SVG text remains selectable when opened directly or embedded inline. PNG pixels
do not provide selectable labels or the SVG's embedded description. Converting
an SVG to a raster image or PDF does not automatically transfer its accessibility
semantics; provide text alternatives and check the destination format separately.

## Publish an understandable alternative

For PNG or SVG displayed through `<img>`, provide meaningful HTML `alt` text and
nearby prose or a linked long description for a complex state. Do not assume an
SVG's internal description will be exposed through an image embedding. W3C's
[complex-image guidance](https://www.w3.org/WAI/tutorials/images/complex/) explains
how a short label and longer description work together.

For the quickstart example, suitable adjacent prose is: “The main frame's alice
variable refers to a Person. Its age is 42; its name refers to the String
containing Alice.” A larger graph needs a correspondingly complete alternative,
including shared references and cycles when relevant to the lesson.

For inline SVG, preserve its accessibility attributes, title, description, and
styles. Prefix IDs uniquely when embedding several diagrams and update all ID
references, including ARIA and clipping references. The comparison gallery
provides a keyboard-operable **Text description** disclosure with headings and
lists; that disclosure belongs to the gallery, not to every exported SVG.

Check the actual host page with keyboard navigation, zoom, and the intended
screen reader/browser. Confirm that the diagram has a useful name, its full
alternative can be reached, and labels are not announced redundantly. Manual
VoiceOver/Safari acceptance remains necessary; automated tests do not establish
it. The [SVG review guide](svg-gallery.md#check-selection-and-accessibility)
contains the reproduction and manual-review procedure. Interactive stepping
controls and host-page navigation need their own review before a full WCAG claim.

See [reading diagrams](reading-diagrams.md) for the visual key and
[known exceptions](known-exceptions.md) for continuing validation limits.
