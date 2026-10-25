import asyncio
import json
import time
from collections import Counter
from types import SimpleNamespace

import pytest

from src.orchestrator.orchestrator import Orchestrator
from src.orchestrator.schemas import AgentResult, AgentStatus, RunConfig, SubTask, TaskType
from src.planner.dag import DAG
from src.planner.planner import Planner, PlanParseError
from src.agents.researcher import ResearcherAgent
from src.utils.async_call import call_sync


class Policy:
    def __init__(self):
        self.prompts = []

    def __call__(self, messages):
        self.prompts.append(messages)
        return {"content": "Supported findings [1]. Overall Confidence: 0.9"}


class Plan:
    _last_raw_json = "{}"

    def __init__(self, tasks, replacement=None):
        self.tasks, self.replacement = tasks, replacement

    def generate_plan(self, *args):
        graph = DAG()
        for task in self.tasks:
            graph.add_node(task.task_id)
            for dep in task.dependencies:
                graph.add_edge(dep, task.task_id)
        return graph

    def get_task_map_from_dag(self, *args):
        return {task.task_id: task for task in self.tasks}

    def replan(self, **kwargs):
        self.tasks = self.replacement or self.tasks
        return self.generate_plan()


class Pool:
    def __init__(self, fail=(), slow=None, transient=()):
        self.fail, self.slow, self.transient = fail, slow or {}, transient
        self.calls, self.contexts = Counter(), {}
        self.active = self.peak = 0

    async def get_agent(self, task_type):
        return self

    async def release_agent(self, agent):
        pass

    async def run(self, task, context):
        self.calls[task.task_id] += 1
        self.contexts[task.task_id] = context
        if task.task_id in self.transient and self.calls[task.task_id] == 1:
            raise ConnectionError("transient")
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(self.slow.get(task.task_id, .001))
        finally:
            self.active -= 1
        if task.task_id in self.fail:
            return AgentResult(task.task_id, AgentStatus.FAILED, output="tool failed")
        return AgentResult(task.task_id, AgentStatus.SUCCESS, output="EVIDENCE_" + task.task_id,
            confidence=.9, trajectory=[{"role": "tool", "result": {"results": [
                {"url": "https://example.test/" + task.task_id, "snippet": "verified fixture"}]}}])


def task(name, deps=(), timeout=1):
    return SubTask(name, TaskType.SEARCH, "research " + name, dependencies=list(deps), timeout_seconds=timeout)


def execute(tasks, pool=None, **config):
    pool = pool or Pool()
    policy = Policy()
    engine = Orchestrator(Plan(tasks), pool, summarizer_policy=policy)
    report = asyncio.run(engine.run("fixture", RunConfig(enable_adversarial=False, max_replan_rounds=0, **config)))
    return report, engine, pool, policy


def test_dependency_reaches_actual_prompt_without_context_keys():
    report, _, pool, _ = execute([task("A"), task("B", ["A"])])
    prompt = ResearcherAgent("probe", None)._build_task_prompt(task("B", ["A"]), pool.contexts["B"])
    assert "EVIDENCE_A" in prompt
    assert report.status == "completed"


def test_failed_dependency_blocks_child_but_keeps_independent_evidence():
    report, _, pool, _ = execute([task("A"), task("B", ["A"]), task("C")], Pool(fail={"A"}))
    assert pool.calls["B"] == 0
    assert report.status == "partial" and set(report.incomplete_tasks) == {"A", "B"}


def test_all_failed_is_not_a_long_successful_report():
    report, _, _, policy = execute([task("A")], Pool(fail={"A"}))
    assert report.status == "failed" and not policy.prompts


def test_concurrency_and_transient_retry():
    _, _, pool, _ = execute([task(str(i)) for i in range(5)], Pool(transient={"0"}), max_concurrent=2)
    assert pool.peak <= 2 and pool.calls["0"] == 2


def test_replan_reuses_success_and_final_synthesis_contains_it():
    policy, pool = Policy(), Pool(fail={"B", "C", "D"})
    planner = Plan([task(n) for n in "ABCD"], [task("A"), task("E", ["A"])])
    engine = Orchestrator(planner, pool, summarizer_policy=policy)
    report = asyncio.run(engine.run("fixture", RunConfig(enable_adversarial=False, max_replan_rounds=1)))
    assert pool.calls["A"] == 1 and pool.calls["E"] == 1
    assert "EVIDENCE_A" in str(policy.prompts) and "EVIDENCE_E" in str(policy.prompts)
    assert report.num_replan == 1 and report.status == "completed"


def test_global_deadline_reserves_bounded_synthesis():
    async def check():
        pool, policy = Pool(slow={"B": 2}), Policy()
        engine = Orchestrator(Plan([task("A"), task("B")]), pool, summarizer_policy=policy)
        start = time.monotonic()
        report = await engine.run("fixture", RunConfig(enable_adversarial=False, global_timeout_seconds=1))
        assert time.monotonic()-start < 2
        assert report.status == "partial" and "B" in report.incomplete_tasks
        assert policy.prompts  # The original timeout branch never synthesized.
    asyncio.run(check())


