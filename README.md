<div align="center">

---

## 当前阅读入口

- [三条主线的简历描述](docs/resume-deep-research-agent.md)
- [项目介绍、演示与面试准备](docs/interview-preparation.md)
- [实现与验证记录](docs/implementation-status.md)

当前围绕 DAG 异步编排、共享记忆与上下文压缩、Red–Blue 证据审查三条主线整理材料。上下文片段和有限审查是设计取舍，不承诺所有回答正确，也不因效果未尽完善继续添加机制。

## 📖 项目背景

大语言模型在单一问答场景表现优异，但在**复杂深度研究任务**中面临三个核心挑战：

1. 🔥 **信息爆炸与上下文遗忘** —— 长文本检索后关键信息淹没在噪声中，模型难以聚焦
2. 👻 **幻觉与事实漂移** —— 多轮推理过程中，模型倾向于"编造"未经验证的事实
3. 📊 **缺乏系统性评估** —— 现有评测多以单轮 QA 为主，缺少对"深度研究报告"这一输出形态的端到端评价体系

本项目构建了一套**面向深度研究任务的 Agent 系统**，覆盖规划、执行、记忆、压缩、审查与评测记录；训练相关模块保留扩展接口。

---

## 🎯 实验动机

> **"如果一个 Agent 只能回答简单问题，那它和搜索引擎有什么区别？"**

我们的动机是：**让 AI 真正具备"深度研究"的能力**——不只是检索信息，而是像人类研究员一样：

- 🧩 **拆解复杂问题** → 将模糊的研究目标分解为可执行的子任务
- 🔍 **多源信息整合** → 从网页、论文、数据库等多渠道收集证据
- ⚖️ **批判性审视** → 主动发现并修正报告中的错误和偏见
- 📝 **结构化输出** → 生成带引用、有逻辑、可验证的研究报告

---

## 💡 解决方法

### 核心模块与扩展接口

| 模块                               | 职责               | 核心技术                                        |
| ---------------------------------- | ------------------ | ----------------------------------------------- |
| 🎛️ **M1 Orchestrator**     | 多智能体编排与调度 | 自研 asyncio + DAG 执行引擎，9 状态状态机       |
| 🗺️ **M2 Planner**          | 复杂问题拆解       | JSON DAG 动态规划，支持执行中 replan            |
| 🗜️ **M3 Compressor**       | 长上下文压缩       | Embedding 相关性筛选、TextRank、层级摘要    |
| 🧠 **M4 Memory Store**       | 跨 Agent 共享记忆  | SQLite + NumPy 向量索引、语义检索与保守去重 |
| ⚔️ **M5 Adversarial Loop** | 证据审查与修复     | Red–Blue 结构化审查、候选复核与预算控制      |
| 🧬 **M6 Evolution Engine**   | 扩展实验接口       | GRPO 与符号规则学习相关接口，不作为当前主线        |

### 数据流全景

```raw
用户 Query
    ↓
🗺️ Planner 拆解为 DAG 子任务图
    ↓
🎛️ Orchestrator 按拓扑排序并发调度
    ↓
🤖 Worker Agents 调用 🔍 搜索 / 📄 论文 / 🌐 网页 工具
    ↓
🧠 Memory Store 写入中间结果，供后续任务检索复用
    ↓
🗜️ Compressor 压缩长上下文（L1→L2→L3）
    ↓
📝 Summarizer 合成带来源的 Markdown 报告
    ↓
⚔️ Red Agent 审查 → 必要时 Blue Agent 修复 → 复核候选
    ↓
📤 输出带元信息的结构化研究报告
```

---

## ✨ 项目精彩之处

### 🏗️ 1. 自研编排引擎，不依赖 LangGraph/AutoGen

> 当前规模下用 asyncio 显式组织依赖数据流、预算和失败收尾，便于定位问题与解释取舍。

- 基于 `asyncio` + `Semaphore` 实现 **DAG 拓扑并发执行**
- **9 状态状态机**：IDLE → PLANNING → DISPATCHING → COLLECTING → SYNTHESIZING → ADVERSARIAL → DONE
- **分级降级策略**：任务超时与失败依赖按规则处理 → 失败比例触发有界 replan → 在收尾预算内合成部分报告，否则返回已有结果和未完成原因

### ⚔️ 2. Red–Blue 证据审查与定向修复

> 将问题定位与修复分工，不涉及 GAN 训练，也不保证消除所有事实错误。

- **Red Agent** 默认审查事实与无依据声明，可配置其他维度，输出问题位置、类型及证据。
- **Blue Agent** 执行原地修正、补充检索或删除，并对修改进行自检。
- **候选复核**：记录来源、修改前后版本及评分；复核或预算不足时保留已接受的报告。
- **有界迭代**：根据配置的轮数、调用预算、分数或变化量终止，记录遗留问题与停止原因。

