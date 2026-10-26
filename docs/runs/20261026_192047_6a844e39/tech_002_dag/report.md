# AI 芯片市场格局：训练与推理竞争力比较

## 核心结论
现有证据仅能支撑 **NVIDIA 一侧**的竞争力描述；AMD、Intel、华为昇腾、寒武纪均**无一手数据**，无法完成跨厂商对比。以下按证据强度分层陈述。

## NVIDIA：训练与推理均有可引用证据
- **推理**：Blackwell Ultra（GB300 NVL72）官方称面向 agentic AI 推理“最高 50x 性能提升、35x 更低成本”，微软、CoreWeave、OCI 已规模化部署，用于低延迟/长上下文场景；使能要素为 NVFP4、NVLink/NVLink Switch、Dynamo + TensorRT-LLM、SGLang/vLLM [s_f6f6f452c0a6]。该倍数为**厂商自述营销口径**，非第三方复现。
- **基准**：MLPerf Inference v6.0 中 Blackwell Ultra 系统在最多模型/场景取得最高吞吐；NVIDIA 自 2018 年累计训练+推理胜场 291 次，为其他所有提交方合计的 9x；本轮 14 家伙伴参与 [s_f600a45f3f4e][s_267fa508d06b]。注意：此为 NVIDIA 对 MLPerf 结果的**自述**，未取得 MLPerf 官方榜单原文。
- **路线图**：Vera Rubin 平台 2026-01-05 发布“六颗新芯片、一台 AI 超算”，2026-03-16 增补第七颗芯片（Groq 3 LPX 低延迟推理加速器），定位以数据中心为计算单元、面向长上下文/agentic 推理 [s_1d2abc303176][s_1c7e1fc9369c]。**未取得** HBM 容量/带宽、FP4 算力等具体规格。

## AMD / Intel：证据缺失
两次 `site:amd.com` 检索返回 0 条，检索预算耗尽，**未获得任何 AMD（MI350/MI355X、MI400/Helios）或 Intel（Gaudi 3）官方规格与基准**。因此无法就训练或推理给出与 NVIDIA 的对比结论。

## 中国厂商：证据缺失
- `site:huawei.com` 命中均为无关文档（Atlas 300I 推理卡手册、OptiX RTN 910 微波设备、ATN 910C 路由器、鲲鹏 S920X10K），**无一条涉及昇腾 910B/910C 规格或性能**；support.huawei.com 部分页面因 SSL 校验失败无法读取 [s_20581477fb31][s_b0693111ec09]。
- `site:cambricon.com` 返回 **0 条**，思元 590/690 无官方页面命中。
- 缺口：昇腾 910C 算力/带宽/互联参数、思元 590/690 规格与量产状态、CANN/MagicMind 生态成熟度、2025–2026 出货与客户案例。

## 证据缺口与建议
本报告无法回答“训练 vs 推理”的跨厂商排序。建议改用非站点限定关键词（如“昇腾 910C 规格 算力”“思元690 发布”），或直接读取华为全联接大会/昇腾社区、寒武纪年报与投资者关系公告、SemiAnalysis 等第三方拆解。

**总体置信度：0.35**（NVIDIA 部分约 0.8；AMD/Intel/中国厂商部分接近 0）

**关键来源**：NVIDIA Developer 官方博客与产品页（推理平台、MLPerf v6.0、Vera Rubin 平台）[s_f6f6f452c0a6][s_f600a45f3f4e][s_267fa508d06b][s_1d2abc303176][s_1c7e1fc9369c]；华为支持站点检索结果（仅证明检索失败，非产品证据）[s_20581477fb31][s_b0693111ec09]。