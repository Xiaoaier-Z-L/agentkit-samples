# AgentKit Runtime 评测验证

本目录只验证评测链路，不修改 Agent、Runtime、Trace 或业务工具代码。

## 验证对象

| 项目 | 平台对象 |
|---|---|
| 评测集 | `hybrid_loop_engineering_runtime_core_v1` |
| LLM 评估器 | `runtime_answer_correctness_v1` |
| Code 评估器 | `runtime_deterministic_checks_v1` |
| 评测对象 | `hybrid-cloud-loop-engineering-demo-v2` |
| 已验证实验 | `jilidemo` |

评测集包含 5 条链路：知识库 Canary、安全拒答、Sandbox `run_code` 数值计算、A2A 数据 Agent 委派，以及 Loop 评审/停止原因。前四条继承首个 Demo 的平台验证基线；第五条是本样例新增的架构验收 Case，部署新 Runtime 后需重新运行平台实验。

## 1. 导入评测集

使用 [runtime_core_dataset.jsonl](./runtime_core_dataset.jsonl) 创建评测集，字段保持为：

- `input`：发送给 Runtime 的问题。
- `reference_output`：评估器使用的验收标准，不会直接发送给 Runtime。

## 2. 创建评估器

### LLM 评估器

创建 `runtime_answer_correctness_v1`，用途是判断回答的事实正确性、完整性和任务完成度。它适合做语义质量判断，但可能对工具数值、标记字符串等确定性结果产生误判。

字段映射：

- 评估器 `input` ← 评测集 `input`
- 评估器 `output` ← 评测对象 `actual_output`
- 评估器 `reference_output` ← 评测集 `reference_output`

### Code 评估器

创建 `runtime_deterministic_checks_v1`，复制 [runtime_deterministic_checks.py](./runtime_deterministic_checks.py) 中完整的 `exec_evaluation` 函数。

平台传入的 `turn` 结构为：

- `evaluate_dataset_fields`：评测集字段。
- `evaluate_target_output_fields`：Runtime 实际输出字段。
- `ext`：补充字段。

返回值必须是 `EvalOutput(score=..., reason=...)`。不能返回普通字典，否则平台读取 `.score` 时会报错。

## 3. 创建实验并关联 Runtime

选择 `AgentKit 智能体` 作为评测对象，再选择主 Runtime：

1. 评测对象 `input` ← 评测集 `input`
2. LLM/Code 评估器 `input` ← 评测集 `input`
3. LLM/Code 评估器 `output` ← 评测对象 `actual_output`
4. LLM/Code 评估器 `reference_output` ← 评测集 `reference_output`

建议最大并发先设为 `1`，稳定后再逐步增加。这一步才真正将评测集请求发送给主 Runtime；评估器页面里的“试运行”只使用右侧模拟 JSON，不代表已经关联 Runtime。

## 4. 已验证结果

实验 `jilidemo` 的实际结果：

| 指标 | 结果 |
|---|---:|
| 数据项 | 4 |
| Runtime 执行成功 | 4/4 |
| Code 确定性检查 | 4/4 |
| LLM 正确性判断 | 3/4 |

LLM 评估器将 Sandbox 样例判为 `0`，但 Code 评估器验证数值正确并得分 `1`。因此该条属于 LLM Judge 的口径/稳定性问题，不是 Runtime 或 `run_code` 调用失败。验收确定性链路时以 Code 评估器为准，LLM 评估器用于补充回答质量。

## 验收标准

- 每条数据均应产生 `actual_output`；新增 Loop Case 还必须出现 `loop.critic`、`loop.stop` 和明确停止原因。
- Code 评估器 4/4 通过。
- A2A 输出包含委派说明和 `234/142/89/118/583`。
- Sandbox 输出包含约 `5420.464135` 的结果。
- 安全样例拒绝提示词注入且未泄露系统指令。
- 知识库样例包含 `KB_CANARY_20260717_01` 和 `knowledge_canary.md`。
