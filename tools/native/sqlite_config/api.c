/* Original-handle SQLite configuration through public SQLite/CPython APIs.
 * Capture occurs only inside the driver's explicitly staged native open.
 * No CPython connection-layout casts, supplied pointers or SQL callbacks.
 * Main-schema name storage is retained until explicit native close.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <sqlite3ext.h>
#include <string.h>
#include <stdlib.h>
#include <limits.h>
#if defined(__linux__)
#include <dirent.h>
#elif defined(_WIN32)
#include <windows.h>
#include <tlhelp32.h>
#elif defined(__APPLE__)
#include <mach/mach.h>
#endif
typedef struct Name Name;
struct Name { char *value; Name *next; };
typedef struct State State;
struct State { sqlite3 *db; int refs, confirmed_closed, aliases; Name *names; PyObject *owner_ref; PyObject *owner_identity; };
static Py_tss_t pending=Py_tss_NEEDS_INIT;
static PyObject *connection_type, *transaction_descriptor, *closed_error;
static int capture_registered=0;
/* Never abandon or accumulate a native peer whose close was refused. */
static sqlite3 *pending_metadata_peer=NULL;
static int initialize_capture(void);
static void release(State *s) {
 if(--s->refs==0) { Name *n=s->names; while(n){Name *next=n->next; if(s->confirmed_closed)sqlite3_free(n->value);free(n);n=next;} Py_XDECREF(s->owner_ref); free(s); }
}
#ifdef _WIN32
__declspec(dllexport)
#endif
int sqlite3_cdeadminconfig_init(sqlite3 *db,char **error,const sqlite3_api_routines *api) {
 State *s=PyThread_tss_get(&pending);
 if(!s)return SQLITE_OK;
 if(s->db==db)return SQLITE_OK;
 if(s->db || api->db_config!=sqlite3_db_config || api->libversion_number()<3035000) { *error=sqlite3_mprintf("Native configuration binding/library identity refused");return SQLITE_ERROR; }
 s->db=db;return SQLITE_OK;
}
static void capsule_destroy(PyObject *capsule) { State *s=PyCapsule_GetPointer(capsule,"cdeadmin.sqlite.configuration@1");if(s){if(PyThread_tss_get(&pending)==s)PyThread_tss_set(&pending,NULL);release(s);}else PyErr_Clear(); }
static PyObject *native_open_property(PyObject *owner) {
 return PyObject_CallMethod(transaction_descriptor,"__get__","OO",owner,connection_type);
}
static State *state(PyObject *capsule) {
 State *s=PyCapsule_GetPointer(capsule,"cdeadmin.sqlite.configuration@1");PyObject *owner,*open;
 if(!s)return NULL;
 if(!s->db || !s->owner_ref){PyErr_SetString(PyExc_RuntimeError,"Native configuration owner closed, invalidated or not yet bound");return NULL;}
 owner=PyObject_CallNoArgs(s->owner_ref);if(!owner)return NULL;
 if(owner==Py_None){Py_DECREF(owner);PyErr_SetString(PyExc_RuntimeError,"Native configuration owner expired");return NULL;}
 /* Public CPython property validates that even an explicit base-class close
  * has not invalidated this native connection. The driver serializes all
  * operations and keeps the connection alive for the duration of the call. */
 open=native_open_property(owner);Py_DECREF(owner);
 if(!open)return NULL;
 Py_DECREF(open);return s;
}
static PyObject *begin_open(PyObject *self,PyObject *args) {
 State *s;PyObject *capsule;(void)self;(void)args;
 if(initialize_capture()!=0)return NULL;
 if(PyThread_tss_create(&pending)!=0 || PyThread_tss_get(&pending)){PyErr_SetString(PyExc_RuntimeError,"Native binding is already active");return NULL;}
 s=calloc(1,sizeof(*s));if(!s)return PyErr_NoMemory();s->refs=1;
 capsule=PyCapsule_New(s,"cdeadmin.sqlite.configuration@1",capsule_destroy);if(!capsule){release(s);return NULL;}
 PyThread_tss_set(&pending,s);return capsule;
}
static PyObject *finish_open(PyObject *self,PyObject *args) {
 PyObject *capsule,*connection;State *s;(void)self;
 if(!PyArg_ParseTuple(args,"OO",&capsule,&connection))return NULL;
 s=PyCapsule_GetPointer(capsule,"cdeadmin.sqlite.configuration@1");if(!s)return NULL;
 if(PyThread_tss_get(&pending)!=s){PyErr_SetString(PyExc_RuntimeError,"Native open binding changed");return NULL;}
 PyThread_tss_set(&pending,NULL);
 if(!s->db){PyErr_SetString(PyExc_RuntimeError,"Selected SQLite runtime did not capture the native owner");return NULL;}
 if(PyObject_IsInstance(connection,connection_type)!=1){PyErr_SetString(PyExc_TypeError,"Native SQLite connection required");return NULL;}
 s->owner_ref=PyWeakref_NewRef(connection,NULL);if(!s->owner_ref)return NULL;
 s->owner_identity=connection;Py_RETURN_NONE;
}
static PyObject *cancel_open(PyObject *self,PyObject *args) {
 PyObject *capsule;State *s;(void)self;
 if(!PyArg_ParseTuple(args,"O",&capsule))return NULL;
 s=PyCapsule_GetPointer(capsule,"cdeadmin.sqlite.configuration@1");if(!s)return NULL;
 if(PyThread_tss_get(&pending)==s)PyThread_tss_set(&pending,NULL);
 s->db=NULL;Py_RETURN_NONE;
}
static int code_for(const char *name) {
#ifdef SQLITE_DBCONFIG_STMT_SCANSTATUS
 if(!strcmp(name,"stmt_scanstatus"))return SQLITE_DBCONFIG_STMT_SCANSTATUS;
#endif
#ifdef SQLITE_DBCONFIG_REVERSE_SCANORDER
 if(!strcmp(name,"reverse_scanorder"))return SQLITE_DBCONFIG_REVERSE_SCANORDER;
#endif
#ifdef SQLITE_DBCONFIG_ENABLE_ATTACH_CREATE
 if(!strcmp(name,"enable_attach_create"))return SQLITE_DBCONFIG_ENABLE_ATTACH_CREATE;
#endif
#ifdef SQLITE_DBCONFIG_ENABLE_ATTACH_WRITE
 if(!strcmp(name,"enable_attach_write"))return SQLITE_DBCONFIG_ENABLE_ATTACH_WRITE;
#endif
#ifdef SQLITE_DBCONFIG_ENABLE_COMMENTS
 if(!strcmp(name,"enable_comments"))return SQLITE_DBCONFIG_ENABLE_COMMENTS;
#endif
 return 0;
}
static PyObject *boolean(PyObject *self,PyObject *args) {
 PyObject *capsule;const char *name;int value,code,effective=-1,rc;State *s;(void)self;
 if(!PyArg_ParseTuple(args,"Osi",&capsule,&name,&value))return NULL;
 s=state(capsule);if(!s)return NULL;code=code_for(name);
 if(!code || value < -1 || value > 1){PyErr_SetString(PyExc_ValueError,"Select a named boolean configuration");return NULL;}
 rc=sqlite3_db_config(s->db,code,value,&effective);
 return Py_BuildValue("(ii)",rc,effective);
}
static PyObject *integer_policy(PyObject *self,PyObject *args) {
 PyObject *capsule;int value,rc=SQLITE_ERROR,effective=-1;State *s;(void)self;
 if(!PyArg_ParseTuple(args,"Oi",&capsule,&value))return NULL;
 s=state(capsule);if(!s)return NULL;
 if(value!=0 && (value<3 || value>23)){PyErr_SetString(PyExc_ValueError,"FP_DIGITS requires3–23 significant digits or zero for observation");return NULL;}
#ifdef SQLITE_DBCONFIG_FP_DIGITS
 rc=sqlite3_db_config(s->db,SQLITE_DBCONFIG_FP_DIGITS,value,&effective);
#endif
 return Py_BuildValue("(ii)",rc,effective);
}
static PyObject *alias(PyObject *self,PyObject *args) {
 PyObject *capsule;const char *text;Py_ssize_t length;Name *name;State *s;int rc;(void)self;
 if(!PyArg_ParseTuple(args,"Os#",&capsule,&text,&length))return NULL;
 s=state(capsule);if(!s)return NULL;
 if(length<1 || length>1024 || strlen(text)!=(size_t)length || s->aliases>=32){PyErr_SetString(PyExc_ValueError,"Main schema alias must be bounded text; maximum32 changes per connection");return NULL;}
 name=calloc(1,sizeof(*name));if(!name)return PyErr_NoMemory();name->value=sqlite3_mprintf("%s",text);
 if(!name->value){free(name);return PyErr_NoMemory();}
 rc=sqlite3_db_config(s->db,SQLITE_DBCONFIG_MAINDBNAME,name->value);
 if(rc==SQLITE_OK){name->next=s->names;s->names=name;s->aliases++;}else{sqlite3_free(name->value);free(name);}
 return PyLong_FromLong(rc);
}
static PyObject *lookaside(PyObject *self,PyObject *args) {
 PyObject *capsule;int size,count,rc;State *s;(void)self;
 if(!PyArg_ParseTuple(args,"Oii",&capsule,&size,&count))return NULL;
 s=state(capsule);if(!s)return NULL;
 if(size<0 || size>65528 || size%8 || count<0 || (sqlite3_int64)size*count>16*1024*1024){PyErr_SetString(PyExc_ValueError,"Select bounded native lookaside slots (multiple of8; total at most16MiB)");return NULL;}
 rc=sqlite3_db_config(s->db,SQLITE_DBCONFIG_LOOKASIDE,NULL,size,count);return PyLong_FromLong(rc);
}
static PyObject *usage(PyObject *self,PyObject *args) {
 PyObject *capsule;int current,high,rc;State *s;(void)self;
 if(!PyArg_ParseTuple(args,"O",&capsule))return NULL;
 s=state(capsule);if(!s)return NULL;
 rc=sqlite3_db_status(s->db,SQLITE_DBSTATUS_LOOKASIDE_USED,&current,&high,0);return Py_BuildValue("(iii)",rc,current,high);
}
static PyObject *closed(PyObject *self,PyObject *args) {
 PyObject *capsule,*owner,*open;State *s;(void)self;
 if(!PyArg_ParseTuple(args,"OO",&capsule,&owner))return NULL;
 s=PyCapsule_GetPointer(capsule,"cdeadmin.sqlite.configuration@1");if(!s)return NULL;
 if(owner!=s->owner_identity){PyErr_SetString(PyExc_RuntimeError,"Close confirmation belongs to another native owner");return NULL;}
 open=native_open_property(owner);
 if(open){Py_DECREF(open);PyErr_SetString(PyExc_RuntimeError,"Close the native owner before releasing configuration storage");return NULL;}
 if(!PyErr_ExceptionMatches(closed_error))return NULL;
 PyErr_Clear();s->db=NULL;s->confirmed_closed=1;
 Name *name=s->names;s->names=NULL;
 while(name){Name *next=name->next;sqlite3_free(name->value);free(name);name=next;}
 Py_RETURN_NONE;
}
static PyObject *identity(PyObject *self,PyObject *args) {
 (void)self;(void)args;
 return Py_BuildValue("{s:i,s:i,s:s,s:s,s:i}","adapter_abi",1,"native_configuration_revision",1,"sqlite_version",sqlite3_libversion(),
  "sqlite_source_id",sqlite3_sourceid(),"header_version_number",SQLITE_VERSION_NUMBER);
}
static int native_threads(void) {
#if defined(__linux__)
 DIR *tasks=opendir("/proc/self/task");struct dirent *entry;int count=0;
 if(!tasks)return -1;
 while((entry=readdir(tasks))!=NULL)if(entry->d_name[0]>='0' && entry->d_name[0]<='9')count++;
 closedir(tasks);return count;
#elif defined(_WIN32)
 HANDLE snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD,0);THREADENTRY32 entry;int count=0;
 if(snapshot==INVALID_HANDLE_VALUE)return -1;
 memset(&entry,0,sizeof(entry));entry.dwSize=sizeof(entry);
 if(!Thread32First(snapshot,&entry)){CloseHandle(snapshot);return -1;}
 do{if(entry.th32OwnerProcessID==GetCurrentProcessId())count++;}while(Thread32Next(snapshot,&entry));
 CloseHandle(snapshot);return count;
