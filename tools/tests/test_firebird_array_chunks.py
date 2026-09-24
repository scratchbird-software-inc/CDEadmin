"""Bounded rectangles, exact coordinate order and failure propagation."""
from itertools import product
from math import prod
from unittest.mock import Mock, patch

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from firebird.driver import fbapi
from pgadmin.cdeadmin.providers.firebird import varying_arrays as arrays
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def descriptor(bounds, width):
    result = fbapi.ISC_ARRAY_DESC(0)
    result.array_desc_dimensions = len(bounds)
    result.array_desc_length = width
    result.array_desc_relation_name = b'T'
    result.array_desc_field_name = b'A'
    for index, (lower, upper) in enumerate(bounds):
        result.array_desc_bounds[index].array_bound_lower = lower
        result.array_desc_bounds[index].array_bound_upper = upper
    return result


def ranges(bounds):
    return [range(b.array_bound_lower, b.array_bound_upper + 1)
            for b in bounds.array_desc_bounds[:bounds.array_desc_dimensions]]


@pytest.mark.parametrize('bounds', [
    [(-5, 11)], [(-3, 1), (2, 6)], [(0, 1), (-2, 0), (4, 10)],
    [(1, 1)] * 15 + [(-2, 2)],
])
@pytest.mark.parametrize('width,cap', [
    (1, 4), (4, 20), (32, 32), (8, 1024), (65535, 1024 * 1024)])
def test_rectangles_reconstruct_native_order_and_never_exceed_cap(
        bounds, width, cap):
    original = descriptor(bounds, width)
    before = bytes(original)
    dimensions = [upper - lower + 1 for lower, upper in bounds]
    visited = []

    def reader(part, shape):
        assert prod(shape) * width <= cap
        visited.extend(product(*ranges(part)))
        coordinates = iter(product(*ranges(part)))

        def nest(depth):
            return [next(coordinates) if depth == len(shape)-1 else
                    nest(depth+1) for _ in range(shape[depth])]

        return nest(0)

    with patch.object(arrays, 'SLICE_BYTES', cap):
        result = arrays._chunked(original, dimensions, width, reader)

    def flatten(items, depth):
        for item in items:
            if depth == len(dimensions)-1:
                yield item
            else:
                yield from flatten(item, depth+1)

    expected = list(product(*ranges(original)))
    assert visited == expected
    assert list(flatten(result, 0)) == expected
    assert bytes(original) == before


def test_failure_after_first_chunk_does_not_return_partial_array():
    original = descriptor([(-1, 2)], 4)
    reader = Mock(side_effect=[['first'], ValueError('native read failure')])
    with patch.object(arrays, 'SLICE_BYTES', 4):
        with pytest.raises(ValueError, match='native read failure'):
            arrays._chunked(original, [4], 4, reader)
    assert reader.call_count == 2


@pytest.mark.parametrize('dimensions,width', [
    ([], 4), ([0], 4), ([2], 4), ([4, 1], 4), ([4], 0), ([4], 65536),
])
def test_invalid_metadata_never_calls_reader(dimensions, width):
    reader = Mock()
    with pytest.raises(RelationalClientError):
        arrays._chunked(descriptor([(-1, 2)], 4), dimensions, width, reader)
    reader.assert_not_called()


def test_single_element_larger_than_cap_fails_without_allocation():
    reader = Mock()
    with patch.object(arrays, 'SLICE_BYTES', 4):
        with pytest.raises(RelationalClientError, match='exceeds buffer cap'):
            arrays._chunked(descriptor([(1, 1)], 8), [1], 8, reader)
    reader.assert_not_called()
