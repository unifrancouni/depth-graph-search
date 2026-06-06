# Skill Registry — depth-graph-search

Generated: 2026-06-05
Project: depth-graph-search
Source: ~/.config/opencode/skills/

---

## Non-SDD Skills (User-Level)

### branch-pr
**Trigger**: Creating, opening, or preparing PRs for review.
**Path**: `~/.config/opencode/skills/branch-pr/SKILL.md`
**Compact Rules**:
- Every PR MUST link an approved issue — no exceptions.
- Every PR MUST have exactly one `type:*` label.
- Automated checks must pass before merge.
- Blank PRs without issue linkage will be blocked by GitHub Actions.

---

### chained-pr
**Trigger**: PRs over 400 lines, stacked PRs, review slices.
**Path**: `~/.config/opencode/skills/chained-pr/SKILL.md`
**Compact Rules**:
- Split PRs over 400 changed lines unless maintainer accepts `size:exception`.
- Keep each PR reviewable in ≤60 minutes.
- One deliverable work unit per PR; keep tests/docs with the unit they verify.
- Every child PR must include a dependency diagram marking current PR with `📍`.
- Do not mix chain strategies after the user chooses one.

---

### cognitive-doc-design
**Trigger**: Writing guides, READMEs, RFCs, onboarding, architecture, or review-facing docs.
**Path**: `~/.config/opencode/skills/cognitive-doc-design/SKILL.md`
**Compact Rules**:
- Lead with the answer: decision/action first, context after.
- Progressive disclosure: happy path first, then details and edge cases.
- Group related info into small sections; keep flat lists short.
- Use tables, checklists, examples over prose that must be remembered.
- Design docs so reviewers can verify intent without reconstructing the full story.

---

### comment-writer
**Trigger**: PR feedback, issue replies, reviews, Slack messages, or GitHub comments.
**Path**: `~/.config/opencode/skills/comment-writer/SKILL.md`
**Compact Rules**:
- Start with the actionable point — no preamble recap.
- Sound like a thoughtful teammate, not a corporate bot.
- Prefer 1–3 short paragraphs or a tight bullet list.
- Always give the technical reason when asking for a change.
- Match thread language; in Spanish use Rioplatense voseo.

---

### go-testing
**Trigger**: Go tests, go test coverage, Bubbletea teatest, golden files.
**Path**: `~/.config/opencode/skills/go-testing/SKILL.md`
**Compact Rules**:
- Prefer table-driven tests; use `t.Run(tt.name, ...)`.
- Test behavior and state transitions, not implementation trivia.
- Use `t.TempDir()` for filesystem tests; never use a real home directory.
- Keep integration tests skippable with `testing.Short()`.
- Golden files must be deterministic; update only via `-update` path.
- *Note: Go-specific. Not applicable to this Python project.*

---

### issue-creation
**Trigger**: Creating GitHub issues, bug reports, or feature requests.
**Path**: `~/.config/opencode/skills/issue-creation/SKILL.md`
**Compact Rules**:
- Blank issues are disabled — MUST use a template (bug report or feature request).
- Every issue gets `status:needs-review` automatically on creation.
- A maintainer MUST add `status:approved` before any PR can be opened.
- Questions go to Discussions, not issues.

---

### judgment-day
**Trigger**: judgment day, dual review, adversarial review, juzgar.
**Path**: `~/.config/opencode/skills/judgment-day/SKILL.md`
**Compact Rules**:
- Launch two blind judges in parallel; never review the code yourself first.
- Wait for both judges before synthesis.
- Classify `WARNING (real)` only if normal use can trigger it; else downgrade to INFO.
- Ask before fixing Round 1 confirmed issues.
- Re-launch both judges after any fix agent runs, before commit/push/done.
- Terminal states: `JUDGMENT: APPROVED` or `JUDGMENT: ESCALATED` only.

---

### skill-creator
**Trigger**: New skills, agent instructions, documenting AI usage patterns.
**Path**: `~/.config/opencode/skills/skill-creator/SKILL.md`
**Compact Rules**:
- A skill is a runtime instruction contract for LLMs, not human documentation.
- Do not add `Keywords` section; preserve trigger words in `description`.
- Keep skill body concise: target 180–450 tokens, hard max 1000.
- Required structure: frontmatter, Activation Contract, Hard Rules, Decision Gates, Execution Steps, Output Contract, References.

---

### work-unit-commits
**Trigger**: Implementation, commit splitting, chained PRs, keeping tests and docs with code.
**Path**: `~/.config/opencode/skills/work-unit-commits/SKILL.md`
**Compact Rules**:
- A commit represents a deliverable behavior, fix, migration, or docs unit.
- Do not commit by file type (e.g., models, then services, then tests).
- Tests belong in the same commit as the behavior they verify.
- Docs belong with the feature or workflow they explain.
- A reviewer should understand why each commit exists from its diff and message.

---

## SDD Skills (Orchestrator-Managed)

| Skill | Trigger |
|-------|---------|
| sdd-init | `sdd init`, initialize SDD context |
| sdd-explore | Exploration or requirement clarification |
| sdd-propose | Create change proposal |
| sdd-spec | Write specifications |
| sdd-design | Create technical design |
| sdd-tasks | Break change into implementation tasks |
| sdd-apply | Implement tasks from specs and design |
| sdd-verify | Execute tests, prove implementation matches specs |
| sdd-archive | Archive completed change, sync delta specs |

---

## Project Skills

None detected. (Empty project — no `.claude/skills/`, `.agent/skills/`, or `skills/` directories found.)

---

## Convention Files

| File | Status |
|------|--------|
| `AGENTS.md` | Not found (project level) |
| `CLAUDE.md` | Not found |
| `.cursorrules` | Not found |
| `README.md` | Present — describes project intent |
