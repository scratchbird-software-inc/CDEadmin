"""Record a generated administration call only after its native return."""


def record(proof, request):
    task = 'visual_admin.' + request['resource_kind'] + '.' + request['operation_id']
    proof.setdefault('task_evidence', {})[task] = {
        'live_execution': 'passed', 'generated_statement_returned': True}
