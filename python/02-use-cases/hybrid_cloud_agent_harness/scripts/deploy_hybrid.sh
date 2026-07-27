#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="${PROJECT_ROOT}/agentkit.yaml.example"
PROJECT_CONFIG="${AGENTKIT_CONFIG_FILE:-${PROJECT_ROOT}/agentkit.yaml}"
TEMP_CONFIG="$(mktemp "${TMPDIR:-/tmp}/agentkit-harness.XXXXXX.yaml")"
RUNTIME_LIST_FILE=""

cleanup() {
  rm -f -- "${TEMP_CONFIG}"
  if [[ -n "${RUNTIME_LIST_FILE}" ]]; then
    rm -f -- "${RUNTIME_LIST_FILE}"
  fi
}
trap cleanup EXIT
chmod 600 "${TEMP_CONFIG}"

require_value() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "缺少 ${name}。" >&2
    exit 1
  fi
}

for command in uv docker curl; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "缺少 ${command}。" >&2
    exit 1
  fi
done

require_value VOLCENGINE_REGION
require_value MODEL_AGENT_NAME
require_value MODEL_AGENT_API_BASE
require_value MODEL_AGENT_API_KEY

cd "${PROJECT_ROOT}"

if [[ -f "${PROJECT_ROOT}/.env" ]] &&
  grep -Eq '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=' "${PROJECT_ROOT}/.env"; then
  echo "检测到项目 .env；AgentKit 可能把其中所有变量注入 Runtime，本次部署拒绝继续。" >&2
  echo "请仅在当前终端提供模型变量，并暂时移走 .env。" >&2
  exit 1
fi

uv sync --frozen --extra dev
uv run --frozen pytest -q

if ! docker info >/dev/null 2>&1; then
  echo "Docker 尚未运行，请启动 Docker Desktop 后重试。" >&2
  exit 1
fi

read -r control_scheme control_host < <(
  uv run --frozen python - <<'PY'
from pathlib import Path

import yaml

path = Path.home() / ".agentkit" / "config.yaml"
config = yaml.safe_load(path.read_text()) if path.exists() else {}
service = (((config or {}).get("services") or {}).get("agentkit") or {})
print(service.get("scheme") or "", service.get("host") or "")
PY
)
if [[ -z "${control_scheme}" || -z "${control_host}" ]]; then
  echo "AgentKit 全局控制面配置不完整，请先运行 ./scripts/deploy_interactive.sh。" >&2
  exit 1
fi
echo "检查控制面：${control_scheme}://${control_host}/ping"
curl --fail --silent --show-error \
  --connect-timeout 10 \
  --max-time 20 \
  "${control_scheme}://${control_host}/ping" |
  grep --quiet '"pong"' || {
    echo "AgentKit OpenAPI /ping 预检失败。" >&2
    exit 1
  }

if [[ ! -f "${PROJECT_CONFIG}" ]]; then
  cp "${TEMPLATE}" "${PROJECT_CONFIG}"
  chmod 600 "${PROJECT_CONFIG}"
fi

read -r runtime_name configured_runtime_id < <(
  CONFIG_PATH="${PROJECT_CONFIG}" uv run --frozen python - <<'PY'
import os
from pathlib import Path

import yaml

config = yaml.safe_load(Path(os.environ["CONFIG_PATH"]).read_text()) or {}
hybrid = ((config.get("launch_types") or {}).get("hybrid") or {})
print(hybrid.get("runtime_name") or "", hybrid.get("runtime_id") or "")
PY
)
if [[ -z "${runtime_name}" ]]; then
  echo "项目配置缺少 launch_types.hybrid.runtime_name。" >&2
  exit 1
fi

resolved_runtime_name="${runtime_name}"
resolved_runtime_id="${AGENTKIT_RUNTIME_ID:-${configured_runtime_id}}"
if [[ -z "${resolved_runtime_id}" ]]; then
  RUNTIME_LIST_FILE="$(mktemp "${TMPDIR:-/tmp}/agentkit-harness-runtime.XXXXXX")"
  chmod 600 "${RUNTIME_LIST_FILE}"
  if ! uv run --frozen agentkit runtime list \
    --name "${runtime_name}" \
    --region "${VOLCENGINE_REGION}" \
    --all \
    --quiet >"${RUNTIME_LIST_FILE}" 2>/dev/null; then
    echo "Runtime 查重失败；详细控制面错误已隐藏。" >&2
    exit 1
  fi

  existing_runtime_ids=()
  while IFS= read -r runtime_id; do
    [[ -n "${runtime_id}" ]] && existing_runtime_ids+=("${runtime_id}")
  done <"${RUNTIME_LIST_FILE}"

  if [[ "${#existing_runtime_ids[@]}" -gt 1 ]]; then
    echo "发现多个同名 Runtime，无法安全自动选择；请显式设置 AGENTKIT_RUNTIME_ID。" >&2
    exit 1
  elif [[ "${#existing_runtime_ids[@]}" -eq 1 ]]; then
    discovered_runtime_id="${existing_runtime_ids[0]}"
    if [[ "${AGENTKIT_EXISTING_RUNTIME_ACTION:-fail}" = "prompt" && -t 0 ]]; then
      echo "发现同名 Runtime：${runtime_name} (${discovered_runtime_id})"
      echo "  1) 更新这个已有 Runtime（推荐）"
      echo "  2) 输入新名称并创建独立 Runtime"
      read -r -p "请选择 [1]: " runtime_choice
      runtime_choice="${runtime_choice:-1}"
      case "${runtime_choice}" in
        1)
          resolved_runtime_id="${discovered_runtime_id}"
          ;;
        2)
          suggested_name="${runtime_name}-$(date +%m%d%H%M)"
          while true; do
            read -r -p "请输入新 Runtime 名称 [${suggested_name}]: " candidate_name
            candidate_name="${candidate_name:-${suggested_name}}"
            if [[ ! "${candidate_name}" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] ||
              [[ "${#candidate_name}" -gt 63 ]]; then
              echo "名称需为 1–63 位小写字母、数字或连字符，且首尾不能是连字符。" >&2
              continue
            fi
            : >"${RUNTIME_LIST_FILE}"
            uv run --frozen agentkit runtime list \
              --name "${candidate_name}" \
              --region "${VOLCENGINE_REGION}" \
              --all \
              --quiet >"${RUNTIME_LIST_FILE}" 2>/dev/null
            if [[ -s "${RUNTIME_LIST_FILE}" ]]; then
              echo "名称 ${candidate_name} 已存在，请更换。" >&2
              continue
            fi
            resolved_runtime_name="${candidate_name}"
            break
          done
          ;;
        *)
          echo "无效选择；未更新或创建 Runtime。" >&2
          exit 2
          ;;
      esac
    else
      echo "平台已存在同名 Runtime：${runtime_name} (${discovered_runtime_id})。" >&2
      echo "请使用交互部署确认更新，或显式设置 AGENTKIT_RUNTIME_ID。" >&2
      exit 1
    fi
  fi
