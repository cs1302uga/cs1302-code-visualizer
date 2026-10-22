# Issue tracker: GitHub

Issues and specifications live in [cs1302uga/cs1302-code-visualizer on GitHub](https://github.com/cs1302uga/cs1302-code-visualizer/issues).

## Issue operations

Use the connected GitHub tools when they support the operation. Use the `gh` CLI for missing capabilities, with `--repo cs1302uga/cs1302-code-visualizer` to select the repository explicitly.

- When a skill says to publish to the issue tracker, create a GitHub issue.
- When a skill says to fetch a ticket, read the issue's current body, labels, and relevant comments.
- Search for an existing issue before creating another issue for the same specification.
- Apply the triage role using [the configured label vocabulary](triage-labels.md).
- Keep published issue bodies self-contained. Use repository permalinks for source evidence; local `.scratch/` files are working artifacts and are not remotely accessible attachments.

For multiline issue bodies and comments, use a structured tool argument or a UTF-8 file passed through `--body-file`. Examples:

```sh
gh issue list --repo cs1302uga/cs1302-code-visualizer --state open --json number,title,labels
gh issue view 42 --repo cs1302uga/cs1302-code-visualizer --json number,title,body,labels,comments
gh issue create --repo cs1302uga/cs1302-code-visualizer --title "Issue title" --body-file /path/to/issue.md --label ready-for-agent
gh issue edit 42 --repo cs1302uga/cs1302-code-visualizer --add-label ready-for-agent
```

## Pull requests as a triage surface

**PRs as a request surface: no.** The issue-triage workflow processes issues. Existing pull-request review workflows remain separate.

## Related tickets

Use GitHub sub-issues and native issue dependencies when supported by the available tools. A dependency requires the issue's numeric database ID, which is distinct from its issue number. If the relevant capability is unavailable, record `Part of #<parent>` or `Blocked by: #<number>` in the child issue and link children from the parent.

For a wayfinding workflow, use an issue for the map and linked issues for child tickets. Verify any additional `wayfinder:*` labels required by that invoked workflow before publishing; they are separate from the five configured triage roles.
