# 在 AgentKit 混合云开发可控的 Loop Agent

## 1. 先区分业务能力与控制循环

混合云客服 Demo 已经验证 Knowledge、MEM0、PostgreSQL Session、工具、Sandbox、MCP、Skill、A2A、身份和 Runtime。Loop Engineering 不再实现一套平行业务能力，而是在 `loop_engine.py` 中组合 `HybridCustomerService`：

```python
service = LoopEngineeringService(
    mode="live",
    policy=LoopPolicy(max_iterations=3, max_tool_calls=4),
)
result = service.chat(
    message,
    tenant_id=tenant_id,
    user_id=user_id,
    session_id=session_id,
)
```

这条边界很重要：业务工具负责“怎么查、怎么算、怎么写”，Loop 控制器负责“下一步做什么、是否允许做、什么证据算完成、何时停止”。

## 2. 一轮的定义是 Act → Observe → Critic

旧式实现常把“执行”和“评审”伪装成固定两轮，即使只调用了一次业务能力。当前实现把 iteration 定义为一次完整的闭环：

| 阶段 | 结构化事件 | 责任 |
| --- | --- | --- |
| Start | `loop.start` | 固化目标和硬预算 |
| Plan | `loop.plan` | 声明步骤、证据和副作用属性 |
| Act | `loop.iteration.start` | 只执行当前步骤 |
| Checkpoint | `loop.checkpoint` | 写操作前记录幂等范围 |
| Observe | `loop.observe` | 汇总事件、引用和真实工具数 |
| Critic | `loop.critic` | 对照 required evidence 验收 |
| Stop | `loop.stop` | 输出原因、用量和已通过步骤 |

简单交易分析只需要一轮。完整退款闭环需要三轮，因为它有三个独立、可验收的步骤。

## 3. 计划不是自然语言列表，而是执行契约

`LoopStep` 明确声明：

```python
LoopStep(
    step_id="ground_policy",
    instruction="理财产品可以退吗？请给出规则依据。",
    required_events=("knowledge.search",),
    expected_tool_calls=1,
    require_citation=True,
    side_effect=False,
)
```

退款闭环的契约为：

| 步骤 | 必要证据 | 工具预算 | 副作用 |
| --- | --- | ---: | --- |
| `ground_policy` | `knowledge.search` + citation | 1 | 否 |
| `analyze_transactions` | `tool.transaction_analysis` | 1 | 否 |
| `create_work_order` | `memory.read` + `tool.work_order.create` | 2 | 是 |

本地 deterministic planner 用于展示和契约测试。接入模型 Planner 时也必须输出同样的结构化 `LoopStep`，并由代码校验，而不是让模型直接控制任意工具和停止条件。

## 4. 工具预算必须真实计数

控制器维护一组受控能力事件。执行前检查预计调用是否还有预算；执行后按真实事件累计：

```python
if tool_calls_used + step.expected_tool_calls > policy.max_tool_calls:
    stop_reason = "tool_budget_reached"

tool_calls_used += count_controlled_events(result.events)
```

如果实际调用超过预算，停止原因为 `tool_budget_exceeded`。两种原因需要区分：

- `tool_budget_reached`：控制器在动作前成功阻止；
- `tool_budget_exceeded`：底层动作违反预计调用契约，需要排查实现或工具链。

## 5. 副作用不允许自动重试

写步骤执行前产生 `loop.checkpoint`，并记录 `session_id + step_id` 的循环幂等范围。底层 CRM 继续使用 `session_id + operation` 生成业务幂等键。

Critic 只读取本轮结构化结果。如果写步骤缺少 `tool.work_order.create` 证据，控制器以 `side_effect_unverified` 停止，交给人工或补偿流程判断外部状态，不能再次调用创建接口来“看看是否成功”。

## 6. Critic 验证证据，不评价文风

Critic 对当前步骤做集合检查：

```text
missing = required_events - observed_events
if require_citation and citations is empty:
    missing += citation
```

安全事件 `status=blocked` 的优先级最高，立即以 `policy_blocked` 停止。对于只读步骤，如果执行后缺少要求的事件或引用，当前 deterministic controller 以 `no_progress` 停止，因为原样重试不会增加新信息。

生产系统若要支持修订，可以让 Critic 生成一个**新的结构化步骤**，但必须满足：

- 新步骤带新的证据契约和预算估计；
- 已完成步骤不重复；
- 写步骤不自动重试；
- 新计划仍受原始总预算约束。

## 7. 停止原因是运行契约

| reason | 含义 | 后续动作 |
| --- | --- | --- |
| `acceptance_criteria_met` | 所有计划步骤证据齐全 | 正常返回 |
| `policy_blocked` | 安全策略拦截 | 正常拒绝，不重试 |
| `tool_budget_reached` | 下一步执行前工具预算不足 | 调整计划或人工确认预算 |
| `tool_budget_exceeded` | 实际调用超出契约 | 排查业务核心或工具链 |
| `iteration_budget_reached` | 仍有步骤但轮次耗尽 | 缩小目标或提高经批准的预算 |
| `no_progress` | 只读动作没有产生所需证据 | 修复依赖或生成不同计划 |
| `side_effect_unverified` | 写操作结果不可证明 | 核对外部状态，禁止自动重写 |

任何退出路径都必须产生 `loop.stop`，同时记录 `iterations_used`、`tool_calls_used`、`accepted_steps` 和 `planned_steps`。

## 8. AgentKit Runtime 与可观测

`agent.py` 将 `loop_engineering_demo` 注册为 VeADK 工具，并使用 `AgentkitAgentServerApp` 暴露 `/invoke`。平台组件仍通过 Runtime 关联注入，浏览器端不持有 Runtime Key。

应用级事件与平台 Trace 分工如下：

- `loop.*`：解释目标、计划、预算、证据和停止原因；
- AgentKit Trace：证明 Runtime、Agent、Workflow、模型、Token、工具和耗时真实发生。

部署时必须在 **高级配置 → 观测服务**启用观测并重新发布。Trace 可以记录 user/session、iteration、step、工具名和 reason，不得记录任何凭据原文。

## 9. 发布前验收矩阵

| 场景 | 本地契约断言 | 混合云证据 |
| --- | --- | --- |
| 单步交易分析 | 1 轮、1 次工具、正常停止 | `/invoke` 200；分析工具 Span 完整 |
| 完整退款闭环 | 3 轮、4 次工具、1 次 checkpoint | Knowledge、分析、MEM0/CRM Span 顺序一致 |
| 工具预算不足 | 工单执行前 `tool_budget_reached` | Trace 中没有工单写 Span |
| Prompt Injection | `policy_blocked`、工具数 0 | 无危险工具 Span、无敏感信息 |
| 无证据问题 | 1 轮后 `no_progress` | 不发生重复模型/工具调用 |
| 写结果不可证明 | `side_effect_unverified` | 人工核对外部工单状态，不自动重试 |

`tests/test_loop_engine.py` 负责确定性状态机回归；`evaluation/` 负责结果和 Loop 架构语义评测；生产验收再用 AgentKit Trace 验证真实执行轨迹。
