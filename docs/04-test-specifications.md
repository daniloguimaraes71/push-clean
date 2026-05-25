# 04 · Test Specifications (Concrete)

These are the gating tests. Each milestone is complete only when **all** its tests
pass. The code below is the **reference implementation of the tests** — the agent
should adapt import paths to the final module layout but MUST preserve each test's
intent, assertions, and the behaviour it pins down. Do not weaken an assertion to
make it pass; fix the production code instead.

Conventions:
- Backend: `pytest`, `pytest-asyncio`, `httpx.AsyncClient` against the ASGI app, a
  transactional Postgres fixture (rolled back per test). All external I/O mocked.
- Frontend: `jest` + `@testing-library/react-native`. Native modules mocked.
- Test IDs match the gating lists in `03-roadmap-milestones.md`.

---

## Backend fixtures (conftest reference)

```python
# backend/tests/conftest.py
import pytest, pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import get_session, Base, engine  # async engine to a TEST db

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c

@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture
async def user(client):
    r = await client.post("/api/v1/users", json={
        "email": "sam@example.com", "display_name": "Sam", "timezone": "Asia/Tokyo"})
    assert r.status_code == 201
    return r.json()

def auth(user):  # helper -> headers
    return {"X-User-Id": user["id"]}
```

---

## M0

### `BE-HEALTH-01`
```python
async def test_health_ok(client):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

### `FE-SMOKE-01`
```tsx
// frontend/__tests__/smoke.test.tsx
import { render } from "@testing-library/react-native";
import App from "../App";

test("app renders without crashing", () => {
  const { toJSON } = render(<App />);
  expect(toJSON()).toBeTruthy();
});
```

---

## M1 — Data Bedrock

### `BE-DB-CASCADE-01`
Deleting a home purges rooms, chores, and completions.
```python
async def test_home_delete_cascades(db_session, seeded_home):
    # seeded_home fixture inserts 1 home, 2 rooms, 3 chores, 2 completions
    home_id = seeded_home.id
    await db_session.delete(seeded_home)
    await db_session.commit()
    assert await count_rows(db_session, "rooms", home_id=home_id) == 0
    assert await count_orphans(db_session, "chore_tasks") == 0
    assert await count_orphans(db_session, "task_completions") == 0
```

### `BE-USER-CREATE-01`
```python
async def test_create_user_returns_defaults(client):
    r = await client.post("/api/v1/users", json={
        "email": "new@example.com", "display_name": "New", "timezone": "Asia/Tokyo"})
    assert r.status_code == 201
    body = r.json()
    assert body["settings"]["daily_intensity_cap"] == 5
    assert body["settings"]["morning_time"] == "08:00"
```

### `BE-USER-EMAIL-CONFLICT-01`
```python
async def test_duplicate_email_conflicts(client, user):
    r = await client.post("/api/v1/users", json={
        "email": "sam@example.com", "display_name": "Other", "timezone": "Asia/Tokyo"})
    assert r.status_code == 409
    assert r.json()["detail"] == "email_exists"
```

### `BE-SETTINGS-GET-DEFAULTS-01`
```python
async def test_settings_defaults(client, user):
    r = await client.get("/api/v1/settings", headers=auth(user))
    assert r.status_code == 200
    s = r.json()
    assert s["evening_nudge_enabled"] is True
    assert s["expo_push_token"] is None
```

### `BE-SETTINGS-PUT-PARTIAL-01`
```python
async def test_settings_partial_update(client, user):
    r = await client.put("/api/v1/settings", headers=auth(user),
                         json={"daily_intensity_cap": 3})
    assert r.status_code == 200
    assert r.json()["daily_intensity_cap"] == 3
    # untouched keys preserved
    assert r.json()["morning_time"] == "08:00"
```

### `BE-SETTINGS-PUT-BADKEY-01`
```python
async def test_settings_unknown_key_rejected(client, user):
    r = await client.put("/api/v1/settings", headers=auth(user),
                         json={"nonsense": True})
    assert r.status_code == 422
    assert r.json()["detail"] == "invalid_settings_key"
