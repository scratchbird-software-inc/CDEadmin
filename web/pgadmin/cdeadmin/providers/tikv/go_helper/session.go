package main

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"io"
	"strconv"
	"time"

	"github.com/tikv/client-go/v2/config"
	tikverr "github.com/tikv/client-go/v2/error"
	"github.com/tikv/client-go/v2/rawkv"
	"github.com/tikv/client-go/v2/txnkv"
	"github.com/tikv/client-go/v2/txnkv/transaction"
)

// A process owns exactly one route and transaction. No transaction replay loop.
type nativeSession struct {
	route  request
	raw    *rawkv.Client
	client *txnkv.Client
	txn    *transaction.KVTxn
	state  string
}

func (s *nativeSession) close() error {
	var failures []error
	if s.txn != nil {
		failures = append(failures, s.txn.Rollback())
		s.txn = nil
	}
	if s.raw != nil {
		failures = append(failures, s.raw.Close())
		s.raw = nil
	}
	if s.client != nil {
		failures = append(failures, s.client.Close())
		s.client = nil
	}
	return errors.Join(failures...)
}

func (s *nativeSession) call(ctx context.Context, v request) (response, error) {
	result := response{Records: []record{}, ProviderFinality: true, Native: map[string]any{
		"operation": v.Operation, "helper_protocol": "retained-v1", "state": s.state,
		"automatic_transaction_retry": false,
	}}
	switch v.Operation {
	case "begin":
		if s.txn != nil {
			return result, errors.New("TiKV transaction already active")
		}
		if s.route.APIVersion == 1 && s.route.EnableTTL {
			return result, errors.New("TxnKV requires API v2 when TTL is enabled")
		}
		if s.client == nil {
			version, err := apiVersion(s.route)
			if err != nil {
				return result, err
			}
			global := config.GetGlobalConfig()
			global.Security = security(s.route)
			config.StoreGlobalConfig(global)
			s.client, err = txnkv.NewClient(s.route.PDEndpoints, txnkv.WithAPIVersion(version))
			if err != nil {
				return result, errors.New("TiKV transaction connection failed")
			}
		}
		var err error
		s.txn, err = s.client.Begin()
		if err != nil {
			return result, errors.New("TiKV begin failed")
		}
		s.txn.SetPessimistic(s.route.TransactionMode == "pessimistic")
		s.state = "active"
	case "commit", "rollback":
		if s.txn == nil {
			return result, errors.New("TiKV transaction unavailable")
		}
		tx := s.txn
		s.txn = nil
		s.state = "decision-unknown"
		var err error
		if v.Operation == "commit" {
			err = tx.Commit(ctx)
		} else {
			err = tx.Rollback()
		}
		if err != nil {
			return result, errors.New("TiKV decision outcome unavailable")
		}
		s.state = v.Operation + "-returned"
	case "txn_get", "txn_set", "txn_delete", "txn_scan":
		if s.txn == nil {
			return result, errors.New("TiKV transaction unavailable")
		}
		if v.Operation == "txn_scan" {
			begin, err := decode(v.StartKey, "start_key")
			if err != nil {
				return result, err
			}
			end, err := decode(v.EndKey, "end_key")
			if err != nil {
				return result, err
			}
			if v.Limit < 1 || v.Limit > 256 {
				return result, errors.New("TiKV transaction page limit invalid")
			}
			iter, err := s.txn.Iter(begin, end)
			if err != nil {
				return result, errors.New("TiKV transaction scan failed")
			}
			defer iter.Close()
			size := 0
			for iter.Valid() && len(result.Records) < v.Limit {
				entry := record{Key: encode(iter.Key()), Value: encode(iter.Value())}
				width := len(entry.Key) + len(entry.Value)
				if len(result.Records) > 0 && size+width > 1048576 {
					break
				}
				result.Records = append(result.Records, entry)
				size += width
				if err := iter.Next(); err != nil {
					return result, errors.New("TiKV transaction scan continuation failed")
				}
			}
			result.Native["more"] = iter.Valid()
		} else {
			key, err := decode(v.Key, "key")
			if err != nil {
				return result, err
			}
			if v.Operation == "txn_get" {
				entry, err := s.txn.Get(ctx, key)
				found := !errors.Is(err, tikverr.ErrNotExist)
				if err != nil && found {
					return result, errors.New("TiKV transaction read failed")
				}
				result.Records = append(result.Records, record{Key: encode(key), Value: encode(entry.Value), Found: boolPointer(found)})
			} else {
				if s.route.TransactionMode == "pessimistic" {
					if err := s.txn.LockKeysWithWaitTime(ctx, 0, key); err != nil {
						return result, errors.New("TiKV native pessimistic lock failed")
					}
				}
				if v.Operation == "txn_set" {
					data, err := decode(v.Value, "value")
					if err != nil {
						return result, err
					}
					err = s.txn.Set(key, data)
					if err != nil {
						return result, errors.New("TiKV staged write failed")
					}
				} else if err := s.txn.Delete(key); err != nil {
					return result, errors.New("TiKV staged delete failed")
				}
				result.Records = append(result.Records, record{Key: encode(key), Accepted: boolPointer(true)})
			}
		}
	case "close":
		if err := s.close(); err != nil {
			return result, errors.New("TiKV native cleanup failed")
		}
		s.state = "closed"
	default:
		if s.txn != nil {
			return result, errors.New("RawKV and bundled transactions cannot join active TxnKV")
		}
		if v.Operation == "transaction" {
			r, err := transactionRequest(ctx, v)
			if err != nil {
				return result, err
			}
			r.Native["helper_protocol"] = "retained-v1"
			r.Native["state"] = s.state
			return r, nil
		}
		r, err := rawOnClient(ctx, s.raw, v)
		if err != nil {
			return result, err
		}
		result.Records = r.Records
		for k, x := range r.Native {
			result.Native[k] = x
		}
	}
	result.Native["state"] = s.state
	if s.txn != nil {
		result.Native["start_ts"] = strconv.FormatUint(s.txn.StartTS(), 10)
	}
	return result, nil
}

