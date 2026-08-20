# GenBox Push Extension Proposal

**Status:** Proposed extension (not accepted, not implemented upstream)

## Purpose

This proposal offers the chatgpt2api maintainers a coherent, reviewable plan to
extend chatgpt2api so its generated images can be forwarded to a GenBox media
library over the documented GenBox Push contract. It is an integration proposal
only: it defines goal, contract, task boundaries, acceptance tests, and
compatibility notes. It does not claim that any chatgpt2api sender code already
exists, and no chatgpt2api production instance was modified to produce this
document.

## Background

GenBox is a separate project (`liwei9745/genbox`) that operates a media library
and an extension center. GenBox implements a Push receiver
(`POST /api/sync/push`) that accepts one image per request from a stable,
pre-provisioned source. The receiving edge is designed for idempotent retry and
returns an authenticated receipt. chatgpt2api generates and stores images
locally on the VPS; the user value of this extension is moving those images into
a GenBox library so VPS disk usage can be managed safely, with source retention
as the default behaviour.

The GenBox receiver contract is defined in the GenBox repository:

- `docs/INTEGRATION.md` — end-to-end responsibility and capability matrix.
- `docs/chatgpt2api-push-integration.md` — receiver contract v1 details.
- `docs/UPSTREAM-VIBE-CODING-GUIDE.md` — AI-oriented implementation guide with
  task prompts, data model, and acceptance-test matrix.

This proposal summarizes the parts a chatgpt2api maintainer needs to evaluate
the idea and to steer an implementation that follows upstream conventions. A
complete sender implementation belongs in this repository and must be reviewed,
tested, and released under normal chatgpt2api quality gates.

## Push Contract Summary (GenBox v1)

Request:

```http
POST <GENBOX_PUSH_URL>/api/sync/push
X-GenBox-Source: <stable-source-id>
X-GenBox-Key: <source-scoped-secret>
Content-Type: multipart/form-data
```

Fields:

```text
image            image bytes (default max 25 MiB)
remote_path      stable source-relative path, required
source_sha256    sender-computed SHA-256, optional; must match bytes when present
created_at       source creation time, optional
prompt           generation prompt, optional
model            model identity, optional
```

Response semantics:

- Success returns `ok=true`, `contract_version="v1"`, the GenBox-computed
  `sha256`, the committed `local_file`, and a commit eligibility field
  (`safe_to_delete_source`).
- The current v1 receiver returns `safe_to_delete_source=false` after a
  successful or idempotent committed import. A sender must treat an HTTP 2xx as
  *transfer confirmation only*; it never grants source-deletion permission by
  itself.
- Replayed requests for the same `source_id + remote_path + sha256` return
  `already-imported` without duplicating media.
- A malformed or mismatched `source_sha256` is rejected with `422` before any
  receiver state is committed.
- Pre-flight: `GET /api/sync/push/status` with the same authenticated headers
  returns the v1 contract version and the running process's maximum image byte
  limit. A sender should probe for destination compatibility and keep the
  source if the probe or Push fails.
- Sender fallback option: when no inbound network path exists, GenBox continues
  to support a "local pull" mode as a compatible alternative.

## Goal And Non-Goals

Goals:

- Forward newly generated images to a GenBox library.
- Manual forwarding of selected images, date-range batch forwarding, and
  scheduled incremental forwarding.
- Retry failed transfers without duplicates.
- Optional confirmed source cleanup, disabled by default, only after a matching
  authenticated receipt and unchanged source hash.

Non-goals (for the initial proposal):

- No sender-side media management or catalog beyond existing chatgpt2api
  capabilities.
- No changes to GenBox's receiver behaviour.
- No forwarding when the user has not configured a GenBox destination.

## Suggested Task Boundaries

Keep each change small and independently testable:

1. **Push foundation.** GenBox destination settings (base URL, stable source
   ID, masked push key, connection timeout), one shared server-side Push
   service, SHA-256 calculation and receipt validation, durable per-image
   transfer state, connection test, unit/integration tests. No UI, no
   scheduling, no deletion.