```

### `BE-AUTH-MISSING-HEADER-01`
```python
async def test_missing_user_header_rejected(client):
    r = await client.get("/api/v1/settings")  # no X-User-Id
    assert r.status_code in (401, 422)
```

---

## M2 — LLM Scheduling Engine

A shared mock reply (valid) used by several tests:
```python
VALID_PLAN_JSON = {
  "confidence_score": 0.8,
  "detected_zones": [
    {"room_name": "Kitchen", "floor_type": "Tile", "suggested_chores": [
        {"task_name": "Wipe counters", "frequency_days": 1, "estimated_minutes": 5}]},
    {"room_name": "Bedroom", "floor_type": "Carpet", "suggested_chores": [
        {"task_name": "Vacuum", "frequency_days": 3, "estimated_minutes": 10}]}
  ]
}
```

### `BE-LLM-EXTRACT-CLEAN-01`
Extractor parses a clean JSON string.
```python
def test_extract_clean_json():
    import json
    from app.services.llm import extract_house_payload
    raw = json.dumps(VALID_PLAN_JSON)
    payload = extract_house_payload(raw)
    assert payload.detected_zones[0].room_name == "Kitchen"
```

### `BE-LLM-EXTRACT-FENCED-01`
Handles ```` ```json ... ``` ```` fencing.
```python
def test_extract_fenced_json():
    import json
    from app.services.llm import extract_house_payload
    raw = "```json\n" + json.dumps(VALID_PLAN_JSON) + "\n```"
    payload = extract_house_payload(raw)
    assert len(payload.detected_zones) == 2
```

### `BE-LLM-EXTRACT-PREAMBLE-01`
Handles a verbose reasoning preamble before the JSON (DeepSeek is verbose).
```python
def test_extract_with_preamble():
    import json
    from app.services.llm import extract_house_payload
    raw = ("Sure! Here is the schedule I generated after reasoning about the "
           "rooms and floor types:\n\n" + json.dumps(VALID_PLAN_JSON))
    payload = extract_house_payload(raw)
    assert payload.confidence_score == 0.8
```

### `BE-LLM-EXTRACT-INVALID-01`
Garbage or schema-violating content raises the typed error.
```python
import pytest
def test_extract_invalid_raises():
    from app.services.llm import extract_house_payload, ScheduleParseError
    with pytest.raises(ScheduleParseError):
        extract_house_payload("I could not produce a schedule, sorry.")
    with pytest.raises(ScheduleParseError):
        extract_house_payload('{"confidence_score": 0.5, "detected_zones": []}')
```

### `BE-LLM-NO-IMAGE-01`
The LLM request payload MUST be text-only — no image parts ever sent.
```python
from unittest.mock import AsyncMock, patch
async def test_llm_payload_is_text_only():
    from app.services.llm import LLMClient
    with patch("app.services.llm.httpx.AsyncClient.post", new=AsyncMock()) as post:
        post.return_value = _mk_response(VALID_PLAN_JSON)
        await LLMClient().generate_plan(description_text="2 rooms, tile and carpet")
        sent = post.call_args.kwargs["json"]
        # every message content must be a plain string, never an image part
        for msg in sent["messages"]:
            assert isinstance(msg["content"], str), "image content must never be sent"
        assert sent["model"] == "deepseek/deepseek-v4-flash:free"
```

### `BE-ONBOARD-PERSIST-01`
End-to-end onboard with a mocked LLM persists the relational structure.
```python
from unittest.mock import AsyncMock, patch
async def test_onboard_persists(client, user):
    with patch("app.services.llm.LLMClient.generate_plan",
               new=AsyncMock(return_value=__import__("app.schemas.plan", fromlist=["HouseStructurePayload"]).HouseStructurePayload(**VALID_PLAN_JSON))):
        r = await client.post("/api/v1/homes/onboard", headers=auth(user), json={
            "name": "Apartment",
            "description_text": "kitchen tile, bedroom carpet",
            "household_size": 2, "has_pets": True})
    assert r.status_code == 201
    body = r.json()
    assert len(body["rooms"]) == 2
    names = {room["name"] for room in body["rooms"]}
    assert names == {"Kitchen", "Bedroom"}
    assert body["rooms"][0]["chores"][0]["chore_task_id"]
