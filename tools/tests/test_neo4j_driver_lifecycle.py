"""Lossless native Bolt values and retained stream lifecycle checks."""
import math

import pytest
import test_cdeadmin_neo4j_provider  # noqa: F401
from neo4j.time import Date, DateTime, Time, Duration
from neo4j.spatial import WGS84Point, CartesianPoint
from neo4j.vector import Vector
from pgadmin.cdeadmin.providers.neo4j.driver import exact, parameters_native


@pytest.mark.parametrize('value', [
    2**63 - 1, -(2**63), bytearray(b'\x00\xff'),
    Date(2026, 10, 10), Time(12, 30, 10, 123456789),
    DateTime(2026, 10, 10, 12, 30, 10, 123456789),
    Duration(months=1, days=2, seconds=3, nanoseconds=4),
    WGS84Point((1.25, 2.5, 3.75)), CartesianPoint((1, 2)),
    Vector.from_native([1.5, 2.25], 'f32'),
])
def test_exact_bolt_parameter_roundtrip(value):
    encoded = exact(value)
    assert exact(parameters_native(encoded)) == encoded


def test_nonfinite_and_rejected_bolt_values():
    assert math.isnan(parameters_native(exact(float('nan'))))
    with pytest.raises(Exception, match='integer'):
        parameters_native({'$integer': str(2**63)})
    with pytest.raises(Exception, match='dimensions'):
        parameters_native({'$neo4j_point': {'srid': 4979,
                                            'coordinates': [1, 2]}})
    with pytest.raises(Exception, match='lossless'):
        exact(object())
