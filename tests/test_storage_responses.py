from pathlib import Path

from llmnode.storage.db import get_response_state, init_db, upsert_response_state


def test_response_state_roundtrip(tmp_path: Path):
    conn = init_db(tmp_path / "gateway.db")
    upsert_response_state(
        conn,
        response_id="resp_1",
        request_id="req_1",
        model_name="qwen36-27b-fp8",
        input_items=[{"role": "user", "content": "hello"}],
        output_items=[{"type": "message", "role": "assistant"}],
        messages=[{"role": "user", "content": "hello"}, {"role": "assistant", "content": "world"}],
        parent_response_id="resp_0",
        route_name="qwen36-27b-fp8",
        client_protocol="responses",
        upstream_protocol="chat",
        upstream_response_id=None,
        request_payload={"model": "qwen36-27b-fp8", "input": "hello"},
        output_payload={"id": "resp_1", "status": "completed"},
    )
    row = get_response_state(conn, "resp_1")
    assert row is not None
    assert row["request_id"] == "req_1"
    assert row["model_name"] == "qwen36-27b-fp8"
    assert row["input_items"] == [{"role": "user", "content": "hello"}]
    assert row["messages"][-1]["content"] == "world"
    assert row["parent_response_id"] == "resp_0"
    assert row["route_name"] == "qwen36-27b-fp8"
    assert row["client_protocol"] == "responses"
    assert row["upstream_protocol"] == "chat"
    assert row["upstream_response_id"] is None
    assert row["request_payload"]["model"] == "qwen36-27b-fp8"
    assert row["output_payload"]["id"] == "resp_1"
