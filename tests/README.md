# Test suite

From the project root, using the environment from `requirements.txt`:

```sh
python -m unittest discover -s tests -t . -p 'test_*.py' -v
```

No test requires a graphical display. The adapter subprocess tests inject a profile selection; unit tests use fake Tk objects. A passing local suite does not certify Windows/DBeaver behavior.

- `unit/`: planner, spans, source-map coordinates, list edits, procedural grammar and Tk event bindings.
- `contract/`: exact outputs, CLI/adapter transport, profiles, diagnostics, CP01–CP05 and procedural rollback/runtime integration.
- `regression/`: individual SQL layout families and previously observed defects, including procedural DML indentation.
- `helpers/fixtures.py`: synthetic procedures and AST doubles; no tests or runtime singleton caches.
- `helpers/assertions.py`: exact protected-region comparison (kind, count, order, content).
- `helpers/runners.py`: headless adapter subprocess command. Test-specific CLI calls remain local where their encoding/environment differs.
- `fixtures/`: existing golden data, shared by exact-output and focused regression checks. These Python data modules preserve the original SQL strings.
- `manual/`: Windows/DBeaver acceptance checklist; separate from automated results.

Do not import test modules to obtain data. Put genuinely shared fixtures in helpers or fixtures; keep one-off SQL adjacent to its assertions. Historical B-stage class names retain provenance, while modules describe behavior. Avoid sharing mutable linters or combining distinct encoding, transport, diagnostic and rollback scenarios for speed.

Golden updates need separate authorization. Keep negative validator/planner tests, repeated-pass diagnostics and independent profile/byte-preservation cases. Do not add private SQL or diagnostic logs to fixtures.

B10.3d migration, duplicate proof and all 358 old→new method mappings: [report](../docs/archive/B103D_REPORT.md).
