from st_platform.dataset.core import (
    Dataset,
    DatasetSplit,
    case_signature,
    contamination_detect,
)


def test_dataset_sha_stable():
    a = Dataset(dataset_id="d", version=1, source="s", split=DatasetSplit.EVAL,
                rows=[{"case_id": "1", "text": "hello"}, {"case_id": "2", "text": "world"}])
    b = Dataset(dataset_id="d", version=1, source="s", split=DatasetSplit.EVAL,
                rows=[{"case_id": "1", "text": "hello"}, {"case_id": "2", "text": "world"}])
    assert a.compute_sha() == b.compute_sha()


def test_signature_changes_on_text():
    assert case_signature({"case_id": "1", "text": "a"}) != case_signature({"case_id": "1", "text": "b"})


def test_contamination_detects_overlap():
    train_rows = [{"case_id": "A", "text": "secret"}]
    train_sigs = {case_signature(r) for r in train_rows}
    eval_ds = Dataset(dataset_id="e", version=1, source="s", split=DatasetSplit.EVAL,
                      rows=[{"case_id": "A", "text": "secret"}, {"case_id": "C", "text": "new"}])
    res = contamination_detect(eval_ds, train_sigs)
    assert res["contaminated"] is True
    assert res["train_overlap_count"] == 1
    assert res["overlap_ratio"] == 0.5


def test_contamination_clean_when_no_overlap():
    sigs = {case_signature({"case_id": "Z", "text": "x"})}
    eval_ds = Dataset(dataset_id="e", version=1, source="s", split=DatasetSplit.EVAL,
                      rows=[{"case_id": "1", "text": "new"}])
    res = contamination_detect(eval_ds, sigs)
    assert res["contaminated"] is False
