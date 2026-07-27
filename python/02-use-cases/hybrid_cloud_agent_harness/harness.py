"""Production governance envelope for the validated hybrid-cloud business agent.

The business core decides *what* to do.  This module owns the controls that
must be identical for every business agent: request validation, trusted
identity binding, route-scoped capability policy, budgets, output contracts,
redaction and auditable governance events.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from demo_core import HybridCustomerService
from utils.models import AgentResponse, CapabilityEvent

CONTROLLED_CAPABILITY_PREFIXES = (
    "tool.",
    "knowledge.",
    "memory.",
    "a2a.delegate.",
    "sandbox.",
    "mcp.tool_",
    "skill.execute",
)
SENSITIVE_KEY_PARTS = (
    "authorization",
    "api_key",
    "access_key",
    "secret",
    "password",
    "credential",
    "session_token",
)
SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]+"),
    re.compile(r"\b(?:sk|ak)-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bAKLT[A-Za-z0-9]{8,}\b"),
)


@dataclass(frozen=True, slots=True)
class RoutePolicy:
    allowed_tools: frozenset[str]
    max_tool_calls: int
    require_citations: bool = False


def _default_routes() -> dict[str, RoutePolicy]:
    return {
        "analysis": RoutePolicy(frozenset({"tool.transaction_analysis"}), 1),
        "delegation": RoutePolicy(frozenset({"a2a.delegate.data_agent"}), 1),
        "customer_operation": RoutePolicy(
            frozenset({"memory.read", "memory.write", "tool.work_order.create"}), 2
        ),
        "sandbox": RoutePolicy(frozenset({"sandbox.exec", "mcp.tool_call"}), 2),
        "compliance": RoutePolicy(frozenset({"skill.execute"}), 1),
        "grounded_answer": RoutePolicy(frozenset({"knowledge.search"}), 1),
    }


@dataclass(frozen=True, slots=True)
class HarnessPolicy:
    """Immutable policy compiled before the business agent is called."""

    allowed_tools: frozenset[str] = frozenset(
        {
            "knowledge.search",
            "memory.read",
            "memory.write",
            "tool.work_order.create",
            "tool.transaction_analysis",
            "a2a.delegate.data_agent",
            "sandbox.exec",
            "mcp.tool_call",
            "skill.execute",
        }
    )
    max_tool_calls: int = 4
    max_message_chars: int = 4000
    max_answer_chars: int = 8000
    require_identity: bool = True
    route_policies: dict[str, RoutePolicy] = field(default_factory=_default_routes)


@dataclass(slots=True)
class RequestContext:
    tenant_id: str
    user_id: str
    session_id: str
    identity_source: str


def _redact(value: Any, *, key: str = "") -> tuple[Any, int]:
    """Recursively redact telemetry values and report the number of changes."""
    if any(part in key.lower() for part in SENSITIVE_KEY_PARTS):
        return "[REDACTED]", 1
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        changes = 0
        for child_key, child_value in value.items():
            output[child_key], count = _redact(child_value, key=str(child_key))
            changes += count
        return output, changes
    if isinstance(value, list):
        output = []
        changes = 0
        for item in value:
            redacted, count = _redact(item)
            output.append(redacted)
            changes += count
        return output, changes
    if isinstance(value, str):
        redacted = value
        for pattern in SENSITIVE_VALUE_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted, int(redacted != value)
    return value, 0


class AgentHarness:
    """Enforce a stable request/execute/attest response envelope."""

    def __init__(
        self,
        mode: str = "demo",
        policy: HarnessPolicy | None = None,
        agent: Any | None = None,
    ) -> None:
        self.mode = mode
        self.policy = policy or HarnessPolicy()
        self.agent = agent or HybridCustomerService(mode)

    @staticmethod
    def _route(message: str) -> str:
        lowered = message.lower()
        if "sandbox" in lowered or "隔离计算" in message:
            return "sandbox"
        if "合规" in message or "skill" in lowered:
            return "compliance"
        if "237" in message or "交易" in message or "总收益" in message:
            return "analysis"
        if "投诉" in message or "趋势" in message or "预测" in message:
            return "delegation"
        if (
            "工单" in message
            or "偏好" in message
            or "快速到账" in message
            or ("提交" in message and "退" in message)
        ):
            return "customer_operation"
        return "grounded_answer"

    def _request_violations(self, message: str, context: RequestContext) -> list[str]:
        violations = []
        if not isinstance(message, str) or not message.strip():
            violations.append("message_required")
        elif len(message) > self.policy.max_message_chars:
            violations.append("message_too_large")
        if self.policy.require_identity:
            if not context.tenant_id.strip():
                violations.append("tenant_required")
            if not context.user_id.strip():
                violations.append("user_required")
            if not context.session_id.strip():
                violations.append("session_required")
            if not context.identity_source.strip():
                violations.append("identity_source_required")
        return violations

    @staticmethod
    def _controlled_calls(events: list[CapabilityEvent]) -> list[str]:
        return [
            event.name for event in events if event.name.startswith(CONTROLLED_CAPABILITY_PREFIXES)
        ]

    def _redact_response(self, response: AgentResponse) -> int:
        changes = 0
        response.answer, count = _redact(response.answer)
        changes += count
        response.citations, count = _redact(response.citations)
        changes += count
        for event in response.events:
            event.detail, count = _redact(event.detail)
            changes += count
        return changes

    def invoke(
        self,
        message: str,
        *,
        tenant_id: str = "demo-bank",
        user_id: str = "user-001",
        session_id: str = "session-001",
        identity_source: str = "local-request",
    ) -> AgentResponse:
        context = RequestContext(tenant_id, user_id, session_id, identity_source)
        request_violations = self._request_violations(message, context)
        route = self._route(message) if not request_violations else "rejected"
        route_policy = self.policy.route_policies.get(route, RoutePolicy(frozenset(), 0))
        effective_tools = route_policy.allowed_tools & self.policy.allowed_tools
        effective_budget = min(route_policy.max_tool_calls, self.policy.max_tool_calls)

        before = [
            CapabilityEvent(
                "harness.request.accept",
                status="blocked" if request_violations else "succeeded",
                mode=self.mode,
                detail={
                    "schema": "agentkit.invoke.v1",
                    "message_length": len(message) if isinstance(message, str) else 0,
                    "max_message_chars": self.policy.max_message_chars,
                    "violations": request_violations,
                },
            ),
            CapabilityEvent(
                "harness.identity.bind",
                status="blocked" if request_violations else "succeeded",
                mode=self.mode,
                detail={
                    "source": context.identity_source or "missing",
                    "tenant_bound": bool(context.tenant_id),
                    "user_bound": bool(context.user_id),
                    "session_bound": bool(context.session_id),
                },
            ),
            CapabilityEvent(
                "harness.policy.precheck",
                status="blocked" if request_violations else "succeeded",
                mode=self.mode,
                detail={
                    "route": route,
                    "allowed_tools": sorted(effective_tools),
                    "max_tool_calls": effective_budget,
                    "decision": "deny" if request_violations else "allow",
                },
            ),
            CapabilityEvent(
                "harness.route.select",
                status="skipped" if request_violations else "succeeded",
                mode=self.mode,
                detail={"route": route, "agent": "validated_customer_service_core"},
            ),
        ]

        if request_violations:
            result = AgentResponse(
                "请求未通过 Agent Harness 的身份或输入校验，业务 Agent 未执行。",
                session_id or "rejected-session",
                f"trace-{uuid.uuid4().hex[:12]}",
                self.mode,
            )
        else:
            result = self.agent.chat(
                message,
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                session_id=context.session_id,
                identity_source=context.identity_source,
            )

        calls = self._controlled_calls(result.events)
        unregistered = [name for name in calls if name not in self.policy.allowed_tools]
        route_denied = [name for name in calls if name not in effective_tools]
        over_budget = max(0, len(calls) - effective_budget)
        tool_violations = [
            *(f"unregistered:{name}" for name in unregistered),
            *(f"route_denied:{name}" for name in route_denied if name not in unregistered),
        ]
        if over_budget:
            tool_violations.append(f"budget_exceeded:{over_budget}")

        policy_blocked = any(event.status == "blocked" for event in result.events)
        citation_valid = all(
            isinstance(item, dict) and bool(item.get("title")) and bool(item.get("chunk_id"))
            for item in result.citations
        )
        output_violations = []
        if not result.answer.strip():
            output_violations.append("answer_required")
        if len(result.answer) > self.policy.max_answer_chars:
            output_violations.append("answer_too_large")
        if not citation_valid:
            output_violations.append("citation_schema_invalid")
        if (route_policy.require_citations or "knowledge.search" in calls) and not result.citations:
            output_violations.append("citation_required")
        if tool_violations:
            output_violations.append("tool_attestation_failed")

        governance_failed = bool(request_violations or tool_violations or output_violations)
        if governance_failed and not request_violations:
            result.answer = "执行结果未通过 Agent Harness 治理校验，已阻止向调用方返回。"
            result.citations = []

        tools_event = CapabilityEvent(
            "harness.tools.authorize",
            status="blocked"
            if tool_violations
            else ("skipped" if request_violations else "succeeded"),
            mode=self.mode,
            detail={
                "authorized": [name for name in calls if name in effective_tools],
                "observed_call_count": len(calls),
                "budget": effective_budget,
                "within_budget": over_budget == 0,
                "violations": tool_violations,
            },
        )
        output_event = CapabilityEvent(
            "harness.output.validate",
            status="blocked" if output_violations else "succeeded",
            mode=self.mode,
            detail={
                "answer_present": bool(result.answer),
                "citations": len(result.citations),
                "citation_schema_valid": citation_valid,
                "policy_blocked": policy_blocked,
                "violations": output_violations,
            },
        )
        result.events = [*before, *result.events, tools_event, output_event]
        redacted_fields = self._redact_response(result)
        result.events.append(
            CapabilityEvent(
                "harness.telemetry.export",
                mode=self.mode,
                detail={
                    "trace_id": result.trace_id,
                    "redaction": "authorization-and-secrets",
                    "redacted_fields": redacted_fields,
                    "event_count": len(result.events) + 1,
                    "governance_decision": "deny" if governance_failed else "allow",
                },
            )
        )
        return result

    def chat(self, message: str, **kwargs: Any) -> AgentResponse:
        """Compatibility alias used by the shared HTTP/UI surface."""
        return self.invoke(message, **kwargs)
