from st_platform.exposure import AssignmentEvent, ExposureEvent, reconcile


def test_reconcile_missing_exposure():
    assignments = [AssignmentEvent("u1", "exp1", "A"), AssignmentEvent("u2", "exp1", "B")]
    exposures = [ExposureEvent("u1", "exp1")]
    r = reconcile(assignments, exposures)
    assert r["assignment_count"] == 2
    assert r["exposure_count"] == 1
    assert r["missing_exposure_count"] == 1
    assert r["missing_user_ids"] == ["u2"]


def test_reconcile_no_missing():
    assignments = [AssignmentEvent("u1", "exp1", "A")]
    exposures = [ExposureEvent("u1", "exp1")]
    r = reconcile(assignments, exposures)
    assert r["missing_exposure_count"] == 0
    assert r["missing_exposure_ratio"] == 0.0