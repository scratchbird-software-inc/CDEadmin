"""Explicit native LIKE/GLOB replacement; no invented PRAGMA getter."""
import uuid
from ...sdk import RelationalClientError


def action(connection,request,revision):
    operation=request.get('operation')
    fields={'review':{'operation','pragma','value'},
        'set_connection_pragma':{'operation','pragma','value','review_id','confirmed','replace_callback_confirmed'}}
    if (not isinstance(operation,str) or operation not in fields or set(request)-fields[operation]
            or type(request.get('value')) is not bool or type(revision) is not int or revision<0):
        raise RelationalClientError('Native LIKE policy requires a typed original-session review and revision')
    reviews=getattr(connection,'_cdeadmin_pragma_policy_reviews',None)
    if not isinstance(reviews,dict):raise RelationalClientError('Driver-owned native policy review required')
    statement='PRAGMA case_sensitive_like='+('ON' if request['value'] else 'OFF')
    cursor=connection.cursor()
    try:
        if operation=='review':
            cursor.execute('PRAGMA pragma_list')
            if 'case_sensitive_like' not in {row[0]for row in cursor.fetchall()}:
                raise RelationalClientError('Native LIKE replacement unavailable in this build')
            token=uuid.uuid4().hex
            reviews['case_sensitive_like']={'review_id':token,'revision':revision,'value':request['value']}
            return {'pragma':'case_sensitive_like','review_id':token,'ready_to_apply':True,
                'requested_value':request['value'],'before_value':None,'before_value_observed':False,
                'previous_callback_identity':'unobservable','callback_restoration_claimed':False,
                'native_statement':statement,'native_work_revision':str(revision),
                'warning':'Replaces existing LIKE/GLOB callbacks. Previous policy/identity is unobservable and rollback does not restore it. LIKE in CHECK, expression or partial indexes can change schema behaviour or require REINDEX under the intended policy.'}
        review=reviews.get('case_sensitive_like')
        if (request.get('confirmed') is not True or request.get('replace_callback_confirmed') is not True
                or not isinstance(review,dict) or request.get('review_id')!=review['review_id']
                or review['revision']!=revision or review['value'] is not request['value']):
            raise RelationalClientError('Refresh and confirm the original-session LIKE callback replacement')
        # Consume before dispatch. An interrupted/unknown setter cannot be
        # replayed using the same review, even if the requested value was equal.
        reviews.pop('case_sensitive_like')
        try:
            cursor.execute(statement)
            cursor.execute("SELECT 'a' LIKE 'A','a' LIKE 'a','a' GLOB 'A','a' GLOB 'a'")
            observed=cursor.fetchone()
            expected=(0 if request['value'] else 1,1,0,1)
            if observed!=expected:raise ValueError('Native pattern postcondition is unconfirmed')
        except Exception as error:
            failure=RelationalClientError('Native LIKE callback outcome is unconfirmed; do not replay; obtain a new explicit review')
            failure.native_outcome='unknown_outcome';raise failure from error
        return {'pragma':'case_sensitive_like','outcome':'native_pattern_postcondition_observed',
            'effective_value':request['value'],'before_value':None,'before_value_observed':False,
            'native_pattern_probe':list(observed),'previous_callback_identity':'unobservable',
            'callback_restoration_claimed':False,'scope':'original-connection',
            'transaction_open':connection.in_transaction,'commit_requested':False,'rollback_requested':False,
            'future_connection_defaults_changed':False,'file_persisted':False,'automatic_retry':False}
    finally:cursor.close()
