import {useEffect, useRef, useState} from 'react';

// Policy acknowledgement belongs to the native Query Tool endpoint. A lost
// reply blocks execution until an explicit setting request is acknowledged.
export default function useExecutionPolicy({request, onAccepted, onError, scope}) {
  const [status, setStatus] = useState({pending: false, uncertain: false});
  const pending = useRef(false);
  const generation = useRef(0);
  const uncertain = useRef(new Set());
  useEffect(() => {
    generation.current++;
    pending.current = false;
    uncertain.current.clear();
    setStatus({pending: false, uncertain: false});
    return () => { generation.current++; };
  }, [scope]);
  const change = async (name, value) => {
    if(pending.current) return;
    pending.current = true;
    const current = generation.current;
    setStatus(previous => ({...previous, pending: true}));
    try {
      const response = await request(name, value);
      if(response?.data?.data?.status !== true) throw new Error('Execution policy was not acknowledged');
      if(current !== generation.current) return;
      onAccepted(name, value);
      uncertain.current.delete(name);
      setStatus({pending: false, uncertain: uncertain.current.size > 0});
    } catch(error) {
      if(current !== generation.current) return;
      uncertain.current.add(name);
      setStatus({pending: false, uncertain: true});
      onError(error);
    } finally {
      if(current === generation.current) pending.current = false;
    }
  };
  return {...status, change};
}
