# Cascade Research and Handoff

**Author:** Manus AI  
**Date:** 2026-08-24  
**Repository:** [muhumuza684/Cascade](https://github.com/muhumuza684/Cascade)

## Executive summary

The repository was empty at the time of inspection. The attached notes describe a proposed system for distributing AI work across capability levels: a small model shapes prompts and decomposes requests, medium models execute bounded coding or review tasks, and a larger model integrates results. The notes also identify the name **Project Cascade**, with the tagline “Distribute the flow. Prevent the flood.”

This first implementation converts that concept into a dependency-free Python foundation. It defines a provider protocol, task and level configuration objects, a bounded asynchronous dispatcher, a spacing-based rate limiter, bounded exponential retries, and a local ZIP creator. An offline example and tests make the project usable without credentials. Provider-specific API clients remain intentionally unimplemented so that the next contributor can choose providers without rewriting the orchestration core.

## Source material distilled

The attachment contains a long list of prior conversation topics followed by a focused architecture proposal. The relevant design statements are:

| Source idea | Interpretation used in this repository |
|---|---|
| “Small AIs write prompts” | Level 1 is responsible for shaping, summarization, classification, and decomposition. |
| “Medium/bigger AIs write code” | Level 2 handles bounded implementation, debugging, and review tasks. |
| “Biggest AIs write zip files” | The host process performs binary ZIP creation; the model supplies plans or code, not a binary archive through text. |
| “Distribute the load” | Independent tasks may run concurrently, while semaphores and rate limiters control pressure. |
| “Beat limits” | Reframed as reducing context and pacing authorized API usage, never evading quotas or provider policies. |
| “Project Cascade” | Adopted as the repository name and branding. |

The attached notes mention example model names and multiple providers. Those names are treated as historical examples, not recommendations. Model catalogs, pricing, quotas, and terms change; integrations should be configured at runtime and verified against current provider documentation.

## Research findings

Python’s `asyncio` library is designed for concurrent code using `async`/`await` and is suitable for coordinating independent I/O-bound provider calls [1]. Python’s standard `zipfile` module supports creating, reading, writing, appending, and listing ZIP archives [2]. HTTP status `429 Too Many Requests` indicates that the client has sent too many requests in a period, and a server may provide `Retry-After` guidance [3] [4]. These sources support the implementation choices of asynchronous orchestration, host-side packaging, and explicit retry/pacing behavior.

> “asyncio is a library to write concurrent code using the async/await syntax.” — Python documentation [1]

> “The ZIP file format is a common archive and compression standard.” — Python documentation [2]

The practical conclusion is that Cascade should be implemented as an orchestration boundary around provider adapters. The boundary should manage task identity, scheduling, concurrency, retries, and outputs, while adapters manage authentication, request serialization, provider-specific error classes, and response parsing.

## Proposed architecture

```text
User request
     |
     v
Level 1: shape, summarize, split
     |
     v
Task queue / structured task list
     |
     +--> Level 2 worker: implement or review task A
     +--> Level 2 worker: implement or review task B
     +--> Level 2 worker: test or debug task C
     |
     v
Level 3: aggregate, resolve conflicts, produce final result
     |
     v
Host process: write files, run tests, create ZIP
```

The current code implements the central scheduling and packaging primitives but leaves the Level 1 splitter and Level 3 aggregator as callables supplied by the application. This is a deliberate seam: it prevents the core package from depending on a specific model vendor or prompt format.

## Implementation status

| Area | Status | Notes |
|---|---|---|
| Provider abstraction | Complete | `Provider` protocol exposes one async `complete` method. |
| Task model | Complete | `Task` includes prompt, level, ID, and metadata. |
| Level configuration | Complete | Provider, concurrency, optional limiter, and system prompt. |
| Async dispatch | Complete | Tasks are grouped by level and bounded by a semaphore. |
| Pacing | Complete | `AsyncRateLimiter` spaces calls for a level. |
| Retry policy | Starter | Exponential backoff is bounded, but adapters should classify retryable errors. |
| ZIP packaging | Complete | Host-side archive creation excludes VCS and cache directories. |
| Offline demonstration | Complete | `examples/offline_demo.py`. |
| Offline tests | Complete | `tests/test_cascade.py`. |
| Real provider adapters | Not started | Add one at a time behind environment configuration. |
| Durable queue and state | Not started | Needed for crash recovery and distributed workers. |
| Observability | Not started | Add metrics for latency, tokens, failures, retries, and cost. |
| License | Decision needed | No license file exists yet. |

## Important corrections to the original proposal

The phrase “beat API limits” needs careful engineering and compliance language. Cascade can reduce avoidable load by summarizing context, decomposing work, limiting concurrency, honoring reset instructions, and routing only authorized work to configured providers. It must not rotate keys, create accounts, or distribute traffic for the purpose of evading a provider’s quota, abuse controls, billing, or terms of service.

Likewise, a text model does not need to emit a ZIP as base64. Base64 would increase payload size and expose a fragile binary transport path. The safer design is for the model to produce structured file content or a packaging plan, after which a trusted host process writes files and invokes `zipfile`. The current `create_zip()` helper follows that design.

The initial pseudocode in the attachment also mixed synchronous and asynchronous client styles and hard-coded outdated model identifiers. The current project avoids those issues by exposing a small async protocol and leaving concrete SDK calls to future adapters.

## Next contributor’s setup path

Begin by creating a virtual environment and running the offline example and tests. Then choose one provider and implement an adapter with environment-based configuration. Do not place credentials in source code, README files, fixtures, or ZIP archives. Add a mock-based test for successful responses, a timeout or transient failure test, and a permanent error test before enabling live calls.

Next, formalize the splitter and aggregator contracts. A good first schema should include `task_id`, `level`, `prompt`, `dependencies`, `expected_output_type`, `max_output_tokens`, `privacy_class`, and `timeout_seconds`. Validate that schema before work enters the queue. Add a correlation ID to every request and redact prompts from ordinary logs.

After one adapter is stable, add metrics and a durable queue. Record queue wait time, provider latency, retry count, failure category, output size, and—where the provider exposes it—token usage and cost. Add cancellation and deadline propagation so a cancelled top-level request does not leave orphaned provider calls.

Only then consider a web API, persistent database, or worker pool. Those features introduce authentication, authorization, tenant isolation, secret management, rate limiting per user, and data-retention decisions that should not be hidden inside the initial dispatcher.

## Risks and controls

| Risk | Why it matters | Recommended control |
|---|---|---|
| Sensitive prompt leakage | Multi-provider routing may move data across trust boundaries. | Classify data, allow provider policies per task, redact logs, and require explicit routing configuration. |
| Retry storm | Repeated failures can amplify provider load and cost. | Bounded retries, jitter, deadlines, circuit breakers, and `Retry-After` handling. |
| Non-deterministic aggregation | Different workers may produce incompatible code or assumptions. | Structured outputs, schemas, tests, and a final validation stage. |
| Hidden cost growth | Parallel calls and repeated retries can multiply usage. | Budgets, token ceilings, per-task cost estimates, and metrics. |
| Stale model configuration | Provider model names and capabilities change. | Runtime configuration, adapter tests, and a documented model registry. |
| Unsafe generated code | Generated scripts may execute destructive or untrusted actions. | Review, sandboxing, allowlists, and never execute model output blindly. |
| Archive contamination | Secrets or caches can enter a distributable ZIP. | Explicit exclusions, secret scanning, and archive manifest review. |

## Suggested milestones

**Milestone 1: single-provider vertical slice.** Add one adapter, a structured splitter, a structured aggregator, timeouts, and mock tests. The offline path must remain the default.

**Milestone 2: operational safety.** Add token/cost budgets, `Retry-After` support, jitter, circuit breaking, structured logs, correlation IDs, and archive secret scanning.

**Milestone 3: durable execution.** Add a persistent job store, resumable task states, idempotency keys, and a worker process. Document deployment and data retention before exposing an API.

**Milestone 4: evaluation.** Build a small benchmark of representative prompts and compare quality, latency, cost, retry rate, and context reduction across routing policies. Treat model routing as an empirically measured policy rather than a fixed hierarchy.

## Verification checklist

The current handoff is ready when the following commands succeed from the repository root:

```bash
python examples/offline_demo.py
python -m unittest discover -s tests -p 'test_*.py'
python -m zipfile -l dist/cascade-project.zip
```

Before accepting real credentials or publishing a release, also verify that the archive contains no `.env` files, private keys, tokens, caches, or `.git` data; confirm the selected license; and document the provider adapter’s privacy and retention behavior.

## References

[1]: https://docs.python.org/3/library/asyncio.html "Python asyncio documentation"
[2]: https://docs.python.org/3/library/zipfile.html "Python zipfile documentation"
[3]: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/429 "MDN HTTP 429 Too Many Requests"
[4]: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Retry-After "MDN Retry-After header"