```

### `BE-ONBOARD-BADLLM-502-01`
```python
from unittest.mock import AsyncMock, patch
async def test_onboard_bad_llm_returns_502(client, user):
    from app.services.llm import ScheduleParseError
    with patch("app.services.llm.LLMClient.generate_plan",
               new=AsyncMock(side_effect=ScheduleParseError("nope"))):
        r = await client.post("/api/v1/homes/onboard", headers=auth(user), json={
            "name": "Apartment", "description_text": "x",
            "household_size": 1, "has_pets": False})
    assert r.status_code == 502
    assert r.json()["detail"] == "schedule_generation_failed"
```

### `BE-VISION-STUB-DISABLED-01`
The default stub extractor is inert: it signals "disabled," and the factory returns it
when vision isn't configured.
```python
import pytest
def test_vision_stub_disabled():
    from app.services.vision import StubVisionExtractor, VisionDisabledError, get_vision_extractor
    with pytest.raises(VisionDisabledError):
        StubVisionExtractor().extract(image_bytes=b"\x89PNG")
    # factory with vision off -> stub
    extractor = get_vision_extractor(enabled=False, model=None)
    assert isinstance(extractor, StubVisionExtractor)
```

### `BE-VISION-CAPABILITIES-01`
The capabilities endpoint reflects config both ways.
```python
from unittest.mock import patch
async def test_capabilities_reflects_config(client):
    # default: vision off
    r = await client.get("/api/v1/capabilities")
    assert r.status_code == 200
    assert r.json()["vision_onboarding"] is False
    assert r.json()["vision_model"] is None
    # enabled via settings override
    with patch("app.core.config.settings.VISION_ENABLED", True), \
         patch("app.core.config.settings.VISION_MODEL", "google/gemini-2.5-flash"):
        r2 = await client.get("/api/v1/capabilities")
        assert r2.json()["vision_onboarding"] is True
        assert r2.json()["vision_model"] == "google/gemini-2.5-flash"
```

### `BE-VISION-DESCRIBE-DISABLED-404-01`
With vision off (default), the describe-from-image endpoint is guarded.
```python
async def test_describe_from_image_disabled(client, user):
    r = await client.post("/api/v1/homes/describe-from-image", headers=auth(user),
                          files={"image": ("plan.png", b"\x89PNG\r\n", "image/png")})
    assert r.status_code == 404
    assert r.json()["detail"] == "vision_disabled"
```

### `BE-VISION-DESCRIBE-ENABLED-01`
With vision enabled (mocked model), the endpoint returns text and never creates a home.
```python
from unittest.mock import AsyncMock, patch
async def test_describe_from_image_enabled(client, user):
    fake_text = "Two bedrooms with carpet, a tiled kitchen, one tiled bathroom."
    with patch("app.core.config.settings.VISION_ENABLED", True), \
         patch("app.core.config.settings.VISION_MODEL", "google/gemini-2.5-flash"), \
         patch("app.services.vision.OpenRouterVisionExtractor.extract",
               new=AsyncMock(return_value=fake_text)):
        r = await client.post("/api/v1/homes/describe-from-image", headers=auth(user),
                              files={"image": ("plan.png", b"\x89PNG\r\n", "image/png")})
    assert r.status_code == 200
    assert r.json()["description_text"] == fake_text
    # no home was created by this call
    assert "home_id" not in r.json()
