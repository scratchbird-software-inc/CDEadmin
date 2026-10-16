import pytest
from tools.mysql_reply_loss_fixture import CommitReplyLoss


@pytest.mark.parametrize('body', [b'\x03COMMIT', b'\x03commit', b'\x03\x00\x01COMMIT', b'\x03\x00\x01commit'])
def test_commit_fault_recognizes_pure_and_native_client_commands(body):
    assert CommitReplyLoss.commit_request(body)


@pytest.mark.parametrize('body', [b'\x03SELECT COMMIT', b'\x03SELECT \'COMMIT\'', b'\x03ROLLBACK', b'\x16COMMIT'])
def test_commit_fault_does_not_drop_unrelated_responses(body):
    assert not CommitReplyLoss.commit_request(body)
