---
name: commit-protocol
description: "Trigger: commits, commit, hacer commits, push, subir cambios. Branch + work-unit commits + engram sync protocol."
license: Apache-2.0
metadata:
  author: gentleman-programming
  version: "1.0"
---

# Skill: commit-protocol

## Activation Contract

Load this skill when the user asks to commit, push, or prepare changes for review. This overrides ad-hoc commit behavior with a mandatory protocol.

## Hard Rules

| Rule | Requirement |
|------|-------------|
| Branch first | ALWAYS create a branch before committing. Ask the user for the branch name. |
| Work-unit commits | Each commit is a deliverable behavior with tests and docs included. Never commit by file type. |
| Engram last | After ALL feature/docs commits, run `engram sync` and commit `.engram/` as the final commit. |
| No force-push | Never force-push. Never amend published commits. |
| Conventional commits | Use `feat:`, `fix:`, `docs:`, `chore:`, `refactor:` prefixes. Match repo style from `git log --oneline -5`. |
| Do not push | Do NOT push unless the user explicitly asks. |

## Execution Steps

1. **Inspect state**: `git status`, `git diff --stat`, `git log --oneline -5`. Understand what changed.
2. **Ask branch name**: Ask the user what to name the branch. Create it from current HEAD: `git checkout -b {branch-name}`.
3. **Plan commits**: Group changes into work units. Present the plan to the user for approval.
4. **Execute commits**: Stage and commit each work unit. Verify `git diff --cached --stat` before each commit.
5. **Engram sync**: Run `engram sync`. This generates/updates files in `.engram/`.
6. **Engram commit**: Stage `.engram/` and commit: `chore: sync engram state`.
7. **Report**: Show `git log --oneline` with all new commits. Do NOT push unless asked.

## Decision Gates

| Situation | Action |
|-----------|--------|
| Single SDD archived | One branch, commits by SDD phase (code, then docs, then engram) |
| Multiple SDDs archived | One branch, one commit per SDD + one docs commit + engram last |
| Non-SDD changes | Same protocol: branch, work-unit commits, engram sync last |
| Mixed SDD + non-SDD | Group logically, engram always last |

## Output Contract

Return:
- Branch name created
- List of commits with short descriptions
- Confirmation that engram sync ran and was committed
- Whether push was done (only if user asked)
