import asyncio
import json
import pytest
from types import SimpleNamespace

from src.agents.researcher import ResearcherAgent
from src.adversarial.red_agent import RedAgent
from src.adversarial.verdict import Dimension
from src.orchestrator.schemas import AgentResult, AgentStatus, ResearchReport, SubTask, TaskType
from src.tools.browser import BrowserTool
from src.utils.retrieval import filter_search_results, evidence_excerpt
from src.utils.sources import extract_sources, result_sources


def test_scope_filter_rejects_wrong_versions_but_keeps_retrospectives():
    result = filter_search_results({"results": [
        {"title": "2026 Alpha3.5 performance", "url": "https://news.test/new"},
        {"title": "2026 model roundup", "url": "https://news.test/roundup"},
        {"title": "2026 retrospective on Alpha2.5", "url": "https://news.test/history"},
        {"title": "Review of 2024 published in 2026", "url": "https://news.test/2024"},
        {"title": "Alpha2.5 technical report", "url": "https://research.test/report"},
        {"title": "Alpha2.5 technical report", "url": "https://research.test.evil.test/report"},
    ]}, "比较2024年Alpha2.5", ["site:research.test Alpha2.5"])
    assert result["results"][0]["url"] == "https://research.test/report"
    assert not result["results"][-1]["preferred_domain"]
    assert len(result["rejected_results"]) == 2
    assert {r["url"] for r in result["results"]} >= {"https://news.test/history", "https://news.test/2024"}


def test_evidence_window_finds_late_benchmark_without_generating_facts():
    text = "unrelated navigation\n" * 400 + "Alpha2.5 | MMLU | 87.0\n" + "irrelevant\n" * 200
    excerpt = evidence_excerpt(text, "Alpha2.5 MMLU benchmark", 1600)
    assert "Alpha2.5 | MMLU | 87.0" in excerpt and len(excerpt) <= 1600
    assert all(piece in text for piece in excerpt.split("\n\n"))


def test_browser_preserves_table_cell_associations():
    text = BrowserTool()._extract_text("<main><table><tr><th>Model</th><th>MMLU</th></tr>"
        "<tr><td>Alpha2.5</td><td>87.0</td></tr></table></main>")
    assert "Model | MMLU" in text and "Alpha2.5 | 87.0" in text


def test_research_protocol_reads_page_and_persists_body_evidence():
    calls = []
    class Search:
        name = "web_search"
        def get_openai_tool_schema(self):
            return {"type": "function", "function": {"name": self.name}}
        async def execute(self, query):
            calls.append(("search", query))
            return {"query": query, "results": [{"url": "https://research.test/alpha",
                "title": "Alpha2.5 report", "snippet": "Abstract without results"}]}
    class Browser:
        name = "browser"
        def get_openai_tool_schema(self):
            return {"type": "function", "function": {"name": self.name}}
        async def execute(self, url, max_chars=8000, query=""):
            calls.append(("browser", url))
            return "Table: Alpha2.5 MMLU 87.0 in the evaluated setting."
    class Policy:
        def set_tools(self, tools): pass
        def __call__(self, messages):
            tools = [m for m in messages if m["role"] == "tool"]
            if not tools:
                return {"tool_calls": [{"id": "read_A", "function": {"name": "web_search",
                    "arguments": json.dumps({"query": "Alpha2.5 official MMLU"})}}]}
            assert "Alpha2.5 MMLU 87.0" in tools[-1]["content"]
            return {"content": "Alpha2.5 MMLU is 87.0 in this setting. Confidence: 0.8"}
    agent = ResearcherAgent("fixture", Policy(), [Search(), Browser()])
    task = SubTask("A", TaskType.SEARCH, "Alpha2.5 MMLU", search_hints=["site:research.test Alpha2.5"])
    result = asyncio.run(agent.run(task, {"query": "2024 Alpha2.5 MMLU"}))
    assert result.status == AgentStatus.SUCCESS
    assert calls == [("search", "site:research.test Alpha2.5 2024"), ("browser", "https://research.test/alpha")]
    source = result_sources([result])[0]
    assert source["evidence_kind"] == "page_excerpt" and "87.0" in source["snippet"]