```

### `BE-VISION-IMAGE-NOT-TO-SCHEDULER-01`
The image goes to the vision model only; the scheduling model is never sent image content.
```python
from unittest.mock import AsyncMock, patch
async def test_image_never_reaches_scheduler(client, user):
    sched_spy = AsyncMock()
    with patch("app.core.config.settings.VISION_ENABLED", True), \
         patch("app.core.config.settings.VISION_MODEL", "openai/gpt-4o"), \
         patch("app.services.vision.OpenRouterVisionExtractor.extract",
               new=AsyncMock(return_value="A tiled kitchen and a carpeted bedroom.")), \
         patch("app.services.llm.LLMClient.generate_plan", new=sched_spy):
        await client.post("/api/v1/homes/describe-from-image", headers=auth(user),
                          files={"image": ("plan.png", b"\x89PNG\r\n", "image/png")})
    # describe-from-image must not trigger the scheduling model at all
    sched_spy.assert_not_called()
```

---

## M4 — Deterministic Scheduler (backend)

Scheduler unit tests operate on the pure function so they're fast and clock-free.

### `BE-SCHED-DUE-RULE-01`
```python
from datetime import date
def test_due_rule():
    from app.services.scheduler import is_due
    # never completed -> due
    assert is_due(last_completed_on=None, frequency_days=3, on=date(2026,5,25))
    # completed today, freq 3 -> not due
    assert not is_due(date(2026,5,25), 3, date(2026,5,25))
    # completed 3 days ago, freq 3 -> due
    assert is_due(date(2026,5,22), 3, date(2026,5,25))
    # completed 2 days ago, freq 3 -> not due
    assert not is_due(date(2026,5,23), 3, date(2026,5,25))
```

### `BE-SCHED-ORDERING-01`
Most overdue first, then shortest task first.
```python
from datetime import date
def test_ordering():
    from app.services.scheduler import order_tasks
    tasks = [
        {"id": "a", "overdue_days": 0, "estimated_minutes": 10},
        {"id": "b", "overdue_days": 4, "estimated_minutes": 30},
        {"id": "c", "overdue_days": 4, "estimated_minutes": 5},
    ]
    ordered = [t["id"] for t in order_tasks(tasks)]
    assert ordered == ["c", "b", "a"]  # b & c most overdue; c shorter first
```

### `BE-SCHED-CAP-01`
```python
def test_intensity_cap_trims():
    from app.services.scheduler import apply_cap
    tasks = [{"id": str(i)} for i in range(10)]
    assert len(apply_cap(tasks, cap=5)) == 5
```

### `BE-SCHED-MATERIALISE-IDEMPOTENT-01`
Calling daily twice for the same date doesn't duplicate completion rows.
```python
from unittest.mock import AsyncMock, patch
async def test_daily_materialise_idempotent(client, user, onboarded_home):
    h = {"headers": auth(user)}
    r1 = await client.get("/api/v1/schedule/daily?date=2026-05-25", **h)
    r2 = await client.get("/api/v1/schedule/daily?date=2026-05-25", **h)
    assert r1.status_code == r2.status_code == 200
    ids1 = {t["completion_id"] for t in r1.json()["tasks"]}
    ids2 = {t["completion_id"] for t in r2.json()["tasks"]}
    assert ids1 == ids2  # same rows reused, none duplicated
```

### `BE-COMPLETE-UPDATES-LASTDONE-01`
```python
async def test_complete_updates_last_done(client, user, onboarded_home):
    h = {"headers": auth(user)}
    day = await client.get("/api/v1/schedule/daily?date=2026-05-25", **h)
    cid = day.json()["tasks"][0]["completion_id"]
    r = await client.post("/api/v1/schedule/complete", **h,
                          json={"completion_id": cid, "completed": True})
    assert r.status_code == 200
    assert r.json()["completed"] is True
    # the same task should not reappear as due the very next day if freq>1
    nxt = await client.get("/api/v1/schedule/daily?date=2026-05-26", **h)
    assert cid not in {t["completion_id"] for t in nxt.json()["tasks"]}
