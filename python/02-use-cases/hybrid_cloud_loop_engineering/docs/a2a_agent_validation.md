# A2A 数据分析 Agent：部署、注册与验证

本章验证的是**真实的跨 Runtime A2A 调用**，不是 `demo_core.py` 中的本地 fallback 事件。

角色分工：

| Runtime | 镜像入口 | 职责 |
| --- | --- | --- |
| 企业智能客服 | `AGENT_APP_MODE=customer_service` | 识别投诉趋势需求、发现 Agent Card、委派任务并整合结果 |
| 投诉数据分析 Agent | `AGENT_APP_MODE=a2a_data_analyst` | 提供 Agent Card，执行 A2A `message/send`，返回趋势 Artifact |

两者可以复用同一镜像，但必须是两个独立的 AgentKit Runtime。这样 A2A 中心能独立登记、授权和审计数据 Agent。

## 1. 发布数据分析 A2A Agent

在 AgentKit 创建一个新的 Runtime，镜像使用当前项目构建的同一镜像。只需要设置：

```bash
AGENT_APP_MODE=a2a_data_analyst
PORT=8000
```

发布后，在 **A2A 中心 → 注册 A2A 智能体 → 智能体运行时** 中选择这个 Runtime。平台已知该 Runtime 的服务地址，会按该地址发现和登记 AgentCard；因此在 AgentKit Runtime 注册模式下，**不需要填写 `A2A_PUBLIC_URL`，也不需要为此二次发布**。

数据 Agent 对外暴露：

```text
GET  <A2A_PUBLIC_URL>/.well-known/agent-card.json
POST <A2A_PUBLIC_URL>/a2a
```

代码入口在 [a2a_data_agent.py](../a2a_data_agent.py)。它使用 `a2a-sdk` 的 `A2AStarletteApplication` 和 `DefaultRequestHandler`，声明 `complaint-trend-analysis` Skill；任务返回标准 A2A Task、Artifact 和完成状态。

## 2. 先直接验收数据 Agent

先配置本地变量；API Key 从**数据 Agent Runtime** 的快速调用区域复制，不能用主客服 Runtime 的 Key 替代。

```bash
export A2A_AGENT_BASE='https://<data-agent-runtime-public-base>'
export A2A_AGENT_API_KEY='<data-agent-runtime-api-key>'
```

验证 Card：

```bash
curl -sS "$A2A_AGENT_BASE/.well-known/agent-card.json" \
  -H "Authorization: Bearer $A2A_AGENT_API_KEY"
```

预期 JSON 包含：

```json
{
  "name": "hybrid-cloud-complaint-data-agent",
  "url": "https://<data-agent-runtime-public-base>/a2a",
  "skills": [{"id": "complaint-trend-analysis"}]
}
```

再验证标准 A2A 请求：

```bash
curl -sS -X POST "$A2A_AGENT_BASE/a2a" \
  -H "Authorization: Bearer $A2A_AGENT_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": "a2a-proof-001",
    "method": "message/send",
    "params": {
      "message": {
        "kind": "message",
        "messageId": "m-a2a-proof-001",
        "role": "user",
        "parts": [{"kind": "text", "text": "分析过去一年的投诉趋势并预测下季度"}]
      },
      "configuration": {"blocking": true}
    }
  }'
```

预期 HTTP 200，`result.artifacts[0].name` 为 `complaint-trend-analysis`，文本包含“已由 A2A 数据分析 Agent 完成”。若是 401，检查该请求是否使用了数据 Agent Runtime 自己的 API Key。

## 3. 注册到 A2A 中心

进入 **AgentKit → A2A 中心 → 注册 A2A 智能体**：

1. 选择目标 A2A 智能体空间（没有则按平台提示创建）。
2. 选择通过智能体运行时注册，或输入上一步验证成功的 Agent Card URL。
3. 选择控制台自动带出的“服务地址”，保存注册。
4. 注册完成后确认平台生成的 Card 预览中展示 `complaint-trend-analysis`、版本和服务地址。

注册是平台治理和发现入口；平台会根据所选 Runtime 的服务地址定位对端。不要把 Skills Space ID (`ss-...`) 或 Sandbox Tool ID (`t-...`) 填到 A2A 配置中。

