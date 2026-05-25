# 01 · Architecture Specification

This document defines the system. It is binding. Where it says **MUST**, deviation
requires explicit human approval.

---

## 1. Product in one paragraph

A user describes their home (rooms, floor types, household size, pets, cleaning
preferences) through a short guided onboarding flow. The backend sends that
structured description to a text LLM, which returns a structured cleaning plan: a
set of rooms, each with recurring chores and sensible frequencies. The app turns
that plan into a **daily checklist**, navigable by date, and sends up to two push
notifications a day (a morning briefing and an optional evening nudge for unfinished
tasks). Users can tune notification times and intensity in settings.

---

## 2. Technology stack (fixed for the prototype)

| Layer | Choice | Notes |
|-------|--------|-------|
| Backend language | Python 3.12 | |
| Backend framework | FastAPI | async, OpenAPI built in |
| ORM | SQLAlchemy 2.x (async) | with Alembic for migrations |
| Validation | Pydantic v2 | request/response + LLM output parsing |
| Database | PostgreSQL 16 | `JSONB` for the raw LLM plan snapshot |
| Background jobs | APScheduler (in-process) | sufficient for prototype; no Celery/Redis yet |
| LLM | `deepseek/deepseek-v4-flash:free` via OpenRouter | **text only** |
| Mobile | React Native + Expo (TypeScript) | Strategy 2: Expo Go distribution |
| Mobile state | Zustand | + AsyncStorage for local persistence |
| Mobile navigation | React Navigation (native stack + bottom tabs) | |
| Push | Expo Notifications + Expo Push API | |
| HTTP client (app) | native `fetch`, wrapped in a typed client | |
| Local orchestration | Docker Compose (postgres + backend) | |
| Backend tests | PyTest + pytest-asyncio + httpx AsyncClient | |
| Frontend tests | Jest + React Native Testing Library | |

**Do not add libraries beyond these without human approval.** Notably absent on
purpose: Celery, Redis, SageMaker, any reinforcement-learning framework, any
cloud SDK. Those are future extensions (`docs/07`), not prototype dependencies.

---

## 3. Two models, two roles — the architectural keystone

There are **two distinct AI roles**, and they are deliberately separated because the
default scheduling model cannot see images:

1. **Scheduling model (required, text-only).** `deepseek/deepseek-v4-flash:free` on
   OpenRouter. Takes a text home description, returns a strict JSON cleaning plan.
   This is the always-on model. Verified text-only (May 2026), so **no image is ever
   sent on this path.**
2. **Vision model (optional, multimodal).** A separately-configured, image-capable
   model used *only* to turn an uploaded blueprint/photo into the same
   `description_text` the guided form would have produced. It is **off by default**
   and feeds the scheduling model — it never replaces it.

The pipeline always converges on one thing: a **text `description_text`**. Vision, if
enabled, is just an alternate way to produce that text.

### The scheduling path (always present)
- The scheduling prompt sends the structured home description and **demands a strict
  JSON response** matching `HouseStructurePayload` (defined in `02-api-contract.md`).
  DeepSeek is verbose, so the client MUST defensively extract the JSON object (strip
  prose, code fences, and any reasoning preamble) before parsing.

### The vision path (optional, pluggable)
- A `VisionExtractor` **interface** defines `async extract(image_bytes) -> str`,
  returning a natural-language home description.
- **Two implementations ship:**
  - `StubVisionExtractor` — the **default**. Raises `VisionDisabledError`. Selected
    whenever vision is not configured. The app simply doesn't show image upload.
  - `OpenRouterVisionExtractor` — a **real, working** implementation that calls a
    configurable multimodal model (`VISION_MODEL` env var, e.g.
    `google/gemini-2.5-flash`, `openai/gpt-4o`, or `deepseek/deepseek-v4-vision` —
    any OpenRouter image-capable model). Sends the image as an `image_url`/base64
    content part with a prompt instructing it to describe rooms, floor types, and
    layout as plain text.
- Selection is by config: `VISION_ENABLED=1` + a valid `VISION_MODEL` activates the
  real extractor; otherwise the stub. The **scheduling pipeline is identical either
  way** — it only ever receives `description_text`.

```
                         ┌─ (default) guided form ──────────────┐
                         │                                       │
[App] ───────────────────┤                                       ├─► description_text
                         │                                       │
                         └─ (optional) image upload ─► VisionExtractor ─┘
                                                       │  Stub  → VisionDisabledError
                                                       │  OpenRouterVision → text
                                                       ▼
                          [LLMClient → deepseek-v4-flash:free]  (text-only, required)
                                                       │
                                            strict JSON: HouseStructurePayload
                                                       ▼
                          [Scheduler: persist Home, Rooms, ChoreTasks]
```

