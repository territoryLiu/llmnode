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
    )
    row = get_response_state(conn, "resp_1")
    assert row is not None
    assert row["request_id"] == "req_1"
    assert row["model_name"] == "qwen36-27b-fp8"
    assert row["input_items"] == [{"role": "user", "content": "hello"}]
    assert row["messages"][-1]["content"] == "world"
