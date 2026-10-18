from gridpulse.ingestion import brightsky, smard
from gridpulse.sample import write_sample_bronze
from gridpulse.storage import BronzeStore


def test_sample_data_covers_all_datasets_and_is_deterministic(tmp_path):
    a, b = BronzeStore(tmp_path / "a"), BronzeStore(tmp_path / "b")
    write_sample_bronze(a, "2026-01-01", 2)
    write_sample_bronze(b, "2026-01-01", 2)
    for name in smard.DATASETS:
        df = a.read("smard", name)
        assert len(df) == 48
        assert df["value"].tolist() == b.read("smard", name)["value"].tolist()
    assert len(a.read("dwd", f"weather_{next(iter(brightsky.LOCATIONS))}")) == 48
