"""Bounded, secret-free HTTP contracts for pre-dispatch refusals."""
import re


def response(error):
    errors = []
    for value in getattr(error, 'errors', ())[:128]:
        if not isinstance(value, dict):
            continue
        field, code = value.get('field_id'), value.get('code')
        if field is not None and (not isinstance(field, str) or not re.fullmatch(r'[A-Za-z0-9_.\[\]-]{1,128}', field)):
            field = None
        if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,128}', code):
            code = 'invalid_field'
        errors.append({'field_id': field, 'code': code})
    return {'status': error.status, 'success': 0, 'info': error.code,
            'errormsg': 'The operation was refused before dispatch. Review the indicated fields or create a new plan.',
            'data': {'refusal': {'code': error.code, 'errors': errors, 'native_dispatched': False, 'automatic_retry': False}}}
