import importlib.util
from pathlib import Path
from types import SimpleNamespace

from src.core.runner import initialize_modules
from src.models.model_router import ModelRouter


def test_disabled_modules_are_not_constructed(monkeypatch):
    import src.core.runner as runner
    import src.compressor.compressor as compression
    import src.memory.memory_store as memory
    def forbidden(*args, **kwargs):
        raise AssertionError("Disabled module was constructed")
    monkeypatch.setattr(compression, "ContextCompressor", forbidden)
    monkeypatch.setattr(memory, "SharedMemoryStore", forbidden)
    monkeypatch.setattr(ModelRouter, "create_backend", lambda *a, **k: SimpleNamespace())
    monkeypatch.setattr(runner, "_create_tools_factory", lambda c: [])
    modules = initialize_modules({"compressor": {"enable_multilevel": False}, "memory": {"enabled": False}})
    assert modules["compressor"] is None and modules["memory_store"] is None
    assert modules["orchestrator"].compressor is None


def test_integration_test_preserves_project_data_and_uses_isolated_paths(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("continuous", Path(__file__).with_name("continuous_test.py"))
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    (tmp_path / "data").mkdir()
    database = tmp_path / "data/memory.db"
    database.write_bytes(b"preserve")
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    monkeypatch.setattr(script, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(script.tempfile, "mkdtemp", lambda **k: str(isolated))
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout="", stderr="", returncode=0)
    monkeypatch.setattr(script.subprocess, "run", run)
    script.run_single_test(script.TEST_QUERIES[0])
    args = calls[0]
    assert database.read_bytes() == b"preserve"
    assert args[args.index("--memory_db") + 1] == str(isolated / "memory.db")
    assert "--session_id" in args


def test_tool_journal_counts_failures_instead_of_only_accepted_evidence():
    import asyncio
    from src.utils.async_call import track_tool, tool_call_records
    class Tool:
        name = "search"
        async def execute(self, fail=False):
            return {"error": "fixture"} if fail else {"results": []}
    async def check():
        records = []
        token = tool_call_records.set(records)
        try:
            tool = track_tool(Tool())
            await tool.execute()
            await tool.execute(fail=True)
            assert [r["status"] for r in records] == ["completed", "failed"]
        finally:
            tool_call_records.reset(token)
    asyncio.run(check())
