from st_platform.dataset.core import (
    Dataset,
    DatasetSplit,
    case_signature,
    contamination_detect,
    contamination_violated,
)


def test_dataset_sha_stable():
    a = Dataset(
        dataset_id="d",
        version=1,
        source="s",
        split=DatasetSplit.EVAL,
        rows=[{"case_id": "1", "text": "hello"}, {"case_id": "2", "text": "world"}],
    )
    b = Dataset(
        dataset_id="d",
        version=1,
        source="s",
        split=DatasetSplit.EVAL,
        rows=[{"case_id": "1", "text": "hello"}, {"case_id": "2", "text": "world"}],
    )
    assert a.compute_sha() == b.compute_sha()


def test_signature_changes_on_text():
    assert case_signature({"case_id": "1", "text": "a"}) != case_signature(
        {"case_id": "1", "text": "b"}
    )


def test_contamination_detects_overlap():
    train_rows = [{"case_id": "A", "text": "secret"}]
    train_sigs = {case_signature(r) for r in train_rows}
    eval_ds = Dataset(
        dataset_id="e",
        version=1,
        source="s",
        split=DatasetSplit.EVAL,
        rows=[{"case_id": "A", "text": "secret"}, {"case_id": "C", "text": "new"}],
    )
    res = contamination_detect(eval_ds, train_sigs)
    assert res["contaminated"] is True
    assert res["train_overlap_count"] == 1
    assert res["overlap_ratio"] == 0.5


def test_contamination_clean_when_no_overlap():
    sigs = {case_signature({"case_id": "Z", "text": "x"})}
    eval_ds = Dataset(
        dataset_id="e",
        version=1,
        source="s",
        split=DatasetSplit.EVAL,
        rows=[{"case_id": "1", "text": "new"}],
    )
    res = contamination_detect(eval_ds, sigs)
    assert res["contaminated"] is False
    assert res["train_corpus_supplied"] is True


# --- T-M7-11: an unchecked contamination claim is not a clean claim -----------
# Without a training corpus there is nothing to intersect with, so the conclusion
# is unknown. Recording 0 here (CP-7's 「没采到」 written as 0) is what let
# `stctl run` certify `contaminated=False` for a check that never ran.


def _eval_ds() -> Dataset:
    return Dataset(
        dataset_id="e",
        version=1,
        source="s",
        split=DatasetSplit.EVAL,
        rows=[{"case_id": "1", "text": "new"}, {"case_id": "2", "text": "fresh"}],
    )


def test_contamination_unchecked_reports_unknown_not_clean():
    res = contamination_detect(_eval_ds(), None)
    assert res["train_corpus_supplied"] is False
    assert res["contaminated"] is None, "absent corpus must not be reported as 'not contaminated'"
    assert res["train_overlap_count"] is None, "an unmeasured count must be null, not 0"
    assert res["overlap_ratio"] is None
    assert res["overlap_signatures"] is None


def test_contamination_supplied_empty_corpus_is_a_measured_claim():
    """`[]` was *supplied*: the check ran and found nothing. Different from None."""
    res = contamination_detect(_eval_ds(), [])
    assert res["train_corpus_supplied"] is True
    assert res["contaminated"] is False
    assert res["train_overlap_count"] == 0
    assert res["overlap_ratio"] == 0.0


def test_contamination_violated_treats_unknown_as_violation():
    """One reader for the shape, and it fails closed (mirrors the unevaluated-redline
    and unregistered-rule-id precedents: never downgrade 'did not check' to clean)."""
    assert contamination_violated({"contaminated": True}) is True
    assert contamination_violated({"contaminated": False}) is False
    assert contamination_violated({"contaminated": None}) is True
    assert contamination_violated({"train_corpus_supplied": False}) is True
    assert contamination_violated({}) is True, "a missing conclusion is unknown, not clean"
    assert contamination_violated(None) is True


def test_contamination_violated_reads_a_real_checked_result():
    real = contamination_detect(_eval_ds(), {case_signature({"case_id": "1", "text": "new"})})
    assert contamination_violated(real) is True, "measured overlap must be a violation"
    clean = contamination_detect(_eval_ds(), {case_signature({"case_id": "Z", "text": "z"})})
    assert contamination_violated(clean) is False, "a real check with no overlap stays clean"
