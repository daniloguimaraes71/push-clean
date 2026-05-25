# chore-cast — Engineering Roadmap & Agent Operating Manual

> A home-cleaning schedule app: the user describes their home, an LLM generates a
> light day-to-day cleaning plan, and the app serves it as a daily checklist with
> push notifications.

This repository of documents is the **complete instruction set for a coding agent**.
Read every file in `docs/` in order before writing a single line of code. These
documents are the source of truth; if the user's chat history and these documents
ever disagree, **these documents win** unless the human architect says otherwise.

---

## The one thing you must internalise first

**The default scheduling LLM — `deepseek/deepseek-v4-flash:free` on OpenRouter — is a
TEXT-ONLY model. It cannot see images.** This was verified against OpenRouter's model
listing and independent analyses in May 2026. The design separates two AI roles:

- **Scheduling (required, text-only):** the home is captured as a **structured text
  description** and sent to DeepSeek, which returns the cleaning plan. No image is ever
  sent on this path.
- **Vision (optional, multimodal):** image upload is supported through a **separate,
  configurable, image-capable model** (`VISION_MODEL` — e.g. Gemini, GPT-4o, or a
  DeepSeek vision model) behind a `VisionExtractor` interface. It is **off by
  default**. When enabled, it only converts an uploaded blueprint/photo into the same
  text description the form would produce, which the user reviews before generating.
  The scheduling model is still the text-only one.

The whole pipeline always converges on a **text description**. The cardinal
implementation rule: **images go only to the vision model, never to the scheduling
model.** If vision is disabled (the default), the app simply doesn't show image upload
and everything runs form-only.

---

## How to read these documents

| Order | File | What it gives you |
|-------|------|-------------------|
| 1 | `docs/01-architecture.md` | The system design, tech stack, data model, and the rules you must never break. |
| 2 | `docs/02-api-contract.md` | The exact HTTP contract between app and backend. Build to this. |
| 3 | `docs/03-roadmap-milestones.md` | The seven milestones, in dependency order, each with a definition of done. |
| 4 | `docs/04-test-specifications.md` | The concrete tests. A milestone is "done" only when its tests are green. |
| 5 | `docs/05-ui-ux-spec.md` | Screen-by-screen UI, navigation, pagination, and settings behaviour. |
| 6 | `docs/06-agent-protocol.md` | Your working rules: TDD loop, git discipline, when to stop and ask. |
| 7 | `docs/07-future-extensions.md` | Explicitly OUT of scope for now. Do not build these. |

---

## The cardinal rule of this project

> **You advance one milestone at a time. A milestone is complete only when every
> test listed for it passes. When the tests are green, you COMMIT, then STOP and
> ask the human for permission to begin the next milestone. You never start the
> next milestone on your own initiative.**

This is not bureaucracy. It is how the human architect verifies the build is
proceeding as intended, milestone by milestone.

---

## Quick map of what gets built

```
chore-cast/
├── backend/                 # Python 3.12 · FastAPI · SQLAlchemy · PostgreSQL
│   ├── app/
│   │   ├── main.py
│   │   ├── core/            # config, db session, security
│   │   ├── models/          # SQLAlchemy ORM models
│   │   ├── schemas/         # Pydantic request/response models
│   │   ├── api/v1/          # routers
│   │   ├── services/        # llm client, vision interface, scheduler, notifier
│   │   └── workers/         # scheduled notification job
│   └── tests/               # PyTest — unit + integration
├── frontend/                # React Native · Expo (TypeScript)
│   ├── src/
│   │   ├── screens/
│   │   ├── components/
│   │   ├── state/           # Zustand stores
│   │   ├── api/             # typed API client
│   │   └── navigation/
│   └── __tests__/           # Jest + React Native Testing Library
├── docker-compose.yml       # postgres + backend for local dev
└── docs/                    # these documents
```

Everything runs **locally first** (Docker Compose). Cloud deployment is deferred
and described only as a future extension. See `docs/01-architecture.md` for why.
