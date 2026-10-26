# AI芯片市场格局：训练与推理竞争力比较

## 核心结论
现有证据仅能支撑**华为昇腾**与**寒武纪**的部分比较，**NVIDIA、AMD、Intel 的检索证据缺失**，无法完成四类厂商的完整横向对比。以下结论置信度有限。

## 华为昇腾
- **规格（多源不一致）**：910B 采用达芬奇架构、7nm；FP16 有 320 TFLOPS [s_fa8faa8b2f26]、256 TFLOPS [s_167414a81a98]、376 TFLOPS [s_9be912e402a8] 三种说法；INT8 约 640 TOPS [s_fa8faa8b2f26][s_167414a81a98]。功耗亦有 310W [s_fa8faa8b2f26] 与 400W 之别。
- **训练定位**：单卡接近 A100（约 90%–100%）[s_9be912e402a8][s_03561847cac6]；LLM 训练效率约 A100 的 80% [s_02bee2bbac10]。
- **生态**：CANN/MindSpore、ModelArts，配合 MindSpore 可近 2 倍提升 [s_02bee2bbac10]；行业覆盖能源、金融、交通等 [s_167414a81a98]。
- **910C/910D**：称比 H100 快 30%、成本低 17%、光计算能效 200% [s_03561847cac6]，属**媒体转述、未经官方证实**。

## 寒武纪
- **思元370**：7nm、chiplet、390 亿晶体管、256 TOPS(INT8)，为思元270 的 2 倍；国内首款公开支持 LPDDR5 的云端 AI 芯片 [s_bd649514edee][s_cf37c5040094]。
- **思元590（2023）**：对标 A100；百度内部测试显示多数主流模型可支持，训练性能部分接近 A100、部分仅约 50% [s_c74944dab68a]。
- **思元270-S4**：70W，推理向，峰值为思元100 的 4 倍 [s_1849820ea8d9]。
- 思元590 适配 DeepSeek-R1 的供应商说法仅见股吧/雪球类内容 [s_a7ac72c18fc6]，**非官方**。

## 证据缺口
- 未取得 NVIDIA/AMD/Intel 任何规格或实测来源，无法比较其训练/推理竞争力。
- 未取得 hiascend.com / cambricon.com 官方规格页；910B 算力数值多源冲突。
- 910C/D、思元590 具体参数及 MLPerf 类实测缺失；寒武纪 Neuware/BANG 生态与市占、营收数据未覆盖。

## 参考来源
[s_fa8faa8b2f26] modb.pro/wiki/8248；[s_9be912e402a8] hangyan.co；[s_02bee2bbac10] idcsp.com；[s_167414a81a98] hiascend.csdn.net；[s_03561847cac6] takungpao.com；[s_c74944dab68a] 163.com；[s_bd649514edee] cnblogs.com；[s_cf37c5040094] caifuhao.eastmoney.com；[s_1849820ea8d9] kuanfans.com；[s_a7ac72c18fc6] xueqiu.com。

**总体置信度：0.45**（华为/寒武纪部分规格有据但相互冲突；NVIDIA/AMD/Intel 完全缺证，无法支撑完整市场格局判断）。

Incomplete tasks: task_1