## 4. 配置客服主 Agent 的对端

在**企业智能客服主 Runtime**的环境变量中设置：

```bash
A2A_DATA_AGENT_URL=https://<A2A中心登记的服务地址>/a2a
A2A_DATA_AGENT_CARD_URL=https://<A2A中心登记的服务地址>/.well-known/agent-card.json
A2A_DATA_AGENT_API_KEY=<data-agent-runtime-api-key>
A2A_DATA_AGENT_TIMEOUT_SECONDS=30
```

然后发布主 Runtime。`A2A_DATA_AGENT_API_KEY` 仅保留在主 Runtime 环境，不进入浏览器、本地 UI LocalStorage、响应、日志或仓库。

主 Agent 在 [agent.py](../agent.py) 的构造阶段仅在 `A2A_DATA_AGENT_URL` 存在时注册 `delegate_complaint_trend_analysis`。函数实现在 [a2a_client.py](../a2a_client.py)：

```python
async with httpx.AsyncClient(
    timeout=config.timeout_seconds,
    follow_redirects=True,
) as client:
    card = await _discover(client, config)
    response = await client.post(
        config.rpc_url,
        headers={**_headers(config), "Content-Type": "application/json"},
        json={
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "message": message,
                "configuration": {"blocking": True},
            },
        },
    )
    response.raise_for_status()
```

因此链路是“**Card 发现 → Skill 能力校验 → `/a2a` 委派 → Artifact 回传**”，而不是主 Agent 在本地直接调用 `complaint_trend()`。这里必须使用异步 HTTP 客户端；同步请求会阻塞 ADK 调用，可能导致 FaaS 取消请求并产生 `Missing tool results`。

## 5. 最终验收：从主 Agent 发起委派

使用主客服 Runtime 的 endpoint 和 API Key：

```bash
curl -sSN -X POST "$RUNTIME_ENDPOINT/invoke" \
  -H "Authorization: Bearer $RUNTIME_API_KEY" \
  -H 'Content-Type: application/json' \
  -H 'user_id: a2a-verify-user' \
  -H 'session_id: a2a-verify-001' \
  -d '{"prompt":"请调用 delegate_complaint_trend_analysis，委派给 A2A 数据分析 Agent：分析过去一年的投诉趋势并预测下季度。返回委派结果和数据来源说明。"}'
```

预期结果包含：

- `委派给 hybrid-cloud-complaint-data-agent 的结果`；
- `全年 583`、`95-110` 等脱敏示例分析；
- `已由 A2A 数据分析 Agent 完成`。

同时检查两边 Runtime：数据 Agent 有 `GET /.well-known/agent-card.json 200 OK` 和 `POST /a2a 200 OK`；主客服 Agent 的最终响应以 `委派给 hybrid-cloud-complaint-data-agent 的结果` 开头并包含对端统计数据。主 Runtime 没有额外打印 A2A INFO 日志不代表失败，对端两次 HTTP 200 与主响应中的 Agent 名称、远端结果才是端到端证据。工作台点击 **A2A 中心**可查看同一流程、配置、代码与 curl；正式验收建议新建会话后点击“在当前会话演示”。

## 常见失败

| 现象 | 原因与处理 |
| --- | --- |
| Card 访问 404 | 检查数据 Agent 是否以 `AGENT_APP_MODE=a2a_data_analyst` 运行；从 A2A 中心选中的服务地址发起请求，且 URL 没有错误拼接 `/invoke`。 |
| Card 访问 401 | API Key 是数据 Agent Runtime 的 Key；配置到主 Runtime 的 `A2A_DATA_AGENT_API_KEY` 也必须是它。 |
| 主 Agent 不调用委派工具 | 主 Runtime 缺少 `A2A_DATA_AGENT_URL` 或没有重新发布；使用明确包含函数名的验收提示。 |
| `A2A Agent Card does not advertise required skill` | 注册/部署的不是本样例数据 Agent，或 Card 中缺少 `complaint-trend-analysis`。 |
| A2A 中心可见但主 Agent 调用失败 | 平台登记不等于运行时网络连通；先按第 2 步直接 curl 对端。 |
