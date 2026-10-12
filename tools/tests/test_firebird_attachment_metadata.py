"""Non-UTF8 metadata must preserve native status and ownership semantics."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird.attachment_metadata import (
    Attachment, Metadata,
)


@pytest.mark.parametrize('codec,text', [
    ('latin1', 'café'), ('cp1251', 'таблица'), ('shift_jis', 'テーブル'),
])
@pytest.mark.parametrize('method,native_method', [
    ('get_field', 'getField'), ('get_relation', 'getRelation'),
    ('get_owner', 'getOwner'), ('get_alias', 'getAlias'),
])
def test_metadata_names_use_attachment_codec(
        codec, text, method, native_method):
    native = Mock()
    getattr(native.vtable, native_method).return_value = text.encode(codec)
    metadata = Metadata(native, codec)
    assert getattr(metadata, method)(2) == text
    getattr(native.vtable, native_method).assert_called_once_with(
        native, native.status, 2)
    native._check.assert_called_once_with()
    metadata.release()
    native.release.assert_called_once_with()


def test_native_error_precedes_invalid_text():
    native = Mock()
    native.vtable.getField.return_value = None
    native._check.side_effect = RuntimeError('native error')
    with pytest.raises(RuntimeError, match='native error'):
        Metadata(native, 'utf8').get_field(0)


def test_invalid_text_is_not_replaced():
    native = Mock()
    native.vtable.getField.return_value = b'\xff'
    with pytest.raises(UnicodeDecodeError):
        Metadata(native, 'utf8').get_field(0)


def test_derived_metadata_and_plan_keep_attachment_codec():
    native = Mock()
    statement = native.prepare.return_value
    metadata = statement.get_output_metadata.return_value
    built = metadata.get_builder.return_value.get_metadata.return_value
    built.vtable.getAlias.return_value = b'caf\xe9'
    statement.vtable.getPlan.return_value = b'PLAN caf\xe9'
    wrapper = Attachment(native, 'latin1')
    prepared = wrapper.prepare('transaction', 'sql', 3)
    assert prepared.get_plan(False) == 'PLAN café'
    assert prepared.get_output_metadata().get_builder().get_metadata().\
        get_alias(0) == 'café'
    prepared.free()
    statement.free.assert_called_once_with()
    native.prepare.assert_called_once_with('transaction', 'sql', 3)


def test_pointer_identity_and_context_cleanup_are_forwarded():
    native = Mock()
    native._as_parameter_ = object()
    native.__enter__ = Mock()
    native.__exit__ = Mock(return_value=False)
    wrapper = Attachment(native, 'latin1')
    with wrapper as entered:
        assert entered is wrapper
        assert entered._as_parameter_ is native._as_parameter_
    native.__enter__.assert_called_once_with()
    native.__exit__.assert_called_once_with(None, None, None)


def test_sdl_identifiers_are_utf8_even_on_legacy_attachment():
    from pgadmin.cdeadmin.providers.firebird.array_layout import lookup
    from unittest.mock import MagicMock
    catalog = MagicMock()
    catalog.__enter__.return_value = catalog
    catalog.fetchall.return_value = [(8, 0, 0, 4, 0, 1, 3)]
    cursor = SimpleNamespace(
        _encoding='latin1',
        _transaction=SimpleNamespace(cursor=lambda: catalog))
    descriptor, _ = lookup(cursor, 'café', 'clé')
    assert descriptor.array_desc_relation_name == 'café'.encode('utf8')
    assert descriptor.array_desc_field_name == 'clé'.encode('utf8')


@pytest.mark.parametrize('name', ['été', '日本語', 'ключ', 'a b',
                                  'a#2', 'a/b', ' leading '])
def test_grid_record_keys_survive_repeated_normalization(name):
    from pgadmin.cdeadmin.grid_contract import normalize_columns
    records = [{name: 'native value'}]
    columns = normalize_columns([{'name': name, 'key': name}], records)
    repeated = normalize_columns(columns, records)
    assert repeated[0]['key'] == name
    assert records[0][repeated[0]['key']] == 'native value'


def test_unicode_grid_columns_do_not_collapse_to_ascii_collisions():
    from pgadmin.cdeadmin.grid_contract import normalize_columns
    columns = normalize_columns([{'name': name} for name in
                                 ('été', 't', 'ete', 'été#2')])
    assert [item['key'] for item in columns] == ['été', 't', 'ete', 'été#2']
    assert normalize_columns(columns) == columns


@pytest.mark.parametrize('output', [False, True])
def test_fss_utf8_payload_preserves_blob_width(output):
    from unittest.mock import MagicMock, call
    from firebird.driver.types import SQLDataType
    from pgadmin.cdeadmin.providers.firebird.attachment_metadata import (
        Statement,
    )
    from pgadmin.cdeadmin.providers.firebird.fss_codec import NAME
    native = MagicMock()
    method = 'get_output_metadata' if output else 'get_input_metadata'
    original = getattr(native, method).return_value
    original.__enter__.return_value = original
    original.get_count.return_value = 4
    original.get_type.side_effect = [SQLDataType.TEXT, SQLDataType.VARYING,
                                     SQLDataType.BLOB, SQLDataType.TEXT]
    original.get_charset.side_effect = lambda index: [3, 3, 3, 1][index]
    original.get_length.side_effect = [9, 6]
    builder = original.get_builder.return_value
    builder.__enter__.return_value = builder
    result = getattr(Statement(native, NAME), method)()
    assert result.native is builder.get_metadata.return_value
    assert result.encoding == NAME  # Names are still attachment encoded.
    assert builder.set_charset.call_args_list == (
        [call(0, 4), call(1, 4)] + ([] if output else [call(2, 4)]))
    assert builder.set_length.call_args_list == [call(0, 12), call(1, 8)]
    original.__exit__.assert_called_once()
    builder.__exit__.assert_called_once()
