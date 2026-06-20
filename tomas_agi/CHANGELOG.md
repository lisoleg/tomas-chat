# Changelog

## [Unreleased]

### Added
- HyperIndex v2.0: DB-backed k-hop subgraph loading with OrderedDict LRU cache
- UnionFind matroid circuit detection: O(|E|·α(|V|)) complexity
- ChainDB distributed hypergraph: HyperShard + DistributedHyperIndex
- EML v2.0: n-ary hyperedge binary format
- 6 new API endpoints for hypergraph operations
- HypergraphPanel frontend: 5 tabs (overview/k-hop/matroid/distributed/export)
- create_shards.py: HyperShard generation script

### Fixed
- INSERT OR IGNORE pattern in migrate_hypergraph.py (UNIQUE constraint fix)
- matroid-unionfind API: added seeds concept resolution
- export-eml-v2 API: fixed parameter names
- Frontend TypeScript errors in AEGISPanel/TShieldPanel/TProcessorPanel
- tomas_agi package import (added __init__.py)

### Changed
- eml_dimred/__init__.py: v1.0.0 → v2.0.0, 27 exports
- README.md: updated with new features and 101M+ triples badge

---

## [v3.4] - 2026-06-15

### Added
- DIKWP five-layer mapping
- Semantic firewall
- T-Processor/T-Shield panels
- ARC-AGI-3/GAIA/SWE-bench evaluation frameworks

### Fixed
- OwnThink import UNIQUE constraint handling
- Frontend build errors

---

## [v3.0] - 2026-06-01

### Added
- "Translator + Writer" V3 hybrid architecture
- Φ-Gate semantic gating
- EML knowledge distillation
- DeepSeek LLM integration

---

## [v2.0] - 2026-05-01

### Added
- NASGA octonion algebra
- κ-Gate semantic pruning
- Hypergraph data model
- SQLite backend for knowledge storage

---

## [v1.0] - 2026-03-01

### Added
- Initial TOMAS-AGI implementation
- Basic EML knowledge graph
- LSTM-based translator
- Token bridge architecture
