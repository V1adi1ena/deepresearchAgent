"""Regression cases discovered in the first real multi-question run."""
import asyncio
from types import SimpleNamespace

import pytest

from scripts.run_interview_checks import technical_checks
from src.agents.summarizer import SummarizerAgent
from src.models.vllm_policy import VLLMPolicy
from src.orchestrator.schemas import AgentResult, AgentStatus, ResearchReport, SubTask, TaskType
from src.adversarial.red_agent import RedAgent
from src.adversarial.verdict import Dimension, Issue, Severity, FixOperation, RedVerdict
from src.adversarial.blue_agent import BlueAgent
from src.utils.async_call import model_call_records, model_budget
from src.planner.planner import Planner


def test_empty_partial_and_unreviewed_reports_cannot_pass():
    source = [{"url": "https://example.test/source"}]
    for report in (ResearchReport("q", "", sources=source),
                   ResearchReport("q", "Incomplete tasks: task_2", sources=source, status="partial"),
                   ResearchReport("q", "Supported findings", sources=source, review_status="timeout")):
        assert not all(technical_checks(report, [], review_required=True).values())
    good = ResearchReport("q", "Supported findings", sources=source, review_status="completed")
    assert all(technical_checks(good, [], review_required=True).values())
    assert not all(technical_checks(good, [{"error": "embedding unavailable"}]).values())


@pytest.mark.parametrize("content,reason", [("", "stop"), ("cut off", "length")])
def test_synthesizer_rejects_empty_and_truncated_outputs(content, reason):
    evidence = AgentResult("search", AgentStatus.SUCCESS, output="count=30", trajectory=[
        {"role": "tool", "result": {"results": [{"url": "https://example.test/source", "snippet": "count=30"}]}}])
    agent = SummarizerAgent("fixture", lambda m: {"content": content, "finish_reason": reason})
    result = asyncio.run(agent.run(SubTask("summary", TaskType.ANALYZE, "summarize"),
                                    {"query": "q", "results": [evidence]}))
    assert result.status == AgentStatus.FAILED


@pytest.mark.parametrize("content,reason", [("", "stop"), ("cut off", "length")])
def test_model_records_incomplete_response_instead_of_accepting_it(content, reason):
    policy = VLLMPolicy(base_url="https://example.test", api_key="fixture", thinking="disabled")
    captured = {}
    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(finish_reason=reason,
            message=SimpleNamespace(content=content, tool_calls=None))])
    policy.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    records = []
    token = model_call_records.set(records)
    try:
        with pytest.raises(RuntimeError):
            policy([{"role": "user", "content": "fixture"}])
    finally:
        model_call_records.reset(token)
    assert records[0]["status"] == "failed"
    assert records[0]["finish_reason"] == reason
    assert captured["extra_body"] == {"thinking": {"type": "disabled"}}


@pytest.mark.parametrize("raw", ["", "not JSON", '{}', '{"score":8,"issues":"missing"}'])
def test_malformed_review_is_not_a_successful_no_issue_verdict(raw):
    red = RedAgent(lambda m: SimpleNamespace(content=raw), dimensions=[Dimension.FACTUAL])
    with pytest.raises(RuntimeError, match="Review evaluation failed"):
        asyncio.run(red.attack(ResearchReport("q", "count=30")))


def test_fix_round_is_bounded_and_prioritizes_critical_issue():
    blue = BlueAgent(None, max_fixes_per_round=1)
    seen = []
    async def fix(report, issue):
        seen.append(issue.severity)
        return FixOperation(issue, "fixture", False, "no change")
    blue._fix_single_issue = fix
    problems = [Issue(Severity.MINOR, Dimension.FACTUAL, "minor"),
                Issue(Severity.CRITICAL, Dimension.FACTUAL, "critical")]
    asyncio.run(blue.defend(ResearchReport("q", "original"), RedVerdict(issues=problems)))
    assert seen == [Severity.CRITICAL]


def test_fix_does_not_consume_calls_reserved_for_candidate_review():
    blue = BlueAgent(None)
    async def forbidden(*args):
        raise AssertionError("Insufficient budget for a verified candidate")
    blue._fix_single_issue = forbidden
    token = model_budget.set({"used": 2, "limit": 5, "post_review_calls": 2})
    try:
        result, operations = asyncio.run(blue.defend(ResearchReport("q", "original"),
            RedVerdict(issues=[Issue(Severity.CRITICAL, Dimension.FACTUAL, "wrong number")])))
    finally:
        model_budget.reset(token)
    assert result.content == "original" and operations == []


def test_review_and_verification_keep_tail_and_stable_source_ids():
    prompts = []
    def policy(messages):
        prompts.append(messages[-1]["content"])
        return SimpleNamespace(content='{"score":9,"issues":[]}')
    sources = [{"source_id": f"s_{i}", "url": f"https://example.test/{i}", "snippet": "count=30"}
               for i in range(20)]
    text = "prefix " * 700 + "TAIL_EVIDENCE"
    asyncio.run(RedAgent(policy, dimensions=[Dimension.FACTUAL]).attack(ResearchReport("q", text, sources)))
    assert "TAIL_EVIDENCE" in prompts[-1] and "[s_19]" in prompts[-1]
    blue = BlueAgent(policy)
    asyncio.run(blue._self_verify(text, text + " corrected", [], sources=sources))
    assert "TAIL_EVIDENCE corrected" in prompts[-1] and "[s_19]" in prompts[-1]


def test_planning_instructions_obey_small_task_budget_without_conflicting_counts():
    planner = Planner(None)
    planner.max_tasks = 2
    for memory in ("", "previous evidence"):
        prompt = planner._build_prompt("Compare five vendors", memory)
        assert "Generate 1 to 2 sub_tasks" in prompt
        assert "6-10" not in prompt and "3 to 8" not in prompt


def test_unchanged_repair_is_not_counted_as_successful_fix():
    blue = BlueAgent(None)
    async def no_change(report, issue):
        return FixOperation(issue, "fixture", True, "model returned the original")
    blue._fix_single_issue = no_change
    result, operations = asyncio.run(blue.defend(ResearchReport("q", "original"),
        RedVerdict(issues=[Issue(Severity.MAJOR, Dimension.FACTUAL, "wrong fact")])))
    assert result.content == "original" and not operations[0].success
    assert operations[0].detail["no_change"]