func serveSession(input io.Reader, output io.Writer) error {
	scanner := bufio.NewScanner(input)
	scanner.Buffer(make([]byte, 4096), maximumRequestBytes+1)
	var session *nativeSession
	defer func() {
		if session != nil {
			_ = session.close()
		}
	}()
	for scanner.Scan() {
		if len(scanner.Bytes()) > maximumRequestBytes {
			return errors.New("TiKV request exceeds bounds")
		}
		var v request
		if err := json.Unmarshal(scanner.Bytes(), &v); err != nil {
			return errors.New("TiKV request malformed")
		}
		if session == nil {
			if v.Operation != "open" {
				return errors.New("TiKV session must open first")
			}
			if err := validateRequest(v); err != nil {
				return err
			}
			if v.OperationTimeoutSeconds == 0 {
				v.OperationTimeoutSeconds = 30
			}
			if v.TransactionMode == "" {
				v.TransactionMode = "optimistic"
			}
			session = &nativeSession{route: v, state: "idle"}
			ctx, cancel := context.WithTimeout(context.Background(), time.Duration(v.OperationTimeoutSeconds)*time.Second)
			version, err := apiVersion(v)
			if err == nil {
				session.raw, err = rawkv.NewClientWithOpts(ctx, v.PDEndpoints, rawkv.WithAPIVersion(version), rawkv.WithSecurity(security(v)))
			}
			cancel()
			if err != nil {
				return errors.New("TiKV retained connection failed")
			}
			data, err := encodedResponse(response{Records: []record{}, ProviderFinality: true, Native: map[string]any{"helper_protocol": "retained-v1", "state": "idle", "cluster_id": strconv.FormatUint(session.raw.ClusterID(), 10)}})
			if err != nil {
				return err
			}
			if _, err = output.Write(data); err != nil {
				return err
			}
			continue
		}
		// Subsequent frames cannot redirect the pinned native connection.
		v.PDEndpoints = session.route.PDEndpoints
		v.APIVersion, v.EnableTTL = session.route.APIVersion, session.route.EnableTTL
		v.TLSCA, v.TLSCertificate, v.TLSKey = session.route.TLSCA, session.route.TLSCertificate, session.route.TLSKey
		v.TransactionMode = session.route.TransactionMode
		v.OperationTimeoutSeconds = session.route.OperationTimeoutSeconds
		if err := validateRequest(v); err != nil {
			return err
		}
		ctx, cancel := context.WithTimeout(context.Background(), time.Duration(v.OperationTimeoutSeconds)*time.Second)
		result, err := session.call(ctx, v)
		cancel()
		if err != nil {
			return err
		}
		data, err := encodedResponse(result)
		if err != nil {
			return err
		}
		if _, err = output.Write(data); err != nil {
			return err
		}
		if v.Operation == "close" {
			return nil
		}
	}
	return scanner.Err()
}
