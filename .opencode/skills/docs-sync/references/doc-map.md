# Document Map — depth-graph-search

> Dependency graph and content scope for each document. Used by `docs-sync` to trace which docs need updating when changes are made.

## Document Graph

```
CHANGELOG.md (root — always updated)
│
docs/
├── architecture/
│   ├── overview.md ← entry point, references all architecture/* docs
│   ├── layers.md ← referenced by overview, ports-and-adapters, strategies
│   ├── ports-and-adapters.md ← referenced by strategies, flows/*, requirements/functional
│   ├── strategies.md ← referenced by ports-and-adapters, flows/search, requirements/functional
│   └── decisions/
│       └── ADR-001-postgresql-age.md ← referenced by overview
│
├── requirements/
│   ├── functional.md ← referenced by flows/*, architecture/overview
│   └── non-functional.md ← referenced by functional
│
├── flows/
│   ├── ingestion.md ← references functional FR-01/FR-02/FR-10, ports-and-adapters
│   └── search.md ← references functional FR-02–FR-05, strategies, ports-and-adapters
│
├── changelog-convention.md ← references architecture/overview, requirements/functional
├── branching-strategy.md ← references commit-convention, changelog-convention
└── commit-convention.md ← references branching-strategy, changelog-convention
```

## Change-to-Document Mapping

| What changed | Documents to update |
|-------------|-------------------|
| New domain entity (Node, Edge, etc.) | `layers.md`, `ports-and-adapters.md` |
| New port / interface | `ports-and-adapters.md`, `layers.md` |
| New adapter | `ports-and-adapters.md`, `layers.md` |
| New strategy level | `strategies.md`, `ports-and-adapters.md` (new port) |
| New strategy implementation | `strategies.md` |
| New functional requirement | `functional.md`, possibly `flows/*.md` |
| New non-functional requirement | `non-functional.md` |
| New ingestion pipeline step | `flows/ingestion.md`, `functional.md`, possibly `strategies.md` |
| New search pipeline step | `flows/search.md`, `functional.md`, possibly `strategies.md` |
| New architectural decision | `decisions/ADR-NNN-*.md`, `overview.md` |
| New delivery surface (SDK/API/CLI change) | `layers.md`, `functional.md` |
| New LLM provider | `strategies.md`, `ports-and-adapters.md` |
| Docker/infra change | `functional.md` (FR-09) |
| Any change | `CHANGELOG.md` |

## Content Scope Per Document

| Document | Owns | Does NOT own |
|----------|------|-------------|
| `overview.md` | System boundary, layer diagram, dependency rule, v0.1 scope | Detailed interfaces, algorithms |
| `layers.md` | Layer→package mapping, domain entities, adapter/delivery listing | Interface signatures, strategy details |
| `ports-and-adapters.md` | Port method signatures, adapter mapping table, architecture rationale | Strategy algorithms, flow sequences |
| `strategies.md` | Strategy hierarchy, level descriptions, extension guide, pipeline-as-strategy | Port signatures (→ ports-and-adapters), runtime sequences (→ flows) |
| `ADR-*` | Decision context, alternatives, consequences | Implementation details |
| `functional.md` | FR-ID, description, input/output, process summary | Runtime sequences (→ flows), architecture details (→ architecture/) |
| `non-functional.md` | Quality attributes, constraints, v0.1 honesty | Functional behavior |
| `ingestion.md` | Ingestion sequence diagram, metadata handling, error paths, entity resolution | Port definitions, strategy details |
| `search.md` | Search sequence diagram, parameters, edge cases, output format | Port definitions, strategy details |
