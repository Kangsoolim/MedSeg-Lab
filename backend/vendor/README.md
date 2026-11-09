# Vendored course algorithms

The four top-level module copies and seven training-source copies are byte-identical to their recorded source files. `SOURCES.json` and `training/SOURCES.json` retain relative source paths and SHA-256 values; the runtime verifies source integrity. These copies cover nine distinct original module paths. No algorithm bodies were changed for Phase 3B.

The owner explicitly confirmed on 2026-11-09 that they hold open-source authorization for the course-derived code and MedSeg-Lab additions and selected MIT. The repository LICENSE applies to this authorized project code. This authorization does not grant redistribution rights to third-party dependencies, medical images, checkpoints or historical results; see docs/THIRD_PARTY_LICENSES.md.

The course directory is an optional read-only adapter resource, never an output destination. Exact vendored computational primitives are retained; the new training orchestrator does not claim to reproduce the complete historical optimization trajectory.
