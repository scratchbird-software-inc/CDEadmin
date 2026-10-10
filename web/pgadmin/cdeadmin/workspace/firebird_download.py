"""Authenticated HTTP delivery; native ownership stays in the provider."""
import base64

from flask import Response, stream_with_context


def response(service, server, data):
    request = data.get('request')
    if not isinstance(request, dict) or set(request) != {
            'owner_id', 'stream_reference', 'download_id'}:
        raise ValueError('Invalid file delivery request')
    if any(not isinstance(value, str) or not 1 <= len(value) <= 128
           for value in request.values()):
        raise ValueError('Invalid file delivery identity')

    def call(action, **values):
        return service.query_stream(
            server, data.get('session_id'),
            {**request, 'stream_action': action, **values},
            data.get('database_target_id'))

    admission = call('download_open')
    kind = admission['kind']
    if kind not in ('blob', 'array'):
        call('download_abort')
        raise ValueError('Invalid file delivery kind')

    def generate():
        finished = False
        try:
            sequence = 0
            while True:
                part = call('download_chunk', sequence=sequence)
                raw = base64.b64decode(part['data'], validate=True)
                if part['sequence'] != sequence or len(raw) > 1048576:
                    raise ValueError('Invalid file delivery chunk')
                yield raw
                if part['complete']:
                    call('download_finish')
                    finished = True
                    break
                sequence += 1
        finally:
            if not finished:
                try:
                    call('download_abort')
                except Exception:
                    # Expired/released owners cannot be re-created by cleanup.
                    pass

    result = Response(stream_with_context(generate()),
                      mimetype='application/octet-stream')
    suffix = 'blob.bin' if kind == 'blob' else 'array.jsonl'
    result.headers['Content-Disposition'] = (
        'attachment; filename="firebird-' + suffix + '"')
    result.headers['Cache-Control'] = 'no-store, private'
    result.headers['X-Content-Type-Options'] = 'nosniff'
    result.headers['X-Accel-Buffering'] = 'no'
    if kind == 'blob':
        result.content_length = admission['content_length']
    return result
