# 智能体运行时部署

本文说明如何在本地使用 AgentKit CLI 将本样例部署到混合云智能体运行时。部署模式使用 `hybrid`：镜像在本地构建并上传到目标 CR，运行时在云端创建。

## 1. 准备条件

- 本地 Python 3.10+；本样例建议使用 Python 3.12。
- 已安装 `uv`。
- 已获取当前云管理平台环境的 Region、Access Key ID 和 Secret Access Key。
- 已获取模型 Endpoint ID、模型 API Key 和模型 API Base。
- 本地网络可以访问当前环境的 AgentKit OpenAPI 和镜像仓库。

真实凭据只放在当前终端环境变量中。不要把 AK/SK、模型 API Key、Runtime API Key、内部域名或终端输出提交到仓库。

## 2. 安装项目与 AgentKit CLI

在项目根目录执行：

```bash
uv venv --python 3.12
source .venv/bin/activate
uv sync --extra dev
agentkit --help
```

`agentkit --help` 能正常显示命令列表，才继续配置目标环境。

## 3. 设置本地凭据

在当前终端设置变量。以下均为变量名，不要把真实值写回脚本：

```bash
export VOLCENGINE_ACCESS_KEY=<your-access-key>
export VOLCENGINE_SECRET_KEY=<your-secret-key>
export VOLCENGINE_REGION=<target-region>

export MODEL_AGENT_NAME=<model-endpoint-id>
export MODEL_AGENT_API_KEY=<model-api-key>
export MODEL_AGENT_API_BASE=<model-api-base>
```

关闭终端后这些导出值不会自动保留。如果通过其他安全凭据工具注入环境变量，也可以直接复用。

## 4. 配置目标环境 OpenAPI

仓库提供 [configure_agentkit_cli.sh.example](../scripts/configure_agentkit_cli.sh.example)。执行前只需修改其中的 `COMMON_HOST`：

```bash
# 公共变量配置（从环境变量读取）
# AgentKit OpenAPI 的访问域名，其中 xxx、yyy 为云管理平台用户端的域名，请根据实际情况替换。
COMMON_HOST="openapi.xxx.yyy"
```

`xxx`、`yyy` 必须替换为当前用户环境对应的域名部分。不同环境的域名可能不同，不要复制其他用户或演示环境的实际域名，也不要在引号内留下尾部空格。

确认后执行：

```bash
chmod +x scripts/configure_agentkit_cli.sh.example
./scripts/configure_agentkit_cli.sh.example
```

脚本会配置 AgentKit、IAM、CR、Region、`hybrid` 部署方式以及当前终端提供的 AK/SK。凭据值不会出现在脚本文件中，但 AgentKit CLI 会把它们写入本机的全局配置；请按本机安全规范保护该配置。

## 5. 检查应用配置

复制公开模板生成本地配置：

```bash
cp agentkit.yaml.example agentkit.yaml
agentkit config
```

确认以下项目：

- 应用名称和入口文件分别为 `hybrid_cloud_loop_engineering`、`agent.py`。
- Python 版本为 `3.12`。
- 部署模式为 `hybrid`。
- 依赖文件为 `requirements.txt`。
- `MODEL_AGENT_NAME`、`MODEL_AGENT_API_KEY`、`MODEL_AGENT_API_BASE` 从当前环境变量取得。

`agentkit.yaml` 已被仓库忽略，不要强制提交它。

## 6. 构建并部署

```bash
agentkit launch
agentkit status
```

首次部署通常需要 2～3 分钟。满足以下条件才视为成功：

1. `agentkit status` 显示 Runtime 为 `Ready`。
2. Runtime 日志没有镜像架构、依赖或环境变量启动错误。
3. 控制台在线测试调用 `/invoke` 能返回最终回答。

本样例生产镜像必须使用 `linux/amd64`。需要独立检查镜像时可执行：

```bash
docker build --platform linux/amd64 -t hybrid-cloud-loop-engineering:latest .
```

## 7. 调试与观测

可以在控制台使用在线测试，也可以启动本地 UI，并在顶部“连接配置”中填写 Runtime Endpoint 与 API Key：

```bash
./scripts/run_local_ui.sh
```

完成一次成功请求后，在 **可观测 → Trace 分析** 中按 Runtime 名称、时间和 Trace ID 核对 Agent、Workflow、LLM 与 Tool Span。Runtime 创建或编辑时还需在“高级配置”中开启观测服务并重新发布。

## 8. 查看状态与清理

```bash
agentkit status
```

仅在确认不再使用目标 Runtime 时执行：

```bash
agentkit destroy
```

`destroy` 会删除运行时及相关资源。执行前务必核对当前 Region、Runtime 名称和目标环境。