def test_failed_page_read_stays_a_search_snippet_and_read_budget_is_bounded():
    class Search:
        name = "web_search"
        async def execute(self, query):
            return {"results": [{"url": f"https://example.test/{i}", "title": "Alpha2.5", "snippet": "Abstract"}
                                for i in range(5)]}
    class Browser:
        name = "browser"
        async def execute(self, url, max_chars=8000):
            return "[Browser Error] Access denied"
    agent = ResearcherAgent("fixture", None, [Search(), Browser()])
    state = {"scope": "Alpha2.5", "hints": [], "searches": 0, "reads": 0}
    async def check():
        first = await agent._retrieve("web_search", {"query": "Alpha2.5"}, state)
        second = await agent._retrieve("web_search", {"query": "Alpha2.5 report"}, state)
        third = await agent._retrieve("web_search", {"query": "Alpha2.5 again"}, state)
        assert len(first["page_reads"]) == 2 and not second["page_reads"]
        assert all(s["evidence_kind"] == "search_snippet" for s in extract_sources(first))
        assert third.get("error") and state["reads"] == state["searches"] == 2
    asyncio.run(check())


def test_later_search_summary_does_not_replace_body_excerpt_for_same_url():
    page = {"url": "https://example.test/report", "content": "body fact 30", "evidence_kind": "page_excerpt"}
    search = {"results": [{"url": page["url"], "title": "Source title", "snippet": "search abstract"}]}
    result = AgentResult("A", AgentStatus.SUCCESS, trajectory=[
        {"role": "tool", "result": search}, {"role": "tool", "result": page}, {"role": "tool", "result": search}])
    source = result_sources([result])[0]
    assert source["title"] == "Source title" and source["snippet"] == "body fact 30"


def test_reviewer_gets_cited_body_beyond_first_300_characters():
    prompts = []
    def policy(messages):
        prompts.append(messages[-1]["content"])
        return SimpleNamespace(content='{"score":9,"issues":[]}')
    report = ResearchReport("q", "Supported finding [s_abc]", sources=[
        {"source_id": "s_abc", "url": "https://example.test/a", "evidence_kind": "page_excerpt",
         "snippet": "context " * 100 + "GOLD_FACT_30"},
        {"source_id": "s_other", "url": "https://example.test/b", "snippet": "UNRELATED_EVIDENCE"}])
    asyncio.run(RedAgent(policy, dimensions=[Dimension.FACTUAL]).attack(report))
    assert "GOLD_FACT_30" in prompts[-1] and "UNRELATED_EVIDENCE" not in prompts[-1]


def test_publication_date_risk_is_preserved_even_when_title_matches():
    result = filter_search_results({"results": [
        {"title": "Alpha2.5 extension", "url": "https://research.test/new", "published_at": "2025-01-26"},
        {"title": "Alpha2.5 release", "url": "https://research.test/old", "published_at": "2024-09-19"},
    ]}, "2024 Alpha2.5", ["site:research.test"])
    assert result["results"][0]["url"].endswith("old")
    source = extract_sources(result)[1]
    assert source["scope_note"] == "later_publication_requires_date_check"
    assert source["published_at"] == "2025-01-26"


def test_planner_preserves_publisher_preferences_for_retrieval():
    from src.planner.planner import Planner
    planner = Planner(None)
    planner._parse_plan(json.dumps({"sub_tasks": [{"task_id": "A", "description": "Alpha2.5",
        "preferred_domains": ["research.test", "https://not-a-domain.test/path"]}]}))
    assert planner._last_task_map["A"].preferred_domains == ["research.test"]


def test_bocha_retains_long_summary_and_publication_date(monkeypatch):
    from src.tools.web_search import WebSearchTool
    class Response:
        status = 200
        async def json(self):
            return {"data": {"webPages": {"value": [{"name": "Alpha2.5 official report",
                "url": "https://research.test/report", "snippet": "short abstract",
                "summary": "Longer provider summary with a benchmark result", "datePublished": "2024-09-19"}]}}}
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    tool = WebSearchTool(backend="bocha", api_key="fixture")
    captured = {}
    def post(*args, **kwargs):
        captured.update(kwargs["json"])
        return Response()
    monkeypatch.setattr(tool, "_get_session", lambda: SimpleNamespace(post=post))
    result = asyncio.run(tool.execute("Alpha2.5", domains=["research.test"]))
    item = result["results"][0]
    assert item["snippet"].startswith("Longer provider summary")
    assert item["evidence_kind"] == "search_summary" and item["published_at"] == "2024-09-19"
    assert captured["include"] == "research.test"


