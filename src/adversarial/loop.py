"""
M5 Red-Blue 对抗降噪循环 — 主控制器

AdversarialLoop 驱动 Red Agent → Blue Agent → 评分的完整对抗流程，
具备死循环检测、震荡检测、收敛判断等鲁棒机制。

设计决策：
1. 维护 resolved_issues 集合：已修复的 issue 如果在新轮次中重新出现，判定为震荡。
2. 收敛条件三选一：round >= 3 / overall >= 8.0 / Δscore < 0.3。
3. 每轮记录完整评分历史，便于后续分析和审计。
"""
from __future__ import annotations

import copy
import logging
from typing import Any

from src.adversarial.blue_agent import BlueAgent
from src.adversarial.red_agent import RedAgent
from src.adversarial.verdict import (
    Dimension,
    FixOperation,
    Issue,
    RedVerdict,
    VerdictEngine,
)
from src.orchestrator.schemas import ResearchReport
from src.utils.tracing import trace_chain
from src.utils.async_call import model_budget
import hashlib


__all__ = ["AdversarialLoop"]

logger = logging.getLogger(__name__)


class AdversarialLoop:
    """Red-Blue 对抗降噪循环主控制器。

    Attributes:
        red_agent: Red Agent 实例，负责攻击。
        blue_agent: Blue Agent 实例，负责修复。
        policy: 用于 self_verify 或辅助评分的策略对象（可选）。
        max_rounds: 硬上限轮数。
        score_threshold: 综合分达标阈值。
        delta_threshold: 轮间变化量收敛阈值。
    """

    def __init__(
        self,
        red_agent: RedAgent,
        blue_agent: BlueAgent,
        policy: Any | None = None,
        max_rounds: int = 3,
        score_threshold: float = 8.0,
        delta_threshold: float = 0.3,
        max_model_calls: int = 24,
    ):
        self.red_agent = red_agent
        self.blue_agent = blue_agent
        self.policy = policy
        self.max_rounds = max(max_rounds, 1)
        self.score_threshold = score_threshold
        self.delta_threshold = delta_threshold
        self.max_model_calls = max_model_calls

    @trace_chain(name="adversarial_loop.run", tags=["m5", "loop", "adversarial"])
    async def run(
        self, report: ResearchReport
    ) -> tuple[ResearchReport, list[dict[str, Any]]]:
        """运行完整的对抗降噪循环。

        流程：
        1. 每轮用 Red Agent 攻击当前报告。
        2. Blue Agent 根据 Verdict 修复。
        3. 记录本轮评分和修复操作。
        4. 检查收敛条件或震荡/死循环。
        5. 返回最终报告和完整历史。

        Args:
            report: 初始研究报告（不会被修改，内部深拷贝）。

        Returns:
            (修复后的报告, 每轮评分记录列表)
            每轮记录包含: round, dimension_scores, overall_score, delta, issues_count,
            fix_operations, resolved_count, oscillation_detected, stop_reason
        """
        current = copy.deepcopy(report)
        history = []
        budget = {"used": 0, "limit": self.max_model_calls, "exhausted": False}
        token = model_budget.set(budget)
        try:
            verdict = await self.red_agent.attack(current)
            current.final_score = verdict.overall_score
            for round_idx in range(1, self.max_rounds + 1):
                if not verdict.issues or verdict.overall_score >= self.score_threshold:
                    break
                if budget["exhausted"] or budget["used"] >= budget["limit"]:
                    history.append({"round": round_idx, "stop_reason": "model_budget_exhausted",
                                    "candidate_published": False, "model_calls": budget["used"]})
                    break
                before = copy.deepcopy(current)
                budget["post_review_calls"] = len(getattr(self.red_agent, "dimensions", []))
                fixed, operations = await self.blue_agent.defend(current, verdict)
                if not operations:
                    reason = ("insufficient_fix_budget" if budget["limit"] - budget["used"] <
                              2 + budget["post_review_calls"] else "no_fix_performed")
                    history.append({"round": round_idx, "stop_reason": reason,
                                    "candidate_published": False, "model_calls": budget["used"],
                                    "issues_count": len(verdict.issues)})
                    break
                # Re-evaluate the exact candidate before publishing it or its score.
                after = await self.red_agent.attack(fixed)
                if budget["exhausted"]:
                    history.append({"round": round_idx, "stop_reason": "model_budget_exhausted",
                                    "candidate_published": False, "model_calls": budget["used"]})
                    break
                delta = VerdictEngine.compute_delta(verdict.dimension_scores, after.dimension_scores)
                reason = self._check_convergence(round_idx, after.overall_score, delta)
                if fixed.content == before.content:
                    reason = "no_change"
                record = self._build_round_record(round_idx, after, operations, sum(op.success for op in operations), False, reason)
                record.update({"content_before": before.content, "content_after": fixed.content,
                    "before_version": hashlib.sha256(before.content.encode()).hexdigest(),
                    "after_version": hashlib.sha256(fixed.content.encode()).hexdigest(),
                    "score_before": verdict.overall_score, "sources_after": copy.deepcopy(fixed.sources),
                    "model_calls": budget["used"], "candidate_published": True})
                history.append(record)
                current, verdict = fixed, after
                current.final_score = after.overall_score
                current.adversarial_rounds = len(history)
                if reason:
                    break
            return current, history
        except RuntimeError:
            if not budget["exhausted"]:
                raise
            history.append({"stop_reason": "model_budget_exhausted", "candidate_published": False,
                            "model_calls": budget["used"]})
            return current, history
        finally:
            model_budget.reset(token)

    def _check_convergence(
        self, round_idx: int, overall_score: float, delta: float
    ) -> str:
        """检查是否满足任一收敛条件。

        Returns:
            空字符串表示继续；非空字符串为停止原因。
        """
        if round_idx >= self.max_rounds:
            return f"max_rounds_reached({self.max_rounds})"
        if overall_score >= self.score_threshold:
            return f"score_threshold_met({overall_score:.2f}>={self.score_threshold})"
        # 第一轮没有上一轮做对比，delta 恒为 0，跳过 delta 收敛检测
        if round_idx > 1 and delta < self.delta_threshold:
            return f"delta_converged({delta:.3f}<{self.delta_threshold})"
        return ""

    def _build_round_record(
        self,
        round_idx: int,
        verdict: RedVerdict,
        operations: list[FixOperation],
        resolved_count: int,
        oscillation: bool,
        stop_reason: str,
    ) -> dict[str, Any]:
        """构造单轮记录字典。"""
        return {
            "round": round_idx,
            "dimension_scores": {
                k.value: round(v, 3) for k, v in verdict.dimension_scores.items()
            },
            "overall_score": round(verdict.overall_score, 3),
            "issues_count": len(verdict.issues),
            "fix_operations": [op.to_dict() for op in operations],
            "resolved_count": resolved_count,
            "oscillation_detected": oscillation,
            "stop_reason": stop_reason,
            "raw_feedback": verdict.raw_feedback,
        }
