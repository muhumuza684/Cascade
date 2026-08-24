"""Run Cascade locally with deterministic fake providers.

Usage: python examples/offline_demo.py
"""

import asyncio
from pathlib import Path

from cascade.dispatcher import CascadeDispatcher, Level, Task, create_zip


class EchoProvider:
    def __init__(self, label: str) -> None:
        self.label = label

    async def complete(self, prompt: str, *, system: str = "") -> str:
        return f"[{self.label}] {prompt}"


async def main() -> None:
    dispatcher = CascadeDispatcher({
        1: Level("shaper", EchoProvider("level-1"), concurrency=2),
        2: Level("builder", EchoProvider("level-2"), concurrency=2),
        3: Level("aggregator", EchoProvider("level-3"), concurrency=1),
    })
    results = await dispatcher.run([
        Task("Summarize the project goal", level=1, task_id="shape-1"),
        Task("Design the provider adapter interface", level=2, task_id="build-1"),
    ])
    for result in results:
        print(result)

    output = create_zip(Path(__file__).parents[1], Path("dist/cascade-project.zip"))
    print(f"Created {output}")


if __name__ == "__main__":
    asyncio.run(main())
