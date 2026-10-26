# 2024 主流 LLM 中文推理/代码/长上下文对比：证据现状

## 核心结论
**无法完成所要求的四模型对比。** 检索仅取得 Qwen2.5 官方博客正文与 GPT-4o System Card 的摘要；Claude 3.5、Gemini 1.5 无任何可用原文，中文推理与长上下文基准数值全部缺失。任何跨模型性能排序都将是无据推断。

## 已获证据（仅限 Qwen2.5）
- **架构/规模**：全系开源权重为 decoder-only；0.5B–72B 共 7 档，另有 Coder（1.5B/7B/32B）与 Math 变体；除 3B、72B 外为 Apache 2.0 [s_e8f0a037900e]。
- **训练**：预训练最多 18 万亿 tokens；Coder 用 5.5 万亿代码 tokens [s_e8f0a037900e]。
- **上下文**：128K 输入、8K 生成；29+ 语言含中文 [s_e8f0a037900e]。
- **基准（官方口径）**：MMLU 85+、HumanEval 85+、MATH 80+；Qwen-Plus 显著优于 DeepSeek-V2.5，但**部分维度仍落后 GPT-4o 与 Claude-3.5-Sonnet** [s_e8f0a037900e]。此为厂商自评，非独立复现。

## 技术路线差异（仅可作有限陈述）
Qwen2.5 走**开源权重 + 大规模预训练 + 代码/数学专用分支**路线 [s_e8f0a037900e]。GPT-4o 的公开文档为**安全评估报告**（外部红队、Preparedness Framework 前沿风险分级），不含能力基准或架构细节 [s_c786d7c5432e]。二者文档性质不同，不能据此比较能力。Claude 3.5 与 Gemini 1.5 的架构（如是否 MoE）、上下文规格与训练方法均无原文佐证，不作断言。

## 证据缺口
1. Claude 3.5 Sonnet 模型卡/基准（anthropic.com 检索无结果）。
2. Gemini 1.5 全部技术数据（检索 0 条、页面超时）。
3. GPT-4o System Card 正文（403）。
4. 中文推理（C-Eval/CMMLU）与长上下文（RULER/LongBench）具体分数——四模型均缺。
5. 统一评测设置下的横向对比数据。

## 置信度
**0.35**：Qwen2.5 部分较可靠；其余三模型关键数据缺失，跨模型结论不可得。

**主要来源**：Qwen2.5 官方博客 [s_e8f0a037900e]（page_excerpt）；GPT-4o System Card [s_c786d7c5432e]（search_summary，仅证其存在与性质）。