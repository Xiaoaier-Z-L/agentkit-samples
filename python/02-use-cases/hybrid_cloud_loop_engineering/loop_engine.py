"""Evidence-driven bounded loop around the validated hybrid-cloud business core.

The customer-service capabilities stay in :mod:`demo_core`.  This module owns
the production loop contract: objective-specific plans, hard iteration/tool
budgets, side-effect checkpoints, evidence-based criticism and explicit stop
reasons.  The deterministic planner also makes the contract testable without a
model or cloud credentials.
"""

from __future__ import annotations

from dataclasses import dataclass

from demo_core import HybridCustomerService
from utils.models import AgentResponse, CapabilityEvent


@dataclass(frozen=True, slots=True)
class LoopPolicy:
    """Hard limits enforced by the controller rather than suggested to a model."""

    max_iterations: int = 3
    max_tool_calls: int = 4
    require_evidence: bool = True

    def __post_init__(self) -> None:
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        if self.max_tool_calls < 0:
            raise ValueError("max_tool_calls cannot be negative")


@dataclass(frozen=True, slots=True)
class LoopStep:
    """One bounded action and the evidence that proves it completed."""

    step_id: str
    instruction: str
    required_events: tuple[str, ...]
    expected_tool_calls: int
    require_citation: bool = False
    side_effect: bool = False


_TOOL_EVENTS = {
    "knowledge.search",
    "memory.write",
    "memory.read",
    "tool.work_order.create",
    "tool.transaction_analysis",
    "a2a.delegate.data_agent",
    "sandbox.exec",
    "mcp.tool_call",
    "skill.execute",
}


