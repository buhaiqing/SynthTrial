"""Testing for metric registry."""

import pytest

from st_platform.registry.metrics import (
    MetricDefinition,
    MetricKind,
    MetricRegistry,
    RegistryError,
)


def _metric(mid, name="accuracy"):
    return MetricDefinition(metric_id=mid, name=name, kind=MetricKind.SCORE)


def test_register_assigns_version():
    reg = MetricRegistry()
    m1 = reg.register(MetricDefinition(metric_id="m.acc", name="acc", kind=MetricKind.SCORE))
    assert m1.version == 1
    m2 = reg.register(
        MetricDefinition(metric_id="m.acc", version=2, name="acc2", kind=MetricKind.SCORE)
    )
    assert m2.version == 2
    assert [m.version for m in reg.all_versions("m.acc")] == [1, 2]


def test_register_rejects_non_incremental_version():
    reg = MetricRegistry()
    reg.register(MetricDefinition(metric_id="m.acc", name="acc", kind=MetricKind.SCORE))
    with pytest.raises(RegistryError):
        reg.register(
            MetricDefinition(metric_id="m.acc", version=99, name="x", kind=MetricKind.SCORE)
        )


def test_latest_and_none():
    reg = MetricRegistry()
    assert reg.latest("nope") is None
    reg.register(_metric("candidate"))
    assert reg.latest("candidate").version == 1


def test_list_ids_sorted():
    reg = MetricRegistry()
    reg.register(_metric("z"))
    reg.register(_metric("a"))
    assert reg.list_ids() == ["a", "z"]


def test_validate_unknown_raises():
    reg = MetricRegistry()
    with pytest.raises(RegistryError):
        reg.validate_metric_exists("ghost")
