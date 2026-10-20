from gridpulse import state
from gridpulse.ml.artifacts import META_FILE, MODEL_FILE


def test_local_state_store_roundtrip(tmp_path):
    store = state.StateStore(root=tmp_path / "state")
    assert store.get("model/model.txt") is None  # nothing published yet
    store.put("model/model.txt", b"abc")
    assert store.get("model/model.txt") == b"abc"
    store.put("model/model.txt", b"xyz")  # overwrite is idempotent
    assert store.get("model/model.txt") == b"xyz"


def test_model_push_then_pull_restores_both_files(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / MODEL_FILE).write_bytes(b"booster")
    (src / META_FILE).write_text('{"name": "m"}')
    store = state.StateStore(root=tmp_path / "state")
    assert state.pull_model(store, dst) is False  # no model yet: the cloud job must say so
    state.push_model(store, src)
    assert state.pull_model(store, dst) is True
    assert (dst / MODEL_FILE).read_bytes() == b"booster"
    assert (dst / META_FILE).read_text() == '{"name": "m"}'
