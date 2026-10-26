# 2024 主流大模型中文推理、代码与长上下文对比

## 结论先行
现有证据**不足以**对 GPT-4o、Claude 3.5、Gemini 1.5、Qwen2.5 做同基准、同版本、同中文语料的定量排序。可支撑的只有零散事实与路线差异，中文推理与代码的横向分数基本缺失。

## 可支撑的事实
- **上下文窗口**：GPT-4o 128K、Claude 3.5 Sonnet 200K、Gemini 1.5 Pro 1M+（二手汇总，非官方模型卡）[s_7c3978260062]。
- **GPT-4o 参考分**（第三方汇总，非 OpenAI 官方）：HumanEval 74.8%、MMLU 88.7%、GPQA 83.3%、SWE-bench 69.1%[s_7c3978260062]。注意该表混排了 2025 年 Claude 4 / Gemini 2.5，存在版本错配风险。
- **Qwen2.5 路线**：预训练 7T→18T tokens，开放权重为稠密 decoder，含 Coder/Math 专项模型（转述，非原文）[s_c73cb81e0e0d][s_2484610d4a4c]。
- **Qwen2.5-1M 长上下文**：128K→1M，采用长数据合成、渐进式预训练、多阶段 SFT；推理侧免训练长度外推、稀疏注意力+chunked prefill，1M prefill 提速 3–7×；长上下文任务优于 GPT-4o-mini[s_c70c2f59c9a9]。
- **GPT-4o 系统卡**侧重安全（Preparedness Framework、100+ 外部红队、音频风险），未披露架构、上下文长度或中文/代码基准[s_bb98744d1ec8][s_c188811f5181]。

## 技术路线差异（有限证据）
- Qwen2.5：稠密架构 + 数据规模扩张 + 专项模型 + 长上下文工程化（训练与推理双侧优化）[s_c73cb81e0e0d][s_c70c2f59c9a9]。
- GPT-4o：官方文档以安全评估为主，架构与训练细节未公开[s_bb98744d1ec8]。
- Claude 3.5、Gemini 1.5：**无官方原文**，其 MoE 架构、computer use 等说法缺证据支撑。

## 证据缺口
1. Claude 3.5、Gemini 1.5 的官方模型卡/技术报告与三项任务基准分数均未取得。
2. 四模型同基准、同版本、同中文语料横向分数缺失；CLUE、SuperCLUE、SuperBench 资源存在但未取到可比数值[s_f032c1ccd0ff][s_4ead460cbd69][s_b7e06ff8595b]。
3. 现有对比多为 2025 年新版本混排，不能代表 2024 年版本表现。

**总体置信度：0.4**

**关键来源**：OpenAI GPT-4o System Card（s_bb98744d1ec8、s_c188811f5181）；Qwen2.5-1M Technical Report（s_c70c2f59c9a9）；Qwen2.5 技术报告转述（s_c73cb81e0e0d、s_2484610d4a4c）；第三方对比表（s_7c3978260062，二手）。