from st_platform.causal.triggers import check_triggers


def test_triggers():
    r = check_triggers(reports_count=50, bucket_deviations_ge_10pp=3, compliance_approval=True)
    assert r["all_met"] is True
    r2 = check_triggers(reports_count=1, bucket_deviations_ge_10pp=0, compliance_approval=False)
    assert r2["all_met"] is False