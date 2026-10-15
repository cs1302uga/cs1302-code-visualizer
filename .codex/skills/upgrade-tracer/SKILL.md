---
name: upgrade-tracer
description: Upgrade a project's tracer to its latest stable release, bump the application patch version, and create or update a PR with full coverage and iterative balanced-code-review and CodeQL remediation. Use for the complete tracer upgrade and review workflow.
---

# Upgrade Tracer

Deliver a verified tracer upgrade PR, close its coverage gap, and resolve review findings with an auditable comment trail. Finish with an interactive stress test of the result.

## Scope and prerequisites

Invoking this workflow authorizes task-related edits, tests, commits, pushes, PR creation or updates, review comments, replies, and resolution of verified findings. It does not authorize merging, publishing a release, or deployment. A request to create or edit this skill is not a request to execute it.

Read repository instructions and discover its tracer integration, versioning conventions, test/coverage commands, and PR tooling. Preserve unrelated work. Identify the target branch and existing task PR before creating either, so reruns resume the same work.

Locate the installed `balanced-code-review` and `codeql` skills through the skill catalog and read each before its review phase. Use their actual instructions rather than treating slash names as shell commands. If a required skill, tool, credential, or source is unavailable, complete independent work and report the specific blocker; do not substitute another scanner and call CodeQL complete.

## 1. Establish the upgrade

- Identify the tracer's upstream project and current pinned version. Verify the latest stable, non-prerelease version against official release metadata at execution time; record its URL and the old/new versions. Read the intervening release notes for integration changes.
- Upgrade to that release using the repository's dependency or vendoring mechanism, including relevant lockfiles, artifact hashes, generated integration files, and compatibility changes. If the latest release cannot work with the project, explain the concrete incompatibility instead of silently choosing an older release.
- Bump the consuming application's patch version once, using its established version source and synchronization mechanism. Keep the upstream tracer version distinct from the application version. Preserve an already-applied bump when resuming or making review fixes. Ask only if the intended versioned artifact is genuinely ambiguous.

Completion: the new release is pinned reproducibly, related version metadata agrees, and the upgrade's compatibility implications are understood.

## 2. Close coverage and verify behavior

Run the repository's real coverage command and examine uncovered lines and branches. Default to the existing project coverage scope, not merely changed lines. If no scope exists, define and report coverage of first-party application code; distinguish upstream vendored code explicitly.

Reach 100% for the configured coverage metrics with meaningful behavior tests. Exercise tracer integration, output compatibility, error paths, and any migration changes. Do not reduce the measured scope, weaken thresholds, or add exclusions merely to manufacture 100%. Report an unachievable target as unfinished work with evidence.

Run required tests, build, lint, and other repository checks. Record commands, results, and exact coverage measurements, including scope. A rounded display of 100% is insufficient if the report still contains uncovered items.

Completion: the coverage target and required checks pass for the proposed change.

## 3. Commit and open the PR

Commit and push task changes, then create or update the task PR against the verified base. Follow the host's PR registration requirements when available.

Describe the upgrade's purpose, tracer and application version changes, compatibility work, coverage improvements, validation evidence, and any remaining limitations. Keep the PR open for review; unresolved required checks or blockers must be visible.

## 4. Review, triage, fix, and repeat

Use this loop until a complete review round on the final commit has no findings needing resolution:

1. Record the PR base and head SHAs and inspect existing reviews and unresolved threads. Run `balanced-code-review` on the full PR change set. Run `codeql` on the current source with its database-quality, modeling, and query-suite checks. Build fresh databases for changed source; reuse only when extraction is verified to represent the exact source under review. Report unsupported languages and analysis gaps explicitly.
2. Publish a PR review with findings from both reviews, identifying the reviewed SHA and coverage/analysis limits. Prefer one inline review thread per distinct finding, with location, severity, evidence, and proposed correction. Use a clearly identified review-body finding when the hosting API cannot attach it inline. If there are no findings, publish a concise review summary with the verification evidence. Reuse existing threads for repeated findings rather than creating duplicates.
3. Track every finding by source, comment/thread URL or ID, disposition, evidence, and fix commit where applicable. Include actionable findings from existing PR comments. Investigate each finding against actual behavior; uncertain findings remain open until evidence supports a decision.
4. For a false positive, reply to its related comment stating that classification and the concrete reason, citing code, a test, or analysis evidence. Do not classify a real issue as a false positive merely because it is inconvenient or pre-existing. A real finding that cannot be resolved remains an explicit blocker unless the user changes scope.
5. For a valid finding, implement the correction and an appropriate regression test, rerun affected checks and coverage, then commit and push the fix. Reply in the related thread describing the fix and linking its commit and verification. Mark the thread resolved only after this verification and reply succeed. If the platform lacks thread resolution or denies permission, retain that limitation visibly rather than claiming resolution.
6. Update the PR description to reflect the committed changes, current validation evidence, and material review decisions. Recheck the remote head. If code changed, repeat coverage verification and both reviews against the new head, including inspection for regressions introduced by fixes.

Keep replies and review submissions idempotent: inspect existing remote state before retrying a failed publication. Never resolve someone else's unrelated thread or dismiss a review wholesale to reach a clean count.

Continue while fixes make progress. If the same unresolved condition persists through three consecutive rounds without new evidence or a viable fix, stop the loop and report the blocker and needed decision. Failed scans, unavailable tooling, incomplete coverage, and unresolved valid findings never count as a clean review.

## 5. Finalize the PR and grill the result

Confirm that the remote PR head matches the tested and reviewed commit, coverage remains 100% in the stated scope, required checks pass, and all findings have evidence-backed dispositions and the required replies. Incorporate the final commits and material PR discussion into the PR description. Summarize the PR link, versions, coverage, review outcomes, and any unfinished work honestly.

Then perform the requested `/grill-me` interaction using the available `grilling` or GrillMe skill. If neither is installed, use this self-contained fallback: stress-test the upgrade's remaining assumptions and tradeoffs with the user, asking one decision question at a time, giving a recommended answer, and waiting for feedback. Resolve discoverable facts through repository evidence instead of asking the user. Keep this interview distinct from automated review; do not invent user agreement or silently omit it.

Await shared understanding before implementing changes proposed during the interview. If accepted changes affect code, return to verification and the review loop, and refresh the PR description again. Leave merging and release publication to a separate instruction.
