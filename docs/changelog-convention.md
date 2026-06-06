# Changelog Convention

> How to read and contribute to the project changelog.

## Standard

This project follows [Keep a Changelog v1.1.0](https://keepachangelog.com/en/1.1.0/) combined with [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

The changelog lives at the repository root: [`CHANGELOG.md`](../CHANGELOG.md).

## Guiding Principles

1. **Changelogs are for humans**, not machines.
2. There should be an entry for every single version.
3. The same types of changes should be grouped.
4. Versions and sections should be linkable.
5. The latest version comes first.
6. The release date of each version is displayed.

## Change Categories

Every entry must be placed under one of these categories:

| Category | When to use |
|----------|-------------|
| `Added` | New features or capabilities |
| `Changed` | Modifications to existing functionality |
| `Deprecated` | Features that will be removed in a future version |
| `Removed` | Features that have been removed |
| `Fixed` | Bug fixes |
| `Security` | Vulnerability patches |

## Format

```markdown
## [Unreleased]

### Added

- Short description of what was added.

## [0.1.0] - 2026-06-15

### Added

- Initial implementation of ingestion pipeline.
- BM25 + embedding hybrid search strategy.
```

### Rules

- **Unreleased section** always stays at the top. All in-progress changes go here until a release is cut.
- When releasing, move entries from `[Unreleased]` into a new version section with the release date.
- Each entry is a single bullet point. Start with a verb in past tense or a noun phrase.
- Keep entries concise — one line per change. Link to issues or PRs when relevant.
- Do **not** log internal refactors or whitespace changes unless they affect public behavior.
- Group entries by category. Omit empty categories.

## Versioning

Following [Semantic Versioning](https://semver.org/spec/v2.0.0.html):

| Version bump | When |
|-------------|------|
| **MAJOR** (`X.0.0`) | Breaking changes to the public SDK/API/CLI interface |
| **MINOR** (`0.X.0`) | New features, new strategies, new adapters — backward compatible |
| **PATCH** (`0.0.X`) | Bug fixes, documentation corrections — backward compatible |

> **v0.1 scope**: Until the first stable release (`1.0.0`), the public API is not guaranteed to be stable. Minor versions may include breaking changes during the `0.x` series.

## See Also

- [Architecture Overview](architecture/overview.md)
- [Functional Requirements](requirements/functional.md)
- [Branching Strategy](branching-strategy.md)
- [Commit Convention](commit-convention.md)