### 🗜️ 3. 语义级上下文压缩 —— 不是简单截断

> 关键词匹配会丢失语义，简单截断会丢失关键信息。**我们用 Embedding 做语义压缩**。

- **L1 粗过滤**：按查询相关性与当前预算筛选内容
- **L2 细筛选**：TextRank + Query-Biased 提取关键句
- **L3 层级摘要**：在更紧预算下进一步汇总；必要时采用窗口兜底，存在信息损失

### 🧠 4. 跨 Agent 共享记忆

- **保守去重**：相似度提出候选，再核对规范化文本，避免合并不同数值或否定结论。
- **可选冲突接口**：启发式标记与冲突处理接口，不作为通用事实判别能力或当前简历主线。
- **Session 隔离**：共享 SQLite 中按会话逻辑过滤，并以运行/任务作用域管理结果；不等同于物理数据库隔离

### 🔌 5. 多后端 LLM 路由 —— 零源码切换模型

```yaml
# configs/default.yaml
model:
  backend_mapping:
    solver: "deepseek"      # 研究
    planner: "deepseek"     # 结构化输出
    red_agent: "mimo"       # 审查
    blue_agent: "mimo"
    judge: "mimo"
    compressor: "mimo"
```

- 支持通过配置选择 DeepSeek / MiMo / vLLM / OpenAI 等兼容后端
- 模块级采样参数集中管理，**避免配置漂移**
- `.env` 驱动，**零源码修改**接入新后端

### 📊 6. 评测入口与结果记录

> 评测入口与统计工具已提供；离线、组件与真实链路记录分别保存，不声明统计显著性或普遍效果收益。

| 评测层级                        | 方法                                          | 特点                              |
| ------------------------------- | --------------------------------------------- | --------------------------------- |
| 📏 **规则指标**           | 参考事实匹配、引用覆盖等启发式指标 | 不替代事实正确性或引用支持核验         |
| 📚 **公共数据集**         | HotpotQA 多跳 QA 深度研究变体                 | 传统 EM/F1 + 新增语义覆盖度       |
| 🏗️ **自建评测集**       | ResearchBench 35 题 × 11 领域                | 含 expected_topics + ground_truth |
| 👨‍⚖️ **LLM-as-Judge** | MiMo 5 维度 0-10 分深度评分                   | 定性+定量互补                     |
| 🥊 **Head-to-Head**       | Agent vs 单轮 LLM 直接对比                    | pairwise 更可靠                   |
| 📈 **统计工具**           | Bootstrap CI + Cohen's d + t-test             | 预留分析能力，不代表已有显著性结论 |

---

## 🚀 快速开始

当前代码与验证范围见 [实施记录](docs/implementation-status.md)：保存了 69 项完整离线回归记录，以及后续针对性回归和真实研究记录；真实 embedding 与合成错值审查也有对应产物。检索约束和正文证据回传另见[检索质量记录](docs/retrieval-quality-review.md)，尚无多题效果收益结论。测试与验证脚本使用独立数据库和目录。

### 环境准备

```bash
# 1. 克隆项目
git clone https://github.com/qiqihezh/deepresearch-agent.git
cd deepresearch-agent

# 2. 创建 uv 虚拟环境并激活
uv venv .venv
source .venv/bin/activate

# 3. 安装核心依赖
pip install -r requirements.txt

# 4. 配置 API Key（复制模板后填入）
cp .env.template .env
# 编辑 .env：填入 DEEPSEEK_API_KEY、BOCHA_API_KEY 等
```

### 三种运行方式

本机 Windows 若 `.venv` 解释器写入被拒绝，可在项目根目录使用匹配 Python 版本的 `(base)` 环境：

```powershell
python scripts/run_interview_checks.py --smoke --timeout 90
python scripts/run_interview_checks.py --count 1 --compare 1 --timeout 90
python scripts/run_interview_checks.py --question-id tech_002 --count 1 --compare 0 --timeout 90
```

检查入口和 `run_single.py` 会加载 `.venv/Lib/site-packages` 中已安装的项目依赖，无需激活 `.venv`。完整检查会先核验真实 embedding；`technical_chain_success` 要求完整非空报告、来源、任务完成、无执行异常以及所需审查完成，不代表事实和引用已人工核验。运行记录保存在 `docs/runs`。

**🎯 单条 Query（单次深度研究）**

```bash
python scripts/run_single.py \
    --query "2024-2025年大模型Agent技术趋势与落地案例研究" \
    --config configs/default.yaml
```