**Rule the agent must never break:** images go *only* to the `VisionExtractor`, never
to the scheduling model. The scheduling model receives text and text alone.

---

## 4. Data model (authoritative)

Five tables. Relationships and cascade behaviour are part of the contract and are
tested in Milestone 1.

### `users`
| column | type | notes |
|--------|------|-------|
| id | UUID PK | |
| email | text unique | login identity for prototype (no password flow yet; see §7) |
| display_name | text | |
| timezone | text | IANA tz, e.g. `Asia/Tokyo`; drives notification timing |
| created_at | timestamptz | |

### `homes`
| column | type | notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID FK → users.id | **ON DELETE CASCADE** |
| name | text | e.g. "Apartment" |
| description_text | text | the raw structured description the user provided |
| raw_plan | JSONB | the verbatim `HouseStructurePayload` the LLM returned |
| created_at | timestamptz | |

### `rooms`
| column | type | notes |
|--------|------|-------|
| id | UUID PK | |
| home_id | UUID FK → homes.id | **ON DELETE CASCADE** |
| name | text | e.g. "Kitchen" |
| floor_type | text | e.g. "Tile" |

### `chore_tasks`
| column | type | notes |
|--------|------|-------|
| id | UUID PK | |
| room_id | UUID FK → rooms.id | **ON DELETE CASCADE** |
| name | text | e.g. "Wipe counters" |
| frequency_days | int | interval between repetitions |
| estimated_minutes | int | |
| last_completed_on | date null | drives scheduling/decay |

### `task_completions`
| column | type | notes |
|--------|------|-------|
| id | UUID PK | |
| chore_task_id | UUID FK → chore_tasks.id | **ON DELETE CASCADE** |
| scheduled_for | date | the day this instance was surfaced |
| completed_at | timestamptz null | null = surfaced but not done |
| UNIQUE (chore_task_id, scheduled_for) | | one instance per task per day |

**Cascade rule (tested):** deleting a `Home` MUST purge its `rooms`, their
`chore_tasks`, and those tasks' `task_completions`, leaving no orphans.

---

## 5. The scheduling logic (deterministic, no LLM at runtime)

The LLM is called **once per home, at onboarding**. Daily scheduling is plain
deterministic code — cheap, fast, testable, no hallucination:

> A task is **due on date D** if `last_completed_on IS NULL` or
> `D >= last_completed_on + frequency_days`. The day's checklist is the set of due
> tasks, ordered by (most overdue first, then shortest `estimated_minutes` first),
> then trimmed to the user's daily intensity cap (a settings value; default 5).

This rule is the heart of Milestone 4 and is heavily unit-tested. Keeping it out of
the LLM is a deliberate ROI decision carried over from the design conversation.

---

## 6. Environment strategy — local first, with production parity

**Build and test entirely locally before any cloud work.** Rationale: cloud
round-trips slow the TDD loop and make tests non-deterministic.

- `docker-compose.yml` brings up PostgreSQL + the FastAPI backend, mirroring the
  eventual production topology closely enough for confidence ("production parity").
- All external calls (OpenRouter, Expo Push) are **mocked in the test suites** so CI
  is deterministic and offline. Live calls happen only in manual local runs, gated
  behind an env flag.
- Configuration is via environment variables (`.env`, never committed). Required
  keys are listed in `docs/06-agent-protocol.md`.

Cloud deployment (ECS/RDS/etc.) is **explicitly deferred** — see `docs/07`.

---

## 7. Auth scope for the prototype

Full auth is out of scope. For the prototype, a user is identified by an
`X-User-Id` header carrying their UUID (created via a simple `POST /users`). This
keeps the focus on the core loop. **Do not build OAuth, JWT, or password flows
now**; note them as a future extension. Treat this as a known, intentional
simplification — not a security model for production.

---

## 8. Non-negotiable engineering rules

1. **Backend and frontend live in isolated directories** (`/backend`, `/frontend`)
   with independent dependency manifests and test runners.
2. **Test-Driven Development.** For each unit of behaviour: write the test, watch it
   fail, write the minimum code to pass, refactor. No production code without a
   test that motivated it.
3. **No network egress in tests.** Mock OpenRouter and Expo Push with
   `unittest.mock` (backend) and Jest mocks (frontend).
4. **Strict typing.** Backend passes `mypy`; frontend is TypeScript `strict: true`.
5. **Every endpoint matches `02-api-contract.md` exactly** — paths, status codes,
   and JSON shapes.
6. **Milestone gates are hard.** See the cardinal rule in the root README.