def test_stage_timeout_blocks_dependent_task():
    report, _, pool, _ = execute([task("A", timeout=.01), task("B", ["A"])], Pool(slow={"A": .1}))
    assert pool.calls["B"] == 0 and report.status == "failed"


def test_cancelled_thread_result_is_not_committed():
    async def check():
        committed = []
        async def work():
            value = await call_sync(lambda: (time.sleep(.06), "late")[1])
            committed.append(value)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(work(), .01)
        await asyncio.sleep(.09)
        assert committed == []
    asyncio.run(check())


@pytest.mark.parametrize("items", [
    [{"task_id": "A"}, {"task_id": "A"}],
    [{"task_id": "B", "dependencies": ["missing"]}],
    [{"task_id": "A", "dependencies": ["B"]}, {"task_id": "B", "dependencies": ["A"]}],
    [],
])
def test_invalid_plan_is_rejected(items):
    planner = Planner(policy=None)
    with pytest.raises((PlanParseError, ValueError)):
        planner._parse_plan(json.dumps({"sub_tasks": items}))


def test_run_scoped_memory_ids_and_query_context():
    entries = []
    memory = SimpleNamespace(session_id="session", put=entries.append,
        get_context_for_query=lambda *a, **k: "MEMORY_EVIDENCE")
    pool = Pool()
    engine = Orchestrator(Plan([task("A")]), pool, memory_store=memory, summarizer_policy=Policy())
    for _ in range(2):
        asyncio.run(engine.run("fixture", RunConfig(enable_adversarial=False)))
    assert len({entry.entry_id for entry in entries}) == 2
    assert pool.contexts["A"]["research_memory"] == "MEMORY_EVIDENCE"


def test_outer_cancellation_cleans_up_workers():
    async def check():
        pool = Pool(slow={"A": 1})
        engine = Orchestrator(Plan([task("A")]), pool, summarizer_policy=Policy())
        job = asyncio.create_task(engine.run("fixture"))
        await asyncio.sleep(.02)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
        assert pool.active == 0 and not engine._running
        assert not engine._results
    asyncio.run(check())


def test_researcher_performs_real_tool_protocol_with_fixture():
    class Tool:
        name = "web_search"
        def get_openai_tool_schema(self):
            return {"type": "function", "function": {"name": self.name}}
        async def execute(self, query):
            return {"results": [{"url": "https://example.test/source", "snippet": "count=30"}]}
    class RecordedPolicy:
        def __init__(self): self.messages = []
        def set_tools(self, tools): pass
        def __call__(self, messages):
            self.messages.append(messages)
            if any(m["role"] == "tool" for m in messages):
                return {"content": "The retrieved count is 30. Confidence: 0.9"}
            return {"tool_calls": [{"id": "call_1", "function": {"name": "web_search", "arguments": '{"query":"count"}'}}]}
    policy = RecordedPolicy()
    agent = ResearcherAgent("fixture", policy, [Tool()])
    result = asyncio.run(agent.run(task("A"), {}))
    assert result.status == AgentStatus.SUCCESS
    assert result.trajectory[-1]["role"] == "assistant"
    assert any(t.get("result", {}).get("results") for t in result.trajectory)


def test_timed_out_agents_are_not_reused():
    from src.orchestrator.agent_pool import AgentPool
    async def check():
        pool = AgentPool(Policy)
        agent = await pool.get_agent(TaskType.ANALYZE)
        agent._discard = True
        await pool.release_agent(agent)
        other = await pool.get_agent(TaskType.ANALYZE)
        assert other is not agent
        await pool.release_agent(other)
        assert pool.get_stats()["analyze"]["active"] == 0
    asyncio.run(check())


def test_replanner_can_reference_completed_task_without_regenerating_it():
    payload = {"sub_tasks": [{"task_id": "B", "dependencies": ["A"], "description": "use A"}]}
    planner = Planner(policy=lambda messages: {"content": json.dumps(payload)})
    planner._parse_plan(json.dumps({"sub_tasks": [{"task_id": "A", "description": "original"}]}))
    graph = planner.replan("fixture", [], [AgentResult("A", AgentStatus.SUCCESS, output="evidence", confidence=.9)], "retry")
    assert set(graph) == {"A", "B"}
    assert planner._last_task_map["A"].description == "original"


def test_review_timeout_retains_complete_report_and_is_visible():
    class SlowReview:
        async def run(self, report):
            await asyncio.sleep(1)
    async def check():
        engine = Orchestrator(Plan([task("A")]), Pool(), summarizer_policy=Policy(),
                              adversarial_loop=SlowReview())
        report = await engine.run("fixture", RunConfig(global_timeout_seconds=.15))
        assert report.content.startswith("Supported findings")
        assert report.review_status == "timeout" and report.status == "completed"
    asyncio.run(check())
