"""Native lock lists preserve exact parent identities and avoid self duplicates."""
import pytest
from pgadmin.cdeadmin.workspace.mysql_foreign_key_locks import lock_source


def row(clauses):
    return {'name':'child`é','native':{'database':'db`é','definition':'CREATE TABLE `child``é` (`id` int'+clauses+')'}}


def test_parent_lock_union_is_deterministic_and_self_references_are_not_duplicated():
    before=row(', CONSTRAINT `old` FOREIGN KEY (`id`) REFERENCES `z_parent` (`id`)')
    after=row(', CONSTRAINT `new` FOREIGN KEY (`id`) REFERENCES `other``db`.`a_parent` (`id`), CONSTRAINT `self` FOREIGN KEY (`id`) REFERENCES `child``é` (`id`)')
    assert lock_source(before,after,'')=='LOCK TABLES `db``é`.`child``é` WRITE, `db``é`.`z_parent` READ, `other``db`.`a_parent` READ'


def test_unquoted_or_extra_native_parent_tokens_cannot_become_lock_sql():
    for parent in ('unquoted','`a` AS `alias`','`a`.`b`.`c`'):
        with pytest.raises(ValueError):lock_source(row(''),row(', CONSTRAINT `fk` FOREIGN KEY (`id`) REFERENCES '+parent+' (`id)'), '')
