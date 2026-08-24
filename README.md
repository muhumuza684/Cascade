# Project Cascade

> **Distribute the flow. Prevent the flood.**

Project Cascade is a Python starter implementation for a tiered AI task-routing system. It turns a large request into smaller units, assigns those units to logical capability levels, limits concurrency, retries transient failures with bounded backoff, and packages the resulting project locally as a ZIP archive.

The repository began as an empty GitHub repository. Its initial design is based on the attached notes, which describe three main levels: a small model for prompt shaping and decomposition, a medium model for focused code work and review, and a larger model for integration and final aggregation. The implementation intentionally keeps provider-specific SDK code outside the core so that the system can be tested offline and adapted to any provider.

## What Cascade does

Cascade is an orchestration layer, not an AI model and not a method for defeating provider policies. It provides a controlled way to reduce unnecessary context, pace requests, run independent work concurrently, and reserve expensive reasoning for tasks that need it. A provider adapter is responsible for translating the generic `Provider.complete()` interface to a specific API.

| Level | Typical responsibility | Typical input | Expected output |
|---|---|---|---|
| Level 1 | Prompt shaping, classification, summarization, task splitting | Raw user request or large context | Compact task plan |
| Level 2 | Focused implementation, review, debugging, testing | One bounded subtask | Code, analysis, or review result |
| Level 3 | Integration, conflict resolution, final synthesis | Level 1 plan plus Level 2 results | Final answer, patch, or build plan |

The level numbers are configuration labels rather than fixed model names. A production deployment should choose models according to quality, latency, context window, privacy requirements, and provider terms. The repository does not hard-code third-party credentials or model identifiers.

## Repository map

| Path | Purpose |
|---|---|
| `cascade/dispatcher.py` | Core provider protocol, task model, rate limiter, retry policy, dispatcher, and ZIP helper |
| `cascade/__init__.py` | Public package exports |
| `examples/offline_demo.py` | Runnable demonstration that needs no API key or network connection |
| `tests/test_cascade.py` | Offline tests for routing and safe archive creation |
| `RESEARCH.md` | Detailed research and handoff notes, including design decisions, risks, and roadmap |
| `REPO_FINDINGS.md` | Initial repository-state notes captured during setup |

## Requirements

Cascade uses the Python standard library for its core functionality. Python **3.10 or newer** is recommended because the implementation uses modern type annotations. No provider SDK is required to run the offline example or the tests.

## Quick start

Clone the repository, optionally create a virtual environment, and run the offline example:

```bash
git clone https://github.com/muhumuza684/Cascade.git
cd Cascade
python -m venv .venv
source .venv/bin/activate
python examples/offline_demo.py
```

The example prints the results returned by three logical levels and creates `dist/cascade-project.zip`. On Windows PowerShell, activate the environment with `.venv\\Scripts\\Activate.ps1`.

Run the tests with:

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

If `pytest` is installed, the same tests can also be run with `pytest -q`.

## Core usage

A provider only needs an asynchronous `complete` method:

```python
class MyProvider:
    async def complete(self, prompt: str, *, system: str = "") -> str:
        # Translate this method into your provider SDK call.
        return await call_your_provider(prompt, system=system)
```

Configure levels and submit tasks:

```python
import asyncio
from cascade import CascadeDispatcher, Level, Task

async def main():
    provider = MyProvider()
    dispatcher = CascadeDispatcher({
        1: Level("shaper", provider, concurrency=2),
        2: Level("builder", provider, concurrency=2),
        3: Level("aggregator", provider, concurrency=1),
    })
    results = await dispatcher.run([
        Task("Turn the request into three subtasks", level=1, task_id="plan"),
        Task("Review the authentication module", level=2, task_id="review"),
    ])
    print(results)

asyncio.run(main())
```

Each result includes the task ID, level, provider output, and caller-supplied metadata. The dispatcher processes levels in the order they appear in the submitted task groups; applications that require a strict Level 1 → Level 2 → Level 3 pipeline should use `pipeline()` and provide a splitter and aggregator function.

## Rate limits and retries

`AsyncRateLimiter` spaces calls for a configured level. `RetryPolicy` performs a bounded exponential backoff after an adapter raises an exception. These controls are deliberately conservative: they help a client behave predictably, but they do not guarantee quota availability and must not be used to evade provider restrictions. A production adapter should distinguish retryable errors such as temporary service failures from permanent authentication, validation, or policy errors. When an HTTP service returns `429 Too Many Requests`, the adapter should honor the provider's documented reset behavior and any `Retry-After` value rather than blindly retrying.

Independent tasks can run concurrently through the level semaphore, but concurrency should be set below the provider's documented limits. Using multiple providers may improve resilience when the user is authorized to use each provider, yet every provider's terms, quotas, privacy rules, and billing must still be followed.

## Packaging

The local helper creates a ZIP archive with deterministic, relative paths and excludes `.git`, Python cache directories, and pytest cache directories by default:

```python
from cascade import create_zip

create_zip(".", "dist/cascade-project.zip")
```

The archive is created by the host Python process. An AI response should provide code or structured data for packaging; the host program should perform the actual binary archive operation. This keeps the boundary explicit and avoids putting credentials or binary data into prompts.

## Provider integration checklist

A provider adapter should keep credentials in environment variables or a secret manager, set explicit timeouts, normalize the provider response into a string, classify errors, log request IDs without logging sensitive prompts, and make its model, region, and data-retention behavior configurable. It should also include a small integration test that is opt-in and never runs in the default offline test suite.

## Current limitations

This first commit is a framework skeleton rather than a complete multi-provider product. It does not include provider SDKs, persistent queues, durable state, token accounting, an HTTP API, distributed workers, authentication, a web dashboard, or automatic model selection. The splitter and aggregator are caller-provided so that the repository stays dependency-free and easy to pick up.

The retry implementation catches exceptions from the generic provider boundary. Before production use, replace broad retry behavior with an adapter-specific exception policy and add timeouts, cancellation handling, tracing, and a durable job store.

## Roadmap

The recommended next sequence is to add one provider adapter behind environment-based configuration, introduce a structured JSON task schema, add token and latency metrics, implement provider-aware retry classification, and then add a durable queue. Only after those foundations are tested should the project add a web interface or distributed workers.

## License

No license has been selected yet. Before redistributing or accepting external contributions, choose a license and add a `LICENSE` file.

## References

[1]: https://docs.python.org/3/library/asyncio.html "Python asyncio documentation"
[2]: https://docs.python.org/3/library/zipfile.html "Python zipfile documentation"
[3]: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/429 "MDN HTTP 429 Too Many Requests"
[4]: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Retry-After "MDN Retry-After header"
