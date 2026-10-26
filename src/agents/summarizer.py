"""
合成 Agent (SummarizerAgent)

将多个 SubTask 的执行结果合成为结构化的研究报告。
区别于 ResearcherAgent 的多轮 tool-calling，Summarizer 是单轮长上下文生成任务：
  - 把所有子结果按置信度排序后拼接为上下文
  - 调用 LLM 一次性生成 Markdown 格式报告
  - 提取引用来源，计算整体置信度
"""
from __future__ import annotations

import json
import copy
import re
from ..utils.async_call import call_sync
from ..utils.sources import result_sources
from typing import Any

from .base_agent import BaseAgent
from ..orchestrator.schemas import SubTask, AgentResult, AgentStatus, ResearchReport
from ..utils.tracing import trace_agent


__all__ = ["SummarizerAgent"]


class SummarizerAgent(BaseAgent):
    """合成 Agent：将子任务结果合成为最终研究报告。

    Attributes:
        max_output_tokens: 报告生成的最大 token 数（通过 policy.max_tokens 控制）。
    """

    def __init__(self, name: str, policy, tools: list | None = None) -> None:
        super().__init__(name, policy, tools)

    @trace_agent(name="summarizer.run", tags=["agent", "summarizer"])
    async def run(self, task: SubTask, context: dict) -> AgentResult:
        """执行合成任务。

        Args:
            task: 通常是一个特殊的 "synthesize" 类型任务。
            context: 全局上下文，必须包含 "results" 和 "query" 键。
                results: list[AgentResult]
                query: str 原始研究问题

        Returns:
            AgentResult，output 字段为 ResearchReport 实例。
        """
        query = context.get("query", "")
        results: list[AgentResult] = context.get("results", [])

        if not results or not result_sources(results):
            report = ResearchReport(
                query=query,
                content="No retrieved evidence available to synthesize.",
                confidence=0.0,
                status="failed",
            )
            return AgentResult(
                task_id=task.task_id,
                status=AgentStatus.FAILED,
                output=report,
                trajectory=[],
                token_usage=0,
                confidence=0.0,
            )

        # 构建 synthesis prompt
        prompt = self._build_synthesis_prompt(query, results)
        compressor = context.get("compressor")
        if compressor:
            texts = [str(r.output) for r in results]
            compressed = await call_sync(compressor.compress, texts, query)
            prompt = "# Question\n" + query + "\n# Findings\n" + "\n".join(compressed)
        # Stable evidence records stay outside compression, and generated URLs are not new sources.
        sources = result_sources(results)
        # Keep structured evidence valid, giving read passages more space than
        # provider summaries; full records remain in the report and task trace.
        prompt_sources = [{**s, "snippet": ""} for s in sources]
        excerpt_budget = max(0, 30000 - len(prompt) - len(json.dumps(prompt_sources, ensure_ascii=False)))
        weights = [4 if s.get("evidence_kind") == "page_excerpt" else 1 for s in sources]
        unit_budget = excerpt_budget // max(1, sum(weights))
        for view, source, weight in zip(prompt_sources, sources, weights):
            limit = min(2000 if weight == 4 else 500, unit_budget * weight)
            view["snippet"] = source["snippet"][:limit]
        prompt += "\n# Retrieved sources\n" + json.dumps(prompt_sources, ensure_ascii=False)
        messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": prompt},
        ]

        try:
            # 合成任务不需要工具调用，临时禁用 tools 避免模型进入 tool-calling 模式
            policy = copy.copy(self.policy)
            policy.tools = None
            response = await call_sync(policy, messages)
        except RuntimeError as e:
            return AgentResult(
                task_id=task.task_id,
                status=AgentStatus.FAILED,
                output=str(e),
                trajectory=[{"error": str(e)}],
                token_usage=0,
                confidence=0.0,
            )

        content = response.get("content", "") or ""
        if not content.strip() or response.get("finish_reason") in ("length", "content_filter", "aborted", "insufficient_system_resource"):
            return AgentResult(task.task_id, AgentStatus.FAILED,
                output="Synthesis returned empty or incomplete model output", confidence=0.0)
        token_usage = len(content) // 3  # 简化估算

        # 解析报告内容，提取来源和置信度
        report = self._parse_report(query, content, results)

        return AgentResult(
            task_id=task.task_id,
            status=AgentStatus.SUCCESS,
            output=report,
            trajectory=[{"role": "assistant", "content": content}],
            token_usage=token_usage,
            confidence=report.confidence,
        )

    def _system_prompt(self) -> str:
        target_chars = max(512, getattr(self.policy, "max_tokens", 4096) // 2)
        return (
            "You are an expert research synthesizer. "
            "Your task is to integrate multiple research findings into a coherent, well-structured report. "
            "Use Markdown formatting. Cite sources explicitly. "
            "Use only the supplied evidence. State gaps explicitly; do not invent facts to meet a length target. "
            "Sources marked search_snippet/search_summary have not been read as page text; page_excerpt contains retrieved verbatim passages, not an independent truth guarantee. "
            "Respect source publication dates and scope_note: later extensions or renamed versions must not stand in for a requested historical release. A later retrospective is usable only for explicitly supported historical facts. "
            "Do not promote a secondary site's claim into an official benchmark, or mix different model sizes/versions or evaluation settings. "
            f"Keep the entire report, including references, under {target_chars} characters. "
            "Prioritize the answer, supported comparisons and evidence gaps; avoid repetitive background or restating the question. "
            "Use compact inline source IDs and list only sources actually cited, not the full retrieved inventory. "
            "DO NOT describe what you will do — directly output the synthesized report. "
            "At the end, provide an overall confidence score (0-1) and a summary of key sources."
        )

    def _build_synthesis_prompt(self, query: str, results: list[AgentResult]) -> str:
        """构建合成 prompt，按置信度降序排列结果。"""
        sorted_results = sorted(results, key=lambda r: r.confidence, reverse=True)

        parts = [
            f"# Research Question\n{query}\n",
            f"# Sub-task Results ({len(results)} total)\n",
        ]
        for i, r in enumerate(sorted_results, 1):
            status_icon = "✓" if r.status == AgentStatus.SUCCESS else "✗"
            parts.append(
                f"## Result {i} [{status_icon}] (confidence: {r.confidence:.2f})\n"
                f"Task: {r.task_id}\n"
                f"Output:\n{r.output}\n"
            )

        parts.append(
            "\n# Instructions\n"
            "1. Directly write the synthesized report based on the findings above. Do NOT say 'I will synthesize'.\n"
            "2. Report only supported findings; state missing evidence and unresolved contradictions.\n"
            "3. Structure: Summary → Supported Findings/Comparisons → Evidence Gaps → Cited Sources. Stay within the system output budget.\n"
            "4. Resolve any contradictions between sources.\n"
            "5. Explicitly list all sources cited.\n"
            "6. End with: Overall Confidence: X.XX"
        )
        return "\n".join(parts)

    def _parse_report(self, query: str, content: str, results: list[AgentResult]) -> ResearchReport:
        """从 LLM 输出中解析 ResearchReport，并基于子任务成功率校准置信度。"""
        # 1. 从文本中提取 LLM 自评置信度
        llm_confidence = 0.5
        m = re.search(r"[Oo]verall\s+[Cc]onfidence[:\s]+(0\.\d+|1\.0|1)", content)
        if m:
            try:
                llm_confidence = float(m.group(1))
            except ValueError:
                pass

        # 2. 基于子任务成功率计算客观置信度
        total = len(results)
        success = sum(1 for r in results if r.status == AgentStatus.SUCCESS)
        success_rate = success / max(total, 1)

        # 3. 综合置信度 = LLM 自评 × 成功率开根（降低成功率的影响权重）
        confidence = llm_confidence * (success_rate ** 0.5)
        confidence = round(max(0.0, min(1.0, confidence)), 2)

        unique_sources = result_sources(results)

        # 统计实际工具调用次数（遍历所有子任务的 trajectory）
        num_searches = sum(
            len([t for t in r.trajectory if t.get("role") == "tool"])
            for r in results
        )

        return ResearchReport(
            query=query,
            content=content,
            sources=unique_sources,
            confidence=confidence,
            num_searches=num_searches,
        )
