"""Core orchestration primitives for Project Cascade.

Cascade deliberately keeps provider integrations behind a small protocol so the
routing and packaging logic can be tested without network access or API keys.
"""

from __future__ import annotations

import asyncio
import json
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Protocol


class Provider(Protocol):
    """Minimal async provider contract used by the dispatcher."""

    async def complete(self, prompt: str, *, system: str = "") -> str:
        ...


@dataclass(frozen=True)
class Task:
    """A unit of work submitted to Cascade."""

    prompt: str
    level: int = 1
    task_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetryPolicy:
    """Bounded exponential backoff settings for transient provider failures."""

    attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0

    def delay_for(self, failed_attempt: int) -> float:
        return min(self.max_delay, self.base_delay * (2 ** failed_attempt))


class AsyncRateLimiter:
    """Simple spacing limiter; it does not attempt to bypass provider quotas."""

    def __init__(self, calls_per_minute: float) -> None:
        if calls_per_minute <= 0:
            raise ValueError("calls_per_minute must be positive")
        self.interval = 60.0 / calls_per_minute
        self._last_call = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            pause = self.interval - (now - self._last_call)
            if pause > 0:
                await asyncio.sleep(pause)
            self._last_call = time.monotonic()


@dataclass
class Level:
    """Configuration for one logical Cascade level."""

    name: str
    provider: Provider
    limiter: AsyncRateLimiter | None = None
    concurrency: int = 1
    system_prompt: str = ""


class CascadeDispatcher:
    """Route work through configured levels and return structured results.

    The dispatcher orchestrates calls; it does not claim to remove provider
    limits. It reduces pressure through decomposition, pacing, bounded retries,
    and selective use of more capable levels.
    """

    def __init__(self, levels: dict[int, Level], retry: RetryPolicy | None = None) -> None:
        if not levels:
            raise ValueError("at least one level is required")
        self.levels = levels
        self.retry = retry or RetryPolicy()

    async def _call(self, level: Level, prompt: str) -> str:
        last_error: Exception | None = None
        for attempt in range(self.retry.attempts):
            try:
                if level.limiter:
                    await level.limiter.wait()
                return await level.provider.complete(prompt, system=level.system_prompt)
            except Exception as exc:  # Provider adapters decide which errors are transient.
                last_error = exc
                if attempt + 1 == self.retry.attempts:
                    break
                await asyncio.sleep(self.retry.delay_for(attempt))
        assert last_error is not None
        raise last_error

    async def run(self, tasks: Iterable[Task]) -> list[dict[str, Any]]:
        grouped: dict[int, list[Task]] = {}
        for task in tasks:
            grouped.setdefault(task.level, []).append(task)

        results: list[dict[str, Any]] = []
        for level_number, level_tasks in grouped.items():
            level = self.levels.get(level_number)
            if level is None:
                raise KeyError(f"no configuration for level {level_number}")
            semaphore = asyncio.Semaphore(level.concurrency)

            async def run_one(task: Task) -> dict[str, Any]:
                async with semaphore:
                    output = await self._call(level, task.prompt)
                    return {"task_id": task.task_id, "level": level_number, "output": output, "metadata": task.metadata}

            results.extend(await asyncio.gather(*(run_one(task) for task in level_tasks)))
        return results

    async def pipeline(self, user_request: str, splitter: Callable[[str], Awaitable[list[Task]]], aggregator: Callable[[str, list[dict[str, Any]]], Awaitable[str]]) -> str:
        """Run a Level 1 split, execute returned tasks, then aggregate once."""
        tasks = await splitter(user_request)
        results = await self.run(tasks)
        return await aggregator(user_request, results)


def write_manifest(root: Path, output: Path) -> None:
    """Create a deterministic JSON manifest of files included in an archive."""
    files = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and path != output)
    output.write_text(json.dumps({"files": files}, indent=2) + "\n", encoding="utf-8")


def create_zip(source_dir: str | Path, output_zip: str | Path, *, exclude: Iterable[str] = (".git", "__pycache__", ".pytest_cache")) -> Path:
    """Package a project directory without including VCS or cache directories."""
    root = Path(source_dir).resolve()
    destination = Path(output_zip).resolve()
    excluded = set(exclude)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.resolve() == destination:
                continue
            relative_parts = path.relative_to(root).parts
            if any(part in excluded for part in relative_parts):
                continue
            archive.write(path, path.relative_to(root).as_posix())
    return destination
