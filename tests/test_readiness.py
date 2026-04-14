def test_system_readiness_endpoint_returns_structured_report(test_env):
    client = test_env["client"]
    response = client.get("/system/readiness")
    assert response.status_code == 200
    data = response.json()

    assert "readiness_score" in data
    assert 0 <= data["readiness_score"] <= 100
    assert data["readiness_level"] in {"ready", "attention", "risk"}
    assert isinstance(data["checks"], list)
    assert isinstance(data["stats"], dict)
    assert "users" in data["stats"]
    assert "resources" in data["stats"]
    assert "llm" in data


def test_system_readiness_probe_llm_returns_llm_status(test_env):
    client = test_env["client"]
    response = client.get("/system/readiness?probe_llm=true")
    assert response.status_code == 200
    data = response.json()
    assert "ok" in data["llm"]
    assert "message" in data["llm"]
