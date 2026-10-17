"""Explicit external-content FTS reconstruction during native owner renames."""
from copy import deepcopy

from ..providers.sqlite.modules import declaration,arguments,option,unquote
from ..providers.sqlite.fts_configuration import statements,quote,validate

FOLD=str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')


def equal(left,right):return left.translate(FOLD)==right.translate(FOLD)


def plans(baseline,renames,selected):
    if (not isinstance(selected,(list,tuple)) or len(selected)>16 or
            any(not isinstance(item,str) or not item for item in selected) or len(set(selected))!=len(selected)):
        raise ValueError('Select exact distinct external-content FTS rebuild identities')
    result=[]
    for row in baseline['rows'].values():
        if row['kind']!='fts-table' or row['path'][0]!='main' or row['system']!='false':continue
        native=declaration(row['native'].get('ddl'))
        if native is None or native[1].lower() not in {'fts4','fts5'}:continue
        module=native[1].lower();source=row['native']['ddl'];content=option(source,'content')
        if not content:continue
        original_content=content;name=row['name'];rowid=option(source,'content_rowid') or 'rowid';new_rowid=rowid
        fields={item['name'].translate(FOLD) for item in row['native'].get('columns',[]) if not item.get('hidden')}
        for item in renames:
            if item['kind']=='table':
                if equal(item['table'],name):name=item['to']
                if equal(item['table'],content):content=item['to']
            elif equal(item['table'],content):
                if item['from'].translate(FOLD) in fields:
                    raise ValueError('Renaming an external-content FTS column requires coordinated FTS column and dependency rewriting')
                if module=='fts5' and equal(item['from'],new_rowid):new_rowid=item['to']
                elif module=='fts4' and (item['from'].translate(FOLD) in {'rowid','oid','_rowid_'} or
                        option(source,'languageid') and equal(item['from'],option(source,'languageid'))):
                    raise ValueError('Native FTS4 row/language identity renames require a dedicated mapping')
        if content==original_content and new_rowid==rowid:continue
        constructor=arguments(source)
        replacements={'content':content,**({'content_rowid':new_rowid} if new_rowid!=rowid else {})}
        for key,value in replacements.items():
            encoded="'"+value.replace("'","''")+"'";found=False
            for index,argument in enumerate(constructor):
                left,separator,_value=argument.partition('=')
                if separator and unquote(left).lower()==key:
                    constructor[index]=left+'='+encoded;found=True;break
            if not found:constructor.append(key+'='+encoded)
        configuration=deepcopy(row['native'].get('fts_configuration'))
        validate(configuration)
        restore=statements(name,configuration)
        ddl='CREATE VIRTUAL TABLE "main".'+quote(name)+' USING '+quote(module)+'('+','.join(constructor)+')'
        rebuild='INSERT INTO "main".'+quote(name)+'('+quote(name)+") VALUES('rebuild')"
        integrity='INSERT INTO "main".'+quote(name)+'('+quote(name)+(',rank' if module=='fts5' else '')+") VALUES('integrity-check'"+(',1' if module=='fts5' else '')+')'
        result.append({'resource_id':row['resource_id'],'source_name':row['name'],'name':name,'module':module,
            'original_content':original_content,'content':content,'configuration':configuration,
            'stages':['DROP TABLE "main".'+quote(name),ddl,*(restore if module=='fts5' else []),rebuild,*restore,integrity]})
    required={item['resource_id'] for item in result}
    if set(selected)!=required:
        raise ValueError('Select exactly the required native FTS rebinding adapter rebuild identities: '+', '.join(sorted(required)))
    return result
