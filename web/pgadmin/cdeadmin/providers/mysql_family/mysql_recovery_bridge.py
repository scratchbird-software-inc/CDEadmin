"""Application-owned SSH streams for separate native recovery registrations."""
import atexit
import copy
import os
import select
import socket
import threading
import weakref

from ...sdk import RelationalClientError

SCHEMA = 'cdeadmin.mysql-recovery-registration.v1'
ROUTE_KEY = 'mysql_recovery_binding'


class Bridge:
    def __init__(self, binding, transport, request):
        self.binding=copy.deepcopy(binding);self.transport=transport;self.request=copy.deepcopy(request)
        self.lock=threading.RLock();self.active=True;self.users=0;self.sockets=set();self.channels=set()
        self.listener=socket.socket();self.listener.bind(('127.0.0.1',0));self.listener.listen(8);self.listener.settimeout(.2)
        self.port=self.listener.getsockname()[1]
        self.thread=threading.Thread(target=self._accept,daemon=True);self.thread.start()

    def acquire(self):
        with self.lock:
            if not self.active:raise RelationalClientError('Recovery transport is detached; attach it again from its recovery workspace')
            if self.users>=64:raise RelationalClientError('Recovery transport connection limit reached')
            self.users+=1
        return Lease(self)

    def release(self):
        with self.lock:
            self.users-=1
            if not self.active and self.users==0:self.listener.close()

    def _accept(self):
        while True:
            try:client,_peer=self.listener.accept()
            except socket.timeout:continue
            except OSError:return
            with self.lock:
                if not self.active or len(self.sockets)>=64:client.close();continue
                self.sockets.add(client)
            threading.Thread(target=self._relay,args=(client,),daemon=True).start()

    def _relay(self, client):
        channel=None
        try:
            channel=self.transport.open_stream(self.request)
            with self.lock:
                if not self.active:return
                self.channels.add(channel)
            reading=[client,channel]
            while reading:
                ready,_,_=select.select(reading,[],[],.5)
                for source in ready:
                    data=source.recv(65536)
                    if not data:
                        if source is client:
                            reading.remove(client);channel.shutdown_write()
                        else:return
                    elif source is client:channel.sendall(data)
                    else:client.sendall(data)
        except Exception:
            # Never retain native packets, SQL, authentication or result bytes.
            pass
        finally:
            client.close()
            if channel is not None:channel.close()
            with self.lock:self.sockets.discard(client);self.channels.discard(channel)

    def close(self):
        with self.lock:
            self.active=False
            for stream in (*self.sockets,*self.channels):
                try:stream.close()
                except OSError:pass
            self.transport.close()
            if self.users==0:self.listener.close()


class Lease:
    def __init__(self, bridge):self.bridge=bridge;self.released=False
    def release(self):
        if not self.released:self.released=True;self.bridge.release()


class Bridges:
    def __init__(self):self.lock=threading.RLock();self.entries={}
    def install(self,binding,transport,request):
        with self.lock:
            previous=self.entries.get(binding['id'])
            if previous is not None:
                with previous.lock:
                    if previous.users:raise RelationalClientError('Close this recovery registration\'s native SQL connections before replacing its transport')
                    previous.close()
            bridge=Bridge(binding,transport,request);self.entries[binding['id']]=bridge
        return bridge
    def get(self,binding):
        with self.lock:bridge=self.entries.get(binding.get('id'))
        if bridge is None or bridge.binding!=binding or not bridge.active:
            raise RelationalClientError('Recovery transport is unavailable; attach its pinned SSH connection again')
        return bridge
    def detach(self,binding,*,expected=None,force=False):
        with self.lock:
            bridge=self.entries.get(binding['id'])
            if bridge is None or bridge.binding!=binding or expected is not None and bridge is not expected:return
            with bridge.lock:
                if bridge.users and not force:raise RelationalClientError('Close this recovery registration\'s native SQL connections before detaching its transport')
                self.entries.pop(binding['id']);bridge.close()
    def close(self):
        with self.lock:values=list(self.entries.values());self.entries.clear()
        for bridge in values:bridge.close()


bridges=Bridges()
atexit.register(bridges.close)


UTILITY_KEY='_mysql_recovery_raw_utility'