```

### `BE-COMPLETE-WRONG-USER-404-01`
```python
async def test_complete_foreign_completion_404(client, user, other_user_completion_id):
    r = await client.post("/api/v1/schedule/complete", headers=auth(user),
                          json={"completion_id": other_user_completion_id, "completed": True})
    assert r.status_code == 404
    assert r.json()["detail"] == "not_found"
```

---

## M5 — Notifications & Cron (backend)

### `BE-PUSH-REGISTER-VALIDATION-01`
```python
async def test_push_token_validation(client, user):
    ok = await client.post("/api/v1/notifications/register", headers=auth(user),
                           json={"expo_push_token": "ExponentPushToken[abc123]"})
    assert ok.status_code == 200
    bad = await client.post("/api/v1/notifications/register", headers=auth(user),
                            json={"expo_push_token": "not-a-token"})
    assert bad.status_code == 422
    assert bad.json()["detail"] == "invalid_push_token"
```

### `BE-CRON-PAYLOAD-INCOMPLETE-ONLY-01`
The morning aggregator includes only incomplete due tasks.
```python
from unittest.mock import AsyncMock, patch
async def test_cron_payload_incomplete_only(db_session, user_with_due_tasks):
    from app.workers.notify import build_morning_payload
    # fixture: 3 due tasks, 1 already completed today
    payload = await build_morning_payload(db_session, user_with_due_tasks.id,
                                           on=__import__("datetime").date(2026,5,25))
    assert payload["task_count"] == 2  # completed one excluded
    assert "ExponentPushToken" in payload["to"]
```

### `BE-CRON-TIMEZONE-TARGETING-01`
Only users whose local time equals the configured time are targeted.
```python
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone
async def test_cron_targets_by_timezone(db_session, two_users_diff_tz):
    # user A in Asia/Tokyo (morning 08:00), user B in America/New_York (08:00)
    from app.workers.notify import users_due_for_morning
    # 08:00 in Tokyo == 23:00 previous day UTC
    now_utc = datetime(2026, 5, 24, 23, 0, tzinfo=timezone.utc)
    due = await users_due_for_morning(db_session, now_utc)
    ids = {u.id for u in due}
    assert two_users_diff_tz["tokyo"].id in ids
    assert two_users_diff_tz["ny"].id not in ids
```

### `BE-CRON-EVENING-SUPPRESSED-01`
Evening nudge does not fire when nothing is outstanding.
```python
async def test_evening_nudge_suppressed_when_clear(db_session, user_all_done):
    from app.workers.notify import build_evening_payload
    payload = await build_evening_payload(db_session, user_all_done.id,
                                          on=__import__("datetime").date(2026,5,25))
    assert payload is None  # nothing to nag about -> no notification
```

---

## M6 — End to end (backend)

### `BE-E2E-HAPPYPATH-01`
```python
from unittest.mock import AsyncMock, patch
async def test_happy_path(client):
    from app.schemas.plan import HouseStructurePayload
    u = (await client.post("/api/v1/users", json={
        "email": "e2e@example.com", "display_name": "E2E", "timezone": "Asia/Tokyo"})).json()
    h = {"headers": {"X-User-Id": u["id"]}}
    with patch("app.services.llm.LLMClient.generate_plan",
               new=AsyncMock(return_value=HouseStructurePayload(**VALID_PLAN_JSON))):
        onb = await client.post("/api/v1/homes/onboard", **h, json={
            "name": "Home", "description_text": "kitchen tile, bedroom carpet",
            "household_size": 2, "has_pets": True})
    assert onb.status_code == 201
    day = await client.get("/api/v1/schedule/daily?date=2026-05-25", **h)
    assert day.status_code == 200 and len(day.json()["tasks"]) >= 1
    cid = day.json()["tasks"][0]["completion_id"]
    done = await client.post("/api/v1/schedule/complete", **h,
                             json={"completion_id": cid, "completed": True})
    assert done.json()["completed"] is True
```

*(Frontend test code continues in `04b-frontend-tests.md`.)*
