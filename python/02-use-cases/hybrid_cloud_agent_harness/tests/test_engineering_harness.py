from engineering_harness import CustomerPolicyHarness, EngineeringHarnessPolicy


def test_ralph_style_loop_repairs_from_mechanical_feedback(tmp_path) -> None:
    result = CustomerPolicyHarness(tmp_path).run(
        "将理财产品退款窗口调整为 10 天，并保留人工确认和引用",
        run_id="policy-change",
    )

    assert result.status == "completed"
    assert result.completion_promise == "HARNESS_COMPLETE"
    assert [item.role for item in result.iterations] == [
        "planner",
        "builder",
        "builder",
        "critic",
        "finalizer",
    ]
    assert result.iterations[1].status == "needs_revision"
    assert result.iterations[1].checks["citation_required"] is False
    assert all(result.iterations[2].checks.values())
    assert result.final_policy["refund_window_days"] == 10
    assert result.final_policy["manual_confirmation"] is True
    assert result.final_policy["citation_required"] is True


def test_completion_is_blocked_by_iteration_budget(tmp_path) -> None:
    harness = CustomerPolicyHarness(tmp_path, policy=EngineeringHarnessPolicy(max_iterations=4))
    result = harness.run("将退款窗口调整为 10 天", run_id="budget-block")

    assert result.status == "blocked"
    assert result.completion_promise is None
    assert result.iterations[-1].checks["within_iteration_budget"] is False
