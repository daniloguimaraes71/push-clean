# 03 · Roadmap — Incremental Milestones

Seven milestones in strict dependency order: data → contract → AI → app shell →
checklist → notifications → hardening. Each lists its **deliverables**, its
**definition of done (DoD)**, and the **test IDs** (defined in `04-test-specifications.md`)
that gate it.

> **Gate rule (repeat of the cardinal rule):** a milestone is done only when all its
> listed tests pass. Then `git commit`, then **STOP and ask the human** before
> starting the next milestone.

A milestone checklist for the human reviewer is at the bottom of this file.

---

## M0 · Project Scaffolding & Toolchain
*No product behaviour yet — just a skeleton that runs and a green "hello" test.*

**Deliverables**
- `/backend` FastAPI app with `GET /api/v1/health`, `pyproject.toml` (or
  `requirements.txt`), `mypy` + `ruff` configured, `pytest` runnable.
- `/frontend` Expo TypeScript app (`strict: true`), Jest + RNTL configured, renders
  a placeholder screen.
- `docker-compose.yml` bringing up PostgreSQL + backend; backend connects on boot.
- `.env.example` listing every required variable (no secrets committed).
- `README` at repo root explaining how to run each side locally.

**DoD**
- `docker compose up` yields a healthy backend answering `/api/v1/health`.
- `pytest` and `npm test` both run and pass their smoke tests.

**Gating tests:** `BE-HEALTH-01`, `FE-SMOKE-01`.

---

## M1 · The Data Bedrock (backend)
*Schema, models, migrations, and user/settings CRUD. No AI, no notifications.*

**Deliverables**
- SQLAlchemy models for all five tables (architecture §4) with correct cascades.
- Alembic migration creating the schema.
- Pydantic schemas for `User` + `Settings`.
- `POST /api/v1/users`, `GET /api/v1/settings`, `PUT /api/v1/settings`.
- `X-User-Id` auth dependency.

**DoD**
- Full user + settings lifecycle works via Swagger `/docs`.
- Cascade behaviour verified.

**Gating tests:** `BE-DB-CASCADE-01`, `BE-USER-CREATE-01`, `BE-USER-EMAIL-CONFLICT-01`,
`BE-SETTINGS-GET-DEFAULTS-01`, `BE-SETTINGS-PUT-PARTIAL-01`, `BE-SETTINGS-PUT-BADKEY-01`,
`BE-AUTH-MISSING-HEADER-01`.

---

## M2 · The LLM Scheduling Engine + Optional Vision (backend)
*The one-time, text-only scheduling call, plus an optional image→text vision assist.*

**Deliverables**
- `LLMClient` service targeting OpenRouter `deepseek/deepseek-v4-flash:free`,
  configured by env var, **text-only payload**.
- A robust **JSON extractor** that recovers a valid `HouseStructurePayload` from a
  verbose/prose-wrapped/code-fenced model reply, or raises a typed error.
- `VisionExtractor` interface with **two implementations**:
  - `StubVisionExtractor` (default) — raises `VisionDisabledError`.
  - `OpenRouterVisionExtractor` — real multimodal call to a configurable
    `VISION_MODEL`, sending the image as a base64 `image_url` content part and
    returning a plain-text home description.
  - A factory picks the implementation from config (`VISION_ENABLED` + `VISION_MODEL`).
- `POST /api/v1/homes/onboard` performing the full parse-and-persist pipeline (text).
- `POST /api/v1/homes/describe-from-image` (guarded: `404 vision_disabled` when the
  stub is active; image→text via the real extractor when enabled).
- `GET /api/v1/capabilities` reflecting whether vision is active.

**DoD**
- Mocked scheduling responses (clean JSON, fenced JSON, JSON-with-preamble) all parse
  and persist correctly; malformed/empty responses yield `502
  schedule_generation_failed`.
- With vision disabled (default): `describe-from-image` → `404 vision_disabled`,
  `capabilities` reports `vision_onboarding: false`.
- With vision enabled (mocked vision model): `describe-from-image` returns
  `description_text`; the image is sent to the **vision** model only, never the
  scheduling model.
- **No live network call in tests.**

**Gating tests:** `BE-LLM-EXTRACT-CLEAN-01`, `BE-LLM-EXTRACT-FENCED-01`,
`BE-LLM-EXTRACT-PREAMBLE-01`, `BE-LLM-EXTRACT-INVALID-01`, `BE-LLM-NO-IMAGE-01`,
`BE-ONBOARD-PERSIST-01`, `BE-ONBOARD-BADLLM-502-01`, `BE-VISION-STUB-DISABLED-01`,
`BE-VISION-CAPABILITIES-01`, `BE-VISION-DESCRIBE-DISABLED-404-01`,
`BE-VISION-DESCRIBE-ENABLED-01`, `BE-VISION-IMAGE-NOT-TO-SCHEDULER-01`.

---

## M3 · The Native Shell & Onboarding (frontend)
*The Expo app: navigation, the guided home-description form, and the onboard call.*

**Deliverables**
- React Navigation skeleton (onboarding stack → main tabs).
- Typed API client (`/frontend/src/api`) generated from / aligned to the contract.
- Guided onboarding form: name, room builder (room name + floor type rows),
  household size, pets, free-text notes — assembled into `description_text`.
