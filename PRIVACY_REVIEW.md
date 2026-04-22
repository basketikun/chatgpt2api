# Privacy Review (2026-04-22)

This repository was checked for accidental personal information, custom personal data, and secret leakage.

## Scope

- Code and docs under the repository (excluding `.git` internals).
- Regex-based scan for likely secrets and PII patterns.

## Findings

1. **No hardcoded real API keys or private secrets were found in tracked source files.**
   - Matches were primarily placeholders (for example `Authorization: Bearer <auth-key>` in docs) and variable names like `access_token`.
2. **No obvious personal identity data (phone, email, ID number) was found in tracked source files.**
3. **Potential privacy risk in runtime logs:**
   - The backend logs the first 12 characters of access tokens in multiple places. Even partial token exposure may still be sensitive in shared log systems.

## Risk level

- Current repository snapshot: **Low** for committed-secret leakage.
- Operational/privacy risk: **Medium** if production logs are broadly accessible, due to partial token logging.

## Recommendations

- Replace token-prefix logging with stable anonymous IDs (hash-based short IDs), or remove token text from logs entirely.
- Keep using `config.example.json` for placeholders and avoid committing real `config.json`.
- Add CI secret scanning (e.g., gitleaks) to block future accidental commits.

## Follow-up update

- Implemented: runtime logs now use anonymized token references (`token:<sha256-prefix>`) instead of raw token prefixes.
