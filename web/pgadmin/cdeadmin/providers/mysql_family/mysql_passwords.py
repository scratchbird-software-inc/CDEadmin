"""Native generated-password producer; the shared application owns delivery/reveal.

The trusted receiver reserves before DCL and publishes a SecretLease into a
SecretReference. It must preserve published references when releasing capacity.
No receiver is inferred from HTTP fields, and a missing receiver fails closed.
"""
from uuid import UUID
from ...sdk import RelationalClientError
from ...security import SecretLease, SecretReference


def factors(intent):
    draft=intent['draft']
    return tuple(([1] if draft.get('authentication_mode')=='RANDOM_PASSWORD' else [])+
        [n for n,row in enumerate(draft.get('authentication_factors',[]),2) if row.get('mode')=='RANDOM_PASSWORD']+
        [row['factor'] for row in draft.get('factor_actions',[]) if row.get('mode')=='RANDOM_PASSWORD'])


def receiver(client,intent,expected=None,scope=None):
    if not factors(intent):return None
    value=getattr(client,'protected_password_receiver',None)
    try:
        if value is None and callable(getattr(client, 'protected_password_receiver_factory', None)):
            value = client.protected_password_receiver_factory(scope or intent.get('review', {}).get('delivery_scope'))
        binding=str(UUID(value.binding_id))
        if binding!=value.binding_id or expected is not None and expected!=binding:raise ValueError()
        if not all(callable(getattr(value,name,None)) for name in ('reserve','publish','release')):raise ValueError()
    except Exception:
        raise RelationalClientError('Protected generated-password delivery is unavailable or changed; no account command was sent') from None
    return value


def binding(client,intent,scope=None):
    value=receiver(client,intent,scope=scope)
    return value.binding_id if value else None


def deliver(receiver,reservation,cursor,intent):
    expected=factors(intent);result=[];seen=set()
    if not cursor.description and (intent['draft'].get('if_exists') or intent['draft'].get('if_not_exists')):return result
    if not cursor.description:raise RelationalClientError('Native generated-password result is missing')
    if [str(row[0]).lower() for row in cursor.description]!=['user','host','generated password','auth_factor']:
        raise RelationalClientError('Unexpected native generated-password result columns')
    rows=cursor.fetchall()
    if not rows and (intent['draft'].get('if_exists') or intent['draft'].get('if_not_exists')):return result
    for user,host,password,factor in rows:
        if (user,host)!=(intent['user'],intent['host']) or type(factor) is not int or factor not in expected or factor in seen:
            raise RelationalClientError('Unexpected native generated-password identity')
        seen.add(factor)
    if set(expected)!=seen:raise RelationalClientError('Native generated-password factors are incomplete')
    for user,host,password,factor in rows:
        with SecretLease(password) as lease:reference=receiver.publish(reservation,factor,lease)
        if not isinstance(reference,SecretReference) or reference.endpoint_mode!='legacy_native' or reference.secret_kind!='password':
            raise RelationalClientError('Protected delivery did not return an endpoint password reference')
        result.append({'factor':factor,'secret_reference_id':reference.reference_id})
    return result