2. **Generation and Gallery UI.** Per-generation "Push to GenBox" option,
   manual single/date-range batch selection, durable progress, error reporting,
   cancellation, failed-only retry, "already imported" clarity. UI and API
   tests.
3. **Scheduler and confirmed cleanup.** Default weekly incremental schedule
   with persistent cursor, overlap handling, per-item state, worker lease;
   explicit opt-in cleanup policy (off by default, disabled in development),
   dry-run and audit summary. Only after authenticated receipt, matching SHA-256
   and `safe_to_delete_source=true` may an unchanged confirmed source be
   deleted.

The recommended PR split is `Push Foundation` → `Generation And Gallery UI` →
`Scheduler And Confirmed Cleanup`. Scheduling and deletion must not block the
basic interoperability work.

## Data Model Suggestions

Adapt names and persistence to upstream conventions:

```text
GenBoxDestination
  enabled
  base_url
  source_id
  push_key_secret_ref
  timeout_seconds
  cleanup_enabled = false

TransferItem
  source_path
  source_sha256
  status
  attempts
  receipt_sha256
  genbox_local_file
  last_error_code
  last_attempt_at
  completed_at

PushSchedule
  enabled
  schedule_expression
  start_date
  end_date
  scan_cursor
  lease_owner
  lease_expires_at
```

Store secrets through the project's protected configuration mechanism. Do not
return secret values from ordinary settings APIs or logs.

## Recommended Item States

```text
pending -> running -> succeeded
                   -> already_imported
                   -> retryable_failure -> pending
                   -> permanent_failure
pending/running -> cancelled
```

Persist state transitions before any source cleanup. A process restart must not
convert an unconfirmed item into success.

## Acceptance Test Matrix

| Scenario | Expected Result |
|---|---|
| Valid single image | One GenBox media item and matching receipt |
| Same request repeated | No duplicate media; already-imported success |
| Same path, changed bytes | New content handled by hash policy |
| Invalid Push key | No import; source retained; no secret in logs |
| Network timeout | Retryable failure; source retained |
| Invalid image | Permanent failure; source retained |
| Batch interrupted | Durable state resumes without duplicate success |
| Late file in schedule range | Later overlapping scan discovers it |
| Two scheduler workers | Lease prevents duplicate active processing |
| Cleanup disabled | Source always retained |
| Receipt hash mismatch | Source retained and error recorded |
| Confirmed cleanup enabled | Only unchanged confirmed source is deleted |

## Security And Privacy Constraints

- Do not log Push keys, administrator keys, cookies, account tokens, or full
  authorization headers.
- Validate destination URL policy against upstream deployment needs.
- Keep the GenBox Push key separate from any chatgpt2api management key.
- Do not include real deployment addresses, images, prompts, or credentials in
  tests, fixtures, screenshots, commits, or PR descriptions.
- Do not enable cleanup from a per-generation checkbox.
- Do not develop or test against an existing production container.

## Compatibility And Migration Notes

- This extension is additive: existing image generation, storage, Gallery, and
  management behaviour remains unchanged when no GenBox destination is
  configured.
- The Ping/status probe lets an older or newer GenBox receiver self-describe its
  contract version and limits, so the sender can fail closed on incompatible
  destinations.
- Forwarding is best-effort and durable: transient receiver unavailability
  leaves the source untouched and retry state recorded.
- No media stored under a GenBox destination is modified or deleted by this
  extension except under the confirmed-cleanup rule stated above.

## How To Proceed

1. Read the GenBox contract documents linked in Background.
2. Decide whether to accept this extension and which task boundary to start
   with (recommended: Push Foundation).
3. Implement against an isolated development clone, not production.
4. Follow the upstream PR split and acceptance-test matrix above.
5. Present changes per upstream review and release rules.

This document contains only design intent and generic examples. It introduces
no configuration, credentials, deployment addresses, or environment-specific
values.