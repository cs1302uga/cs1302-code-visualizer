# Agent guidance

## Tracer upgrades

Use the repository's [upgrade-tracer skill](.codex/skills/upgrade-tracer/SKILL.md) when asked to upgrade the tracer to its latest stable release and carry the change through coverage verification, a patch version bump, and PR review. Read the skill before starting; it defines the balanced-code-review and CodeQL remediation loop, PR comment handling, and final interactive review. It can also be invoked explicitly as `$upgrade-tracer`.

Requests to document or edit the skill do not trigger the upgrade workflow. Follow the user's requested scope for narrower tracer tasks.

For repository setup and verification commands, consult [CONTRIBUTING.md](CONTRIBUTING.md).
