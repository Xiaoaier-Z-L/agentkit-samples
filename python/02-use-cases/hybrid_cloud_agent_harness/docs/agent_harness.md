# 在 AgentKit 混合云开发 Agent Harness

> 本文描述 Runtime 请求级安全包络，它是完整 Harness Engineering 的一层，不是全部。自主交付循环、fresh context、机械背压、持久状态和完成承诺见 [Ralph Harness 思路在混合云客服中的实现](ralph_customer_service_mapping.md) 与 `engineering_harness.py`。

## 1. Harness 的职责

Harness 是 Agent 的生产运行包络，不是另一个业务 Agent。它把所有请求都必须经过的治理逻辑放在一个稳定边界中。

| 层 | 代码事件 | 责任 |
| --- | --- | --- |
| Request | `harness.request.accept` | 校验请求结构和大小 |
| Identity | `harness.identity.bind` | 绑定网关认证后的租户、用户、会话 |
| Policy | `harness.policy.precheck` | 编译全局 + 路由级 allowlist 与调用预算 |
| Router | `harness.route.select` | 选择已注册业务路径 |
| Agent | 原 `identity/session/security/tool/...` 事件 | 执行已验证业务核心 |
| Tool gate | `harness.tools.authorize` | 逐次核对实际调用、路由权限与预算 |
| Output | `harness.output.validate` | 检查回答、引用、安全状态和工具证明 |
| Telemetry | `harness.telemetry.export` | 递归脱敏后汇聚 Trace，记录最终决策 |

## 2. 代码边界

```python
def agent_harness_demo(message: str) -> str:
    identity = request_identity()  # request-scoped ContextVar
    return harness.invoke(
        message,
        tenant_id=identity.tenant_id,
        user_id=identity.user_id,
        session_id=identity.session_id,
        identity_source=identity.source,
    )
```

业务能力仍由 `HybridCustomerService` 提供。模型可见的工具 schema 只有 `message`，不包含 tenant/user/session，模型无法用工具参数伪造身份。`RequestAuthorizationMiddleware` 从网关头绑定请求级上下文；Harness 只依赖业务核心返回的结构化事件，不读取工具内部凭据，也不把跨切面策略散落到每个工具。

## 3. 身份与凭据边界

AgentKit 网关先验证 OAuth JWT 或 Runtime API Key。应用只消费网关覆盖后的 tenant/user/session 头，不能相信 Prompt 中声称的 user_id；如果网关不提供 tenant，使用 Runtime 的受信部署变量 `HARNESS_TENANT_ID`，不能使用模型参数兜底。生产网关必须删除客户端自带的同名身份头再写入已验证值。Knowledge Bearer token 保持请求级传递；MEM0、PostgreSQL、Sandbox、MCP 等凭据由平台组件关联注入。

请求大小与身份字段在调用业务 Agent 前校验。即使绕过 FastAPI/Pydantic 直接调用 Python API，空 tenant/user/session、缺失 identity source 和超长消息也会被拒绝，业务核心不会执行。

Harness 在导出前递归检查回答、引用和每个事件的 `detail`。敏感键会整体替换，字符串中的 Bearer token、API Key 和 AK 形态也会被替换：

```text
redaction = authorization-and-secrets
```

## 4. 工具注册表和预算

`HarnessPolicy.allowed_tools` 是全局注册表；`RoutePolicy` 再为 analysis、delegation、customer_operation、sandbox、compliance 和 grounded_answer 分配最小能力集合与独立预算。两者交集在业务执行前写入 `harness.policy.precheck`，形成可审计的策略决定。

执行后 Harness 对每一次受控能力事件做证明核验，不按名称去重：

- 不在全局注册表中：`unregistered`；
- 已注册但不属于本路由：`route_denied`；
- 实际调用次数超过路由或全局预算：`budget_exceeded`。

任何一项失败，原始业务回答和引用都会被丢弃，调用方只得到统一治理拒绝响应。这是 fail-closed，不是只在 Trace 中告警。

工具不可用、未注册或超预算时必须返回明确失败，禁止模型用自然语言伪造成功。写操作仍依赖业务核心的参数校验、人工确认与幂等键。

## 5. AgentKit Runtime 集成

`agent.py` 将 `agent_harness_demo` 注册为 VeADK 工具，使用 `AgentkitAgentServerApp(agent=..., short_term_memory=...)`。Knowledge、Memory、Session、MCP、Sandbox、Skills 与 A2A 的挂载方式与第一个已验证 Demo 一致。

生产镜像使用 `linux/amd64`、监听 8000，并提供 `/app/entrypoint.sh` 与 `/opt/application/run.sh`。公开测试和本地 UI 调用 `/invoke`，不会使用 `/list-apps` 的 ADK 在线调试流程。

## 6. 可观测设计

本地 UI 展示 `harness.*` 应用事件；平台 Trace 展示 Runtime、Agent、Workflow、模型和工具 Span。部署时必须在 Runtime **高级配置 → 观测服务**开启观测并重新发布。

建议在 Trace 中检查：

- `user.id`、`session.id` 与测试请求一致；
- 工具名称属于 allowlist；
- Token、耗时和状态码完整；
- Authorization、JWT、API Key、AK/SK 不存在于输入输出、属性和日志；
- 攻击请求没有危险工具 Span。

## 7. 本地与混合云验收矩阵

| 场景 | 本地确定性断言 | 混合云证据 |
| --- | --- | --- |
| 交易分析 | 路由为 analysis，预算 1，仅授权交易工具 | `/invoke` 200，工具 Span 与 allowlist 一致 |
| 知识问答 | 输出有引用且校验成功 | 命中已发布云搜索 Knowledge |
| 身份 | `identity.bind` 有 tenant/user/source | JWT 与 API Key 分别通过网关验证 |
| 攻击请求 | 业务 blocked，Harness 正常完成输出校验 | 无敏感信息和危险工具 Span |
| 组件缺失 | 不伪造工具结果 | 解绑组件后返回明确降级或失败 |
| 未知/跨路由工具 | `tools.authorize=blocked`，原始结果不返回 | Trace 中治理决策为 deny |
| 重复超预算 | 相同工具调用两次仍按 2 次计数并阻断 | 工具 Span 数量与 observed_call_count 一致 |
| 敏感事件字段 | 递归替换并累计 `redacted_fields` | Trace/日志中不存在凭据原文 |

## 8. 扩展方式

新增业务 Agent 时注册新的 route 和 `RoutePolicy`，不复制身份、策略或 Telemetry 代码。新增平台能力时先更新全局注册表、路由最小权限、预算和反例测试，再把 VeADK 工具加入 `agent.py`。
