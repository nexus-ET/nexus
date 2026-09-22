# ScanX v1 SRS — Nexus CRM (FINAL)

**Status:** FINAL v1 SRS · **Scope:** CRM Document Readiness only · **Mobile:** Phase 2  
**Canonical canvas:** `~/.cursor/projects/e-NEXUS/canvases/scanx-nexus-crm-requirements.canvas.tsx`  
**Locked:** 2026-09-14 (D1–D11)

## Product intent

Lead-scoped CRM document ingest → durable RQ parse/OCR → counsellor verify → R2 store, with a split-view under **Students → Document Readiness** (`/students/document-readiness`). Mobile bearer upload is **out of v1**.

## Hard decisions

| ID | Decision |
|----|----------|
| D1 | Mobile auth = separate client credentials (Phase 2); never share counsellor JWT |
| D2 | Worker = Redis + RQ |
| D3 | Reject password-protected PDFs in v1 |
| D4 | Free-text extract + manual Action Required verify (field packs = Could) |
| D5 | Concurrent upload cap = 10 per CRM `user_id` |
| D6 | Checklist stays parallel; ScanX does not gate FlowX in v1 |
| D7 | Retention TTL set by product/legal later |
| D8 | Generic completeness Must; country packs Could |
| D9 | R2 bucket by env (`R2_BUCKET_NAME`); key root `STUDENTS/{lead_id}/{SUBFOLDER}/…` |
| D10 | Hybrid naming: UI shows `original_filename`; R2 key = `{doc_uuid}__{document_type_id}__{safe_original_basename}{ext}` |
| D11 | Always-visible upload rules panel + counsellor messages **M1–M12** |

## Env

- `SCANX_MAX_FILE_SIZE_BYTES` (required; default 10 MB)
- `SCANX_MAX_PAGES` (required; default **10** — PDF page cap; DOCX limited by file size)
- `SCANX_R2_KEY_ROOT=STUDENTS` (optional default)
- `SCANX_OCR_ENGINE=rapid` (default) — primary image OCR; `paddle` to use PaddleOCR as primary
- `SCANX_OCR_FALLBACK=paddle` (default) — used when Rapid ImportError / runtime fail / empty / timeout
- `SCANX_OCR_BUDGET_SECONDS` (optional; default 45) — wall-clock OCR budget for Parsing
- Reuse `R2_BUCKET_NAME`, `REDIS_URL`, `EMBEDDING_*`

Parse metrics may include `ocr_engine_used` (`paddle` | `rapid`), `ocr_engine_primary`, and `ocr_fallback_reason` when image OCR ran (Paddle fallback is never silent). Native PDF/DOCX text extract is unchanged. PaddleOCR needs `paddlepaddle` on Python 3.9–3.13 — not available on 3.14 yet.

## Formats

PDF, DOCX, PNG, JPEG, TIFF. DOCX text extracted via `python-docx` in the parse job. Image / scanned-PDF pages use RapidOCR with PaddleOCR fallback.

## R2 key

```
{SCANX_R2_KEY_ROOT}/{lead_id}/{SUBFOLDER}/{doc_uuid}__{document_type_id}__{safe_original_basename}{ext}
```

### Eight SUBFOLDERS

`ACADEMICS` · `APPLICATIONS` · `DIGITAL-PRESENCE` · `NON-ACADEMICS` · `PROFESSIONAL-EXPERIENCE` · `PROFILE` · `PROJECTS-AND-RESEARCH` · `TEST-SCORES`

## Statuses (tokens + labels)

`uploading` → Uploading · `parsing` → Parsing · `action_required` → Action Required · `verified` → Verified · `red_flag` → Red Flags

Live updates via WebSocket (`scanx.document.status` / `scanx.document.progress`); poll fallback OK.

## Data

- Document row: `lead_id`, `uploader_user_id`, `source=crm`, `document_type_id`, `original_filename`, `r2_key`, `content_sha256`, `status`, `extracted_text` (UTF-8), metrics/json, timestamps
- Chunk/embedding tables for documents only — **not** taxonomy embedding tables
- Password PDFs rejected; SHA-256 stored

## UI (Must)

- Student selected before upload; document type required
- D11 rules panel + M1–M12 catalog (no raw HTTP/stacks)
- Lists show `original_filename`
- Split-view: left viewer, right fields
- Status badges use design tokens (icon + label)

## Non-goals (v1)

Mobile ingest · counsellor webhooks · taxonomy embedding reuse for OCR · hard DPI reject without metadata · admin UI for size/page caps · writing outside the eight SUBFOLDERS

## M1–M12 (summary)

| ID | Severity | Message gist |
|----|----------|--------------|
| M1 | Blocking | Select a student before uploading |
| M2 | Blocking | Choose a document type |
| M3 | Blocking | PDF, DOCX, PNG, JPEG, or TIFF |
| M4 | Blocking | File too large (max {X}) |
| M5 | Blocking | Too many pages (max {N} for PDF; DOCX by size) |
| M6 | Blocking | Password-protected PDF |
| M7 | Blocking | Corrupted / unreadable |
| M8 | Warning | Low DPI (&lt;150) |
| M9 | Blocking | Concurrent upload cap |
| M10 | Blocking | Upload didn’t complete |
| M11 | Blocking | Security / Red Flag |
| M12 | Info | Review needed (Action Required) |