class ReplayUtility:
    """An unpersisted reservation of one original process-bound route."""
    def __init__(self,route,*,family):
        if family not in {'raw','shell'}:raise RelationalClientError('Select a native replay utility family')
        if family=='shell' and os.name!='posix':
            raise RelationalClientError('Managed recovery Shell replay currently requires a POSIX application execution host')
        self.family=family
        self.binding=copy.deepcopy(route[ROUTE_KEY]);self.released=False;self.uncertain=False
        if self.binding.get('recovery_mode')!='replay':
            raise RelationalClientError('Start a separately reviewed writable recovery instance before native replay')
        with bridges.lock:
            self.bridge=bridges.get(self.binding);self.lease=self.bridge.acquire()
        self.route={**copy.deepcopy(route),'host':'127.0.0.1','port':self.bridge.port,UTILITY_KEY:self}
        self.route.pop('unix_socket',None);self.route.pop('failover',None)

    def validate(self,route):
        if (self.released or route.get(UTILITY_KEY) is not self or route.get(ROUTE_KEY)!=self.binding or
                route.get('host')!='127.0.0.1' or route.get('port')!=self.bridge.port or route.get('unix_socket') or route.get('failover') or
                bridges.get(self.binding) is not self.bridge):
            raise RelationalClientError('Native recovery utility lease is unavailable or changed')

    def __deepcopy__(self,memo):return self

    def close(self):
        if self.uncertain:
            # Retain the reservation when original utility termination is
            # unknown. Closing/replacing its route cannot establish finality.
            with self.bridge.lock:
                pending=getattr(self.bridge,'uncertain_utilities',None)
                if pending is None:pending=self.bridge.uncertain_utilities=[]
                if self not in pending:pending.append(self)
        elif not self.released:self.released=True;self.lease.release()


def admit_raw_utility(route):
    return admit_replay_utility(route,family='raw')


def admit_replay_utility(route,*,family):
    return ReplayUtility(route,family=family) if route.get(ROUTE_KEY) else None


def require_raw_utility(route):
    require_replay_utility(route,family='raw')


def require_replay_utility(route,*,family=None):
    value=route.get(UTILITY_KEY)
    if not isinstance(value,ReplayUtility) or family is not None and value.family!=family:
        raise RelationalClientError('This recovery route requires an admitted native replay utility lease')
    value.validate(route)


def confirm_raw_utility_termination(binding,job_id):
    """Release only the original job's reservation after durable observation."""
    if not binding:return
    with bridges.lock:
        original=bridges.entries.get(binding.get('id'))
        if original is None or original.binding!=binding:return
        with original.lock:
            pending=getattr(original,'uncertain_utilities',[])
            for value in list(pending):
                if getattr(value,'job_id',None)==job_id:
                    value.uncertain=False;value.close();pending.remove(value)


def native_connection(connect,args,options):
    binding=options.pop(ROUTE_KEY,None)
    if binding is None:return connect(*args,**options)
    bridge=bridges.get(binding);lease=bridge.acquire();native=None
    try:
        options.update(host='127.0.0.1',port=bridge.port);options.pop('unix_socket',None);options.pop('failover',None)
        native=connect(*args,**options)
        verify(native,binding)
        close=native.close;reconnect=native.reconnect;state={'lease':lease}
        def release():
            current=state.pop('lease',None)
            if current is not None:current.release()
        def closed(*a,**kw):
            try:return close(*a,**kw)
            finally:release()
        def connected(*a,**kw):
            if bridges.get(binding) is not bridge:
                raise RelationalClientError('Recovery transport was replaced; open a new native session')
            temporary=bridge.acquire()
            try:
                value=reconnect(*a,**kw);verify(native,binding)
                if state.get('lease') is None:state['lease']=bridge.acquire()
                return value
            except BaseException:closed();raise
            finally:temporary.release()
        native.close=closed;native.reconnect=connected
        weakref.finalize(native,release)
        return native
    except BaseException:
        if native is not None:
            try:native.close()
            except Exception:pass
        lease.release();raise


def verify(connection,binding):
    cursor=connection.cursor()
    try:
        cursor.execute('SELECT @@server_uuid,VERSION(),@@datadir');value=cursor.fetchone()
        if not value or value[0]!=binding['server_uuid'] or value[1]!=binding['version'] or value[2].rstrip('/')!=binding['datadir'].rstrip('/'):
            raise RelationalClientError('Native SQL peer differs from the registered recovery instance')
    finally:cursor.close()
