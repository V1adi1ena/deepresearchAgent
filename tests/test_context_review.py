import asyncio
import copy
import json
import time
from types import SimpleNamespace

from src.adversarial.blue_agent import BlueAgent
from src.adversarial.loop import AdversarialLoop
from src.adversarial.verdict import Issue, Severity, Dimension, FixType, FixOperation, RedVerdict
from src.compressor.compressor import ContextCompressor
from src.memory.long_term import MemoryEntry
from src.memory.memory_store import SharedMemoryStore
from src.orchestrator.schemas import ResearchReport
from src.utils.async_call import call_model


class Embedding:
    dim = 2
    def encode(self, text): return [1.0, 0.0]
    def encode_batch(self, texts): return [self.encode(t) for t in texts]


def test_compression_keeps_tool_protocol_and_source_mapping():
    compressor = ContextCompressor(None, embedder=Embedding(), budget=100, output_reserve=10)
    compressor.summarizer = SimpleNamespace(summarize_document=lambda *a, **k: "gold fact 30",
        summarize_documents=lambda *a, **k: "gold fact 30")
    messages = [{"role": "assistant", "content": "", "tool_calls": [{"id": "call_A"}]},
        {"role": "tool", "tool_call_id": "call_A", "content": json.dumps({"results": [
            {"url": "https://example.test/a", "snippet": "gold fact 30 " * 500}]})}]
    compressed = compressor.compress_messages(messages, "gold fact")
    assert compressed[0] == messages[0]
    assert compressed[1]["tool_call_id"] == "call_A"
    payload = json.loads(compressed[1]["content"])
    assert payload["sources"][0]["url"] == "https://example.test/a"
    assert len(compressed[1]["content"]) < len(messages[1]["content"])
    assert "gold fact 30" in payload["evidence"]


def test_similarity_does_not_merge_changed_values_or_negation(tmp_path):
    store = SharedMemoryStore(str(tmp_path / "memory.db"), embedder=Embedding(), session_id="one")
    def entry(key, claim):
        return MemoryEntry(key, claim, "fixture", .9, "agent", time.time(), "primary", [1, 0], "topic")
    a = entry("one:run1:A", "The measured deployment cost is 10 units in the reference experiment.")
    b = entry("one:run2:A", "The measured deployment cost is not 10 units in the reference experiment.")
    store.put(a)
    store.put(b)
    assert len(store._entry_ids) == 2
    other = SharedMemoryStore(str(tmp_path / "memory.db"), embedder=Embedding(), session_id="two")
    assert other.query_by_similarity("deployment") == []


def issue():
    return Issue(severity=Severity.MAJOR, dimension=Dimension.FACTUAL,
        description="Incorrect number", location="count", fix_type=FixType.SUPPLEMENTARY,
        evidence="Source states 30")


def test_failed_supplementary_search_does_not_invent_repair():
    class Search:
        name = "web_search"
        async def execute(self, query): return {"error": "offline"}
    policy = lambda messages: (_ for _ in ()).throw(AssertionError("No model call without evidence"))
    blue = BlueAgent(policy, [Search()])
    report = ResearchReport("query", "count=300")
    operation = asyncio.run(blue._do_supplementary_search(report, issue()))
    assert not operation.success and report.content == "count=300" and not report.sources


def test_supplementary_sources_are_registered():
    class Search:
        name = "web_search"
        async def execute(self, query):
            return {"results": [{"url": "https://example.test/new", "snippet": "count=30"}]}
    blue = BlueAgent(lambda m: SimpleNamespace(content='{"fixed_content":"count=30","changes":[]}'), [Search()])
    # Isolate parser format here; the assertion targets source registry integration.
    blue._parse_fix_json = lambda raw: ("count=30", ["number corrected"])
    report = ResearchReport("query", "count=300")
    operation = asyncio.run(blue._do_supplementary_search(report, issue()))
    assert operation.success and report.sources[0]["url"] == "https://example.test/new"


def test_review_score_is_for_published_report_not_original():
    class Red:
        async def attack(self, report):
            correct = report.content == "count=30"
            return RedVerdict({Dimension.FACTUAL: 9 if correct else 2}, 9 if correct else 2, [] if correct else [issue()])
    class Blue:
        async def defend(self, report, verdict):
            fixed = copy.deepcopy(report)
            fixed.content = "count=30"
            return fixed, [FixOperation(issue(), "fix", True, "source fixture")]
    original = ResearchReport("query", "count=300")
    result, history = asyncio.run(AdversarialLoop(Red(), Blue(), max_rounds=1).run(original))
    assert original.content == "count=300" and result.content == "count=30"
    assert result.final_score == 9 and history[0]["score_before"] == 2
    assert history[0]["before_version"] != history[0]["after_version"]


def test_review_call_budget_prevents_unscored_candidate_publication():
    class Red:
        async def attack(self, report):
            await call_model(lambda m: {}, [])
            return RedVerdict({Dimension.FACTUAL: 2}, 2, [issue()])
    class Blue:
        async def defend(self, report, verdict):
            fixed = copy.deepcopy(report)
            fixed.content = "unverified modification"
            return fixed, []
    original = ResearchReport("query", "count=300")
    result, history = asyncio.run(AdversarialLoop(Red(), Blue(), max_model_calls=1).run(original))
    assert result.content == original.content
    assert history[0]["stop_reason"] == "model_budget_exhausted"


def test_failed_self_verification_reverts_candidate():
    blue = BlueAgent(lambda m: SimpleNamespace(content="not valid verification JSON"))
    blue._parse_fix_json = lambda raw: ("count=30", ["fixture fix"])
    problem = issue()
    problem.fix_type = FixType.IN_PLACE
    report = ResearchReport("query", "count=300", sources=[{"url": "https://example.test/a", "snippet": "count=30"}])
    result, operations = asyncio.run(blue.defend(report, RedVerdict(issues=[problem])))
    assert result.content == report.content
    assert not operations[0].success and operations[0].detail["reverted"]


def test_self_verification_uses_source_evidence_not_wrong_original():
    prompts = []
    def policy(messages):
        prompts.append(messages[-1]["content"])
        return SimpleNamespace(content='{"has_new_issue":false,"new_issues":[]}')
    blue = BlueAgent(policy)
    blue._parse_fix_json = lambda raw: ("count=30", ["corrected using source"])
    problem = issue()
    problem.fix_type = FixType.IN_PLACE
    report = ResearchReport("query", "count=300", sources=[{"url": "https://example.test/a", "snippet": "count=30"}])
    result, operations = asyncio.run(blue.defend(report, RedVerdict(issues=[problem])))
    assert result.content == "count=30" and operations[0].success
    assert "Authoritative evidence" in prompts[-1] and "count=30" in prompts[-1]
