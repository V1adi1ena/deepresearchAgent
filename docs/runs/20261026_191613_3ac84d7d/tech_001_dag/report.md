# 2024 主流 LLM 中文推理/代码/长上下文对比：证据现状

## 核心结论
**现有证据不足以完成所要求的对比分析。** 检索仅覆盖 GPT-4o 与 Claude 3.5 Sonnet 的官方安全/发布文档，未获得任何中文推理、代码生成或长上下文基准的**具体分数**，且完全缺失 Gemini 1.5 与 Qwen2.5 的资料。以下仅陈述可支持的事实。

## 可支持的事实
- **GPT-4o**：官方 System Card（2024-08-08）聚焦安全评估（外部红队、Preparedness Framework 风险评分），**并非**能力基准报告 [s_c786d7c5432e]。上下文长度 128k tokens（定价页 2024-11 快照）[s_0083b7297196]。
- **Claude 3.5 Sonnet**：官方发布页确认 200K token 上下文、$3/$15 每百万输入/输出 token、速度约为 Claude 3 Opus 的 2 倍，并宣称在研究生级推理等基准上超越 Claude 3 Opus 及竞品，但**摘要未给出具体分数** [s_e91e6f80eaac]。

## 证据缺口（明确）
1. **无中文推理数据**：两份官方文档均无中文专项评测；需转向 C-Eval/CMMLU 等第三方榜单（未检索）。
2. **无具体数值**：GPT-4o 的 MMLU/HumanEval/MGSM、Claude 3.5 的 GPQA/SWE-bench/MATH 均未取到。
3. **Gemini 1.5、Qwen2.5 完全无来源**，无法纳入对比。
4. **技术路线**：GPT-4o 端到端多模态、Claude 3.5 架构细节官方均未披露，属未公开信息。
5. 页面抓取两次 403 失败，正文未获取。

## 不可用的来源
- o1 System Card [s_dcf8ab338d73] 为不同模型，不适用。
- Anthropic 首页 [s_afe2508ac4ca] 提及 Claude 3.7 Sonnet，属后续版本，不能代表 3.5。
- Claude 3.5 发布页标注日期为 2025-03-01，晚于 2024 年，需谨慎对待其时效性 [s_e91e6f80eaac]。

## 建议下一步
抓取 System Card 与 Anthropic 模型卡 PDF 直链；中文能力改用 C-Eval/CMMLU 第三方榜单；补充 Gemini 1.5 与 Qwen2.5 官方技术报告。

---
**总体置信度：0.35**（仅确认上下文长度、定价、安全文档性质等元信息；核心对比维度无数据支撑）。
**关键来源**：OpenAI GPT-4o System Card [s_c786d7c5432e]、OpenAI 定价页 [s_0083b7297196]、Anthropic Claude 3.5 Sonnet 发布页 [s_e91e6f80eaac]。

Incomplete tasks: task_2