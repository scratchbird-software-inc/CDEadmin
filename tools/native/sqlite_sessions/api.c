/* Public SQLite session APIs on the same library and connection as the driver.
 * The application owns the capability, session lifetime, destination descriptors
 * and cancellation pipe. No CPython connection/statement layout is accessed. */
#include <sqlite3ext.h>
#include "../sqlite_hook_ownership.h"
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <io.h>
#include <windows.h>
#else
#include <poll.h>
#include <unistd.h>
#endif

typedef struct Capture Capture;
struct Capture { char *id; sqlite3_session *session; Capture *next; char *filter_pattern; int filter_exclude; };
typedef struct State State;
struct State { sqlite3 *db; unsigned char capability[32]; int bound, refs; Capture *captures; };
typedef struct Output Output;
struct Output { int descriptor, cancel; sqlite3_int64 bytes; };

static void close_all(State *state){
  Capture *capture=state->captures;
  while(capture){
    Capture *next=capture->next;
    sqlite3session_delete(capture->session);
    sqlite3_free(capture->filter_pattern);sqlite3_free(capture->id);sqlite3_free(capture);capture=next;
  }
  state->captures=0;sqlite3_set_clientdata(state->db,CDEADMIN_SESSION_ACTIVE,0,0);
}

static void release_state(void *opaque){
  State *state=(State*)opaque;
  if(--state->refs==0){
    /* The driver must close all native sessions before sqlite3_close(), as
     * required by SQLite. This destructor releases only adapter allocations. */
    memset(state->capability,0,sizeof(state->capability));sqlite3_free(state);
  }
}

static void fail(sqlite3_context *context,int code,const char *message){
  /* Returning INTERRUPT/IOERR as the surrounding SQL VM's result can roll
   * back the user's transaction. Preserve the native API result as data. */
  sqlite3_str *builder=sqlite3_str_new(sqlite3_context_db_handle(context));
  const unsigned char *cursor=(const unsigned char*)message;char *result;
  sqlite3_str_appendf(builder,"{\"native_result_code\":%d,\"message\":\"",code);
  for(;*cursor;cursor++){
    if(*cursor=='"' || *cursor=='\\'){sqlite3_str_appendchar(builder,1,'\\');sqlite3_str_appendchar(builder,1,(char)*cursor);}
    else if(*cursor<32)sqlite3_str_appendf(builder,"\\u%04x",(unsigned int)*cursor);
    else sqlite3_str_appendchar(builder,1,(char)*cursor);
  }
  sqlite3_str_appendall(builder,"\"}");result=sqlite3_str_finish(builder);
  if(!result)sqlite3_result_error_nomem(context);else sqlite3_result_text(context,result,-1,sqlite3_free);
}

static int admitted(State *state,sqlite3_value *value){
  const unsigned char *bytes=sqlite3_value_blob(value);unsigned char different=0;int index;
  if(!state->bound || sqlite3_value_type(value)!=SQLITE_BLOB || sqlite3_value_bytes(value)!=32 || !bytes)return 0;
  for(index=0;index<32;index++)different|=(unsigned char)(bytes[index]^state->capability[index]);
  return different==0;
}

static const char *text(sqlite3_value *value){
  const char *result=(const char*)sqlite3_value_text(value);
  return result && sqlite3_value_type(value)==SQLITE_TEXT &&
    strlen(result)==(size_t)sqlite3_value_bytes(value) ? result : 0;
}

static void bind_capability(sqlite3_context *context,int count,sqlite3_value **values){
  State *state=(State*)sqlite3_user_data(context);const void *value;
  (void)count;
  if(state->bound || sqlite3_value_type(values[0])!=SQLITE_BLOB || sqlite3_value_bytes(values[0])!=32){
    fail(context,SQLITE_AUTH,"Native session capability is unavailable");return;
  }
  value=sqlite3_value_blob(values[0]);if(!value){sqlite3_result_error_nomem(context);return;}
  memcpy(state->capability,value,32);state->bound=1;sqlite3_result_int(context,1);
}

static int cancelled(int descriptor){
  if(descriptor<0)return 0;
#ifdef _WIN32
  { DWORD available=0;
    HANDLE handle=(HANDLE)_get_osfhandle(descriptor);
    return handle==INVALID_HANDLE_VALUE || !PeekNamedPipe(handle,0,0,0,&available,0) || available>0;
  }
#else
  { struct pollfd item;int result;
    item.fd=descriptor;item.events=POLLIN;item.revents=0;
    do{result=poll(&item,1,0);}while(result<0 && errno==EINTR);
    return result<0 || (result>0 && item.revents!=0);
  }
#endif
}

