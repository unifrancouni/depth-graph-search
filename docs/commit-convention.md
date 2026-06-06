# Commit Convention

> How to write commit messages in depth-graph-search.

## Standard

This project follows [Conventional Commits v1.0.0](https://www.conventionalcommits.org/en/v1.0.0/).

## Format

```
<type>(<optional scope>): <description>

[optional body]

[optional footer(s)]
```

### Examples

```
docs(architecture): add Clean Architecture layer documentation

feat(ingestion): implement LLM entity extraction pipeline

fix(search): deduplicate nodes shared across BFS expansions

feat(search)!: change search return type from list to SearchResult

BREAKING CHANGE: search() now returns SearchResult instead of list[Node]
```

## Types

| Type | Purpose | SemVer impact |
|------|---------|---------------|
| `feat` | New feature or capability | MINOR |
| `fix` | Bug fix | PATCH |
| `docs` | Documentation only | None |
| `refactor` | Code restructuring without behavior change | None |
| `test` | Adding or updating tests | None |
| `style` | Formatting, linting, no logic change | None |
| `perf` | Performance improvement | None |
| `ci` | CI/CD pipeline changes | None |
| `build` | Build system or dependency changes | None |
| `chore` | Maintenance tasks (tooling, config) | None |

## Scopes

Scopes are optional but recommended. Use the module or area being changed:

| Scope | When to use |
|-------|-------------|
| `ingestion` | Ingestion pipeline, entity extraction |
| `search` | Search pipeline, RAG, graph traversal |
| `graph` | Graph storage, nodes, edges |
| `api` | HTTP API layer |
| `cli` | CLI interface |
| `sdk` | SDK exports and public interface |
| `docker` | Docker Compose, containerization |
| `architecture` | Architecture documentation |
| `deps` | Dependency updates |

New scopes can be introduced as the project grows. Keep them short and consistent.

## Rules

1. **Subject line**: imperative mood, lowercase, no period at the end, max 72 characters.
2. **Body** (optional): explain *what* and *why*, not *how*. Wrap at 72 characters.
3. **Footer** (optional): reference issues (`Closes #42`) or note breaking changes.
4. **Breaking changes**: append `!` after the type/scope OR add a `BREAKING CHANGE:` footer. Both are valid.
5. One logical change per commit. Do not mix unrelated changes.

## Breaking Changes

A breaking change is any modification that breaks the public SDK, API, or CLI interface for existing users.

```
feat(sdk)!: rename DepthSearch to GraphSearchEngine

BREAKING CHANGE: The main entry point class has been renamed.
Users must update their imports from DepthSearch to GraphSearchEngine.
```

Breaking changes correlate with a **MAJOR** version bump in [Semantic Versioning](https://semver.org/).

## Relationship with Changelog

Each commit type maps to a changelog category:

| Commit type | Changelog category |
|------------|-------------------|
| `feat` | Added |
| `fix` | Fixed |
| `docs` | — (not logged unless significant) |
| `refactor` | Changed |
| `perf` | Changed |
| `BREAKING CHANGE` | Changed / Removed |
| `security fix` | Security |
| `deprecation` | Deprecated |

See [Changelog Convention](changelog-convention.md) for details.

## See Also

- [Branching Strategy](branching-strategy.md)
- [Changelog Convention](changelog-convention.md)