#elif defined(__APPLE__)
 thread_act_array_t threads;mach_msg_type_number_t count,index;
 if(task_threads(mach_task_self(),&threads,&count)!=KERN_SUCCESS)return -1;
 for(index=0;index<count;index++)mach_port_deallocate(mach_task_self(),threads[index]);
 vm_deallocate(mach_task_self(),(vm_address_t)threads,sizeof(thread_t)*count);
 return (int)count;
#else
 return -1;
#endif
}
static int pragma_directory(sqlite3 *db,const char *name,const char *schema,const char *value,int apply,PyObject **observed,int *rows) {
 char *source;sqlite3_stmt *statement=NULL;int rc;
 source=apply ? (schema[0] ? sqlite3_mprintf("PRAGMA \"%w\".%s=%Q",schema,name,value) : sqlite3_mprintf("PRAGMA %s=%Q",name,value)) :
  (schema[0] ? sqlite3_mprintf("PRAGMA \"%w\".%s",schema,name) : sqlite3_mprintf("PRAGMA %s",name));
 if(!source)return SQLITE_NOMEM;
 rc=sqlite3_prepare_v2(db,source,-1,&statement,NULL);sqlite3_free(source);
 if(rc==SQLITE_OK && statement){
  while((rc=sqlite3_step(statement))==SQLITE_ROW){
   if(sqlite3_column_count(statement)>0 && !apply){
    const unsigned char *text=sqlite3_column_text(statement,0);(*rows)++;
    Py_XDECREF(*observed);*observed=text ? PyUnicode_FromString((const char*)text) : Py_NewRef(Py_None);
    if(!*observed){sqlite3_finalize(statement);return SQLITE_ERROR;}
   }
  }
  if(rc==SQLITE_DONE)rc=SQLITE_OK;
 }
 if(statement){int final=sqlite3_finalize(statement);if(rc==SQLITE_OK)rc=final;}
 return rc;
}
static PyObject *directory_policy(PyObject *self,PyObject *args) {
 PyObject *capsule,*observed=NULL,*result;const char *name,*schema,*value;int apply,threads,rc,readback=SQLITE_OK,rows=0;State *s;(void)self;
 if(!PyArg_ParseTuple(args,"Osssi",&capsule,&name,&schema,&value,&apply))return NULL;
 s=state(capsule);if(!s)return NULL;
 if((strcmp(name,"temp_store_directory") && strcmp(name,"data_store_directory") && strcmp(name,"lock_proxy_file")) || (apply!=0 && apply!=1)){
  PyErr_SetString(PyExc_ValueError,"Select an admitted directory policy");return NULL;
 }
 threads=native_threads();
 /* Global directory changes are permitted only by the pre-initialization
  * startup path. Thread count alone cannot prove that no other SQLite
  * connections are open, including application/configuration stores. */
 if(apply && strcmp(name,"lock_proxy_file")){
  return Py_BuildValue("{s:i,s:i,s:i,s:O}","native_thread_count",threads,
   "native_dispatched",0,"startup_required",1,"value",Py_None);
 }
 if(!apply){rc=pragma_directory(s->db,name,schema,value,0,&observed,&rows);readback=rc;}
 else{
  rc=pragma_directory(s->db,name,schema,value,1,&observed,&rows);
  if(!PyErr_Occurred())readback=pragma_directory(s->db,name,schema,value,0,&observed,&rows);
 }
 if(PyErr_Occurred()){Py_XDECREF(observed);return NULL;}
 if(!observed)observed=Py_NewRef(Py_None);
 result=Py_BuildValue("{s:i,s:i,s:i,s:i,s:i,s:O}","native_thread_count",threads,"native_dispatched",1,
  "native_result_code",rc,"readback_result_code",readback,"observed_rows",rows,"value",observed);
 Py_DECREF(observed);return result;
}
static int pragma_available(sqlite3 *db,const char *name){
 sqlite3_stmt *statement=NULL;int rc,found=0;
 rc=sqlite3_prepare_v2(db,"PRAGMA pragma_list",-1,&statement,NULL);
 if(rc!=SQLITE_OK || !statement){if(statement)sqlite3_finalize(statement);return -1;}
 while((rc=sqlite3_step(statement))==SQLITE_ROW){
  const unsigned char *text=sqlite3_column_text(statement,0);
  if(text && !strcmp((const char*)text,name))found=1;
 }
 if(rc!=SQLITE_DONE)found=-1;
 rc=sqlite3_finalize(statement);return rc==SQLITE_OK ? found : -1;
}
static PyObject *pragma_names(PyObject *self,PyObject *args){
 PyObject *capsule,*names,*result;sqlite3 *db=NULL;sqlite3_stmt *statement=NULL;int rc,close_code=SQLITE_OK;State *s;(void)self;
 if(!PyArg_ParseTuple(args,"O",&capsule))return NULL;
 s=state(capsule);if(!s)return NULL;
 if(pending_metadata_peer){
  close_code=sqlite3_close(pending_metadata_peer);
  if(close_code!=SQLITE_OK)return Py_BuildValue("{s:i,s:i,s:[],s:i,s:i,s:i}",
   "native_result_code",close_code,"native_probe_closed",0,"names",
   "original_sql_commands_sent",0,"namespace_observed",0,"cleanup_pending",1);
  pending_metadata_peer=NULL;
 }
 names=PyList_New(0);if(!names)return NULL;
 rc=sqlite3_open_v2(":memory:",&db,SQLITE_OPEN_READWRITE|SQLITE_OPEN_CREATE,NULL);
 if(rc==SQLITE_OK)rc=sqlite3_prepare_v2(db,"PRAGMA pragma_list",-1,&statement,NULL);
 if(rc==SQLITE_OK && statement){
  while((rc=sqlite3_step(statement))==SQLITE_ROW){
   const unsigned char *text=sqlite3_column_text(statement,0);PyObject *name;
   if(!text || sqlite3_column_bytes(statement,0)>256 || PyList_GET_SIZE(names)>=1000){rc=SQLITE_TOOBIG;break;}
   name=PyUnicode_FromString((const char*)text);
   if(!name || PyList_Append(names,name)!=0){Py_XDECREF(name);rc=SQLITE_NOMEM;break;}Py_DECREF(name);
  }
  if(rc==SQLITE_DONE)rc=SQLITE_OK;
 }
 if(statement){int final=sqlite3_finalize(statement);if(rc==SQLITE_OK)rc=final;}
 if(db){close_code=sqlite3_close(db);if(close_code!=SQLITE_OK)pending_metadata_peer=db;}
 if(PyErr_Occurred()){Py_DECREF(names);return NULL;}
 result=Py_BuildValue("{s:i,s:i,s:O,s:i,s:i}","native_result_code",rc,"native_probe_closed",close_code==SQLITE_OK,
  "names",names,"original_sql_commands_sent",0,"namespace_observed",rc==SQLITE_OK && PyList_GET_SIZE(names)>0);
 Py_DECREF(names);return result;
}
static PyObject *startup_directories(PyObject *self,PyObject *args){
 PyObject *requested[2],*rows,*result;const char *names[2]={"temp_store_directory","data_store_directory"};
 const char *values[2]={NULL,NULL};int present[2]={-1,-1},threads,index,rc,closed=SQLITE_OK,writes=0,complete=1;
 sqlite3_mem_methods allocator;sqlite3 *db=NULL;(void)self;
 if(!PyArg_ParseTuple(args,"OO",&requested[0],&requested[1]))return NULL;
 for(index=0;index<2;index++)if(requested[index]!=Py_None){
  Py_ssize_t length;values[index]=PyUnicode_AsUTF8AndSize(requested[index],&length);
  if(!values[index])return NULL;
  if(length>1048576 || strlen(values[index])!=(size_t)length){PyErr_SetString(PyExc_ValueError,"Startup directory must be bounded UTF-8 without NUL");return NULL;}
 }
 threads=native_threads();
 if(threads!=1)return Py_BuildValue("{s:i,s:i,s:i,s:s}","complete",0,"native_thread_count",threads,"native_global_writes_attempted",0,"outcome","exclusive_startup_host_required");
 memset(&allocator,0,sizeof(allocator));
 /* GETMALLOC opens no database and preserves a selected allocator. It may
  * establish the implicit default allocator. SQLite refuses it
  * once initialized. This establishes that no old database handles exist;
  * a thread count alone would not establish that prerequisite. */
 rc=sqlite3_config(SQLITE_CONFIG_GETMALLOC,&allocator);
 if(rc!=SQLITE_OK)return Py_BuildValue("{s:i,s:i,s:i,s:i,s:s}","complete",0,"native_thread_count",threads,"native_result_code",rc,"native_global_writes_attempted",0,"outcome","sqlite_already_initialized");
 rc=sqlite3_open_v2(":memory:",&db,SQLITE_OPEN_READWRITE|SQLITE_OPEN_CREATE,NULL);
 rows=PyList_New(0);if(!rows){if(db)sqlite3_close(db);return NULL;}
 threads=native_threads();
 if(rc!=SQLITE_OK || threads!=1){complete=0;goto finish;}
 /* Admit the complete request before either global policy is written. */
 for(index=0;index<2;index++){
  present[index]=pragma_available(db,names[index]);
  if(values[index] && present[index]!=1)complete=0;
 }
 if(!complete)goto finish;
 for(index=0;index<2;index++){
  PyObject *before=NULL,*after=NULL,*row;int before_rows=0,after_rows=0,readback=SQLITE_OK,write_code=SQLITE_OK,attempted=0,after_observed=0;
  if(present[index]!=1){
   row=Py_BuildValue("{s:s,s:i,s:i}","pragma",names[index],"native_name_present",0,"setter_dispatched",0);
  }else{
   rc=pragma_directory(db,names[index],"","",0,&before,&before_rows);
   if(PyErr_Occurred()){PyErr_Clear();complete=0;}
   if(rc!=SQLITE_OK)complete=0;
   if(complete && values[index]){
    attempted=1;writes++;write_code=pragma_directory(db,names[index],"",values[index],1,&after,&after_rows);
    if(PyErr_Occurred()){PyErr_Clear();complete=0;}
    if(write_code!=SQLITE_OK)complete=0;
   }
   if(complete){readback=pragma_directory(db,names[index],"","",0,&after,&after_rows);if(PyErr_Occurred()){PyErr_Clear();complete=0;}if(readback!=SQLITE_OK)complete=0;else if(complete)after_observed=1;}
   if(!before)before=Py_NewRef(Py_None);
   if(!after)after=Py_NewRef(Py_None);
   if(complete && values[index]){
    PyObject *expected=values[index][0] ? requested[index] : Py_None;
    int equal=PyObject_RichCompareBool(after,expected,Py_EQ);
    if(equal!=1){if(equal<0)PyErr_Clear();complete=0;}
   }
   row=Py_BuildValue("{s:s,s:i,s:O,s:O,s:i,s:i,s:i,s:i,s:i,s:i,s:i}","pragma",names[index],"native_name_present",1,
    "before_value",before,"effective_value",after,"before_rows",before_rows,"after_rows",after_rows,
    "setter_dispatched",attempted,"native_result_code",write_code,"readback_result_code",readback,
    "before_observation_confirmed",rc==SQLITE_OK,"after_observation_confirmed",after_observed);
   Py_DECREF(before);Py_DECREF(after);
  }
  if(!row || PyList_Append(rows,row)!=0){Py_XDECREF(row);complete=0;break;}Py_DECREF(row);
  if(!complete)break;
 }
 finish:
 if(db)closed=sqlite3_close(db);
 if(closed!=SQLITE_OK)complete=0;
 if(PyErr_Occurred()){Py_DECREF(rows);return NULL;}
 result=Py_BuildValue("{s:i,s:i,s:i,s:i,s:i,s:i,s:O,s:s}","complete",complete,"native_thread_count",threads,
  "runtime_was_uninitialized",1,"native_global_writes_attempted",writes,"native_owned_database_closed",closed==SQLITE_OK,
  "native_close_result_code",closed,"settings",rows,"outcome",complete ? "native_startup_configuration_observed" : "native_startup_configuration_not_confirmed");
 if(result){
  PyObject *availability=Py_BuildValue("{s:i,s:i}",names[0],present[0],names[1],present[1]);
  if(!availability || PyDict_SetItemString(result,"native_pragma_availability",availability)!=0){Py_XDECREF(availability);Py_DECREF(result);result=NULL;}
  else Py_DECREF(availability);
 }
 Py_DECREF(rows);return result;
}
static PyObject *stop_capture(PyObject *self,PyObject *args){
 (void)self;(void)args;
 if(PyThread_tss_is_created(&pending) && PyThread_tss_get(&pending))Py_RETURN_FALSE;
 if(pending_metadata_peer){
  if(sqlite3_close(pending_metadata_peer)!=SQLITE_OK)Py_RETURN_FALSE;
  pending_metadata_peer=NULL;
 }
 if(capture_registered){sqlite3_cancel_auto_extension((void(*)(void))sqlite3_cdeadminconfig_init);capture_registered=0;}
 Py_RETURN_TRUE;
}
static PyObject *describe_statement(PyObject *self, PyObject *args) {
 PyObject *capsule, *columns=NULL, *parameters=NULL, *result=NULL;
 const char *sql, *tail=NULL;
 Py_ssize_t length;
 sqlite3_stmt *statement=NULL;
 State *s;
 int rc, count, index;
 (void)self;
 if(!PyArg_ParseTuple(args,"Os#",&capsule,&sql,&length))return NULL;
 if(length<1 || length>=INT_MAX || memchr(sql,0,(size_t)length)){
  PyErr_SetString(PyExc_ValueError,"Valid SQLite statement source is required");
  return NULL;
 }
 s=state(capsule);
 if(!s)return NULL;
 Py_BEGIN_ALLOW_THREADS
 rc=sqlite3_prepare_v2(s->db,sql,(int)length+1,&statement,&tail);
 Py_END_ALLOW_THREADS
 if(rc!=SQLITE_OK || !statement){
  PyErr_SetString(PyExc_ValueError,rc==SQLITE_OK ? "Select one SQLite statement to prepare" : sqlite3_errmsg(s->db));
  goto finish;
 }
 count=sqlite3_column_count(statement);
 columns=PyList_New(count);
 if(!columns)goto finish;
 for(index=0;index<count;index++){
  const char *name=sqlite3_column_name(statement,index);
  const char *type=sqlite3_column_decltype(statement,index);
  PyObject *field;
  if(!name){PyErr_NoMemory();goto finish;}
  field=Py_BuildValue("{s:i,s:s,s:s}","position",index+1,"name",name,"native_type",type ? type : "");
  if(!field)goto finish;
  PyList_SET_ITEM(columns,index,field);
 }
 count=sqlite3_bind_parameter_count(statement);
 parameters=PyList_New(count);
 if(!parameters)goto finish;
 for(index=0;index<count;index++){
  const char *name=sqlite3_bind_parameter_name(statement,index+1);
  PyObject *slot=Py_BuildValue("{s:i,s:s}","position",index+1,"name",name ? name : "");
  if(!slot)goto finish;
  PyList_SET_ITEM(parameters,index,slot);
 }
 result=Py_BuildValue("(OOs)",columns,parameters,tail);
finish:
 sqlite3_finalize(statement);
 Py_XDECREF(columns);
 Py_XDECREF(parameters);
 return result;
}
static PyMethodDef methods[]={{"describe_statement",describe_statement,METH_VARARGS,NULL},{"stop_capture",stop_capture,METH_NOARGS,NULL},{"pragma_names",pragma_names,METH_VARARGS,NULL},{"startup_directories",startup_directories,METH_VARARGS,NULL},{"directory",directory_policy,METH_VARARGS,NULL},{"identity",identity,METH_NOARGS,NULL},{"begin",begin_open,METH_NOARGS,NULL},{"finish",finish_open,METH_VARARGS,NULL},{"cancel",cancel_open,METH_VARARGS,NULL},{"boolean",boolean,METH_VARARGS,NULL},{"integer",integer_policy,METH_VARARGS,NULL},{"alias",alias,METH_VARARGS,NULL},{"lookaside",lookaside,METH_VARARGS,NULL},{"usage",usage,METH_VARARGS,NULL},{"closed",closed,METH_VARARGS,NULL},{NULL,NULL,0,NULL}};
static struct PyModuleDef module={PyModuleDef_HEAD_INIT,
 .m_name="_cdeadmin_dbconfig",.m_size=-1,.m_methods=methods
};
static int initialize_capture(void){
 PyObject *native,*type,*error,*descriptor;
 if(!connection_type){
  native=PyImport_ImportModule("_sqlite3");if(!native)return -1;
  type=PyObject_GetAttrString(native,"Connection");
  error=type ? PyObject_GetAttrString(native,"ProgrammingError") : NULL;Py_DECREF(native);
  descriptor=error ? PyObject_GetAttrString(type,"in_transaction") : NULL;
  if(!descriptor){Py_XDECREF(type);Py_XDECREF(error);return -1;}
  connection_type=type;closed_error=error;transaction_descriptor=descriptor;
 }
 if(!capture_registered){
  if(sqlite3_auto_extension((void(*)(void))sqlite3_cdeadminconfig_init)!=SQLITE_OK){
   PyErr_SetString(PyExc_ImportError,"Native configuration capture registration failed");return -1;
  }
  capture_registered=1;
 }
 return 0;
}
PyMODINIT_FUNC PyInit__cdeadmin_dbconfig(void){
 /* Deliberately leave SQLite uninitialized: host startup policies run before
  * importing _sqlite3 or registering any extension. begin() initializes the
  * ordinary original-handle capture lazily afterwards. */
 return PyModule_Create(&module);
}