class LoopEngineeringService:
    """Resolve a business objective through a bounded, inspectable loop."""

    def __init__(self, mode: str = "demo", policy: LoopPolicy | None = None) -> None:
        self.mode = mode
        self.policy = policy or LoopPolicy()
        self.business = HybridCustomerService(mode)

    @staticmethod
    def _objective(message: str) -> str:
        lowered = message.lower()
        if "ignore all previous" in lowered or "system prompt" in lowered:
            return "block_unsafe_request"
        if "sandbox" in lowered or "隔离计算" in message:
            return "run_isolated_calculation"
        if "合规" in message or "skill" in lowered:
            return "run_compliance_skill"
        if "你是谁" in message or "可以帮助" in message:
            return "explain_capabilities"
        has_refund = "退" in message or "退款" in message
        has_policy = "规则" in message or "依据" in message or "能退" in message
        has_analysis = "237" in message or "交易" in message or "总收益" in message
        if "闭环" in message or (has_refund and has_policy and has_analysis):
            return "resolve_refund_case"
        if has_analysis:
            return "analyze_transactions"
        if "投诉" in message or "趋势" in message or "预测" in message:
            return "delegate_complaint_analysis"
        if "提交" in message and ("退" in message or "工单" in message):
            return "create_refund_work_order"
        if "偏好" in message or "快速到账" in message:
            return "persist_customer_preference"
        return "answer_with_grounded_evidence"

    @classmethod
    def _plan(cls, message: str, objective: str) -> list[LoopStep]:
        if objective == "block_unsafe_request":
            return [
                LoopStep(
                    "security_preflight",
                    message,
                    ("security.prompt_injection",),
                    expected_tool_calls=0,
                )
            ]
        if objective == "resolve_refund_case":
            steps = [
                LoopStep(
                    "ground_policy",
                    "理财产品可以退吗？请给出规则依据。",
                    ("knowledge.search",),
                    expected_tool_calls=1,
                    require_citation=True,
                ),
                LoopStep(
                    "analyze_transactions",
                    "分析这 237 笔交易的总收益。",
                    ("tool.transaction_analysis",),
                    expected_tool_calls=1,
                ),
            ]
            if "提交" in message or "创建" in message or "工单" in message:
                steps.append(
                    LoopStep(
                        "create_work_order",
                        "帮我提交退款工单。",
                        ("memory.read", "tool.work_order.create"),
                        expected_tool_calls=2,
                        side_effect=True,
                    )
                )
            return steps
        if objective == "analyze_transactions":
            return [
                LoopStep(
                    "analyze_transactions",
                    message,
                    ("tool.transaction_analysis",),
                    expected_tool_calls=1,
                )
            ]
        if objective == "run_isolated_calculation":
            return [
                LoopStep(
                    "run_isolated_calculation",
                    message,
                    ("sandbox.exec", "mcp.tool_call"),
                    expected_tool_calls=2,
                )
            ]
        if objective == "run_compliance_skill":
            return [
                LoopStep(
                    "run_compliance_skill",
                    message,
                    ("skill.execute",),
                    expected_tool_calls=1,
                )
            ]
        if objective == "explain_capabilities":
            return [
                LoopStep(
                    "explain_capabilities",
                    message,
                    ("router.fallback",),
                    expected_tool_calls=0,
                )
            ]
        if objective == "delegate_complaint_analysis":
            return [
                LoopStep(
                    "delegate_complaint_analysis",
                    message,
                    ("a2a.delegate.data_agent",),
                    expected_tool_calls=1,
                )
            ]
        if objective == "create_refund_work_order":
            return [
                LoopStep(
                    "create_work_order",
                    message,
                    ("memory.read", "tool.work_order.create"),
                    expected_tool_calls=2,
                    side_effect=True,
                )
            ]
        if objective == "persist_customer_preference":
            return [
                LoopStep(
                    "persist_customer_preference",
                    message,
                    ("memory.write",),
                    expected_tool_calls=1,
                    side_effect=True,
                )
            ]
        return [
            LoopStep(
                "ground_answer",
                message,
                ("knowledge.search",),
                expected_tool_calls=1,
                require_citation=True,
            )
        ]

    @staticmethod
    def _tool_calls(events: list[CapabilityEvent]) -> int:
        return sum(event.name in _TOOL_EVENTS for event in events)

    @staticmethod
    def _blocked(events: list[CapabilityEvent]) -> bool:
        return any(event.status == "blocked" for event in events)

    @staticmethod
    def _step_accepted(
        step: LoopStep,
        events: list[CapabilityEvent],
        citations: list[dict[str, str]],
        *,
        require_evidence: bool,
    ) -> tuple[bool, list[str]]:
        if not require_evidence:
            return True, []
        event_names = {event.name for event in events}
        missing = [name for name in step.required_events if name not in event_names]
        if step.require_citation and not citations:
            missing.append("citation")
        return not missing, missing

    @staticmethod
    def _merge_citations(
        accumulated: list[dict[str, str]], incoming: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        seen = {(item.get("title"), item.get("chunk_id")) for item in accumulated}
        for item in incoming:
            key = (item.get("title"), item.get("chunk_id"))
            if key not in seen:
                accumulated.append(item)
                seen.add(key)
        return accumulated

    def chat(
        self,
        message: str,
        *,
        tenant_id: str = "demo-bank",
        user_id: str = "user-001",
        session_id: str = "session-001",
        identity_source: str = "local-request",
    ) -> AgentResponse:
        objective = self._objective(message)
        plan = self._plan(message, objective)
        events: list[CapabilityEvent] = [
            CapabilityEvent(
                "loop.start",
                mode=self.mode,
                detail={
                    "objective": objective,
                    "max_iterations": self.policy.max_iterations,
                    "max_tool_calls": self.policy.max_tool_calls,
                },
            ),
            CapabilityEvent(
                "loop.plan",
                mode=self.mode,
                detail={
                    "steps": [
                        {
                            "id": step.step_id,
                            "required_events": list(step.required_events),
                            "side_effect": step.side_effect,
                        }
                        for step in plan
                    ]
                },
            ),
        ]
        answers: list[str] = []
        citations: list[dict[str, str]] = []
        trace_id = ""
        tool_calls_used = 0
        iterations_used = 0
        stop_reason = "iteration_budget_reached"
        accepted_steps: list[str] = []

        for step in plan:
            if iterations_used >= self.policy.max_iterations:
                stop_reason = "iteration_budget_reached"
                break
            if tool_calls_used + step.expected_tool_calls > self.policy.max_tool_calls:
                stop_reason = "tool_budget_reached"
                break

            iterations_used += 1
            events.append(
                CapabilityEvent(
                    "loop.iteration.start",
                    mode=self.mode,
                    detail={
                        "iteration": iterations_used,
                        "step": step.step_id,
                        "remaining_iterations": self.policy.max_iterations - iterations_used,
                        "remaining_tool_calls": self.policy.max_tool_calls - tool_calls_used,
                    },
                )
            )
            if step.side_effect:
                events.append(
                    CapabilityEvent(
                        "loop.checkpoint",
                        mode=self.mode,
                        detail={
                            "iteration": iterations_used,
                            "step": step.step_id,
                            "idempotency_scope": f"{session_id}:{step.step_id}",
                        },
                    )
                )

            result = self.business.chat(
                step.instruction,
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                identity_source=identity_source,
            )
            trace_id = trace_id or result.trace_id
            answers.append(result.answer)
            citations = self._merge_citations(citations, result.citations)
            events.extend(result.events)

            observed_calls = self._tool_calls(result.events)
            tool_calls_used += observed_calls
            events.append(
                CapabilityEvent(
                    "loop.observe",
                    mode=self.mode,
                    detail={
                        "iteration": iterations_used,
                        "step": step.step_id,
                        "event_count": len(result.events),
                        "citation_count": len(result.citations),
                        "tool_calls_observed": observed_calls,
                        "tool_calls_used": tool_calls_used,
                    },
                )
            )

            blocked = self._blocked(result.events)
            accepted, missing = self._step_accepted(
                step,
                result.events,
                result.citations,
                require_evidence=self.policy.require_evidence,
            )
            events.append(
                CapabilityEvent(
                    "loop.critic",
                    status="blocked" if blocked else ("succeeded" if accepted else "needs_revision"),
                    mode=self.mode,
                    detail={
                        "iteration": iterations_used,
                        "step": step.step_id,
                        "accepted": accepted,
                        "missing_evidence": missing,
                        "policy_blocked": blocked,
                    },
                )
            )

            if blocked:
                stop_reason = "policy_blocked"
                break
            if tool_calls_used > self.policy.max_tool_calls:
                stop_reason = "tool_budget_exceeded"
                break
            if not accepted:
                # A deterministic action produced no required evidence. Repeating
                # the same action would add cost and can duplicate side effects.
                stop_reason = (
                    "side_effect_unverified" if step.side_effect else "no_progress"
                )
                break

            accepted_steps.append(step.step_id)
            if len(accepted_steps) == len(plan):
                stop_reason = "acceptance_criteria_met"

        events.append(
            CapabilityEvent(
                "loop.stop",
                status="succeeded" if stop_reason in {"acceptance_criteria_met", "policy_blocked"} else "blocked",
                mode=self.mode,
                detail={
                    "reason": stop_reason,
                    "iterations_used": iterations_used,
                    "tool_calls_used": tool_calls_used,
                    "accepted_steps": accepted_steps,
                    "planned_steps": len(plan),
                },
            )
        )
        answer = "\n".join(f"{index + 1}. {text}" for index, text in enumerate(answers))
        if len(answers) == 1:
            answer = answers[0]
        if not answer:
            answer = "Loop 在执行前触发预算边界，未调用业务能力。"
        return AgentResponse(
            answer,
            session_id,
            trace_id or "trace-not-started",
            self.mode,
            citations=citations,
            events=events,
        )