fi

cp "${PROJECT_CONFIG}" "${TEMP_CONFIG}"
CONFIG_PATH="${TEMP_CONFIG}" \
  RUNTIME_NAME="${resolved_runtime_name}" \
  RUNTIME_ID="${resolved_runtime_id}" \
  uv run --frozen python - <<'PY'
import os
from pathlib import Path

import yaml

path = Path(os.environ["CONFIG_PATH"])
config = yaml.safe_load(path.read_text())
common = config.setdefault("common", {})
runtime_envs = common.setdefault("runtime_envs", {})
runtime_envs.update(
    {
        "DEMO_MODE": "live",
        "AGENT_APP_MODE": "customer_service",
        "MODEL_AGENT_NAME": os.environ["MODEL_AGENT_NAME"],
        "MODEL_AGENT_API_BASE": os.environ["MODEL_AGENT_API_BASE"],
        "MODEL_AGENT_API_KEY": os.environ["MODEL_AGENT_API_KEY"],
    }
)
hybrid = config.setdefault("launch_types", {}).setdefault("hybrid", {})
hybrid["region"] = os.environ["VOLCENGINE_REGION"]
hybrid["runtime_name"] = os.environ["RUNTIME_NAME"]
if os.environ["RUNTIME_ID"]:
    hybrid["runtime_id"] = os.environ["RUNTIME_ID"]
else:
    hybrid.pop("runtime_id", None)
path.write_text(yaml.safe_dump(config, sort_keys=False))
PY

echo "开始构建 linux/amd64 镜像并部署 Harness Runtime。"
set +e
uv run --frozen agentkit launch \
  --config-file "${TEMP_CONFIG}" \
  --platform linux/amd64 \
  --preflight-mode skip
launch_status=$?
set -e

if [[ "${launch_status}" -ne 0 ]]; then
  echo
  echo "部署失败。若日志包含 token expired/unauthorized，请在镜像仓库重新获取临时登录命令，"
  echo "手动 docker login 成功后重新运行本脚本；若名称重复，请修改临时配置中的 runtime_name。"
  exit "${launch_status}"
fi

DEPLOY_CONFIG_PATH="${TEMP_CONFIG}" \
  PROJECT_CONFIG_PATH="${PROJECT_CONFIG}" \
  uv run --frozen python - <<'PY'
import os
from pathlib import Path

import yaml

deploy_path = Path(os.environ["DEPLOY_CONFIG_PATH"])
project_path = Path(os.environ["PROJECT_CONFIG_PATH"])
deploy_config = yaml.safe_load(deploy_path.read_text()) or {}
deploy_hybrid = ((deploy_config.get("launch_types") or {}).get("hybrid") or {})
runtime_id = deploy_hybrid.get("runtime_id") or ""
runtime_name = deploy_hybrid.get("runtime_name") or ""
if not runtime_id or not runtime_name:
    raise SystemExit("launch succeeded but Runtime ID/name was not returned")

project_config = yaml.safe_load(project_path.read_text()) or {}
project_hybrid = project_config.setdefault("launch_types", {}).setdefault("hybrid", {})
project_hybrid["region"] = os.environ["VOLCENGINE_REGION"]
project_hybrid["runtime_id"] = runtime_id
project_hybrid["runtime_name"] = runtime_name
project_path.write_text(yaml.safe_dump(project_config, sort_keys=False))
PY
chmod 600 "${PROJECT_CONFIG}"

uv run --frozen agentkit status --config-file "${TEMP_CONFIG}" --verbose
echo "调用已部署的 live Runtime ..."
uv run --frozen agentkit invoke \
  --config-file "${TEMP_CONFIG}" \
  "请核验一笔客户退款请求，并返回 Harness 治理结果。"
echo
echo "部署与 live /invoke 已完成。请继续在控制台确认 Runtime 为 Ready/RUNNING/Healthy，"
echo "并核对 harness.* 事件以及 Agent、Workflow、LLM/Tool Trace。"
