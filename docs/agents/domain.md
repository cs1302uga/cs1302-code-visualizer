# Domain documentation

This repository uses a single domain context: a root `GLOSSARY.md` and architectural decision records under `docs/adr/`.

## Reading rules

Before domain exploration, read the root glossary when present and any ADRs relevant to the area being changed. Use the glossary's terms consistently in specifications, tests, code, and review findings.

If these documents are absent, continue with existing repository terminology. Create glossary entries and ADRs when domain-modeling work resolves an actual term or decision; setup does not require placeholder documents.

When a proposed change conflicts with an ADR, identify that conflict and explain why the decision should be reconsidered. Preserve the current decision until a replacement is agreed.
