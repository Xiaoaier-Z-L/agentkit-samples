#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -t 0 ]]; then
  echo "交互式部署需要终端输入。" >&2
  exit 1
fi

for command in uv docker; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "缺少 ${command}，请先按 README 完成环境准备。" >&2
    exit 1
  fi
done

read_global_target() {
  uv run --frozen python - <<'PY' 2>/dev/null || true
from pathlib import Path

import yaml

path = Path.home() / ".agentkit" / "config.yaml"
config = yaml.safe_load(path.read_text()) if path.exists() else {}
config = config or {}
service = ((config.get("services") or {}).get("agentkit") or {})
print(service.get("scheme") or "", service.get("host") or "", config.get("region") or "")
PY
}

cd "${PROJECT_ROOT}"
read -r global_scheme global_host global_region < <(read_global_target)

if [[ -n "${global_host}" ]]; then
  echo "检测到 AgentKit CLI 环境：${global_scheme:-http}://${global_host}"
  read -r -p "复用该控制面配置？[Y/n] " reuse_target
  reuse_target="${reuse_target:-Y}"
else
  reuse_target="n"
fi

if [[ ! "${reuse_target}" =~ ^[Yy]$ ]]; then
  echo "下面进入 AgentKit CLI 的控制面配置；临时凭据过期时也在这里重新登录。"
  uv run --frozen agentkit config --global --interactive
fi

detected_region="${VOLCENGINE_REGION:-${global_region}}"
if [[ -n "${detected_region}" ]]; then
  echo "检测到已有 Region：${detected_region}（仅供参考）。"
fi
runtime_region=""
while [[ -z "${runtime_region}" ]]; do
  read -r -p "请输入本次 Runtime Region（例如 cn-beijing）: " runtime_region
done
export VOLCENGINE_REGION="${runtime_region}"

echo
echo "选择模型配置："
echo "  1) Demo 默认方舟配置（只需 API Key）"
echo "  2) 自定义 OpenAI-compatible 模型"
read -r -p "请选择 [1]: " model_profile
model_profile="${model_profile:-1}"

case "${model_profile}" in
  1)
    export MODEL_AGENT_NAME="${MODEL_AGENT_NAME:-${ARK_MODEL:-deepseek-v4-pro-260425}}"
    export MODEL_AGENT_API_BASE="${MODEL_AGENT_API_BASE:-${ARK_BASE_URL:-https://ark.cn-beijing.volces.com/api/v3}}"
    ;;
  2)
    model_name="${MODEL_AGENT_NAME:-${ARK_MODEL:-}}"
    model_base="${MODEL_AGENT_API_BASE:-${ARK_BASE_URL:-}}"
    while [[ -z "${model_name}" ]]; do
      read -r -p "Model Name / Endpoint ID: " model_name
    done
    while [[ -z "${model_base}" ]]; do
      read -r -p "OpenAI-compatible API Base: " model_base
    done
    export MODEL_AGENT_NAME="${model_name}"
    export MODEL_AGENT_API_BASE="${model_base}"
    ;;
  *)
    echo "无效选择：${model_profile}" >&2
    exit 1
    ;;
esac

model_key="${MODEL_AGENT_API_KEY:-${ARK_API_KEY:-}}"
while [[ -z "${model_key}" ]]; do
  read -r -s -p "Model API Key（输入不可见且不落盘）: " model_key
  echo
done
export MODEL_AGENT_API_KEY="${model_key}"
export DEMO_MODE=live
export AGENTKIT_EXISTING_RUNTIME_ACTION=prompt

echo "部署目标已确认：Region=${VOLCENGINE_REGION}，Model=${MODEL_AGENT_NAME}，API Key=<redacted>。"
exec bash "${PROJECT_ROOT}/scripts/deploy_hybrid.sh"
