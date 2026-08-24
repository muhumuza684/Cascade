import asyncio
import tempfile
import unittest
import zipfile
from pathlib import Path

from cascade.dispatcher import CascadeDispatcher, Level, Task, create_zip


class FakeProvider:
    async def complete(self, prompt: str, *, system: str = "") -> str:
        return f"done:{prompt}"


class CascadeTests(unittest.TestCase):
    def test_dispatcher_routes_tasks_by_level(self):
        dispatcher = CascadeDispatcher({1: Level("small", FakeProvider(), concurrency=2)})
        results = asyncio.run(dispatcher.run([Task("one", task_id="a"), Task("two", task_id="b")]))
        self.assertEqual([item["output"] for item in results], ["done:one", "done:two"])
        self.assertTrue(all(item["level"] == 1 for item in results))

    def test_create_zip_excludes_vcs_and_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            root.mkdir()
            (root / "README.md").write_text("hello", encoding="utf-8")
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("private", encoding="utf-8")
            destination = Path(temporary) / "out.zip"
            create_zip(root, destination)
            with zipfile.ZipFile(destination) as archive:
                self.assertEqual(archive.namelist(), ["README.md"])


if __name__ == "__main__":
    unittest.main()
