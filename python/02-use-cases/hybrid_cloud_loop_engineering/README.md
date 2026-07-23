# AgentKit 混合云 Loop Engineering 最佳实践

## 这个样例解决什么问题

本样例沿用 [混合云企业智能客服 Demo](../hybrid_cloud_customer_service/) 的真实业务能力与部署链路，专门回答一个生产问题：

> 当一个目标需要 Agent 多步取证、判断和执行时，怎样允许它迭代，又不把停止、成本和副作用交给模型自行决定？

贯穿场景是一条退款闭环：先通过混合云云搜索查询规则依据，再分析 237 笔合成交易，最后在预算允许时创建幂等退款工单。Loop 控制器不重写 Knowledge、MEM0、Session、CRM、Sandbox、MCP、Skill 或 A2A；它只负责把这些已经验证过的能力编排成可测试、可停止、可观测的状态机。

```mermaid
flowchart LR
  A[Objective + acceptance evidence] --> B[Plan]
  B --> C[Budget precheck]
  C --> D[Act through validated business core]
  D --> E[Observe events / citations / tool count]
  E --> F[Critic checks required evidence]
  F -->|accepted and steps remain| C
  F -->|complete / blocked / no progress / budget| G[Stop with reason]
  D --> H[Knowledge / MEM0 / Session / Tools / MCP / Skill / A2A]
  B -. loop.* events .-> T[Local workbench + AgentKit Trace]
```

## 与两个参考样例的关系

| 样例 | 主要证明 |
| --- | --- |
| 混合云客服 Demo | 平台组件和业务能力真实可用 |
| Harness Engineering | 环境、角色、机械反馈、持久状态与完成承诺可工程化 |
| 本 Loop Engineering | 单次业务目标能在硬预算和证据门禁内逐步闭环 |

借鉴 Harness Engineering 的地方是：状态和完成条件必须由系统掌握，反馈必须机器可读，Agent 不能自证完成。沿用混合云 Demo 的地方是：用一个真实业务故事串联平台组件、代码、交互页面、测试、评测和 Runtime 验收，而不是单独展示抽象循环。

## 六个工程落点

1. **目标级计划**：每个步骤声明 `required_events`、引用要求、预计工具数和是否有副作用。
2. **硬预算**：控制器在动作前预留 iteration/tool 预算，执行后按真实 capability events 计数。
3. **单步迭代**：一轮包含 Act → Observe → Critic；只有当前步骤通过才进入下一步。
4. **副作用 checkpoint**：写操作执行前记录幂等范围，Critic 不重跑写操作。
5. **证据验收**：工具事件、Knowledge 引用和安全状态决定是否完成，不使用“看起来正确”。
6. **明确停止**：成功、安全拦截、预算不足、无进展和副作用未验证都有独立 `loop.stop.reason`。

完整设计见 [Loop Engineering 开发指南](docs/loop_engineering.md)。

## 关键目录

```text
hybrid_cloud_loop_engineering/
├── loop_engine.py           # 目标计划、硬预算、证据验收、checkpoint 与停止原因
├── demo_core.py             # 从混合云客服 Demo 复用的已验证业务核心
├── guide_web/               # Loop Engineering 建设路线
├── web/                     # 交互式验收与 loop.* 事件面板
├── agent.py                 # VeADK + AgentKit Runtime 入口
├── demo_app.py              # 无云凭据的确定性 HTTP 服务
├── local_ui.py              # 本地 BFF，Runtime Key 不进入浏览器
├── evaluation/              # 版本化评测集和评估器
├── tests/                   # 业务回归 + Loop 契约和反例测试
├── docs/runtime_deployment.md
├── Dockerfile
└── entrypoint.sh
```

## 本地运行

```bash
cd python/02-use-cases/hybrid_cloud_loop_engineering
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest ruff

ruff check .
pytest -q
DEMO_MODE=demo python client.py
./scripts/run_local_ui.sh
```

浏览器打开 `http://127.0.0.1:8000`：

- 首页按六个阶段解释建设方法；
- 点击“进入验收工作台”运行单步任务或完整退款闭环；
- 推荐提示词：`请做退款闭环：先查规则依据，再分析 237 笔交易，最后提交退款工单`；
- 预期结果为 3 轮、4 次受控能力调用、1 次副作用 checkpoint，最终 `loop.stop(reason=acceptance_criteria_met)`。

将 `LoopPolicy(max_tool_calls=2)` 用于同一场景时，控制器会在创建工单前以 `tool_budget_reached` 停止，证明预算不是展示字段。

## 混合云部署与验收

通用发布步骤见 [智能体运行时部署](docs/runtime_deployment.md)：

```bash
COMMON_HOST="openapi.xxx.yyy"

cp agentkit.yaml.example agentkit.yaml
agentkit config
agentkit launch
agentkit status
```

发布时保持镜像为 `linux/amd64`，监听 8000，并提供 `/app/entrypoint.sh` 与 `/opt/application/run.sh`。在 Runtime **高级配置 → 观测服务**启用观测并重新发布，然后按顺序验收：

1. 运行完整退款闭环，核对 Knowledge 引用、交易分析和单次工单创建。
2. 在应用事件中核对 `loop.plan`、每轮 `loop.observe/critic` 和最终停止原因。
3. 在 AgentKit **可观测 → Trace 分析**核对模型、工具、Token、耗时与实际 Span。
4. 降低工具预算，确认写操作前停止且没有 `tool.work_order.create` Span。
5. 发送 Prompt Injection 样例，确认 `policy_blocked`、工具数为 0。
6. 发送无可用证据的问题，确认 `no_progress`，不会原地重复消耗模型和工具。

## 安全边界

真实模型 Key、Runtime API Key、OAuth JWT、AK/SK、内部域名和平台注入凭据只能通过环境变量或平台组件关联提供。`loop.*` 事件可以记录目标、步骤、预算、事件名和停止原因，但不得记录 Authorization、JWT、API Key、AK/SK、Knowledge token 或 Memory Key。
