---
name: docs-sync
description: "Trigger: sdd-archive completes, docs synchronization, update documentation after changes. Synchronize project docs with implemented changes."
license: Apache-2.0
metadata:
  author: gentleman-programming
  version: "1.0"
---

## Activation Contract

This skill activates **automatically after sdd-archive completes successfully**. The orchestrator MUST launch this as the final step of every SDD cycle. No SDD is complete until docs are synchronized.

Also activates manually when the user says: "sync docs", "update docs", "sincronizar docs", "actualizar documentación".

## Hard Rules

- NEVER skip a document that is affected by the change. Trace ALL cross-references.
- NEVER create new docs unless the change introduces a fundamentally new concept not covered by any existing doc.
- ALWAYS update `CHANGELOG.md` if not already updated.
- ALWAYS check cross-references in modified docs — if you change a heading, grep for anchor links to it.
- Read `references/doc-map.md` FIRST to understand the document dependency graph.

## Execution Steps

1. **Load doc map**: Read `references/doc-map.md` from this skill directory to understand which docs exist and their relationships.

2. **Identify the change**: Read the archive report from engram (`sdd/{change-name}/archive-report`) or from the orchestrator prompt to understand what was implemented.

3. **Trace affected docs**: For each implemented feature/change, walk the doc map and identify ALL documents that need updating:
   - New entity/concept → `architecture/layers.md`, `architecture/ports-and-adapters.md`
   - New strategy → `architecture/strategies.md`
   - New functional behavior → `requirements/functional.md`
   - New non-functional constraint → `requirements/non-functional.md`
   - New or changed pipeline step → `flows/ingestion.md` or `flows/search.md`
   - New architectural decision → `architecture/decisions/ADR-NNN-*.md`
   - Any change → `CHANGELOG.md`

4. **Update each affected doc**:
   - Add/modify the relevant sections
   - Preserve existing content not affected by the change
   - Maintain Mermaid diagram consistency (update diagrams if they show the changed component)
   - Add `> **v0.1 scope**` callouts where appropriate
   - Update cross-reference links if new sections are added

5. **Verify cross-references**: Grep for any broken anchor links (`#heading-slug`) across all docs after modifications.

6. **Report**: Return list of files modified, sections added/changed, and any cross-reference issues found.

## Output Contract

Return:
- List of docs modified with what changed in each
- Any new docs created (with justification)
- Cross-reference verification result (all links valid or list of broken ones)
- CHANGELOG.md update confirmation

## References

- `references/doc-map.md` — document dependency graph and content scope per file
