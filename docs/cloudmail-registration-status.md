# CloudMail Registration Status

## Current Result

CloudMail-based OpenAI registration is now working in both deployment modes that were tested:

- VPS mode: the running `chatgpt2api-warp` container uses CloudMail and completed a real `total=5, threads=1` registration batch.
- Local mode: the local API service completed a real registration using the local OpenAI proxy while leaving CloudMail direct.

The latest VPS batch finished with:

- Total: 5
- Threads: 1
- Success: 5
- Fail: 0
- Success rate: 100%
- Average time: 18.8 seconds/account
- Active VPS register config: `total=5`, `threads=1`, `proxy=""`

## Root Cause

The previous `cloudmail_gen` provider only generated an email address string. It did not create/register that address in CloudMail before OpenAI sent the OTP.

For already-existing CloudMail addresses this could work, which made manual tests look healthy. Fresh random addresses used by batch registration often had no CloudMail account state, so CloudMail returned raw count `0` and the registration timed out while waiting for the OTP.

## Implemented Fixes

- `cloudmail_gen` now logs in to CloudMail via `/api/login` and calls `/api/account/add` before returning a generated mailbox.
- Duplicate CloudMail addresses (`code=501`, already registered) are treated as usable instead of fatal.
- CloudMail recipient matching now checks recipient fields such as `toEmail`, `toName`, and `emailId`, and does not treat sender fields as recipients.
- CloudMail wait timeouts include diagnostic counts and recent message metadata.
- OpenAI registration flow records useful debug snippets for `user/register`, `email-otp/send`, and `email-otp/resend`.
- `/api/register/start` accepts an optional config body and applies it before launching, so UI/API starts use the latest `total`, `threads`, proxy, and mail settings.
- The frontend now sends the current register config when starting registration.
- The OpenAI register proxy no longer automatically forces CloudMail traffic through the same proxy. CloudMail is direct by default unless `mail.proxy` or provider-level `proxy` is explicitly set.

## Local And VPS Config

Sensitive runtime config is stored only under ignored `data/` paths and is not committed.

Local files created:

- `data/register.json`: active local config
- `data/register.local.json`: local preset with `proxy=http://127.0.0.1:10808`
- `data/register.vps.json`: VPS preset with `proxy=""`

VPS files created inside the container:

- `/app/data/register.json`: active VPS config
- `/app/data/register.local.json`: local preset copy
- `/app/data/register.vps.json`: VPS preset copy

## Verification Commands

Relevant checks run successfully:

```bash
uv run python -m unittest test.test_register_proxy_runtime
uv run python -m py_compile api/register.py services/register/mail_provider.py services/register/openai_register.py scripts/test_cloudmail.py scripts/test_openai_delivery.py
```

VPS production-style verification:

```bash
POST /api/register/start
body: {"total":5,"threads":1,"mode":"total"}
```

Observed VPS result:

```json
{"enabled":false,"total":5,"threads":1,"proxy":"","success":5,"fail":0,"done":5,"success_rate":100.0,"avg_seconds":18.8,"current_available":10,"current_quota":244}
```

## Diagnostic Scripts

Two helper scripts were added:

- `scripts/test_cloudmail.py`: checks CloudMail token generation, recent messages, recipient matching, and raw inbox visibility.
- `scripts/test_openai_delivery.py`: runs a one-shot OpenAI delivery or registration probe using the production registration flow.

Both scripts can read `data/register.json`, or accept CloudMail parameters via CLI flags for temporary environments.

## Operational Notes

- Keep batch sizes modest while observing domain and IP reputation. The verified baseline is `total=5, threads=1`.
- For local runs, set the OpenAI register proxy to the local browser/system proxy if direct auth requests return `unsupported_country_region_territory`.
- Do not commit files under `data/`; they contain runtime credentials, account state, and generated accounts.
- If CloudMail OTP timeouts return `cloudmail_raw=0`, first verify that `/api/account/add` is still succeeding for fresh addresses.
