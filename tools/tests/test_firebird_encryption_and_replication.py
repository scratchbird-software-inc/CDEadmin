"""Unit tests for Firebird 5.0.4 database encryption (FB-AUD-07) and journal replication (FB-AUD-04)."""
from pathlib import Path
import pytest

from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.providers.firebird import (
    database_encryption,
    embedded_provider as embedded,
    provider as network,
    replication_workflow,
)


def test_database_encryption_compile_and_validation():
    assert database_encryption.descriptor()['application_implements_cryptography'] is False
    assert database_encryption.descriptor()['distinct_from_wire_crypt_and_gbak_crypt'] is True

    sql_with_key = database_encryption.compile_operation(
        'encrypt_database',
        {
            'confirmation': '/data/owned.fdb',
            'crypt_plugin': 'fbSampleDbCrypt',
            'key_name': 'OWNED',
            'confirm_key_recovery_responsibility': True,
        },
        '/data/owned.fdb',
    )
    assert sql_with_key == ['ALTER DATABASE ENCRYPT WITH "fbSampleDbCrypt" KEY "OWNED"']

    sql_default_key = database_encryption.compile_operation(
        'encrypt_database',
        {
            'confirmation': '/data/owned.fdb',
            'crypt_plugin': 'fbSampleDbCrypt',
            'key_name': '',
            'confirm_key_recovery_responsibility': True,
        },
        '/data/owned.fdb',
    )
    assert sql_default_key == ['ALTER DATABASE ENCRYPT WITH "fbSampleDbCrypt"']

    sql_dec = database_encryption.compile_operation(
        'decrypt_database',
        {
            'confirmation': '/data/owned.fdb',
            'confirm_plaintext_storage': True,
        },
        '/data/owned.fdb',
    )
    assert sql_dec == ['ALTER DATABASE DECRYPT']

    with pytest.raises(RelationalClientError, match='Confirm the exact database'):
        database_encryption.compile_operation(
            'encrypt_database',
            {
                'confirmation': '/data/wrong.fdb',
                'crypt_plugin': 'fbSampleDbCrypt',
                'confirm_key_recovery_responsibility': True,
            },
            '/data/owned.fdb',
        )

    with pytest.raises(RelationalClientError, match='key recovery responsibility'):
        database_encryption.compile_operation(
            'encrypt_database',
            {
                'confirmation': '/data/owned.fdb',
                'crypt_plugin': 'fbSampleDbCrypt',
                'confirm_key_recovery_responsibility': False,
            },
            '/data/owned.fdb',
        )

    with pytest.raises(RelationalClientError, match='plaintext disk storage'):
        database_encryption.compile_operation(
            'decrypt_database',
            {
                'confirmation': '/data/owned.fdb',
                'confirm_plaintext_storage': False,
            },
            '/data/owned.fdb',
        )


def test_visual_admin_exposes_encrypt_and_decrypt_in_both_modes():
    for admin in (network.ADMINISTRATION, embedded.ADMINISTRATION):
        assert 'visual_admin.database.encrypt_database' in admin.dialect_task_ids()
        assert 'visual_admin.database.decrypt_database' in admin.dialect_task_ids()
        cat = admin.catalog({'objects': [{'resource_kind': 'database', 'operations': []}]})
        db_ops = {op['operation_id'] for op in cat['objects'][0]['operations']}
        assert {'encrypt_database', 'decrypt_database'} <= db_ops


def test_replication_journal_scanning_sequence_gap_and_promotion_guards(tmp_path):
    desc = replication_workflow.descriptor()
    assert desc['automatic_failover_supported'] is False
    assert desc['postgresql_wal_lsn_semantics'] is False

    j_arch = tmp_path / 'archive'
    j_src = tmp_path / 'replica_src'
    guid_sub = j_arch / '{11111111-2222-3333-4444-555555555555}'
    guid_sub.mkdir(parents=True)
    j_src.mkdir(parents=True)

    (guid_sub / 'pri.fdb.journal-000000001').write_bytes(b'seg1')
    (guid_sub / 'pri.fdb.journal-000000003').write_bytes(b'seg3')

    scope = {
        'firebird_runtime_root': str(tmp_path),
        'firebird_lock_directory': str(tmp_path / 'lock'),
        'journal_directories': [str(j_arch), str(j_src)],
        'staging_directory': str(tmp_path),
        'boot_id': 'unit-boot',
    }

    with pytest.raises(ValueError, match='sequence gaps or duplicates'):
        replication_workflow.prepare_replication_review(scope, {
            'operation': 'distribute_segments',
            'source_archive_directory': str(j_arch),
            'target_source_directory': str(j_src),
        })

    (guid_sub / 'pri.fdb.journal-000000002').write_bytes(b'seg2')
    reviewed = replication_workflow.prepare_replication_review(scope, {
        'operation': 'distribute_segments',
        'source_archive_directory': str(j_arch),
        'target_source_directory': str(j_src),
    })
    assert [s['sequence'] for s in reviewed['segments']] == [1, 2, 3]

    rep_db = tmp_path / 'replica.fdb'
    rep_db.write_bytes(b'placeholder')
    (j_src / 'pri.fdb.journal-000000001').write_bytes(b'unapplied')

    with pytest.raises(ValueError, match='unapplied journal segment'):
        replication_workflow.prepare_replication_review(scope, {
            'operation': 'promote_replica',
            'replica_database_path': str(rep_db),
            'journal_source_directory': str(j_src),
            'promotion_confirmed': True,
            'confirmation': 'replica.fdb',
        })

    allowed_discard = replication_workflow.prepare_replication_review(scope, {
        'operation': 'promote_replica',
        'replica_database_path': str(rep_db),
        'journal_source_directory': str(j_src),
        'promotion_confirmed': True,
        'discard_unapplied_segments_confirmed': True,
        'confirmation': 'replica.fdb',
    })
    assert allowed_discard['unapplied_segments_at_review'] == 1
