# Branching Strategy

> GitFlow branching model for depth-graph-search.

## Standard

This project follows [GitFlow](https://nvie.com/posts/a-successful-git-branching-model/) as its branching strategy.

## Branch Types

| Branch | Purpose | Created from | Merges into | Naming |
|--------|---------|-------------|-------------|--------|
| `main` | Production-ready releases. Every commit is a tagged version. | — | — | `main` |
| `develop` | Integration branch. Latest delivered features for the next release. | `main` | — | `develop` |
| `feature/*` | New features or capabilities. | `develop` | `develop` | `feature/short-description` |
| `release/*` | Prepare a new release. Bug fixes, docs, version bumps only. | `develop` | `main` + `develop` | `release/X.Y.Z` |
| `hotfix/*` | Critical production fixes. | `main` | `main` + `develop` | `hotfix/short-description` |

## Flow

```
main ─────●─────────────────────●─────────────── (tagged releases)
           \                   /
develop ────●───●───●───●───●─── (integration)
                \       /
feature/foo ─────●───●─── (feature work)
```

### Feature Development

1. Create branch from `develop`: `git checkout -b feature/ingestion-pipeline develop`
2. Work on the feature with [Conventional Commits](commit-convention.md).
3. Open a PR targeting `develop`.
4. After review and merge, delete the feature branch.

### Releasing

1. Create branch from `develop`: `git checkout -b release/0.1.0 develop`
2. Only bug fixes, documentation, and version bumps allowed on this branch.
3. When ready, merge into `main` AND back into `develop`.
4. Tag `main` with the version: `git tag -a v0.1.0 -m "v0.1.0"`

### Hotfixes

1. Create branch from `main`: `git checkout -b hotfix/fix-critical-bug main`
2. Fix the issue.
3. Merge into `main` AND back into `develop`.
4. Tag `main` with the patch version.

## Rules

- **Never commit directly to `main` or `develop`**. All changes go through feature/release/hotfix branches.
- Feature branches must be up to date with `develop` before merging (rebase or merge `develop` in).
- Release branches freeze features — only fixes allowed.
- Hotfix branches are the only branches created from `main`.
- Delete branches after merging.

## Branch Naming Examples

```
feature/ingestion-pipeline
feature/bfs-traversal-strategy
feature/openai-provider
release/0.1.0
hotfix/fix-embedding-dimension
```

> **v0.1 scope**: During early development (`0.x`), working directly on `develop` for small changes is acceptable. GitFlow becomes strictly enforced once the project has its first stable release or multiple contributors.

## See Also

- [Commit Convention](commit-convention.md)
- [Changelog Convention](changelog-convention.md)
