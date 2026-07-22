# Ralph Harness 思路在 AgentKit 混合云客服中的实现

## 不是把客服 Agent 再包一层

Harness Engineering 的核心产出是约束系统、可读环境与反馈回路，而不是更多业务代码。本文参考 `deusyu/harness-engineering` 的六个核心概念和 Ralph Demo，把“修改客服退款规则”做成可恢复、可验证、可停止的自主交付循环。

## Ralph Demo 到本样例的映射

| Ralph Demo | 客服规则变更场景 | AgentKit 混合云实现 |
| --- | --- | --- |
| `PROMPT.md` | `SPEC.md` 中的退款窗口与验收标准 | Skill/知识文档随版本发布，Runtime 只读取已发布版本 |
| Planner Hat | 拆分规则、确认、引用、Critic 四类验收项 | VeADK 主 Agent 或 Workflow 生成任务状态 |
| Builder Hat | 在隔离工作区生成候选规则包 | AIO/Skills Sandbox，不直接写生产 Knowledge |
| Tests / backpressure | Schema、窗口范围、人工确认、引用来源检查 | Sandbox 测试 + Code Evaluator + CI；失败结果回写任务状态 |
| Scratchpad | `tasks.json`、`scratchpad.md`、候选规则包 | PostgreSQL Session 保存运行状态，MEM0 只保存稳定经验；大工件落对象存储/仓库 |
| Critic Hat | 独立重载候选包并重跑完整验收 | 独立子 Agent/评估器，不共享 Builder 的临时上下文 |
| `LOOP_COMPLETE` | `HARNESS_COMPLETE` | Finalizer 同时检查任务状态、Critic 证据与迭代预算后才停止 |
| Max iterations | 防止无限修复与成本失控 | Runtime 循环预算、工具预算、超时与 Trace 告警 |

## 六条 Ralph 信条如何落地

1. **Fresh Context Is Reliability**：每轮从版本化 spec、任务状态与候选工件重建上下文，不把无限增长的聊天历史当记忆。
2. **Backpressure Over Prescription**：不给 Builder 写死修复步骤；只返回失败的不变量，让下一轮自主修正。
3. **The Plan Is Disposable**：计划可以重建，验收标准和工件状态才是权威记录。
4. **Disk Is State, Git Is Memory**：运行中状态落 PostgreSQL/对象存储；稳定规范、Skill、测试和文档进入仓库版本。
5. **Steer With Signals, Not Scripts**：用测试失败、评估分数、Trace 和任务状态引导，不用超长 Prompt 规定每个动作。
6. **Let Ralph Ralph**：人定义目标、风险边界和完成条件；Agent 自主选择实现与修复路径。

## 组件职责边界

- Runtime：承载循环、请求身份、模型和 Trace。
- PostgreSQL Session：当前 run、iteration、role、任务状态和恢复点。
- MEM0：跨任务稳定经验；不保存未验证计划或凭据。
- Sandbox：候选规则包的隔离修改与机械测试。
- Skills：Planner/Builder/Critic 的渐进式说明和领域规范。
- Knowledge：只接收 Finalizer 通过后的已发布规则版本。
- Evaluation：评估最终结果与轨迹；Code Evaluator 作为确定性发布门禁。

## 本地确定性示例

`engineering_harness.py` 会运行 Planner → Builder（首次失败）→ Builder（读取机械反馈修复）→ Critic → Finalizer。首次候选故意遗漏引用约束，下一轮只根据 `citation_required` 失败信号修复；Critic 独立从磁盘重载工件，全部通过后才返回 `HARNESS_COMPLETE`。

这里的本地文件存储是无云凭据的可执行参考，只证明循环协议和门禁语义。生产混合云部署不能把 `/tmp` 当持久状态：需要把同一 `spec/tasks/feedback/artifact` 协议接到 PostgreSQL Session 与持久工件存储，并让候选修改真实发生在关联 Sandbox 中。当前仓库尚未声称这条跨 Runtime 重启恢复链路已在线验证。
