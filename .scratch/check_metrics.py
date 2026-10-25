"""一次性核对脚本：验证现有评测指标的实际行为（可删）。"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from evaluation.metrics.rule_based import RuleBasedMetrics as M

gt = {"GPT-4o 的发布方": "OpenAI", "训练成本": "约 1 亿美元"}
good = "GPT-4o 的发布方是 OpenAI，训练成本约 1 亿美元。"
wrong = "GPT-4o 的发布方是 Google，训练成本约 0 美元。"
neg = "GPT-4o 并非由 OpenAI 发布，训练成本也不是 1 亿美元。"

print("== fact_accuracy（只看键名）==")
print("  正确答案 :", M.fact_accuracy(good, gt))
print("  错误答案 :", M.fact_accuracy(wrong, gt))
print("  否定句   :", M.fact_accuracy(neg, gt))
print("  空报告   :", M.fact_accuracy("", gt))

print("== semantic_fact_accuracy（embedding 缺失时）==")
try:
    print("  错误答案 :", M.semantic_fact_accuracy(wrong, gt))
    print("  否定句   :", M.semantic_fact_accuracy(neg, gt))
except Exception as e:
    print("  抛出异常:", type(e).__name__, str(e)[:120])

print("== composite_score（满分维度下）==")
all_perfect = {
    "factual_accuracy_str": 1.0, "factual_accuracy_sem": 1.0,
    "logical_consistency": 1.0, "citation_coverage": 1.0,
    "bias": 1.0, "comprehensiveness": 1.0,
}
print("  当前字段 :", M.composite_score(all_perfect))
print("  补上 factual_accuracy 后 :", M.composite_score({**all_perfect, "factual_accuracy": 1.0}))

print("== ResearchBench ==")
try:
    from evaluation.benchmarks.research_bench import ResearchBench
    b = ResearchBench()
    print("  题目数:", len(b.questions))
    if b.questions:
        q = b.questions[0]
        print("  首题字段:", list(q.keys()))
        print("  首题 id:", q.get("id"), "| ground_truth 条目:", len(q.get("ground_truth", {}) or {}))
except Exception as e:
    print("  加载失败:", type(e).__name__, str(e)[:200])