static int output(void *opaque,const void *data,int length){
  Output *target=(Output*)opaque;const unsigned char *bytes=(const unsigned char*)data;
  while(length>0){
    int chunk=length>1048576 ? 1048576 : length;
    if(cancelled(target->cancel))return SQLITE_INTERRUPT;
#ifdef _WIN32
    { int written=_write(target->descriptor,bytes,(unsigned int)chunk);
#else
    { ssize_t written=write(target->descriptor,bytes,(size_t)chunk);
#endif
      if(written<0 && errno==EINTR)continue;
      if(written<=0)return SQLITE_IOERR_WRITE;
      target->bytes+=written;bytes+=written;length-=(int)written;
    }
  }
  return SQLITE_OK;
}

static int input(void *opaque,void *data,int *length){
  Output *source=(Output*)opaque;
  if(cancelled(source->cancel))return SQLITE_INTERRUPT;
  for(;;){
#ifdef _WIN32
    int received=_read(source->descriptor,data,(unsigned int)*length);
#else
    ssize_t received=read(source->descriptor,data,(size_t)*length);
#endif
    if(received<0 && errno==EINTR)continue;
    if(received<0)return SQLITE_IOERR_READ;
    *length=(int)received;source->bytes+=received;return SQLITE_OK;
  }
}

static void inspect_changeset(sqlite3_context *context,sqlite3_value **values,const char *selected){
  sqlite3_int64 descriptor=sqlite3_value_int64(values[2]),cancel=sqlite3_value_int64(values[3]),rows=0,selected_rows=0;
  sqlite3_changeset_iter *iterator=0;Output source;int result,finished;
  if(descriptor<0 || descriptor>INT_MAX || cancel<-1 || cancel>INT_MAX){fail(context,SQLITE_MISUSE,"Select owned native changeset input descriptors");return;}
  source.descriptor=(int)descriptor;source.cancel=(int)cancel;source.bytes=0;
  result=sqlite3changeset_start_v2_strm(&iterator,input,&source,0);
  if(result==SQLITE_OK){
    while((result=sqlite3changeset_next(iterator))==SQLITE_ROW){
      if(cancelled(source.cancel)){result=SQLITE_INTERRUPT;break;}
      rows++;
      if(!selected)selected_rows++;
      else{
        const char *table=0;int columns=0,operation=0,indirect=0;
        result=sqlite3changeset_op(iterator,&table,&columns,&operation,&indirect);
        if(result!=SQLITE_OK)break;
        if(strcmp(table,selected)==0)selected_rows++;
      }
    }
    finished=sqlite3changeset_finalize(iterator);
    if(result==SQLITE_DONE)result=finished;
  }
  if(result!=SQLITE_OK){fail(context,result,"Native changeset iterator did not reach a complete stream");return;}
  {
    char *metadata=sqlite3_mprintf("{\"native_record_count\":\"%lld\",\"native_selected_record_count\":\"%lld\",\"native_bytes_read\":\"%lld\",\"native_iterator_complete\":true}",rows,selected_rows,source.bytes);
    if(!metadata)sqlite3_result_error_nomem(context);else sqlite3_result_text(context,metadata,-1,sqlite3_free);
  }
}

/* Typed file inspection uses only protected public iterator values. Byte
 * previews do not invent missing old values or native column names. */
static void inspection_hex(sqlite3_str *builder,const void *data,int length){
  const char digits[]="0123456789ABCDEF";const unsigned char *bytes=data;int index;
  sqlite3_str_appendchar(builder,1,'"');
  for(index=0;index<length;index++){char pair[2];pair[0]=digits[bytes[index]>>4];pair[1]=digits[bytes[index]&15];sqlite3_str_append(builder,pair,2);}
  sqlite3_str_appendchar(builder,1,'"');
}
static int inspection_value(sqlite3_str *builder,sqlite3_value *value,sqlite3_int64 offset,int maximum){
  int kind,length,take;const void *data;
  if(!value){if(offset)return SQLITE_RANGE;sqlite3_str_appendall(builder,"{\"native_type\":\"undefined\"}");return SQLITE_OK;}
  kind=sqlite3_value_type(value);
  if(kind==SQLITE_NULL){if(offset)return SQLITE_RANGE;sqlite3_str_appendall(builder,"{\"native_type\":\"null\",\"data\":null}");return SQLITE_OK;}
  if(kind==SQLITE_INTEGER){if(offset)return SQLITE_RANGE;sqlite3_str_appendf(builder,"{\"native_type\":\"integer\",\"data\":\"%lld\"}",sqlite3_value_int64(value));return SQLITE_OK;}
  if(kind==SQLITE_FLOAT){if(offset)return SQLITE_RANGE;sqlite3_str_appendf(builder,"{\"native_type\":\"real\",\"data\":\"%!.17g\"}",sqlite3_value_double(value));return SQLITE_OK;}
  data=kind==SQLITE_TEXT ? (const void*)sqlite3_value_text(value) : sqlite3_value_blob(value);length=sqlite3_value_bytes(value);
  if(length && !data)return SQLITE_NOMEM;
  if(offset>length)return SQLITE_RANGE;
  take=length-(int)offset;if(take>maximum)take=maximum;
  sqlite3_str_appendf(builder,"{\"native_type\":\"%s\",\"byte_length\":\"%d\",\"byte_offset\":\"%lld\",\"preview_byte_length\":\"%d\",\"truncated\":%s,\"hex\":",kind==SQLITE_TEXT?"text":"blob",length,offset,take,offset+take<length?"true":"false");
  inspection_hex(builder,offset ? (const unsigned char*)data+(size_t)offset : data,take);sqlite3_str_appendchar(builder,1,'}');return SQLITE_OK;
}
static int inspection_row(sqlite3_str *builder,sqlite3_changeset_iter *iterator,sqlite3_int64 number,int preview,int budget,int cancel){
  const char *table=0;unsigned char *primary=0;int columns,operation,indirect,primary_columns,index,side,result;
  result=sqlite3changeset_op(iterator,&table,&columns,&operation,&indirect);
  if(result==SQLITE_OK)result=sqlite3changeset_pk(iterator,&primary,&primary_columns);
  if(result!=SQLITE_OK)return result;
  if(columns!=primary_columns || columns<1)return SQLITE_CORRUPT;
  sqlite3_str_appendf(builder,"{\"record_number\":\"%lld\",\"operation\":\"%s\",\"column_count\":%d,\"indirect\":%s,\"table_hex\":",number,operation==SQLITE_INSERT?"insert":operation==SQLITE_UPDATE?"update":"delete",columns,indirect?"true":"false");
  if((sqlite3_int64)strlen(table)*2+sqlite3_str_length(builder)>budget)return SQLITE_TOOBIG;
  inspection_hex(builder,table,(int)strlen(table));sqlite3_str_appendall(builder,",\"primary_key\":[");
  if((sqlite3_int64)columns*4+sqlite3_str_length(builder)>budget)return SQLITE_TOOBIG;
  for(index=0;index<columns;index++){if(index)sqlite3_str_appendchar(builder,1,',');sqlite3_str_appendf(builder,"%d",primary[index]);}
  sqlite3_str_appendchar(builder,1,']');
  for(side=0;side<2;side++){
    sqlite3_str_appendall(builder,side ? ",\"new_values\":" : ",\"old_values\":");
    if((!side && operation==SQLITE_INSERT) || (side && operation==SQLITE_DELETE)){sqlite3_str_appendall(builder,"null");continue;}
    sqlite3_str_appendchar(builder,1,'[');
    for(index=0;index<columns;index++){
      sqlite3_value *value=0;if(cancelled(cancel))return SQLITE_INTERRUPT;
      if(index)sqlite3_str_appendchar(builder,1,',');
      result=side ? sqlite3changeset_new(iterator,index,&value) : sqlite3changeset_old(iterator,index,&value);
      if(result==SQLITE_OK)result=inspection_value(builder,value,0,preview);
      if(result!=SQLITE_OK)return result;
      if(sqlite3_str_length(builder)>budget)return SQLITE_TOOBIG;
      if(sqlite3_str_errcode(builder)!=SQLITE_OK)return sqlite3_str_errcode(builder);
    }
    sqlite3_str_appendchar(builder,1,']');
  }
  sqlite3_str_appendchar(builder,1,'}');return SQLITE_OK;
}
static void inspect_page(sqlite3_context *context,sqlite3_value **values){
  sqlite3_int64 fd=sqlite3_value_int64(values[2]),cancel=sqlite3_value_int64(values[3]),offset=sqlite3_value_int64(values[4]),number=0;
  int limit=sqlite3_value_int(values[5]),preview=sqlite3_value_int(values[6]),budget=sqlite3_value_int(values[7]),written=0,more=0,complete=0,result,finished;
  sqlite3_changeset_iter *iterator=0;Output source;sqlite3_str *builder;char *json;
  if(fd<0 || fd>INT_MAX || cancel<-1 || cancel>INT_MAX || offset<0 || limit<1 || limit>100 || preview<0 || preview>65536 || budget<1 || budget>16777216){fail(context,SQLITE_MISUSE,"Select bounded native inspection descriptors and page limits");return;}
  source.descriptor=(int)fd;source.cancel=(int)cancel;source.bytes=0;builder=sqlite3_str_new(sqlite3_context_db_handle(context));sqlite3_str_appendall(builder,"{\"rows\":[");
  result=sqlite3changeset_start_v2_strm(&iterator,input,&source,0);
  while(result==SQLITE_OK && (result=sqlite3changeset_next(iterator))==SQLITE_ROW){
    if(cancelled(source.cancel)){result=SQLITE_INTERRUPT;break;}
    if(number==LLONG_MAX){result=SQLITE_FULL;break;}
    number++;
    if(number<=offset){result=SQLITE_OK;continue;}
    if(written==limit){more=1;result=SQLITE_OK;break;}
    if(written)sqlite3_str_appendchar(builder,1,',');
    result=inspection_row(builder,iterator,number,preview,budget,source.cancel);if(result!=SQLITE_OK)break;written++;
  }
  if(result==SQLITE_DONE){complete=1;result=SQLITE_OK;}
  if(iterator){finished=sqlite3changeset_finalize(iterator);if(result==SQLITE_OK)result=finished;}
  if(result==SQLITE_OK){sqlite3_str_appendf(builder,"],\"offset\":\"%lld\",\"rows_returned\":%d,\"native_rows_visited\":\"%lld\",\"native_bytes_read\":\"%lld\",\"more\":%s,\"native_iterator_complete\":%s}",offset,written,number,source.bytes,more?"true":"false",complete?"true":"false");result=sqlite3_str_errcode(builder);if(result==SQLITE_OK && sqlite3_str_length(builder)>budget)result=SQLITE_TOOBIG;}
  json=sqlite3_str_finish(builder);if(!json && result==SQLITE_OK)result=SQLITE_NOMEM;
  if(result!=SQLITE_OK){sqlite3_free(json);fail(context,result,"Native inspection did not produce a complete bounded page");return;}
  sqlite3_result_text(context,json,-1,sqlite3_free);
}
static void inspect_cell(sqlite3_context *context,sqlite3_value **values){
  sqlite3_int64 fd=sqlite3_value_int64(values[2]),cancel=sqlite3_value_int64(values[3]),wanted=sqlite3_value_int64(values[4]),offset=sqlite3_value_int64(values[7]),number=0;
  int column=sqlite3_value_int(values[5]),side=sqlite3_value_int(values[6]),maximum=sqlite3_value_int(values[8]),result,finished,found=0;
  sqlite3_changeset_iter *iterator=0;sqlite3_str *builder;Output source;char *json;
  if(fd<0 || fd>INT_MAX || cancel<-1 || cancel>INT_MAX || wanted<1 || column<0 || (side!=0 && side!=1) || offset<0 || maximum<1 || maximum>65536){fail(context,SQLITE_MISUSE,"Select an exact native record, column, side and bounded byte range");return;}
  source.descriptor=(int)fd;source.cancel=(int)cancel;source.bytes=0;builder=sqlite3_str_new(sqlite3_context_db_handle(context));
  result=sqlite3changeset_start_v2_strm(&iterator,input,&source,0);
  while(result==SQLITE_OK && (result=sqlite3changeset_next(iterator))==SQLITE_ROW){
    const char *table;int columns,operation,indirect;sqlite3_value *value=0;
    if(cancelled(source.cancel)){result=SQLITE_INTERRUPT;break;}
    if(number==LLONG_MAX){result=SQLITE_FULL;break;}number++;
    if(number!=wanted){result=SQLITE_OK;continue;}
    result=sqlite3changeset_op(iterator,&table,&columns,&operation,&indirect);
    if(result==SQLITE_OK && (column>=columns || (!side && operation==SQLITE_INSERT) || (side && operation==SQLITE_DELETE)))result=SQLITE_RANGE;
    if(result==SQLITE_OK)result=side ? sqlite3changeset_new(iterator,column,&value) : sqlite3changeset_old(iterator,column,&value);
    if(result==SQLITE_OK)result=inspection_value(builder,value,offset,maximum);
    found=result==SQLITE_OK;break;
  }
  if(result==SQLITE_DONE)result=SQLITE_NOTFOUND;
  if(iterator){finished=sqlite3changeset_finalize(iterator);if(result==SQLITE_OK)result=finished;}
  if(result==SQLITE_OK && !found)result=SQLITE_NOTFOUND;
  if(result==SQLITE_OK)result=sqlite3_str_errcode(builder);
  json=sqlite3_str_finish(builder);if(!json && result==SQLITE_OK)result=SQLITE_NOMEM;
  if(result!=SQLITE_OK){sqlite3_free(json);fail(context,result,"Native cell inspection did not produce the selected value");return;}
  sqlite3_result_text(context,json,-1,sqlite3_free);
}

static void extract_cell(sqlite3_context *context,sqlite3_value **values){
  sqlite3_int64 fd=sqlite3_value_int64(values[2]),cancel=sqlite3_value_int64(values[3]),wanted=sqlite3_value_int64(values[4]),outfd=sqlite3_value_int64(values[7]),number=0;
  int column=sqlite3_value_int(values[5]),side=sqlite3_value_int(values[6]),result,finished,found=0,kind=0,length=0;
  sqlite3_changeset_iter *iterator=0;Output source,target;
  if(fd<0 || fd>INT_MAX || cancel<-1 || cancel>INT_MAX || wanted<1 || column<0 || (side!=0 && side!=1) || outfd<0 || outfd>INT_MAX || outfd==fd){fail(context,SQLITE_MISUSE,"Select an exact native byte value and separate owned output descriptor");return;}
  source.descriptor=(int)fd;source.cancel=(int)cancel;source.bytes=0;target.descriptor=(int)outfd;target.cancel=(int)cancel;target.bytes=0;
  result=sqlite3changeset_start_v2_strm(&iterator,input,&source,0);
  while(result==SQLITE_OK && (result=sqlite3changeset_next(iterator))==SQLITE_ROW){
    const char *table;int columns,operation,indirect;sqlite3_value *value=0;const void *data;
    if(cancelled(source.cancel)){result=SQLITE_INTERRUPT;break;}
    if(number==LLONG_MAX){result=SQLITE_FULL;break;}number++;
    if(number!=wanted){result=SQLITE_OK;continue;}
    result=sqlite3changeset_op(iterator,&table,&columns,&operation,&indirect);
    if(result==SQLITE_OK && (column>=columns || (!side && operation==SQLITE_INSERT) || (side && operation==SQLITE_DELETE)))result=SQLITE_RANGE;
    if(result==SQLITE_OK)result=side ? sqlite3changeset_new(iterator,column,&value) : sqlite3changeset_old(iterator,column,&value);
    if(result==SQLITE_OK){kind=value ? sqlite3_value_type(value) : 0;if(kind!=SQLITE_TEXT && kind!=SQLITE_BLOB)result=SQLITE_MISMATCH;}
    if(result==SQLITE_OK){data=kind==SQLITE_TEXT ? (const void*)sqlite3_value_text(value) : sqlite3_value_blob(value);length=sqlite3_value_bytes(value);result=length && !data ? SQLITE_NOMEM : output(&target,data,length);}
    found=result==SQLITE_OK;break;
  }
  if(result==SQLITE_DONE)result=SQLITE_NOTFOUND;
  if(iterator){finished=sqlite3changeset_finalize(iterator);if(result==SQLITE_OK)result=finished;}
  if(result==SQLITE_OK && !found)result=SQLITE_NOTFOUND;
  if(result!=SQLITE_OK){fail(context,result,"Native byte-value extraction did not complete");return;}
  {char *json=sqlite3_mprintf("{\"native_type\":\"%s\",\"record_number\":\"%lld\",\"column_index\":%d,\"side\":\"%s\",\"byte_length\":\"%d\",\"native_written_bytes\":\"%lld\",\"native_bytes_read\":\"%lld\",\"native_iterator_complete\":false}",kind==SQLITE_TEXT?"text":"blob",wanted,column,side?"new":"old",length,target.bytes,source.bytes);if(!json)fail(context,SQLITE_NOMEM,"Native extraction acknowledgement allocation failed");else sqlite3_result_text(context,json,-1,sqlite3_free);}
}

typedef struct Apply Apply;
struct Apply { int choices[6],cancel;sqlite3_int64 conflicts[6],seen,included;const char *table; };

static int apply_filter(void *opaque,sqlite3_changeset_iter *iterator){
  Apply *apply=(Apply*)opaque;const char *table=0;int columns=0,operation=0,indirect=0;
  apply->seen++;
  if(sqlite3changeset_op(iterator,&table,&columns,&operation,&indirect)!=SQLITE_OK)return 0;
  if(apply->table && strcmp(apply->table,table)!=0)return 0;
  apply->included++;return 1;
}

static int apply_conflict(void *opaque,int kind,sqlite3_changeset_iter *iterator){
  Apply *apply=(Apply*)opaque;(void)iterator;
  if(kind<1 || kind>5)return SQLITE_CHANGESET_ABORT;
  apply->conflicts[kind]++;
  return cancelled(apply->cancel) ? SQLITE_CHANGESET_ABORT : apply->choices[kind];
}

static void apply_changeset(sqlite3_context *context,State *state,sqlite3_value **values){
  sqlite3_int64 descriptor=sqlite3_value_int64(values[2]),cancel=sqlite3_value_int64(values[3]),rebase_descriptor=sqlite3_value_int64(values[10]);
  int flags=sqlite3_value_int(values[4]),result,rebase_size=0,write_result=SQLITE_OK,index;void *rebase=0;Output source,target;Apply apply;char *metadata;
  memset(&apply,0,sizeof(apply));
  if(descriptor<0 || descriptor>INT_MAX || cancel<-1 || cancel>INT_MAX || rebase_descriptor<-1 || rebase_descriptor>INT_MAX ||
      !(flags&SQLITE_CHANGESETAPPLY_NOSAVEPOINT) || (flags&~15) || sqlite3_get_autocommit(state->db)){
    fail(context,SQLITE_MISUSE,"Native apply requires owned descriptors and an application-owned savepoint");return;
  }
  apply.cancel=(int)cancel;
  for(index=1;index<=5;index++){
    int choice=sqlite3_value_int(values[index+4]);
    if(choice<SQLITE_CHANGESET_OMIT || choice>SQLITE_CHANGESET_ABORT ||
        (choice==SQLITE_CHANGESET_REPLACE && index!=SQLITE_CHANGESET_DATA && index!=SQLITE_CHANGESET_CONFLICT)){
      fail(context,SQLITE_MISUSE,"Native conflict replacement is valid only for DATA or CONFLICT");return;
    }
    apply.choices[index]=choice;
  }
  if(sqlite3_value_type(values[11])!=SQLITE_NULL){
    apply.table=text(values[11]);if(!apply.table || !*apply.table){fail(context,SQLITE_MISUSE,"Select an exact native table filter or all tables");return;}
  }
  source.descriptor=(int)descriptor;source.cancel=(int)cancel;source.bytes=0;
  target.descriptor=(int)rebase_descriptor;target.cancel=(int)cancel;target.bytes=0;
  result=cancelled(source.cancel) ? SQLITE_INTERRUPT : sqlite3changeset_apply_v3_strm(state->db,input,&source,apply_filter,apply_conflict,&apply,
      rebase_descriptor<0 ? 0 : &rebase,rebase_descriptor<0 ? 0 : &rebase_size,flags);
  if(result==SQLITE_OK && rebase_size>0)write_result=output(&target,rebase,rebase_size);
  sqlite3_free(rebase);
  metadata=sqlite3_mprintf("{\"native_apply_result_code\":%d,\"rebase_output_result_code\":%d,\"native_bytes_read\":\"%lld\",\"native_changes_seen\":\"%lld\",\"native_changes_included\":\"%lld\",\"native_rebase_bytes\":\"%lld\",\"conflicts\":{\"data\":\"%lld\",\"not_found\":\"%lld\",\"conflict\":\"%lld\",\"constraint\":\"%lld\",\"foreign_key\":\"%lld\"}}",
      result,write_result,source.bytes,apply.seen,apply.included,target.bytes,apply.conflicts[1],apply.conflicts[2],apply.conflicts[3],apply.conflicts[4],apply.conflicts[5]);
  if(!metadata)sqlite3_result_error_nomem(context);else sqlite3_result_text(context,metadata,-1,sqlite3_free);
}

static int rewind_input(int descriptor,sqlite3_int64 *length){
#ifdef _WIN32
  sqlite3_int64 size=_lseeki64(descriptor,0,SEEK_END);
  if(size<0 || _lseeki64(descriptor,0,SEEK_SET)<0)return SQLITE_IOERR_SEEK;
#else
  off_t size=lseek(descriptor,0,SEEK_END);
  if(size<0 || lseek(descriptor,0,SEEK_SET)<0)return SQLITE_IOERR_SEEK;
#endif
  *length=(sqlite3_int64)size;return SQLITE_OK;
}

static int configure_rebaser(sqlite3_rebaser *rebaser,Output *source){
  sqlite3_int64 length=0,offset=0;unsigned char *bytes;int result=rewind_input(source->descriptor,&length);
  if(result!=SQLITE_OK)return result;
  if(length>INT_MAX)return SQLITE_TOOBIG; /* Public configure() accepts int. */
  bytes=sqlite3_malloc64(length ? (sqlite3_uint64)length : 1);
  if(!bytes)return SQLITE_NOMEM;
  while(result==SQLITE_OK && offset<length){
    int count=(int)((length-offset)>1048576 ? 1048576 : length-offset);
    result=input(source,bytes+offset,&count);
    if(result==SQLITE_OK && count==0)result=SQLITE_IOERR_SHORT_READ;
    offset+=count;
  }
  if(result==SQLITE_OK)result=sqlite3rebaser_configure(rebaser,(int)length,bytes);
  sqlite3_free(bytes);return result;
}

static void transform_changeset(sqlite3_context *context,State *state,int count,sqlite3_value **values){
  const char *mode=text(values[2]),*schema=0;sqlite3_int64 outfd=sqlite3_value_int64(values[3]),cancel=sqlite3_value_int64(values[4]);
  int patchset=sqlite3_value_int(values[6]),inputs=count-7,index,result=SQLITE_OK;Output sources[100],target;
  sqlite3_changegroup *group=0;sqlite3_rebaser *rebaser=0;sqlite3_str *builder;char *metadata;
  if(!mode || inputs<1 || inputs>100 || outfd<0 || outfd>INT_MAX || cancel<-1 || cancel>INT_MAX || patchset<-1 || patchset>1){
    fail(context,SQLITE_MISUSE,"Select native transform mode and owned descriptors");return;
  }
  if(sqlite3_value_type(values[5])!=SQLITE_NULL){
    schema=text(values[5]);if(!schema || !*schema){fail(context,SQLITE_MISUSE,"Select an exact native schema or no schema basis");return;}
  }
  if((strcmp(mode,"invert")==0 && inputs!=1) || (strcmp(mode,"concat")==0 && inputs!=2) ||
      (strcmp(mode,"rebase")==0 && inputs<2) ||
      (strcmp(mode,"merge")!=0 && (schema || patchset!=-1)) ||
      (strcmp(mode,"invert")!=0 && strcmp(mode,"concat")!=0 && strcmp(mode,"merge")!=0 && strcmp(mode,"rebase")!=0)){
    fail(context,SQLITE_MISUSE,"Native transform inputs or schema options differ from the selected operation");return;
  }
  for(index=0;index<inputs;index++){
    sqlite3_int64 descriptor=sqlite3_value_int64(values[index+7]);
    if(descriptor<0 || descriptor>INT_MAX){fail(context,SQLITE_MISUSE,"Select owned native transform input descriptors");return;}
    sources[index].descriptor=(int)descriptor;sources[index].cancel=(int)cancel;sources[index].bytes=0;
  }
  target.descriptor=(int)outfd;target.cancel=(int)cancel;target.bytes=0;
  if(cancelled(target.cancel))result=SQLITE_INTERRUPT;
  else if(strcmp(mode,"invert")==0)result=sqlite3changeset_invert_strm(input,&sources[0],output,&target);
  else if(strcmp(mode,"concat")==0)result=sqlite3changeset_concat_strm(input,&sources[0],input,&sources[1],output,&target);
  else if(strcmp(mode,"merge")==0){
    result=sqlite3changegroup_new(&group);
    if(result==SQLITE_OK && patchset>=0)result=sqlite3changegroup_config(group,SQLITE_CHANGEGROUP_CONFIG_PATCHSET,&patchset);
    if(result==SQLITE_OK && schema)result=sqlite3changegroup_schema(group,state->db,schema);
    for(index=0;result==SQLITE_OK && index<inputs;index++)result=sqlite3changegroup_add_strm(group,input,&sources[index]);
    if(result==SQLITE_OK)result=sqlite3changegroup_output_strm(group,output,&target);
  }else{
    result=sqlite3rebaser_create(&rebaser);
    for(index=1;result==SQLITE_OK && index<inputs;index++)result=configure_rebaser(rebaser,&sources[index]);
    if(result==SQLITE_OK)result=sqlite3rebaser_rebase_strm(rebaser,input,&sources[0],output,&target);
  }
  sqlite3changegroup_delete(group);sqlite3rebaser_delete(rebaser);
  if(result!=SQLITE_OK){fail(context,result,"Native changeset transformation did not complete");return;}
  builder=sqlite3_str_new(state->db);
  sqlite3_str_appendf(builder,"{\"native_written_bytes\":\"%lld\",\"native_input_bytes\":[",target.bytes);
  for(index=0;index<inputs;index++)sqlite3_str_appendf(builder,"%s\"%lld\"",index ? "," : "",sources[index].bytes);
  sqlite3_str_appendall(builder,"]}");metadata=sqlite3_str_finish(builder);
  if(!metadata)sqlite3_result_error_nomem(context);else sqlite3_result_text(context,metadata,-1,sqlite3_free);
}

static int table_filter(void *opaque,const char *table){
  Capture *capture=opaque;int matches=sqlite3_strglob(capture->filter_pattern,table)==0;
  return capture->filter_exclude ? !matches : matches;
}

static void control(sqlite3_context *context,int count,sqlite3_value **values){
  State *state=(State*)sqlite3_user_data(context);const char *operation,*id;
  Capture *capture,*previous=0;int result=SQLITE_OK;
  if(count<2 || !admitted(state,values[0])){fail(context,SQLITE_AUTH,"Native session capability is unavailable");return;}
  operation=text(values[1]);if(!operation){fail(context,SQLITE_MISUSE,"Select a native session operation");return;}
  if(strcmp(operation,"extract_cell")==0 && count==8){extract_cell(context,values);return;}
  if(strcmp(operation,"inspect_page")==0 && count==8){inspect_page(context,values);return;}
  if(strcmp(operation,"inspect_cell")==0 && count==9){inspect_cell(context,values);return;}
  if(strcmp(operation,"inspect_file")==0 && count==4){inspect_changeset(context,values,0);return;}
  if(strcmp(operation,"inspect_selection")==0 && count==5){
    const char *selected=sqlite3_value_type(values[4])==SQLITE_NULL ? 0 : text(values[4]);
    if(sqlite3_value_type(values[4])!=SQLITE_NULL && (!selected || !*selected)){fail(context,SQLITE_MISUSE,"Select an exact table filter or all tables");return;}
    inspect_changeset(context,values,selected);return;
  }
  if(strcmp(operation,"apply_file")==0 && count==12){apply_changeset(context,state,values);return;}
  if(strcmp(operation,"transform_file")==0 && count>=8){transform_changeset(context,state,count,values);return;}
  if(strcmp(operation,"identity")==0 && count==2){
    char *identity=sqlite3_mprintf("{\"sqlite_version\":\"%s\",\"sqlite_source_id\":\"%s\",\"adapter_abi\":1,\"native_session_revision\":6}",sqlite3_libversion(),sqlite3_sourceid());
    if(!identity)sqlite3_result_error_nomem(context);else sqlite3_result_text(context,identity,-1,sqlite3_free);return;
  }
  if(strcmp(operation,"close_all")==0 && count==2){close_all(state);return;}
  if(count<3 || !(id=text(values[2])) || !*id || strlen(id)>255){fail(context,SQLITE_MISUSE,"Select a native session identity");return;}
  for(capture=state->captures;capture;previous=capture,capture=capture->next)if(strcmp(capture->id,id)==0)break;
  if(strcmp(operation,"open")==0 && count==6){
    const char *database=text(values[3]);int size=sqlite3_value_int(values[4]),rowid=sqlite3_value_int(values[5]);
    if(capture || !database || (size!=0 && size!=1) || (rowid!=0 && rowid!=1)){
      fail(context,SQLITE_MISUSE,"Native session identity or configuration is invalid");return;
    }
    if(sqlite3_get_clientdata(state->db,CDEADMIN_PREUPDATE_ACTIVE)){
      fail(context,SQLITE_BUSY,"Stop the independent native preupdate hook before opening a session capture");return;
    }
    capture=sqlite3_malloc64(sizeof(*capture));if(!capture){sqlite3_result_error_nomem(context);return;}
    memset(capture,0,sizeof(*capture));capture->id=sqlite3_mprintf("%s",id);
    if(!capture->id){sqlite3_free(capture);sqlite3_result_error_nomem(context);return;}
    result=sqlite3_set_clientdata(state->db,CDEADMIN_SESSION_ACTIVE,state,0);
    if(result==SQLITE_OK)result=sqlite3session_create(state->db,database,&capture->session);
    if(result==SQLITE_OK)result=sqlite3session_object_config(capture->session,SQLITE_SESSION_OBJCONFIG_SIZE,&size);
    if(result==SQLITE_OK)result=sqlite3session_object_config(capture->session,SQLITE_SESSION_OBJCONFIG_ROWID,&rowid);
    if(result!=SQLITE_OK){
      if(capture->session)sqlite3session_delete(capture->session);
      if(!state->captures)sqlite3_set_clientdata(state->db,CDEADMIN_SESSION_ACTIVE,0,0);
      sqlite3_free(capture->id);sqlite3_free(capture);fail(context,result,"Native session creation failed");return;
    }
    capture->next=state->captures;state->captures=capture;return;
  }
  if(!capture){fail(context,SQLITE_NOTFOUND,"Native session identity is unavailable");return;}
  if(strcmp(operation,"close")==0 && count==3){
    if(previous)previous->next=capture->next;else state->captures=capture->next;
    sqlite3session_delete(capture->session);sqlite3_free(capture->filter_pattern);sqlite3_free(capture->id);sqlite3_free(capture);
    if(!state->captures)sqlite3_set_clientdata(state->db,CDEADMIN_SESSION_ACTIVE,0,0);
    return;
  }else if(strcmp(operation,"table_filter")==0 && count==5){
    const char *pattern=sqlite3_value_type(values[3])==SQLITE_NULL ? 0 : text(values[3]);
    int exclude=sqlite3_value_int(values[4]);char *replacement=0,*previous_pattern=capture->filter_pattern;
    if((!pattern && sqlite3_value_type(values[3])!=SQLITE_NULL) || (exclude!=0 && exclude!=1) || (!pattern && exclude)){
      fail(context,SQLITE_MISUSE,"Select a native SQLite GLOB filter or all future table names");return;
    }
    if(pattern){replacement=sqlite3_mprintf("%s",pattern);if(!replacement){fail(context,SQLITE_NOMEM,"Native table filter allocation failed");return;}}
    capture->filter_pattern=replacement;capture->filter_exclude=exclude;
    sqlite3session_table_filter(capture->session,pattern ? table_filter : 0,capture);sqlite3_free(previous_pattern);return;
  }else if(strcmp(operation,"attach")==0 && count==4){
    const char *table=sqlite3_value_type(values[3])==SQLITE_NULL ? 0 : text(values[3]);
    if(!table && sqlite3_value_type(values[3])!=SQLITE_NULL){fail(context,SQLITE_MISUSE,"Select a native table or all-table filter");return;}
    result=sqlite3session_attach(capture->session,table);
  }else if(strcmp(operation,"enable")==0 && count==4){
    sqlite3_result_int(context,sqlite3session_enable(capture->session,sqlite3_value_int(values[3])));return;
  }else if(strcmp(operation,"indirect")==0 && count==4){
    sqlite3_result_int(context,sqlite3session_indirect(capture->session,sqlite3_value_int(values[3])));return;
  }else if(strcmp(operation,"status")==0 && count==3){
    int size=-1,rowid=-1;char *status;
    sqlite3session_object_config(capture->session,SQLITE_SESSION_OBJCONFIG_SIZE,&size);
    sqlite3session_object_config(capture->session,SQLITE_SESSION_OBJCONFIG_ROWID,&rowid);
    status=sqlite3_mprintf("{\"memory_bytes\":\"%lld\",\"changeset_estimate_bytes\":\"%lld\",\"empty\":%s,\"enabled\":%s,\"indirect\":%s,\"estimate_size\":%s,\"track_rowids\":%s}",
      sqlite3session_memory_used(capture->session),sqlite3session_changeset_size(capture->session),
      sqlite3session_isempty(capture->session)?"true":"false",sqlite3session_enable(capture->session,-1)?"true":"false",
      sqlite3session_indirect(capture->session,-1)?"true":"false",size?"true":"false",rowid?"true":"false");
    if(!status)sqlite3_result_error_nomem(context);else sqlite3_result_text(context,status,-1,sqlite3_free);return;
  }else if(strcmp(operation,"object_config")==0 && count==5){
    int option=sqlite3_value_int(values[3]),value=sqlite3_value_int(values[4]);
    if((option!=SQLITE_SESSION_OBJCONFIG_SIZE && option!=SQLITE_SESSION_OBJCONFIG_ROWID) || value<-1 || value>1){
      fail(context,SQLITE_MISUSE,"Select a native session object configuration switch");return;
    }
    result=sqlite3session_object_config(capture->session,option,&value);
    if(result==SQLITE_OK){sqlite3_result_int(context,value);return;}
  }else if(strcmp(operation,"diff")==0 && count==5){
    char *error=0;const char *database=text(values[3]),*table=text(values[4]);
    if(!database || !table){fail(context,SQLITE_MISUSE,"Select an attached native source database and table");return;}
    result=sqlite3session_diff(capture->session,database,table,&error);
    if(error){sqlite3_free(error);}
  }else if(strcmp(operation,"export")==0 && count==6){
    const char *kind=text(values[3]);sqlite3_int64 descriptor=sqlite3_value_int64(values[4]),cancel=sqlite3_value_int64(values[5]);Output target;
    if(!kind || (strcmp(kind,"changeset")!=0 && strcmp(kind,"patchset")!=0) || descriptor<0 || descriptor>INT_MAX || cancel<-1 || cancel>INT_MAX){
      fail(context,SQLITE_MISUSE,"Select a native session format and owned output descriptors");return;
    }
    target.descriptor=(int)descriptor;target.cancel=(int)cancel;target.bytes=0;
    if(cancelled(target.cancel))result=SQLITE_INTERRUPT;
    else result=strcmp(kind,"changeset")==0 ? sqlite3session_changeset_strm(capture->session,output,&target) : sqlite3session_patchset_strm(capture->session,output,&target);
    if(result==SQLITE_OK){sqlite3_result_int64(context,target.bytes);return;}
  }else{fail(context,SQLITE_MISUSE,"Native session operation or argument count is unavailable");return;}
  if(result!=SQLITE_OK)fail(context,result,"Native session API did not complete");
}

#ifdef _WIN32
__declspec(dllexport)
#endif
int sqlite3_cdeadminsessions_init(sqlite3 *db,char **error,const sqlite3_api_routines *api){
  State *state;int result,fresh,index;unsigned char random[16];
  const char hex[]="0123456789abcdef";char suffix[33],binding[96],calling[96];
  if(api->libversion!=sqlite3_libversion || sqlite3_libversion_number()!=3053000 ||
      strcmp(sqlite3_sourceid(),SQLITE_SOURCE_ID)!=0 || !sqlite3_compileoption_used("ENABLE_SESSION") ||
      !sqlite3_compileoption_used("ENABLE_PREUPDATE_HOOK")){
    *error=sqlite3_mprintf("Native session adapter requires the connection's exact SQLite3.53.0 library and session/preupdate APIs");return SQLITE_MISMATCH;
  }
  state=sqlite3_get_clientdata(db,"org.cdeadmin.sqlite.sessions.v1");fresh=state==0;
  if(state && !sqlite3_get_clientdata(db,"org.cdeadmin.sqlite.session.layout.v2")){
    *error=sqlite3_mprintf("Reconnect before loading a different native session controller layout");return SQLITE_MISMATCH;
  }
  if(fresh){
    state=sqlite3_malloc64(sizeof(*state));if(!state)return SQLITE_NOMEM;
    memset(state,0,sizeof(*state));state->db=db;state->refs=1;
  }else state->refs++;
  /* Fresh aliases preserve pre-existing user functions. Reinitialization keeps
   * the existing connection state/capability and only adds new private aliases. */
  sqlite3_randomness(sizeof(random),random);
  for(index=0;index<16;index++){suffix[index*2]=hex[random[index]>>4];suffix[index*2+1]=hex[random[index]&15];}suffix[32]=0;
  sqlite3_snprintf(sizeof(binding),binding,"_cdeadmin_session_bind_%s",suffix);
  sqlite3_snprintf(sizeof(calling),calling,"_cdeadmin_session_call_%s",suffix);
  state->refs++;
  result=sqlite3_create_function_v2(db,binding,1,SQLITE_UTF8|SQLITE_DIRECTONLY,state,bind_capability,0,0,release_state);
  if(result==SQLITE_OK){
    state->refs++;
    result=sqlite3_create_function_v2(db,calling,-1,SQLITE_UTF8|SQLITE_DIRECTONLY,state,control,0,0,release_state);
    if(result!=SQLITE_OK)sqlite3_create_function_v2(db,binding,1,SQLITE_UTF8,0,0,0,0,0);
  }
  if(result==SQLITE_OK && fresh){
    state->refs++;
    result=sqlite3_set_clientdata(db,"org.cdeadmin.sqlite.sessions.v1",state,release_state);
    if(result!=SQLITE_OK){
      sqlite3_create_function_v2(db,binding,1,SQLITE_UTF8,0,0,0,0,0);
      sqlite3_create_function_v2(db,calling,-1,SQLITE_UTF8,0,0,0,0,0);
    }
  }
  if(result==SQLITE_OK)result=sqlite3_set_clientdata(db,"org.cdeadmin.sqlite.session.layout.v2",state,0);
  if(result==SQLITE_OK)result=sqlite3_set_clientdata(db,CDEADMIN_SESSION_GUARD,state,0);
  release_state(state);return result;
}
