"""Unit contracts for Firebird 5.0.4 host configuration, plugin/UDR and runtime lifecycle."""
import os
from pathlib import Path
import struct

import pytest

from pgadmin.cdeadmin.providers.firebird import host_configuration as hcfg
from pgadmin.cdeadmin.providers.firebird import plugin_deployment as pdep
from pgadmin.cdeadmin.providers.firebird import runtime_lifecycle as rlife
from pgadmin.cdeadmin.workspace.firebird_host_actions import HostActions


def _fake_elf64(symbol_name=None, machine=62, e_type=3):
    """Construct a minimal synthetic ELF64 little-endian image for header/symbol unit tests."""
    dynstr = b'\x00' + (symbol_name.encode('ascii') + b'\x00' if symbol_name else b'')
    # Two symbols: STN_UNDEF + optional global defined symbol at st_shndx=1
    sym0 = struct.pack('<IBBHQQ', 0, 0, 0, 0, 0, 0)
    sym1 = struct.pack('<IBBHQQ', 1, (1 << 4) | 2, 0, 1, 0x1000, 16) if symbol_name else b''
    dynsym = sym0 + sym1

    ehdr_size = 64
    dynstr_off = ehdr_size
    dynsym_off = dynstr_off + len(dynstr)
    shoff = dynsym_off + len(dynsym)

    sh_null = b'\x00' * 64
    # Section 1: .dynstr (SHT_STRTAB == 3)
    sh_str = struct.pack('<IIQQQQIIQQ', 0, 3, 0, 0, dynstr_off, len(dynstr), 0, 0, 1, 0)
    # Section 2: .dynsym (SHT_DYNSYM == 11, sh_link=1, sh_entsize=24)
    sh_sym = struct.pack('<IIQQQQIIQQ', 0, 11, 0, 0, dynsym_off, len(dynsym), 1, 1, 8, 24)
    shdrs = sh_null + sh_str + sh_sym

    e_ident = b'\x7fELF' + bytes([2, 1, 1]) + b'\x00' * 9
    ehdr_rest = struct.pack(
        '<HHIQQQIHHHHHH',
        e_type, machine, 1, 0, 0, shoff, 0, ehdr_size, 0, 0, 64, 3, 0,
    )
    return e_ident + ehdr_rest + dynstr + dynsym + shdrs


def test_firebird_conf_validation_covers_types_scopes_and_rejects_macros():
    assert hcfg.validate_setting_value('DefaultDbCachePages', 2048)[1] == '2048'
    assert hcfg.validate_setting_value('TempCacheLimit', '64M')[1] == '64M'
    assert hcfg.validate_setting_value('WireCrypt', 'Required')[1] == 'Required'
    assert hcfg.validate_setting_value('ServerMode', 'SuperClassic')[2]['configuration_scope'] == 'global'

    for bad_key, bad_val in [
        ('UnknownSetting', '1'),
        ('DefaultDbCachePages', '-5'),
        ('DefaultDbCachePages', 'abc'),
        ('RemoteServicePort', 70000),
        ('WireCrypt', 'InvalidPolicy'),
        ('ServerMode', 'UnknownMode'),
        ('AuditTraceConfigFile', '$(root)/audit.conf'),
        ('TempDirectories', '/tmp # injected'),
    ]:
        with pytest.raises(ValueError):
            hcfg.validate_setting_value(bad_key, bad_val)

    with pytest.raises(ValueError, match='include'):
        hcfg.parse_firebird_conf('include /etc/passwd\n')


def test_databases_conf_rejects_global_keys_and_preserves_siblings():
    parsed = hcfg.parse_databases_conf(
        'SIBLING = /srv/fb/sibling.fdb\n'
        'PRIMARY = /srv/fb/primary.fdb\n{\n  DefaultDbCachePages = 512\n}\n'
    )
    assert set(parsed) == {'SIBLING', 'PRIMARY'}
    assert parsed['PRIMARY']['overrides'] == {'DefaultDbCachePages': '512'}

    with pytest.raises(ValueError, match='global scope'):
        hcfg.render_databases_conf({
            'BAD': {'path': '/srv/fb/bad.fdb', 'overrides': {'ServerMode': 'Super'}},
        })


