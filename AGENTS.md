# AGENTS.md

<!-- ds:local interview 2026-10-16 -->
A Claude-Code-style terminal over Cortex Code that scaffolds projects from the canon and keeps them reconciled

- Test: `uv run pytest -q`
- Lint: `uv run ruff check .`
- Before changing anything, read `.ds/manifest.toml`: it says which standards are in force here.

<!-- ds:inherited canon 2026-10-16 -->
## Standards

This repo follows [[adr-000]], [[architecture]], [[change-cadence]], [[cicd]], [[code-review]], [[compliance-rubric]], [[decision-logs]], [[error-handling]], [[lifecycle]], [[llm-agents]], [[normative-language]], [[operating-principles]], [[review-cadence]], [[security]], [[templates]], [[testing]].


## Skills

From skills-os:

- `/so-build-feature-interview`: Turn a feature request on an existing app into a reviewed, phased implementation plan with a decision log and external review gates.
- `/so-bug-review-interview`: Turn a bug report into a reproduced, root-caused, phased fix plan with a decision log and external review gates.
- `/so-best-practice-audit`: Audit a project or change against the best-practices guidebook and report prioritized findings.
- `/so-capture`: Capture problems, discoveries, decisions and gotchas from a coding session into structured draft records, then flush them to the team knowledge repo as a GitLab MR for review before publication.
- `/so-changes`: Record decisions (ADRs), log shipped changes (changelog), draft stakeholder communications, and capture cross-project insights.
