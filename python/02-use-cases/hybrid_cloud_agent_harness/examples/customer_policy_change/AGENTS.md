# Customer Policy Change Harness Map

This directory is the small, stable entry point for the example.

- Read `SPEC.md` for human intent and acceptance criteria.
- Read `acceptance.json` for mechanically testable invariants.
- Run the example through `engineering_harness.py`; do not edit production
  knowledge directly.
- A change is complete only when an independent critic passes every invariant
  and the finalizer emits `HARNESS_COMPLETE`.