- Zustand store for onboarding state. Submit calls `POST /homes/onboard`.
- Loading + error states for the call.
- **Optional vision branch (capability-gated):** on mount, call `GET /capabilities`.
  If `vision_onboarding` is true, show a "Scan a blueprint or photo" button
  (`expo-image-picker`) that uploads to `POST /homes/describe-from-image` and
  pre-fills the editable notes/form with the returned `description_text` for the user
  to confirm before generating. If false, the button is **not rendered** and the flow
  is form-only. Either way, onboarding still submits text to `POST /homes/onboard`.

**DoD**
- On a simulator, filling the form and submitting hits the M2 backend and lands the
  user on the (empty) dashboard.
- The submit button is disabled until the form is minimally valid (≥1 room).
- When `capabilities.vision_onboarding` is false, no image-upload UI appears; when
  true, the scan button appears and pre-fills the description on success.

**Gating tests:** `FE-ONBOARD-VALIDATION-01`, `FE-ONBOARD-ROOMBUILDER-01`,
`FE-ONBOARD-SUBMIT-PAYLOAD-01`, `FE-API-ERROR-SURFACE-01`,
`FE-ONBOARD-VISION-HIDDEN-01`, `FE-ONBOARD-VISION-PREFILL-01`.

---

## M4 · The Daily Checklist (full stack)
*The deterministic scheduler + the checklist UI with date navigation.*

**Deliverables (backend)**
- Deterministic due-task logic (architecture §5) + intensity cap.
- `GET /api/v1/schedule/daily` (materialises completions idempotently) and
  `POST /api/v1/schedule/complete`.

**Deliverables (frontend)**
- Dashboard rendering tasks grouped by room, with a horizontal **date ribbon**
  (date-based pagination — no infinite scroll, no page numbers; see `05-ui-ux-spec.md`).
- Tap-to-toggle a task: optimistic UI update + persisted via the complete endpoint.
- Pull-to-refresh re-fetches the day.

**DoD**
- Due logic matches the spec across the scenarios in the tests (overdue ordering,
  cap trimming, idempotent materialisation).
- Toggling persists and survives a refresh.

**Gating tests:** `BE-SCHED-DUE-RULE-01`, `BE-SCHED-ORDERING-01`, `BE-SCHED-CAP-01`,
`BE-SCHED-MATERIALISE-IDEMPOTENT-01`, `BE-COMPLETE-UPDATES-LASTDONE-01`,
`BE-COMPLETE-WRONG-USER-404-01`, `FE-CHECKLIST-RENDER-01`,
`FE-CHECKLIST-TOGGLE-01`, `FE-CHECKLIST-DATE-NAV-01`.

---

## M5 · Notifications & The Chronos Engine (full stack)
*Push token capture + the twice-daily scheduled job.*

**Deliverables (frontend)**
- Request notification permission on first dashboard load; obtain the Expo push
  token; register it via `POST /notifications/register`.
- Settings screen wired to `GET/PUT /settings` (toggles + time pickers + intensity).

**Deliverables (backend)**
- `POST /notifications/register` (validates token format).
- APScheduler job that, each minute, finds users whose local morning/evening time
  has arrived, aggregates **incomplete due tasks**, and sends via a `Notifier`
  service (Expo Push API), which is **mocked in tests**.
- Evening nudge only fires if the user has incomplete tasks.

**DoD**
- Forcing a scheduled run with a frozen clock produces correctly-targeted payloads
  containing only incomplete due tasks; the Notifier is invoked with the right token.
- Evening nudge is suppressed when nothing is outstanding.

**Gating tests:** `FE-PUSH-TOKEN-CAPTURE-01`, `FE-SETTINGS-SCREEN-01`,
`BE-PUSH-REGISTER-VALIDATION-01`, `BE-CRON-PAYLOAD-INCOMPLETE-ONLY-01`,
`BE-CRON-TIMEZONE-TARGETING-01`, `BE-CRON-EVENING-SUPPRESSED-01`.

---

## M6 · Hardening, E2E & Developer Experience
*Make it robust and demonstrably correct end to end.*

**Deliverables**
- One backend integration test exercising the full happy path: create user →
  onboard (mocked LLM) → fetch daily → complete a task → fetch again.
- One frontend integration test: onboarding → dashboard render → toggle (mocked API).
- Centralised error handling + structured logging on the backend.
- Coverage thresholds enforced: backend ≥85% on `services/` and `api/`; frontend
  ≥80% on stores and screens.
- `README` updated with run/test instructions; `.env.example` complete.

**DoD**
- Both integration tests pass; coverage gates met; `mypy` + `ruff` + `tsc` clean.

**Gating tests:** `BE-E2E-HAPPYPATH-01`, `FE-E2E-ONBOARD-TO-TOGGLE-01`, plus the
coverage gate check.

---

## Human reviewer checklist

| Milestone | What to eyeball | Tests green? | Approved to proceed? |
|-----------|-----------------|:------------:|:--------------------:|
| M0 Scaffolding | `docker compose up` healthy; both test runners run | ☐ | ☐ |
| M1 Data Bedrock | CRUD via `/docs`; cascade delete leaves no orphans | ☐ | ☐ |
| M2 LLM Engine | Onboard persists from mocked replies; no image path | ☐ | ☐ |
| M3 Native Shell | Form → onboard → empty dashboard on simulator | ☐ | ☐ |
| M4 Checklist | Correct due tasks; toggle persists; date ribbon works | ☐ | ☐ |
| M5 Notifications | Forced cron sends correct payloads; evening suppression | ☐ | ☐ |
| M6 Hardening | E2E green; coverage + typing gates met | ☐ | ☐ |
