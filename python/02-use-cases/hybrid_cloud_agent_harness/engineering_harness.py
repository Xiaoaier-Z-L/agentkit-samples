"""Ralph-inspired Harness Engineering loop for a customer-policy change.

This module is intentionally separate from the request security envelope in
``harness.py``.  It demonstrates the broader Harness Engineering discipline:
versioned intent, fresh context per iteration, role separation, mechanical
backpressure, disk state, bounded recovery and a verified completion promise.
"""

from __future__ import annotations

import json
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

COMPLETION_PROMISE = "HARNESS_COMPLETE"


@dataclass(frozen=True, slots=True)
class EngineeringHarnessPolicy:
    max_iterations: int = 8
    completion_promise: str = COMPLETION_PROMISE
    require_independent_critic: bool = True


@dataclass(slots=True)
class IterationEvidence:
    iteration: int
    role: str
    status: str
    observation: str
    checks: dict[str, bool] = field(default_factory=dict)


@dataclass(slots=True)
class EngineeringHarnessResult:
    run_id: str
    status: str
    completion_promise: str | None
    iterations: list[IterationEvidence]
    artifacts: list[str]
    final_policy: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CustomerPolicyHarness:
    """Deliver a small customer-service policy change through a bounded loop."""

    def __init__(
        self,
        state_root: str | Path | None = None,
        policy: EngineeringHarnessPolicy | None = None,
    ) -> None:
        self.state_root = Path(state_root or tempfile.gettempdir()) / "agentkit-harness-runs"
        self.policy = policy or EngineeringHarnessPolicy()

    @staticmethod
    def _window_days(objective: str) -> int:
        match = re.search(r"(\d+)\s*(?:天|day)", objective, re.IGNORECASE)
        return int(match.group(1)) if match else 10

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _read_json(path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _checks(candidate: dict[str, Any]) -> dict[str, bool]:
        return {
            "refund_window_is_bounded": 1 <= candidate.get("refund_window_days", 0) <= 30,
            "manual_confirmation_required": candidate.get("manual_confirmation") is True,
            "citation_required": candidate.get("citation_required") is True,
            "policy_source_recorded": candidate.get("source") == "refund_policy.md",
        }

    def run(self, objective: str, *, run_id: str | None = None) -> EngineeringHarnessResult:
        run_id = run_id or f"run-{uuid.uuid4().hex[:10]}"
        workspace = self.state_root / run_id
        workspace.mkdir(parents=True, exist_ok=True)
        iterations: list[IterationEvidence] = []

        spec = {
            "objective": objective,
            "acceptance": [
                "refund window matches requested days",
                "manual confirmation remains mandatory",
                "answers require a policy citation",
                "independent critic reruns all checks",
            ],
            "completion_promise": self.policy.completion_promise,
        }
        self._write_json(workspace / "spec.json", spec)
        self._write_json(
            workspace / "tasks.json",
            {"stories": [{"id": "policy-change", "passes": False}], "feedback": []},
        )
        (workspace / "scratchpad.md").write_text(
            "# Harness scratchpad\n\n- Planner recorded the objective and acceptance criteria.\n",
            encoding="utf-8",
        )
        iterations.append(
            IterationEvidence(1, "planner", "succeeded", "spec and task state persisted")
        )

        # Builder iteration 1 deliberately leaves out a required invariant.
        # Mechanical feedback, rather than a longer prompt, drives correction.
        fresh_spec = self._read_json(workspace / "spec.json")
        candidate = {
            "refund_window_days": self._window_days(fresh_spec["objective"]),
            "manual_confirmation": True,
            "citation_required": False,
            "source": "refund_policy.md",
        }
        self._write_json(workspace / "candidate_policy.json", candidate)
        first_checks = self._checks(candidate)
        state = self._read_json(workspace / "tasks.json")
        state["feedback"] = [name for name, passed in first_checks.items() if not passed]
        self._write_json(workspace / "tasks.json", state)
        iterations.append(
            IterationEvidence(
                2,
                "builder",
                "needs_revision",
                "mechanical gate rejected the first candidate",
                first_checks,
            )
        )

        # Fresh context: reload only versioned artifacts, not prior model chat.
        state = self._read_json(workspace / "tasks.json")
        candidate = self._read_json(workspace / "candidate_policy.json")
        if "citation_required" in state["feedback"]:
            candidate["citation_required"] = True
        self._write_json(workspace / "candidate_policy.json", candidate)
        repaired_checks = self._checks(candidate)
        iterations.append(
            IterationEvidence(
                3,
                "builder",
                "succeeded" if all(repaired_checks.values()) else "needs_revision",
                "fresh iteration repaired only the failed invariant",
                repaired_checks,
            )
        )

        # Critic reads from disk independently and owns no builder state.
        critic_candidate = self._read_json(workspace / "candidate_policy.json")
        critic_checks = self._checks(critic_candidate)
        critic_passed = all(critic_checks.values())
        iterations.append(
            IterationEvidence(
                4,
                "critic",
                "succeeded" if critic_passed else "needs_revision",
                "independent critic reran the complete acceptance suite",
                critic_checks,
            )
        )

        state = self._read_json(workspace / "tasks.json")
        state["stories"][0]["passes"] = critic_passed
        state["feedback"] = [] if critic_passed else ["critic_rejected_candidate"]
        self._write_json(workspace / "tasks.json", state)
        all_done = critic_passed and all(story["passes"] for story in state["stories"])
        within_budget = len(iterations) + 1 <= self.policy.max_iterations
        completed = all_done and within_budget
        iterations.append(
            IterationEvidence(
                5,
                "finalizer",
                "succeeded" if completed else "blocked",
                "completion promise emitted only after persisted state and critic evidence agree",
                {"all_stories_pass": all_done, "within_iteration_budget": within_budget},
            )
        )
        (workspace / "scratchpad.md").write_text(
            (workspace / "scratchpad.md").read_text(encoding="utf-8")
            + f"- Finalizer decision: {'complete' if completed else 'blocked'}.\n",
            encoding="utf-8",
        )

        return EngineeringHarnessResult(
            run_id=run_id,
            status="completed" if completed else "blocked",
            completion_promise=self.policy.completion_promise if completed else None,
            iterations=iterations,
            artifacts=["spec.json", "tasks.json", "scratchpad.md", "candidate_policy.json"],
            final_policy=critic_candidate,
        )