**💬 交互式 REPL（支持 Session 继承与连续追问）**

```bash
python scripts/run_repl.py
# 交互命令: ls / sessions / save / q
```

**🔬 批量实验（全量评测体系，overnight 可跑完）**

```bash
python scripts/run_all_experiments.py \
    --report_file outputs/reports1/report_xxx.md \
    --report_query "你的研究问题"
```

> 批量实验默认配置：模块消融 5×12 题 + 轮数消融 4×12 题 + 标准评测 35 题 + 领域对比 3×5 题 + Agent vs LLM 3 题 + Judge 1 次 = **165 次独立研究运行**

---

## 📁 仓库结构

```raw
deep_research_agent/
├── 📁 configs/                    # YAML 配置中心
│   ├── default.yaml               # 全局默认配置
│   ├── agents/                    # Agent 行为配置
│   ├── interaction_config/        # 交互层配置
│   └── tool_config/               # 工具层配置
│
├── 📁 src/                        # 核心源码（~5000 行）
│   ├── 📁 core/                   # 核心运行层
│   │   ├── runner.py              # 初始化模块 + 执行完整研究流程
│   │   ├── judge.py               # MiMo Judge 统一接口
│   │   └── ablation.py            # 消融实验通用框架
│   │
│   ├── 📁 orchestrator/           # 🎛️ M1: 多智能体编排器
│   ├── 📁 planner/                # 🗺️ M2: 自适应规划器
│   ├── 📁 compressor/             # 🗜️ M3: 上下文压缩器
│   ├── 📁 memory/                 # 🧠 M4: 共享记忆存储
│   ├── 📁 adversarial/            # ⚔️ M5: 对抗降噪循环
│   ├── 📁 evolution/              # 🧬 M6: 自进化引擎
│   ├── 📁 agents/                 # 🤖 Agent 实现
│   ├── 📁 models/                 # 🔌 模型路由层
│   ├── 📁 tools/                  # 🛠️ 工具层
│   └── 📁 utils/                  # 🧰 工具函数
│
├── 📁 evaluation/                 # 评测体系（~2000 行）
│   ├── benchmarks/                # 评测集（ResearchBench / HotpotQA）
│   ├── metrics/                   # 指标（规则 / Judge / 统计 / 综合）
│   └── analyze_ablation.py        # 消融实验结果分析
│
├── 📁 scripts/                    # 可执行脚本
│   ├── run_single.py              # 🎯 单条 query CLI
│   ├── run_repl.py                # 💬 交互式 REPL
│   ├── run_all_experiments.py     # 🔬 一键批量实验
│   ├── run_ablation.py            # 消融实验独立入口
│   ├── run_benchmark.py           # 🥊 Agent vs LLM
│   ├── run_eval.py                # 标准评测入口
│   ├── run_judge.py               # 👨‍⚖️ Judge 深度评分
│   └── validate_env.py            # 环境配置检查
│
├── 📁 verl/                       # veRL 训练框架（GRPO）
├── requirements.txt               # 依赖清单（分级安装）
└── README.md                      # 📖 本文件
```

---

## 🛠️ 技术栈

| 层级        | 技术                                         |
| ----------- | -------------------------------------------- |
| 🐍 语言     | Python 3.11                                  |
| ⚡ 异步框架 | asyncio                                      |
| 🧠 LLM 后端 | DeepSeek API / MiMo 2.5 Pro / vLLM / OpenAI  |
| 🔢 嵌入模型 | sentence-transformers (`all-MiniLM-L6-v2`) |
| 💾 持久化   | SQLite + numpy 向量索引                      |
| 🎓 训练框架 | veRL (GRPO)                                  |
| 🔭 可观测性 | LangSmith                                    |
| 📦 虚拟环境 | uv                                           |

---

## 🗺️ Roadmap

- [X] 自研编排引擎（asyncio + DAG）
- [X] Red-Blue 对抗降噪
- [X] 语义级上下文压缩
- [X] 跨 Agent 共享记忆
- [X] 多后端 LLM 路由
- [X] 评测入口与指标口径修复（规则 + 可选 Judge；效果结论另行验收）
- [X] REPL 交互式会话
- [ ] 实验结果填充（进行中 🔥）
- [ ] Web UI（Gradio/Streamlit）
- [ ] 用户反馈闭环
- [ ] 多模态支持（图像/表格）

---

## 🤝 贡献

欢迎提交 Issue 和 PR！无论是 bug 修复、功能增强还是文档改进，我们都非常感谢。

---

## 📄 License

[MIT](LICENSE) © 2025 DeepResearch Agent Contributors
