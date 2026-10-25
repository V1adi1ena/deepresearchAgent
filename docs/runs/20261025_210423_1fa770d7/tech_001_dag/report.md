# 2024 主流大模型中文推理/代码/长上下文对比：证据现状

## 核心结论
**无法完成所要求的四模型横向对比。** 检索结果中没有任何一手 benchmark 数据支撑 GPT-4o、Claude 3.5、Gemini 1.5、Qwen2.5 在中文推理、代码生成、长上下文三类任务上的同表比较。以下仅列出可支持事实与明确缺口。

## 可支持的事实（均为二手来源）
- **Qwen2.5-Coder-32B-Instruct**：HumanEval 92.7%、MBPP 90.2%，被称开源最高分 [s_7e29f1d5a43f]。
- **Qwen2.5 综合/中文**：MMLU 85+（7B 级第一）、C-Eval 超 83%、CMMLU 84.7% [s_88aac318b106]。
- **Qwen 长上下文**：128K 窗口，优化涉及 KV Cache 分块、NTK-aware RoPE 缩放、滑动窗口+摘要回填 [s_8d90af8a31f0]；Qwen2.5-Coder-1.5B 支持 32K [s_cac22628dfa4]。

## 证据缺口（关键）
1. **无一手报告**：OpenAI GPT-4o System Card、Anthropic Claude 3.5 Model Card、Gemini 1.5 技术报告（arXiv 2403.05530）、Qwen2.5 技术报告（arXiv 2412.15115）均未命中。
2. **无跨模型同表数值**：C-Eval/CMMLU、HumanEval/MBPP/LiveCodeBench、RULER/LongBench/NIAH 的四模型对比数据完全缺失。
3. **技术路线差异无权威来源**：Qwen 的 GQA+RoPE 缩放+分块 KV Cache、Gemini 的 MoE+原生多模态长上下文、Claude 的 Constitutional AI、GPT-4o 的端到端多模态，均只能定性推断，无一手佐证。
4. **时效污染**：多数结果为 2025–2026 年营销/横评博客，混入 Gemini 3.5、Qwen3、GPT-5.4 等无关新模型 [s_9d5d1b78683a][s_0bb2ec1ac306][s_ddf72d7c38f2]，与指定版本不匹配。

## 建议下一步
直接抓取 arXiv 2412.15115、2403.05530 全文 benchmark 表，以及 OpenAI/Anthropic 官方 model card PDF，获取一手对比数据后再做分析型结论。

## 置信度
**0.22** — 仅 Qwen2.5 系列若干分数有二手来源；四模型横向对比与技术路线分析均缺一手证据。

## 关键来源
- [s_7e29f1d5a43f] php.cn：Qwen2.5-Coder HumanEval/MBPP 分数（二手）
- [s_88aac318b106] php.cn：Qwen2.5 MMLU/C-Eval/CMMLU（二手）
- [s_8d90af8a31f0] php.cn：Qwen 128K 上下文优化（二手）
- [s_cac22628dfa4] CSDN：Qwen2.5-Coder-1.5B 32K 上下文（二手）
- [s_9d5d1b78683a][s_0bb2ec1ac306][s_ddf72d7c38f2] 时效污染示例（2026 年横评）