# AGENTS.md

Rules for any agent working in this repository.

1. Inspect before changing. Read PROJECT-CONTEXT.md first.
2. Label every claim: VERIFIED, OBSERVED, MEASURED, INFERRED, NOT TESTED or NOT VERIFIED.
3. Never fake results. If something cannot run, record it as NOT VERIFIED.
4. Install tools only under `.tools/` inside this folder.
5. Never print, copy or commit secrets. `.env` and the external key file are never read into logs or docs.
6. Never use the em dash character in any file.
7. Never push or deploy without explicit owner approval.
8. Keep SQL parameterized. Keep the API response envelope `{success, data, metadata, errors}`.
9. Run `scripts/orbit.ps1 test` before committing. Update PROJECT-CONTEXT.md when the state changes.
10. `forblog.md` is private and gitignored. Never commit it.
