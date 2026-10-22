"""Qualify native account changes and private password dispatch on owned peers."""
import json


def qualify(context, peer, execute, http, options, sql, login, output):
    checks=[]
    secrets=[]
    def run(method, account, native_options=None, *, secret=None, returned=True):
        arguments=[account]+([native_options] if native_options is not None else [])
        value=execute(context+'.'+method,arguments,peer,account_password=secret,expect_returned=returned)
        if returned:
            observation=value['result']['account_observation']
            assert observation.get('available') is not False,observation
            assert observation['account']==account
        return value
    for purpose in ('admin','router'):
        account={'user':'sr_'+purpose[0]+'_'+context+'`雪','host':'%'}
        method='setup_'+purpose+'_account'
        first='Native-'+purpose+"-one:'\\雪"
        second='Native-'+purpose+"-two:'\\雪"
        secrets.extend([first,second])
        result=run(method,account,secret=first)
        assert result['result']['account_observation']['exists'] is True
        identity=login(peer,account['user'],first)
        assert identity['identity']==account['user']+'@%' and identity['version'].split('-')[0]=='9.7.0'
        sql(peer,'CREATE DATABASE IF NOT EXISTS sr_account_extra')
        sql(peer,'GRANT SELECT ON sr_account_extra.* TO %s@%s',(account['user'],account['host']))
        updated=run(method,account,{'update':True,'passwordExpiration':30})
        assert any('sr_account_extra' in row[0] for row in updated['result']['account_observation']['native_grants'])
        assert login(peer,account['user'],first)['identity']==identity['identity']
        assert sql(peer,'SELECT password_lifetime AS days FROM mysql.user WHERE User=%s AND Host=%s',
            (account['user'],account['host']))==[{'days':30}]
        changed=run(method,account,{'update':True},secret=second)
        assert changed['result']['account_observation']['exists']
        assert login(peer,account['user'],second)['identity']==identity['identity']
        dry={'user':account['user']+'_d','host':'%'}
        dry_result=run(method,dry,{'dryRun':True},secret=first)
        assert dry_result['result']['account_observation']['exists'] is False
        assert sql(peer,'SELECT COUNT(*) AS n FROM mysql.user WHERE User=%s AND Host=%s',
            (dry['user'],dry['host']))==[{'n':0}]
        # Native row or grant changes invalidate reviewed account intent.
        selected=options(context+'.'+method,[account,{'update':True}],peer)
        review=http('review',{'options':selected},peer=peer)
        sql(peer,'ALTER USER %s@%s PASSWORD EXPIRE INTERVAL 31 DAY',(account['user'],account['host']))
        http('start',{key:review[key] for key in ('job_id','review_digest')}|{'confirmed':True},peer=peer,refused=True)
        auth=sql(peer,'SELECT HEX(authentication_string) AS value FROM mysql.user WHERE User=%s AND Host=%s',
            (account['user'],account['host']))[0]['value']
        assert auth
        # Neither password text nor native authentication material belongs in
        # public receipts or retained job programs/configuration.
        for path in (output/'app').rglob('*'):
            if not path.is_file() or path.suffix not in {'.json','.py'}:continue
            text=path.read_text(errors='replace')
            assert auth not in text,('Native authentication material retained',path.name)
            for secret in secrets:
                assert secret not in text and json.dumps(secret,ensure_ascii=True)[1:-1] not in text,('Private password retained',path.name)
        checks.append('native-'+purpose+'-create-quoted-Unicode-identity-private-password-login-preserve-update-retain-extra-grants-expiration-password-change-dry-run-and-stale-state-refusal')
    return {'complete':True,'checks':checks,'scope':'Current writable native primary registrations; login acceptance uses the explicitly selected real pure/C driver'}
