"""Explicit external-content FTS reconstruction during native owner renames."""
from copy import deepcopy

from ..providers.sqlite.modules import declaration,arguments,option,unquote
from ..providers.sqlite.fts_configuration import statements,quote,validate

FOLD=str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')


def equal(left,right):return left.translate(FOLD)==right.translate(FOLD)


def rename_field(argument,former,renamed):
    """Replace the native column's first token, retaining its module suffix."""
    if not argument:return argument
    first=argument[0];end=0
    if first in {'\'','"','`','['}:
        close=']' if first=='[' else first;end=1
        while end<len(argument):
            if argument[end]==close:
                end+=1
                if close!=']' and end<len(argument) and argument[end]==close:end+=1;continue
                break
            end+=1
    else:
        while end<len(argument) and not argument[end].isspace() and argument[end]!='=':end+=1
    if equal(unquote(argument[:end]),former) and not argument[end:].lstrip().startswith('='):
        return quote(renamed)+argument[end:]
    key,separator,value=argument.partition('=')
    if separator and unquote(key).lower()=='notindexed' and equal(unquote(value),former):
        return key+'='+quote(renamed)
    return argument


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
        columns=row['native'].get('columns',[])
        fields={item['name'].translate(FOLD):item['name'] for item in columns if not item.get('hidden')}
        field_renames=[]
        for item in renames:
            if item['kind']=='table':
                if equal(item['table'],name):name=item['to']
                if equal(item['table'],content):content=item['to']
            elif equal(item['table'],content):
                if item['from'].translate(FOLD) in fields:
                    former=fields.pop(item['from'].translate(FOLD));fields[item['to'].translate(FOLD)]=item['to']
                    field_renames.append((former,item['to']))
                if module=='fts5' and equal(item['from'],new_rowid):new_rowid=item['to']
                elif module=='fts4' and (item['from'].translate(FOLD) in {'rowid','oid','_rowid_'} or
                        option(source,'languageid') and equal(item['from'],option(source,'languageid'))):
                    raise ValueError('Native FTS4 row/language identity renames require a dedicated mapping')
        if content==original_content and new_rowid==rowid and not field_renames:continue
        constructor=arguments(source)
        for former,renamed in field_renames:
            constructor=[rename_field(argument,former,renamed) for argument in constructor]
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
        # An empty ordinary relation lets SQLite's own ALTER TABLE rewrite all
        # dependent views/triggers. It lives only inside this rename transaction;
        # the external-content virtual index is then reconstructed and checked.
        before=[]
        if field_renames:
            before=['DROP TABLE "main".'+quote(row['name']),
                'CREATE TABLE "main".'+quote(row['name'])+'('+','.join(quote(column['name']) for column in columns)+')',
                *('ALTER TABLE "main".'+quote(row['name'])+' RENAME COLUMN '+quote(former)+' TO '+quote(renamed)
                  for former,renamed in field_renames)]
        result.append({'resource_id':row['resource_id'],'source_name':row['name'],'name':name,'module':module,
            'original_content':original_content,'content':content,'configuration':configuration,
            'column_renames':[{'from':former,'to':renamed} for former,renamed in field_renames],'before':before,
            'stages':['DROP TABLE "main".'+quote(name),ddl,*(restore if module=='fts5' else []),rebuild,*restore,integrity]})
    required={item['resource_id'] for item in result}
    if set(selected)!=required:
        raise ValueError('Select exactly the required native FTS rebinding adapter rebuild identities: '+', '.join(sorted(required)))
    return result
