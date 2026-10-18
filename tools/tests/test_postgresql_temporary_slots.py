"""Temporary native slot admission preserves exact names and owned scope."""
import pytest

from pgadmin.cdeadmin.providers.postgresql.temporary_slots import options,TemporarySlotError


@pytest.mark.parametrize('operation,value',[
    ('physical_create',{'slot':'UPPER'}),('physical_create',{'slot':'native-unsafe'}),
    ('physical_create',{'slot':'x'*64}),('physical_create',{'slot':'slot','reserve_wal':1}),
    ('physical_create',{'slot':'slot','timeout_seconds':True}),('physical_create',{'slot':'slot','timeout_seconds':0}),
    ('physical_create',{'slot':'slot','timeout_seconds':2147484}),
    ('logical_create',{'slot':'slot','plugin':''}),('logical_create',{'slot':'slot','plugin':'x'*64}),
    ('logical_create',{'slot':'slot','plugin':'bad\x00plugin'}),('logical_create',{'slot':'slot','plugin':'\ud800'}),
    ('logical_create',{'slot':'slot','two_phase':'yes'}),('logical_create',{'slot':'slot','failover':True}),
    ('physical_copy',{'slot':'slot','source_slot':'slot'}),('logical_copy',{'slot':'slot','source_slot':None}),
    ('advance',{'slot':'slot','upto_lsn':'0/0'}),('advance',{'slot':'slot','upto_lsn':'FFFFFFFFF/1'}),
    ('drop',{'slot':'slot','query':'arbitrary SQL'}),('unknown',{'slot':'slot'})])
def test_native_admission_refuses_ambiguous_names_flags_or_truncating_values(operation,value):
    with pytest.raises(TemporarySlotError):options(operation,value)


def test_native_plugin_width_is_deferred_to_database_encoding_and_exact_lsn_is_preserved():
    selected=options('logical_create',{'slot':'exact_slot','plugin':'雪'*21,'timeout_seconds':None,'two_phase':True})
    assert selected=={'slot':'exact_slot','plugin':'雪'*21,'timeout_seconds':None,'two_phase':True}
    assert options('advance',{'slot':'exact_slot','upto_lsn':'f/abcd'})['upto_lsn']=='F/ABCD'
    assert options('logical_copy',{'slot':'copy','source_slot':'source'})['plugin']==''
    assert options('logical_create',{'slot':'slot','plugin':'é'*63})['plugin']=='é'*63
