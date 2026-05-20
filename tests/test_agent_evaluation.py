from app.services.agent_evaluation import run_agent_evaluation


def test_run_agent_evaluation_returns_pass_rate_and_cases():
    result = run_agent_evaluation()

    assert result["total"] >= 4
    assert result["passed"] == result["total"]
    assert result["failed"] == 0
    assert result["pass_rate"] == 1
    assert all("name" in item for item in result["cases"])
    assert any(item["name"] == "多轮上下文补全物流" for item in result["cases"])
