"""Lock exact native FK parents alongside an existing altered source table."""
from .mysql_schema_plan import parts
from .mysql_relational_fields import tokens
from ..providers.mysql_family.mysql_catalog import identifier


def lock_source(before,after,mode):
    database=before['native']['database'];owner=(database,before['name']);parents=set()
    for row in (before,after):
        _layout,clauses,_order=parts(row,mode)
        for (kind,_name),clause in clauses.items():
            if kind!='foreign-key':continue
            parsed=tokens(clause,mode)
            reference=next((i for i,item in enumerate(parsed) if item[0]=='word' and item[1].upper()=='REFERENCES'),None)
            if reference is None:raise ValueError('Native foreign-key reference is unavailable')
            names=[];expect_name=True
            for kind,value,_start,_end in parsed[reference+1:]:
                if kind=='group':break
                if kind=='quoted' and expect_name and (value.startswith('`') or value.startswith('"') and 'ANSI_QUOTES' in mode.split(',')):
                    names.append(value[1:-1].replace(value[0]*2,value[0]));expect_name=False
                elif kind=='symbol' and value=='.' and not expect_name:expect_name=True
                else:raise ValueError('Native foreign-key parent requires exact quoted identity')
            if len(names) not in (1,2) or expect_name:raise ValueError('Native foreign-key parent is ambiguous')
            parent=(database,names[0]) if len(names)==1 else tuple(names)
            if parent!=owner:parents.add(parent)
    return 'LOCK TABLES '+'.'.join(identifier(value) for value in owner)+' WRITE'+''.join(
        ', '+'.'.join(identifier(value) for value in parent)+' READ' for parent in sorted(parents))