def test_matching_version_outranks_unrelated_paper_on_preferred_domain():
    result = filter_search_results({"results": [
        {"url": "https://papers.test/a", "title": "Chinese metaphor generation"},
        {"url": "https://news.test/b", "title": "Alpha2.5 release"},
    ]}, "2024 Alpha2.5", ["site:papers.test"])
    assert result["results"][0]["url"] == "https://news.test/b"


def test_known_publisher_preference_constrains_broad_query():
    calls = []
    class Search:
        name = "web_search"
        async def execute(self, query):
            calls.append(query)
            return {"results": []}
    agent = ResearcherAgent("fixture", None, [Search()])
    state = {"scope": "Alpha2.5", "hints": [], "domains": ["research.test"], "searches": 0, "reads": 0}
    asyncio.run(agent._retrieve("web_search", {"query": "Alpha2.5 facts"}, state))
    assert calls == ["Alpha2.5 facts site:research.test"]


def test_waf_page_is_not_recorded_as_successful_article_read(monkeypatch):
    from src.utils.async_call import track_tool, tool_call_records
    browser = BrowserTool()
    async def fetch(url):
        return '<main>appkey: "CF_APP_WAF" requestInfo.userUserId sceneId</main>'
    monkeypatch.setattr(browser, "_fetch", fetch)
    records = []
    token = tool_call_records.set(records)
    try:
        result = asyncio.run(track_tool(browser).execute("https://example.test/blocked"))
    finally:
        tool_call_records.reset(token)
    assert result.startswith("[Browser Error]") and records[0]["status"] == "failed"


def test_publisher_constraint_is_enforced_locally_if_provider_ignores_it():
    result = filter_search_results({"results": [
        {"title": "Alpha2.5", "url": "https://research.test.evil.test/a"},
        {"title": "Alpha2.5", "url": "https://docs.research.test/a"},
    ]}, "Alpha2.5", allowed_domains=["research.test"])
    assert len(result["results"]) == 1
    assert result["rejected_results"][0]["reason"] == "outside_requested_publisher_domains"


@pytest.mark.parametrize("case", ["budget", "browser_error", "no_source"])
def test_later_tool_failure_preserves_evidence_and_tool_call_pairing(case):
    executions = []
    class Search:
        name = "web_search"
        def get_openai_tool_schema(self):
            return {"type": "function", "function": {"name": self.name}}
        async def execute(self, query):
            executions.append(query)
            return ({"error": "provider unavailable"} if case == "no_source" else
                {"results": [{"url": "https://example.test/alpha", "title": "Alpha2.5", "snippet": "count=30"}]})
    class Browser:
        name = "browser"
        reads = 0
        def get_openai_tool_schema(self):
            return {"type": "function", "function": {"name": self.name}}
        async def execute(self, url, max_chars=8000):
            self.reads += 1
            return "count=30" if self.reads == 1 else "[Browser Error] Page timed out"
    def call(name, identifier, args):
        return {"id": identifier, "function": {"name": name, "arguments": json.dumps(args)}}
    class Policy:
        tools = None
        def set_tools(self, tools): self.tools = tools
        def __call__(self, messages):
            responses = [m for m in messages if m["role"] == "tool"]
            if not responses:
                count = 3 if case == "budget" else 1
                return {"tool_calls": [call("web_search", str(i), {"query": "Alpha2.5"}) for i in range(count)]}
            if case == "browser_error" and len(responses) == 1:
                return {"tool_calls": [call("browser", "read", {"url": "https://example.test/other"})]}
            expected = ["0", "1", "2"] if case == "budget" else (["0", "read"] if case == "browser_error" else ["0"])
            assert [m["tool_call_id"] for m in responses] == expected
            if case == "budget":
                assert self.tools is None
            return {"content": "已取得 count=30；无法获取其他指标。Confidence: 0.7"}
    agent = ResearcherAgent("fixture", Policy(), [Search()] + ([Browser()] if case == "browser_error" else []))
    result = asyncio.run(agent.run(SubTask("A", TaskType.SEARCH, "Alpha2.5"), {}))
    if case == "no_source":
        assert result.status == AgentStatus.FAILED and not result_sources([result])
    else:
        assert result.status == AgentStatus.SUCCESS and "30" in result_sources([result])[0]["snippet"]
    assert len(executions) == (2 if case == "budget" else 1)


