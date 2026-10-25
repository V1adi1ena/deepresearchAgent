import pytest
from evaluation.metrics.rule_based import RuleBasedMetrics as Metrics
from evaluation.benchmarks.research_bench import ResearchBench
from src.memory.embedder import Embedder


@pytest.mark.parametrize("text,expected", [
    ("A=10; B=20", 1), ("A=20; B=10", 0),
    ("A=20 and B=10", 0), ("A is not 10; B is not 20", 0),
    ("A=100; B=200", 0), ("", 0),
])
def test_reference_pairs(text, expected):
    assert Metrics.reference_fact_match(text, {"A": 10, "B": 20}) == expected


def test_tolerance_is_explicit():
    assert Metrics.reference_fact_match("A=10.02", {"A": {"value": 10, "tolerance": .03}}) == 1
    assert Metrics.reference_fact_match("A=10.02", {"A": 10}) == 0


def test_composite_uses_actual_output_keys_and_rejects_missing():
    values = dict(reference_fact_match=1, logical_consistency=1, citation_coverage=1, bias=1, comprehensiveness=1)
    assert Metrics.composite_score(values) == 1
    del values["reference_fact_match"]
    with pytest.raises(ValueError):
        Metrics.composite_score(values)


def test_semantic_metric_refuses_random_vectors(monkeypatch):
    monkeypatch.setattr(Embedder, "_load_model", lambda self: None)
    with pytest.raises(RuntimeError):
        Metrics.semantic_fact_accuracy("The capital is definitely Berlin.", {"capital": "Paris"})


def test_benchmark_reports_scope_without_random_semantic_score():
    result = ResearchBench().evaluate_report("fixture", "tech_001")
    assert "reference_fact_match" in result["metrics"]
    assert result["metrics"]["factual_accuracy_sem"] is None
    assert result["semantic_backend"] == "not_evaluated"


def test_traceable_citation_is_not_a_truth_judgment():
    sources = [{"url": "https://example.test/a", "source_id": "s_abc123"}]
    assert Metrics.citation_traceability("Wrong claim [1]", sources) == 1
    assert Metrics.citation_traceability("Claim [2]", sources) == 0


def test_model_sdk_receives_remaining_deadline():
    import time
    from types import SimpleNamespace
    from src.models.vllm_policy import VLLMPolicy
    from src.utils.async_call import request_deadline
    captured = {}
    def create(**kwargs):
        captured.update(kwargs)
        message = SimpleNamespace(content="ok", tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")], usage=None)
    policy = VLLMPolicy()
    policy.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    token = request_deadline.set(time.monotonic()+.2)
    try:
        policy([{"role": "user", "content": "fixture"}])
    finally:
        request_deadline.reset(token)
    assert 0 < captured["timeout"] <= .2 + 1e-6
