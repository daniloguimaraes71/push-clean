# 02 · API Contract

Every endpoint below is binding: exact path, method, status codes, and JSON shape.
All bodies are JSON unless stated. All authenticated routes require the header
`X-User-Id: <uuid>` (see `01-architecture.md` §7). Base path: `/api/v1`.

Pydantic models are the source of truth for shapes; the JSON examples illustrate them.

---

## Shared LLM output schema

The scheduling LLM MUST return exactly this shape (the client extracts and validates
it). This is the `raw_plan` stored on the home.

```python
from pydantic import BaseModel, Field
from typing import List

class ChoreSeed(BaseModel):
    task_name: str = Field(..., description="e.g. 'Wipe counters'")
    frequency_days: int = Field(..., ge=1, le=90)
    estimated_minutes: int = Field(..., ge=1, le=240)

class RoomZone(BaseModel):
    room_name: str = Field(..., description="e.g. 'Kitchen'")
    floor_type: str = Field(..., description="e.g. 'Tile', 'Hardwood', 'Carpet'")
    suggested_chores: List[ChoreSeed] = Field(..., min_length=1)

class HouseStructurePayload(BaseModel):
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    detected_zones: List[RoomZone] = Field(..., min_length=1)
```

Validation invariants (tested): empty `detected_zones` is rejected; a room with zero
chores is rejected; out-of-range frequency/minutes are rejected.

---

## Endpoints

### `POST /api/v1/users`
Create a user. No auth header required (this is how you get your id).

Request:
```json
{ "email": "a@b.com", "display_name": "Sam", "timezone": "Asia/Tokyo" }
```
Responses:
- `201 Created` → `{ "id": "<uuid>", "email": "...", "display_name": "...", "timezone": "...", "settings": { ...defaults... } }`
- `409 Conflict` if email already exists.
- `422` on invalid timezone or malformed email.

---

### `POST /api/v1/homes/onboard`  *(auth)*
The core onboarding call. Accepts the **structured text description** and triggers
the one-time scheduling LLM call (always text-only).

Request:
```json
{
  "name": "Apartment",
  "description_text": "2 bedrooms (carpet), 1 kitchen (tile), 1 bathroom (tile), 1 living room (hardwood). Two adults, one cat. Prefer light daily upkeep.",
  "household_size": 2,
  "has_pets": true
}
```
Behaviour: build the prompt → call the scheduling LLM → extract & validate
`HouseStructurePayload` → persist `Home` (+ `raw_plan`), `Room`s, `ChoreTask`s.

Responses:
- `201 Created` → the created home summary:
```json
{
  "home_id": "<uuid>",
  "name": "Apartment",
  "confidence_score": 0.82,
  "rooms": [
    { "room_id": "<uuid>", "name": "Kitchen", "floor_type": "Tile",
      "chores": [ { "chore_task_id": "<uuid>", "name": "Wipe counters",
                    "frequency_days": 1, "estimated_minutes": 5 } ] }
  ]
}
```
- `502 Bad Gateway` if the LLM response cannot be parsed into a valid
  `HouseStructurePayload` after extraction (message: `"schedule_generation_failed"`).
- `422` on malformed request body.

---

### `POST /api/v1/homes/describe-from-image`  *(auth)*  — **optional, vision**
Converts an uploaded blueprint/photo into a `description_text` the user can review and
edit before onboarding. **Only available when vision is enabled** (see
`GET /capabilities`). This endpoint never creates a home and never calls the
scheduling model — it returns text only.

Request: `multipart/form-data` with field `image` (PNG/JPEG, ≤8 MB).

Responses:
- `200 OK` → `{ "description_text": "Two bedrooms with carpet, a tiled kitchen, ..." }`
  The app pre-fills the onboarding notes/form with this text for user confirmation.
- `404 Not Found` with `detail: "vision_disabled"` when vision is not configured
  (the `StubVisionExtractor` is active). The app should not call this endpoint in that
  case, but the backend guards it regardless.
- `413 Payload Too Large` if the image exceeds the size limit.
- `415 Unsupported Media Type` for non-image uploads.
- `502 Bad Gateway` with `detail: "vision_extraction_failed"` if the vision model
  errors or returns unusable output.

> Flow: user uploads image → `describe-from-image` returns text → user reviews/edits →
> normal `POST /homes/onboard` with that `description_text`. Vision is strictly an
> input-assist; the schedule still comes from the text-only scheduling model.

---

### `GET /api/v1/capabilities`
Tells the app which optional features are active so the UI can adapt. No auth.

Response `200 OK`:
```json
{ "vision_onboarding": false, "vision_model": null }
```
When vision is enabled: `{ "vision_onboarding": true, "vision_model": "google/gemini-2.5-flash" }`.
The app shows the "Scan a blueprint/photo" option **only** when `vision_onboarding` is
true.

---

### `GET /api/v1/schedule/daily?date=YYYY-MM-DD`  *(auth)*
Return the checklist for a given date (defaults to the user's "today" in their tz).
Implements the deterministic due-task rule and the intensity cap (architecture §5).

Response `200 OK`:
```json
{
  "date": "2026-05-25",
  "intensity_cap": 5,
  "tasks": [
    { "completion_id": "<uuid>", "chore_task_id": "<uuid>", "room_name": "Kitchen",
      "name": "Wipe counters", "estimated_minutes": 5, "overdue_days": 0,
      "completed": false }
  ]
}
```
Notes: calling this for a date **materialises** `task_completions` rows for the due
tasks of that date (idempotent via the UNIQUE constraint). Querying an empty home
returns `{ "date": ..., "intensity_cap": ..., "tasks": [] }`.

---

### `POST /api/v1/schedule/complete`  *(auth)*
Toggle a task instance complete/incomplete.

Request: `{ "completion_id": "<uuid>", "completed": true }`
Behaviour: sets `completed_at` (now) or null; when set to true, updates the parent
`chore_task.last_completed_on` to `scheduled_for`.
Responses: `200 OK` → updated task object (same shape as a daily task item);
`404` if the completion id doesn't belong to the calling user.

---

### `GET /api/v1/settings`  *(auth)* and `PUT /api/v1/settings`  *(auth)*
User preferences that drive notifications and scheduling intensity.

Settings object (defaults shown):
```json
{
  "morning_briefing_enabled": true,
  "morning_time": "08:00",
  "evening_nudge_enabled": true,
  "evening_time": "19:00",
  "daily_intensity_cap": 5,
  "expo_push_token": null
}
```
`PUT` accepts a partial object; unknown keys → `422`. Times are `HH:MM` 24h local to
the user's timezone. `GET` returns the full object. Settings persist on the `users`
row (a `settings` JSONB column) for the prototype.

---

### `POST /api/v1/notifications/register`  *(auth)*
Store the device's Expo push token.
Request: `{ "expo_push_token": "ExponentPushToken[...]" }` → `200 OK`.
Validation: token must match the `ExponentPushToken[...]` format → else `422`.

---

### `GET /api/v1/health`
Liveness probe → `200 OK` `{ "status": "ok" }`. No auth.

---

## Error envelope

All non-2xx responses use:
```json
{ "detail": "machine_readable_code", "message": "human friendly text" }
```
`detail` codes referenced by tests: `email_exists`, `schedule_generation_failed`,
`not_found`, `invalid_settings_key`, `invalid_push_token`, `vision_disabled`,
`vision_extraction_failed`.
