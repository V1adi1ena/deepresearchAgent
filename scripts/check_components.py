"""Record local compression checks and optional real-model review of a synthetic error."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import hashlib
import importlib.metadata
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["LANGSMITH_TRACING"] = "false"
from src.memory.embedder import Embedder
from src.compressor.compressor import ContextCompressor
from src.models.model_router import ModelRouter
from src.adversarial.red_agent import RedAgent
from src.adversarial.blue_agent import BlueAgent
from src.adversarial.loop import AdversarialLoop
from src.orchestrator.schemas import ResearchReport
from src.utils.async_call import model_call_records, request_deadline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", action="store_true", help="Also call the configured LLM on one labelled fixture")
    args = parser.parse_args()
    directory = ROOT / "docs/runs" / ("components-" + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True)
    record = {"scope": "Synthetic component checks, not real research quality or benchmark results",
              "source_fingerprint": hashlib.sha256(b"".join(p.read_bytes() for p in sorted((ROOT / "src").rglob("*.py")))).hexdigest(),
              "environment": {p: importlib.metadata.version(p) for p in ["sentence-transformers", "transformers", "torch"]}}
    with (directory / "execution.log").open("w", encoding="utf-8") as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            embedding = Embedder()
            query = "Orion service request quota and cache expiration"
            gold = ["Orion has a quota of 30 requests per minute.", "Orion cache expires after 90 seconds.",
                    "Orion rejects requests above the quota."]
            noise = ["A botanical catalogue lists trees, flowers and seeds. Seasonal rainfall changes soil moisture. Garden paths open in the afternoon."] * 8
            texts = noise + [s + " This is a synthetic configuration fixture. Evidence must remain identifiable." for s in gold]
            compressor = ContextCompressor(None, embedder=embedding, budget=130, output_reserve=20)
            outputs = {"truncate": ["\n".join(texts)[:385]],
                       "relevance": compressor.compress(texts, query, level=1),
                       "textrank": compressor.compress(texts, query, level=2)}
            record.update(embedding_backend=embedding.backend, query=query, gold=gold, input=texts,
                          estimated_token_budget=110, strategies={})
            for name, parts in outputs.items():
                record["strategies"][name] = {"output": parts, "retained_exact_facts": sum(s in "\n".join(parts) for s in gold),
                    "total_facts": len(gold), "input_characters": sum(map(len, texts)),
                    "output_characters": sum(map(len, parts)), "estimated_tokens": compressor.calculate_tokens(parts)}
            if args.review:
                async def check():
                    policy = ModelRouter.create_backend("deepseek", temperature=.1, max_tokens=1600)
                    calls = []
                    call_token = model_call_records.set(calls)
                    deadline_token = request_deadline.set(time.monotonic()+45)
                    try:
                        original = ResearchReport("What is Orion's quota? Use the supplied fixture only.",
                            "Orion allows 300 requests per minute [1].", sources=[{
                                "url": "fixture://orion/config", "title": "Synthetic configuration fixture",
                                "snippet": "Orion allows 30 requests per minute."}])
                        loop = AdversarialLoop(RedAgent(policy), BlueAgent(policy), max_rounds=1,
                                               score_threshold=9.9, max_model_calls=12)
                        reviewed, history = await asyncio.wait_for(loop.run(original), 45)
                        return {"original": original.content, "reviewed": reviewed.content,
                                "sources": reviewed.sources, "history": history, "model_calls": calls}
                    finally:
                        model_call_records.reset(call_token)
                        request_deadline.reset(deadline_token)
                try:
                    record["real_model_review"] = asyncio.run(check())
                except Exception as exc:
                    record["real_model_review_error"] = {"type": type(exc).__name__, "message": str(exc)}
    (directory / "result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Component records: {directory}")
    print("Exact retained facts:", {k: v["retained_exact_facts"] for k, v in record["strategies"].items()})
    if args.review:
        print("Real model review recorded:", "real_model_review" in record)


if __name__ == "__main__":
    main()
