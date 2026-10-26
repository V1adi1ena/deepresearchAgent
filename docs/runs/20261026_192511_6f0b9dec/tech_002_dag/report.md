# AI 芯片市场格局：训练与推理竞争力（证据受限版）

## 核心结论
现有证据只能支持对 **NVIDIA** 的有限描述，以及 **华为昇腾** 的生态/产品存在性描述。**AMD、Intel、寒武纪的竞争力无法评估**——检索未返回任何相关性能或份额数据。因此无法完成五方横向比较。

## NVIDIA（训练+推理）
- 厂商自述：MLPerf Inference v6.0（2026-04-01 发布）中 Blackwell Ultra（GB300 NVL72）在最多模型/场景上取得最高吞吐，且是唯一在所有新增模型/场景提交结果的平台；称 2018 年以来累计 291 项 MLPerf 训练+推理冠军，约为其他提交方合计的 9 倍 [s_f600a45f3f4e]。
- 引用数字：DeepSeek-R1 offline 2,494,310 tok/s（4×GB300 NVL72，288 GPU）；GB300 NVL72 上 DeepSeek-R1 server 8,064 tok/s/GPU（较 v5.1 提升 2.77×）[s_f600a45f3f4e]。
- **重要限定**：以上均为 NVIDIA 营销材料，非 MLCommons 独立数据；每 GPU 指标并非 MLPerf 主指标 [s_f600a45f3f4e]。另有 NVIDIA 博客声称 Blackwell 全负载领先、较 Hopper 提升 15×，同属厂商自述 [s_67d66e8a36ce]。

## 华为昇腾（训练+推理）
- 官方（Huawei Connect 2025，2025-09-18）称 2025 年 1–4 月持续优化 **910B/910C** 推理能力以承载 DeepSeek 流量；未披露算力/带宽规格 [s_83a086543ef2]。
- 训练方案支持 PyTorch、MindSpore、TensorFlow，提供全流程工具与集群能力（页面更新 2025-09-22）[s_9737f6f27d71]。
- 推理侧 Atlas 800I A2：4U 风冷、4×鲲鹏920、32 个 DDR4 插槽、8 模组推理，面向生成式大模型推理 [s_f29735ee7ed5]。
- 软件栈持续迭代：CANN 8.0.T109（2025-03-21）、Ascend Training Solution 24.0.RC3.1（2025-01-11）[s_80cca55fbbc6]。
- 华为 MLPerf 相关公开成绩仅为 **Storage v2.0**（OceanStor A 系列），与训练/推理算力无关，不可用作算力证据 [s_26f025e4bc60]。

## AMD / Intel / 寒武纪
- **无有效证据**。寒武纪官网仅展示 MLU370-S4、MLU290-M5、MLU220 等旧型号，未见思元 590 规格或性能数据 [s_b08730bfd485]。AMD MI300X/MI350、Intel Gaudi 3 无任何检索结果。

## 证据缺口
1. 无 2025–2026 年独立市场份额数据（IDC/Mercury/TrendForce）。
2. 无昇腾 910B/910C 官方算力、HBM 容量/带宽、互联带宽（华为规格页因 SSL 错误未抓取）。
3. 无寒武纪思元 590 规格、框架适配或基准成绩。
4. 无 MLCommons 官方 results 库中昇腾/寒武纪的训练或推理条目。
5. 无任何 AMD/Intel 数据，故"竞争力排序"不可得。

**置信度：0.30**（NVIDIA 部分为厂商自述，华为部分仅支持存在性与生态描述，其余厂商空白）。

**关键来源**：NVIDIA 博客 [s_f600a45f3f4e]；华为 Connect 2025 演讲 [s_83a086543ef2]、昇腾训练方案页 [s_9737f6f27d71]、Atlas 800I A2 页 [s_f29735ee7ed5]、版本说明书 [s_80cca55fbbc6]；寒武纪官网 [s_b08730bfd485]。