# Manual Windows / DBeaver acceptance

These checks require the actual Windows VDI and DBeaver. They are **not confirmed by the headless unittest suite**. Installation commands and normative transport requirements remain in [DBEAVER_WINDOWS_SETUP](../../docs/DBEAVER_WINDOWS_SETUP.md#ручная-приёмка-windows-vdi).

Use synthetic SQL only; record environment/version and pass/fail, never corporate queries or literals.

1. Invoke Ctrl+Shift+F, then `1` and `2`: both profiles produce the same supported output, with keyboard focus usable.
2. Repeat formatting: identical SQL. Esc and window close: original bytes retained.
3. Exercise Unicode paths (including spaces), Cyrillic SQL comments, BOM, LF/CRLF/CR and mixed endings, multiline protected content.
4. Check a supported procedure with multiline IN/NOT IN and consecutive INSERT SELECT statements; confirm a second pass does not add indentation.
5. Exercise invalid SQL and unsupported named windows; DBeaver must receive original SQL, never diagnostic text.
6. Check log permissions, read/write failure handling, offline dependencies, configured executable/cwd and timeout. Use only a disposable file for failure simulation.
7. Record focus/timing and any existing derived-table JOIN layout issues separately; test-suite cleanup does not fix those behaviors.

Automated counterparts live in `tests/contract/test_adapter*.py`, `test_procedure_transport.py`, `test_source_transport.py`, `test_diagnostics.py`, and `tests/regression/test_procedure_dml_indentation.py`.
