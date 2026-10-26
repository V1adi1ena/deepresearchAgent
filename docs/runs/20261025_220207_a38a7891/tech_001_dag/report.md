# 2024 主流 LLM 中文推理/代码/长上下文对比

## 核心结论
四模型缺乏统一口径的中文基准（C-Eval/CMMLU）与代码基准（HumanEval/MBPP）数值，**无法做严格横向排名**。仅能就长上下文与技术路线给出有据对比。

## 长上下文（证据最充分）
- **Gemini 1.5 Pro**：2M token，跨模态长上下文检索近乎完美召回，刷新长文档/长视频 QA SOTA [s_151ac078b731][s_99586ea66c61]。
- **Qwen2.5**：开源版默认 32K；1M 仅限 API 服务模型 Qwen2.5-Turbo [s_c73cb81e0e0d]。
- **Claude 3.5 Sonnet**：200K token [s_f9594acb8a7d][s_59079f28cea5]。
- **GPT-4o**：本次未取得官方数值，不作断言。

## 代码生成
- Claude 3.5 Sonnet：内部代理编码评估解决 64%（Opus 38%）；2024-10 升级版 SWE-bench Verified 33.4%→49.0% [s_f9594acb8a7d][s_930da13d31d8]。
- Qwen2.5：报告称编码表现突出，但无具体分数 [s_c73cb81e0e0d]。
- GPT-4o/Gemini 1.5：无同口径代码分数。

## 中文推理
仅间接证据：Gemini 1.5 Flash 在中/英/日/法生成速度最快 [s_99586ea66c61]；Claude 3.5 零样本 MATH/MMLU 小幅落后 GPT-4o [s_f9594acb8a7d]（原文表述为“在零样本MATH和MMLU评测中小幅落后GPT-4o”）。**中文专项推理无任何数值**。

## 技术路线
- **Gemini 1.5**：MoE 稀疏专家 + Transformer 解码器；Flash 为蒸馏轻量版，并行计算注意力与 FFN，优化 TPU [s_151ac078b731][s_99586ea66c61]。
- **Qwen2.5**：开源为稠密 Transformer（0.5B–72B），MoE 仅用于 API 模型；预训练 7T→18T token，>100 万 SFT + 离线 DPO/在线 GRPO [s_c73cb81e0e0d]。
- **GPT-4o / Claude 3.5**：架构与训练细节未公开，无可述证据。

## 证据缺口
GPT-4o 官方基准、四模型统一中文/代码基准、GPT-4o 与 Claude 架构细节均缺失；检索中 2026 年 Sonnet 5.5/GPT-6 内容属版本错配，已排除。

**置信度：0.55**（长上下文与路线较可靠；中文/代码横向对比证据不足）

**关键来源**：Gemini 1.5 报告转述 [s_151ac078b731][s_99586ea66c61]；Qwen2.5 报告转述 [s_c73cb81e0e0d]；Claude 3.5 Sonnet 发布 [s_f9594acb8a7d][s_59079f28cea5]；升级版数据 [s_930da13d31d8]。