def test_replication_and_plugins_conf_forbid_inline_secrets_and_bad_macros(tmp_path):
    jdir = tmp_path / 'journal'
    adir = tmp_path / 'archive'
    scope = {
        'firebird_runtime_root': str(tmp_path),
        'journal_directories': [str(tmp_path)],
    }
    rendered = hcfg.render_replication_conf({
        'databases': {
            str(tmp_path / 'primary.fdb'): {
                'journal_directory': str(jdir),
                'journal_archive_directory': str(adir),
                'journal_archive_command': 'test ! -f $(archivepathname) && cp $(pathname) $(archivepathname)',
                'sync_replicas': [
                    {
                        'dsn': '127.0.0.1:/srv/replica.fdb',
                        'username': 'SYSDBA',
                        'password_file': str(tmp_path / 'repl.pw'),
                    }
                ],
            }
        }
    }, scope)
    assert 'journal_archive_command = "test ! -f $(archivepathname)' in rendered
    assert 'password_file =' in rendered

    # Inline user:pass@dsn is forbidden
    with pytest.raises(ValueError, match='inline'):
        hcfg.render_replication_conf({
            'default_section': {
                'sync_replicas': [{'dsn': 'sysdba:secret@127.0.0.1:/srv/replica.fdb'}],
            }
        }, scope)

    # Arbitrary macro or shell pipe in journal_archive_command is forbidden
    for bad_cmd in ('cp $(pathname) $(root)/x', 'cp $(pathname) $(archivepathname); rm -rf /'):
        with pytest.raises(ValueError):
            hcfg.render_replication_conf({
                'default_section': {'journal_archive_command': bad_cmd}
            }, scope)

    pconf = hcfg.render_plugins_conf({
        'plugins': [{'name': 'UDR', 'module': '$(dir_plugins)/udr_engine', 'config': 'UDR_config'}],
        'configs': [{'name': 'UDR_config', 'entries': {'path': '$(dir_plugins)/udr'}}],
    })
    assert 'Plugin = UDR {' in pconf
    with pytest.raises(ValueError):
        hcfg.render_plugins_conf({
            'plugins': [{'name': 'Bad', 'module': '/etc/evil'}],
        })


def test_elf_inspection_enforces_architecture_and_firebird_symbols(tmp_path):
    udr_so = tmp_path / 'libgood_udr.so'
    udr_so.write_bytes(_fake_elf64('firebird_udr_plugin'))
    info = pdep.inspect_elf_shared_object(udr_so)
    assert info['valid_elf_dso'] is True
    assert info['exports_firebird_udr_plugin'] is True
    assert info['exports_firebird_plugin'] is False

    wrong_arch = tmp_path / 'libarm.so'
    wrong_arch.write_bytes(_fake_elf64('firebird_udr_plugin', machine=40))
    assert pdep.inspect_elf_shared_object(wrong_arch)['valid_elf_dso'] is False

    not_elf = tmp_path / 'libtext.so'
    not_elf.write_text('not an elf binary', encoding='utf-8')
    assert pdep.inspect_elf_shared_object(not_elf)['valid_elf_dso'] is False


def test_host_actions_one_use_and_secret_rejection(tmp_path):
    journal = HostActions(tmp_path / 'host.json', 'fb_host_test', {'deploy'})
    with pytest.raises(ValueError, match='Secret'):
        journal.review('u1', 'b1', 'deploy', {'password': 'secret'})

    rev = journal.review('u1', 'b1', 'deploy', {'module': 'demo'})
    req = {'review_id': rev['review_id'], 'review_digest': rev['review_digest'], 'confirmed': True}
    applied = journal.apply('u1', 'b1', req, lambda rec: {'state': 'ok', 'module': rec['payload']['module']})
    assert applied['outcome']['state'] == 'ok'

    with pytest.raises(ValueError, match='already consumed'):
        journal.apply('u1', 'b1', req, lambda _rec: {'state': 'replayed'})


def test_runtime_descriptor_declares_non_equivalence_of_network_maintenance():
    desc = rlife.descriptor()
    assert desc['network_maintenance_upgrades_runtime'] is False
    assert desc['platform_ownership']['windows'] == 'external-platform-team'
