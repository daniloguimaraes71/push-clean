# 06 · Agent Operating Protocol

Your working rules. Follow them literally.

---

## The TDD loop (per unit of behaviour)

1. **Read** the relevant section of `02`, `03`, `04`/`04b`, `05`.
2. **Write the test first** (from `04`/`04b`), adapting only import paths.
3. **Run it; watch it fail** for the right reason (not an import error).
4. **Write the minimum production code** to make it pass.
5. **Refactor** with tests green.
6. Move to the next unit **within the same milestone**.

## The milestone gate (hard stop)

When every gating test for the current milestone passes:
1. Run the full suite for that side (`pytest` / `npm test`) — all green.
2. Run `mypy` + `ruff` (backend) and `tsc --noEmit` + lint (frontend) — clean.
3. `git add -A && git commit` with message `feat(mN): <summary>` and a body listing
   which test IDs now pass.
4. **STOP.** Post a short status report to the human:
   - milestone number, what was built, the passing test IDs, anything noteworthy.
5. **Wait for explicit "proceed" before touching the next milestone.** Do not start
   M(N+1) on your own initiative. This is the cardinal rule.

If you become blocked or discover the spec is wrong/ambiguous, **stop and ask** rather
than guessing or inventing scope.

---

## Git discipline

- Conventional Commits (`feat:`, `fix:`, `test:`, `chore:`, `docs:`).
- Commit at each milestone gate at minimum; smaller commits within a milestone are
  welcome but every commit must have green tests for the code it touches.
- Never commit secrets. `.env` is git-ignored; only `.env.example` is committed.
- One branch per milestone (`mN-short-name`) merged after human approval, or commit
  straight to `main` if the human prefers — confirm at M0.

---

## Required environment variables (`.env.example`)

```
# Backend
DATABASE_URL=postgresql+asyncpg://chore:chore@localhost:5432/chorecast
TEST_DATABASE_URL=postgresql+asyncpg://chore:chore@localhost:5432/chorecast_test
OPENROUTER_API_KEY=          # required for LIVE runs only; tests mock this
OPENROUTER_MODEL=deepseek/deepseek-v4-flash:free
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
LLM_LIVE=0                   # 0 = never call the network (tests/CI); 1 = allow live

# Optional vision onboarding (image -> text). Off by default.
VISION_ENABLED=0             # 1 enables the /describe-from-image endpoint + UI button
VISION_MODEL=                # any OpenRouter image-capable model when enabled,
                             # e.g. google/gemini-2.5-flash, openai/gpt-4o,
                             # deepseek/deepseek-v4-vision. Leave blank when disabled.
LOG_LEVEL=INFO

# Frontend (app.config / extra)
EXPO_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

The OpenRouter chat-completions call (LIVE mode only) targets
`POST {OPENROUTER_BASE_URL}/chat/completions` with header
`Authorization: Bearer ${OPENROUTER_API_KEY}` and a **text-only** `messages` array.
Recommended: set `response_format` to JSON-object mode if available, and always run
the defensive extractor regardless.

The optional vision call (when `VISION_ENABLED=1`) uses the **same OpenRouter endpoint
and key** but targets `VISION_MODEL` and sends one `image_url` content part (base64
data URI) plus a text instruction to describe the home as plain prose. Its output is
text that feeds the normal onboarding flow — it must never be routed into the
scheduling model as image content.

---

## Testing rules (non-negotiable)

- **No real network in any test.** Mock OpenRouter (`unittest.mock`) and Expo Push;
  mock the API client and `expo-notifications` on the frontend.
- Backend tests use the **test database** and roll back per test.
- Determinism: freeze time where behaviour depends on "now" (e.g. `freezegun` or
  injecting a clock). The scheduler core takes dates as arguments precisely so it can
  be tested without mocking the clock.
- A test that is flaky is a failing test. Fix the cause.
- Do not delete or weaken a provided assertion to get green. If a test seems wrong,
  stop and ask.

## Quality gates carried at every milestone

- Backend: `mypy` clean, `ruff` clean.
- Frontend: `tsc --noEmit` clean, lint clean.
- M6 adds coverage thresholds (backend ≥85% on `services/`+`api/`, frontend ≥80% on
  stores+screens).

---

## Definition of "done" for the whole prototype

All seven milestones approved; both integration tests green; the app runs in Expo Go
against the Docker-Compose backend; a user can onboard (mocked or live LLM), see a
daily checklist, complete tasks, adjust settings, and receive a scheduled
notification on the device. Cloud deployment is **not** part of this definition — see
`07`.
