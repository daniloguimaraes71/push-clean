# 07 · Future Extensions (Explicitly OUT of Scope Now)

These ideas surfaced in the design conversation. They are **deliberately deferred**.
The agent must **not** build any of these during the prototype. They are recorded so
the architecture stays friendly to them later.

| Idea | Why deferred | What keeps the door open |
|------|--------------|--------------------------|
| **Auto-parse rich blueprints into exact room geometry** | The optional vision feature (shipped in M2) produces a *text description* a human reviews — not precise CAD-grade floor-plan geometry. Full spatial extraction (areas, adjacencies, door graph) is a much bigger effort. | `OpenRouterVisionExtractor` already exists; a richer structured-vision step can replace its prompt/output without touching the scheduler. |
| **Reinforcement-learning scheduler** (A2C/DQN, reward shaping, replay buffers, shadow mode, SageMaker) | Massive engineering cost; the deterministic rule + one LLM call delivers the product now. ROI strongly favours deferral until there's real usage data. | We log `task_completions` (state/action/reward signal) from day one, so an offline RL dataset accumulates naturally. |
| **Cloud deployment** (ECS/Fargate, RDS, S3, EventBridge, SQS, Pinpoint/SNS, ElastiCache) | Local-first with production parity is faster and cheaper to iterate. | Docker Compose mirrors the topology; the in-process APScheduler job can be lifted to a worker + queue later. |
| **Multi-agent pipeline** (Vision Extractor agent → Scheduling agent) | Unneeded complexity for one LLM call + deterministic logic. | Services are already separated (`llm`, `vision`, `scheduler`, `notifier`). |
| **Self-hosted Gemma / vLLM / serverless GPU** | Only relevant if/when the LLM cost or privacy profile demands it. | `LLMClient` is provider-agnostic behind config; swapping the endpoint is a config change. |
| **Real auth** (OAuth/JWT/passwords, multi-device) | Prototype uses an `X-User-Id` header to stay focused on the core loop. | Auth is isolated in one dependency; replacing it touches one seam. |
| **PWA / TestFlight / store release** | Strategy 2 (Expo Go) is the agreed prototype distribution. | Nothing in the build precludes a later store submission. |

If the human asks for any of these, treat it as a **new project phase** with its own
roadmap and milestone gates — not an extension to sneak into the prototype.
