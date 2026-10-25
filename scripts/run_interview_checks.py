"""Isolated real-chain checks and a small fixed-retrieval/DAG comparison.

This records execution and evidence availability, not automatic quality approval.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import copy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts._project_env import use_project_packages
use_project_packages(ROOT)
# Local per-question records are authoritative for this validation command.
# An unavailable hosted trace service must not obscure the chain's result.
os.environ["LANGSMITH_TRACING"] = "false"
from evaluation.benchmarks.research_bench import ResearchBench
from src.core.runner import initialize_modules, load_config, run_research
from src.agents.summarizer import SummarizerAgent
from src.orchestrator.schemas import AgentResult, AgentStatus, ResearchReport, SubTask, TaskType
from src.tools.web_search import WebSearchTool
from src.utils.async_call import model_call_records, tool_call_records, request_deadline


def technical_checks(report, events, *, review_required=False):
    """Execution checks only; factual correctness still requires evidence review."""
    return {
        "report_completed": report.status == "completed",
        "nonempty_report": bool(report.content.strip()),
        "sources_available": bool(report.sources),
        "all_tasks_completed": not report.incomplete_tasks,
        "no_execution_errors": not any("error" in e or "review_error" in e for e in events),
        "review_completed": not review_required or report.review_status == "completed",
    }


async def fixed_retrieval(query, modules, timeout):
    """One search followed by synthesis, using the same model/tool availability."""
    calls = []
    tools = []
    token = model_call_records.set(calls)
    tool_token = tool_call_records.set(tools)
    deadline_token = request_deadline.set(time.monotonic()+timeout)
    try:
        async def execute():
            tool = next(t for t in modules["tools"] if t.name == "web_search")
            result = await tool.execute(query=query)
            evidence = AgentResult("fixed_search", AgentStatus.SUCCESS,
                output=json.dumps(result, ensure_ascii=False), confidence=.5,
                trajectory=[{"role": "tool", "name": "web_search", "result": result}])
            agent = SummarizerAgent("fixed_synthesis", modules["summarizer_policy"])
            answer = await agent.run(SubTask("synthesize", TaskType.ANALYZE, "Synthesize retrieved evidence"),
                                    {"query": query, "results": [evidence]})
            return answer.output if isinstance(answer.output, ResearchReport) else ResearchReport(query, "No evidence", status="failed")
        return await asyncio.wait_for(execute(), timeout)
    finally:
        model_call_records.reset(token)
        tool_call_records.reset(tool_token)
        request_deadline.reset(deadline_token)
        modules["model_calls"] = calls
        modules["tool_calls"] = tools
        await WebSearchTool.close_session()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="One real query with memory/compression/review disabled")
    parser.add_argument("--count", type=int, default=5, help="Real-chain checks (existing queries)")
    parser.add_argument("--compare", type=int, default=3, help="Existing queries compared against fixed retrieval")
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--question-id", help="Run only this existing benchmark question (for targeted reruns)")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/runs")
    args = parser.parse_args()
    if args.count < 1 or args.compare < 0 or args.timeout <= 0:
        parser.error("count/timeout must be positive; compare must be nonnegative")
    run_dir = args.output.resolve() / (time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8])
    run_dir.mkdir(parents=True)
    base = load_config()
    backend = base["model"].get("backend", "deepseek")
    base["model"]["backend_mapping"] = {k: backend for k in ("solver", "planner", "summarizer", "red_agent", "blue_agent", "compressor")}
    # Bounded chain validation uses non-thinking DeepSeek calls. Other backends
    # keep their own API defaults rather than receiving provider-specific fields.
    provider_options = {"thinking": "disabled"} if backend == "deepseek" else {}
    base["model"]["backend_sampling"] = {"modules": {
        name: {"temperature": .1, "max_tokens": tokens, **provider_options}
        for name, tokens in (("default", 4096), ("planner", 2048), ("solver", 2048),
                             ("summarizer", 4096), ("red_agent", 2048),
                             ("blue_agent", 4096), ("compressor", 2048))}}
    base.setdefault("tools", {}).update(allowed=["web_search", "browser"])
    base["tools"].setdefault("web_search", {})["mock_mode"] = False
    base.setdefault("orchestrator", {}).update(global_timeout_seconds=args.timeout, max_concurrent=2,
        max_sub_questions=2, max_replan_rounds=0, max_subagent_retries=0)
    base.setdefault("adversarial", {}).update(enabled=not args.smoke, max_rounds=1, max_model_calls=12,
                                             max_fixes_per_round=1)
    base.setdefault("memory", {})["enabled"] = not args.smoke
    base.setdefault("compressor", {})["enable_multilevel"] = not args.smoke
    questions = ResearchBench().get_questions(n=1 if args.smoke else max(args.count, args.compare))
    if args.question_id:
        questions = [q for q in ResearchBench().get_questions() if q["id"] == args.question_id]
        if not questions:
            parser.error(f"Unknown question ID: {args.question_id}")
    if not args.smoke:
        from src.memory.embedder import Embedder
        try:
            embedder = Embedder()
            vector = embedder.encode("research dependency preflight")
            embedding_check = {"available": True, "backend": embedder.backend, "dimensions": len(vector)}
        except Exception as exc:
            embedding_check = {"available": False, "error": str(exc)}
        (run_dir / "embedding_preflight.json").write_text(json.dumps(embedding_check, indent=2), encoding="utf-8")
        if not embedding_check["available"]:
            print(f"Embedding preflight failed; no API calls made. Records: {run_dir}")
            raise SystemExit(2)
    async def preflight():
        try:
            result = await asyncio.wait_for(WebSearchTool().execute(query=questions[0]["query"]), 20)
            return {"dependency": "web_search", "available": not bool(result.get("error")) and bool(result.get("results")),
                    "error": result.get("error"), "result_count": len(result.get("results", []))}
        finally:
            await WebSearchTool.close_session()
    try:
        check = asyncio.run(preflight())
    except Exception as exc:
        check = {"dependency": "web_search", "available": False, "error_type": type(exc).__name__}
    (run_dir / "preflight.json").write_text(json.dumps(check, ensure_ascii=False, indent=2), encoding="utf-8")
    if not check["available"]:
        print(f"Search preflight failed; no LLM calls made. Records: {run_dir}")
        raise SystemExit(2)
    records = []
    for index, question in enumerate(questions):
        systems = ["dag"] if args.smoke or index >= args.compare else ["fixed", "dag"]
        if not args.smoke and index >= args.count:
            systems = [s for s in systems if index < args.compare]
        for system in systems:
            cfg = copy.deepcopy(base)
            case_dir = run_dir / f"{question['id']}_{system}"
            case_dir.mkdir()
            cfg["memory"]["db_path"] = str(case_dir / "memory.db")
            started = time.monotonic()
            record = {"question_id": question["id"], "query": question["query"], "system": system,
                "model_backend": backend, "sampling": cfg["model"]["backend_sampling"],
                "timeout": args.timeout, "max_sub_questions": 2,
                "adversarial_config": cfg["adversarial"],
                "runtime": {"executable": sys.executable, "python_version": sys.version.split()[0]},
                "quality_review": {"answers_question": None, "citations_support_claims": None}}
            modules = {}
            with (case_dir / "execution.log").open("w", encoding="utf-8") as log:
                with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                    try:
                        modules = initialize_modules(cfg, session_id=uuid.uuid4().hex)
                        if system == "fixed":
                            report = asyncio.run(fixed_retrieval(question["query"], modules, args.timeout))
                        else:
                            asyncio.run(run_research(question["query"], cfg, modules))
                            report = modules["last_report"]
                        record["report"] = asdict(report)
                        record["technical_checks"] = technical_checks(report, modules["orchestrator"].events,
                            review_required=system == "dag" and not args.smoke)
                        record["technical_chain_success"] = all(record["technical_checks"].values())
                        (case_dir / "report.md").write_text(report.content, encoding="utf-8")
                        record["events"] = modules["orchestrator"].events
                    except Exception as exc:
                        import traceback
                        traceback.print_exc()
                        record.update(technical_chain_success=False, error_type=type(exc).__name__, error=str(exc))
            record["elapsed_seconds"] = time.monotonic()-started
            record["model_calls"] = modules.get("model_calls", [])
            record["tool_calls"] = modules.get("tool_calls", [])
            record["source_fingerprint"] = hashlib.sha256(b"".join(
                p.read_bytes() for p in sorted((ROOT / "src").rglob("*.py")))).hexdigest()
            (case_dir / "result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            records.append(record)
            failed = [name for name, passed in record.get("technical_checks", {}).items() if not passed]
            print(f"{question['id']} {system}: technical_chain_success={record['technical_chain_success']}"
                  + (f"; failed_checks={','.join(failed)}" if failed else ""))
    (run_dir / "summary.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Records: {run_dir}")
    raise SystemExit(0 if records and all(r["technical_chain_success"] for r in records) else 2)


if __name__ == "__main__":
    main()
