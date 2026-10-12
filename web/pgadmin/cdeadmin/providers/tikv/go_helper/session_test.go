package main

import (
	"bytes"
	"context"
	"strings"
	"testing"

	"github.com/tikv/client-go/v2/txnkv/transaction"
)

func TestRetainedProtocolRefusesUnownedAndOversizedFrames(t *testing.T) {
	for _, input := range []string{
		`{"operation":"commit"}` + "\n",
		`{"operation":"open","pd_endpoints":[]}` + "\n",
		strings.Repeat("x", maximumRequestBytes+2) + "\n",
	} {
		var output bytes.Buffer
		if err := serveSession(strings.NewReader(input), &output); err == nil {
			t.Fatal("invalid first frame admitted")
		}
		if output.Len() != 0 {
			t.Fatal("invalid frame emitted success")
		}
	}
}

func TestRawOperationsCannotEscapeActiveTransaction(t *testing.T) {
	session := nativeSession{txn: &transaction.KVTxn{}, state: "active"}
	for _, op := range []string{"put", "get", "transaction", "scan"} {
		if _, err := session.call(context.Background(), request{Operation: op}); err == nil {
			t.Fatal("raw operation bypassed active transaction", op)
		}
	}
	if session.txn == nil {
		t.Fatal("refusal detached original transaction")
	}
}

func TestUnavailableDecisionCannotBecomeSuccess(t *testing.T) {
	session := nativeSession{state: "commit-returned"}
	for _, op := range []string{"commit", "rollback", "txn_get", "txn_set"} {
		if _, err := session.call(context.Background(), request{Operation: op}); err == nil {
			t.Fatal("unowned decision accepted", op)
		}
	}
}
