from __future__ import annotations

import re
from pathlib import Path

import local_ui
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def iter_lines(self, decode_unicode: bool = False):
        assert decode_unicode is True
        return iter(
            [
                'data: {"content":{"parts":[{"text":"internal", "thought":true}]}}',
                'data: {"content":{"parts":[{"text":"最终回答"}]}}',
            ]
        )


def test_remote_ui_omits_model_thought(monkeypatch) -> None:
    monkeypatch.setenv("RUNTIME_ENDPOINT", "https://runtime.example/")
    monkeypatch.setenv("RUNTIME_API_KEY", "test-key")
    monkeypatch.setattr(local_ui.requests, "post", lambda *args, **kwargs: FakeResponse())

    result = local_ui.chat(local_ui.LocalChatRequest(message="测试"))

    assert result["answer"] == "最终回答"
    assert result["thoughts"] == ["internal"]


def test_remote_ui_forwards_incremental_sse(monkeypatch) -> None:
    monkeypatch.setenv("RUNTIME_ENDPOINT", "https://runtime.example/")
    monkeypatch.setenv("RUNTIME_API_KEY", "test-key")
    monkeypatch.setattr(local_ui.requests, "post", lambda *args, **kwargs: FakeResponse())

    response = TestClient(local_ui.app).post("/ui/chat/stream", json={"message": "测试"})

    assert response.status_code == 200
    assert "event: thought" in response.text
    assert "event: answer" in response.text
    assert "event: done" in response.text


def test_remote_ui_requires_api_key(monkeypatch) -> None:
    monkeypatch.setenv("RUNTIME_ENDPOINT", "https://runtime.example/")
    monkeypatch.delenv("RUNTIME_API_KEY", raising=False)

    response = TestClient(local_ui.app).post("/ui/chat/stream", json={"message": "测试"})

    assert response.status_code == 200
    assert "RUNTIME_API_KEY is missing" in response.text


def test_runtime_config_is_process_local_and_never_returns_key(monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_ENDPOINT", raising=False)
    monkeypatch.delenv("RUNTIME_API_KEY", raising=False)
    client = TestClient(local_ui.app)

    response = client.post(
        "/ui/runtime-config",
        json={"endpoint": "https://runtime.example/invoke", "api_key": "secret-key"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "remote": True,
        "endpoint": "https://runtime.example",
        "api_key_configured": True,
        "source": "ui-session",
    }
    assert "secret-key" not in client.get("/ui/config").text
    client.delete("/ui/runtime-config")


def test_evaluation_navigation_items_are_interactive() -> None:
    client = TestClient(local_ui.app)

    index = client.get("/")
    app_js = client.get("/web/app.js")

    assert index.status_code == 200
    assert '<p class="nav-caption">离线评测</p>' in index.text
    assert '<button class="nav-item nav-subitem" data-module="evaluation_dataset">' in index.text
    assert '<button class="nav-item nav-subitem" data-module="evaluator">' in index.text
    assert '<button class="nav-item nav-subitem" data-module="experiment">' in index.text
    assert "大模型调度平台" not in index.text
    assert "evaluation_dataset: {" in app_js.text
    assert "evaluator: {" in app_js.text
    assert "experiment: {" in app_js.text
    assert "evaluate_target_output_fields" in app_js.text


def test_navigation_and_module_guides_stay_aligned() -> None:
    client = TestClient(local_ui.app)
    index_text = client.get("/").text
    app_js_text = client.get("/web/app.js").text

    nav_modules = set(re.findall(r'data-module="([a-z0-9_]+)"', index_text))
    module_block = app_js_text.split("const MODULES = {", 1)[1].split("\n};", 1)[0]
    guide_modules = set(re.findall(r"^  ([a-z0-9_]+): \{", module_block, re.MULTILINE))

    assert nav_modules == guide_modules


def test_public_guides_use_hybrid_cloud_backends_and_sanitized_trace_data() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text()
    app_js = (PROJECT_ROOT / "web/app.js").read_text()
    bootstrap = (PROJECT_ROOT / "scripts/bootstrap_platform.py").read_text()

    assert "云搜索" in readme
    assert "MEM0" in readme
    assert "provider-knowledge-id" not in bootstrap
    assert "Trace ID：<platform-trace-id>" in app_js
    assert "openai/<model-endpoint>" in app_js


def test_runtime_deployment_guide_uses_environment_specific_openapi_host() -> None:
    client = TestClient(local_ui.app)
    index = client.get("/").text
    app_js = client.get("/web/app.js").text
    readme = (PROJECT_ROOT / "README.md").read_text()
    deployment = (PROJECT_ROOT / "docs/runtime_deployment.md").read_text()
    configure_script = (PROJECT_ROOT / "scripts/configure_agentkit_cli.sh.example").read_text()

    assert 'data-module="runtime"' in index
    assert "runtime: {" in app_js
    assert 'COMMON_HOST="openapi.xxx.yyy"' in app_js
    assert "智能体运行时部署" in readme
    assert 'COMMON_HOST="openapi.xxx.yyy"' in deployment
    assert 'COMMON_HOST="openapi.xxx.yyy"' in configure_script
    assert "VAE" not in readme
    assert "VAE" not in deployment
    fixed_demo_host = "top." + "vestack.cloud"
    assert fixed_demo_host not in app_js + readme + deployment + configure_script


def test_identity_self_check_and_streaming_hints_are_visible() -> None:
    client = TestClient(local_ui.app)

    index = client.get("/")
    app_js = client.get("/web/app.js")

    assert index.status_code == 200
    assert ">身份自检</button>" in index.text
    assert "本地 UI 会自动隐藏 thought:true 的思考事件" in index.text
    assert "远端 SSE 会被解析为最终回答" in index.text
    assert "正确阅读在线测试响应" in app_js.text
    assert "content.parts[].thought = true" in app_js.text
    identity_panel = app_js.text.split("  identity: {", 1)[1].split("  session: {", 1)[0]
    knowledge_panel = app_js.text.split("  knowledge: {", 1)[1].split("  memory: {", 1)[0]
    assert "请求范围内传递 Bearer 凭据" not in identity_panel
    assert "供知识库适配器调用" not in identity_panel
    assert "Backend 从当前请求读取 Bearer 凭据" in knowledge_panel


def test_observability_module_shows_trace_code_and_verified_data() -> None:
    client = TestClient(local_ui.app)

    index = client.get("/")
    app_js = client.get("/web/app.js")

    assert 'data-module="observability"' in index.text
    assert "查看本次本地 UI 会话收集的 Trace 历史" in index.text
    assert "observability: {" in app_js.text
    assert "观测服务：☑ 启用" in app_js.text
    assert "这是平台 Trace 的前置条件" in app_js.text
    assert "AgentkitAgentServerApp" in app_js.text
    assert "generate_content        llm" in app_js.text
    assert "Total / Input / Output Tokens" in app_js.text
    assert "Trace ID：<platform-trace-id>" in app_js.text
    assert "openai/<model-endpoint>" in app_js.text
    assert "traceBadge.addEventListener('click', openTrace)" in app_js.text
