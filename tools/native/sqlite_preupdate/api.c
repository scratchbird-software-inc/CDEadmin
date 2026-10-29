/* Native before-change observations. These records NEVER establish commit. */
#include <sqlite3ext.h>
#include <limits.h>
#include <string.h>
#include "../sqlite_hook_ownership.h"

typedef struct Event Event;
struct Event {sqlite3_int64 sequence;int bytes;char *json;Event *next;};
typedef struct State State;
struct State {sqlite3 *db;unsigned char token[32];int bound,refs,enabled,records,max_records,last_error;sqlite3_int64 seen,dropped,bytes,max_bytes;Event *first,*last;};

static void discard(State *s){Event *e=s->first;while(e){Event *next=e->next;sqlite3_free(e->json);sqlite3_free(e);e=next;}s->first=s->last=0;s->records=0;s->bytes=0;s->seen=0;s->dropped=0;s->last_error=SQLITE_OK;}
static void stop(State *s){if(s->enabled){sqlite3_preupdate_hook(s->db,0,0);s->enabled=0;sqlite3_set_clientdata(s->db,CDEADMIN_PREUPDATE_ACTIVE,0,0);}}
static void release(void *p){State *s=p;if(--s->refs==0){stop(s);discard(s);memset(s->token,0,32);sqlite3_free(s);}}
static void failure(sqlite3_context *c,int code){char *r=sqlite3_mprintf("{\"native_result_code\":%d,\"message\":\"Native preupdate operation did not complete\"}",code);if(!r)sqlite3_result_error_nomem(c);else sqlite3_result_text(c,r,-1,sqlite3_free);}
static const char *text(sqlite3_value *v){const char *r=(const char*)sqlite3_value_text(v);return r && sqlite3_value_type(v)==SQLITE_TEXT && strlen(r)==(size_t)sqlite3_value_bytes(v) ? r : 0;}
static void bind_token(sqlite3_context *c,int n,sqlite3_value **v){State *s=sqlite3_user_data(c);const void *p;(void)n;if(s->bound || sqlite3_value_type(v[0])!=SQLITE_BLOB || sqlite3_value_bytes(v[0])!=32){failure(c,SQLITE_AUTH);return;}p=sqlite3_value_blob(v[0]);if(!p){failure(c,SQLITE_NOMEM);return;}memcpy(s->token,p,32);s->bound=1;sqlite3_result_int(c,1);}
static int admitted(State *s,sqlite3_value *v){const unsigned char *p=sqlite3_value_blob(v);unsigned char x=0;int i;if(!s->bound || sqlite3_value_type(v)!=SQLITE_BLOB || sqlite3_value_bytes(v)!=32 || !p)return 0;for(i=0;i<32;i++)x|=p[i]^s->token[i];return x==0;}
static void hex(sqlite3_str *b,const void *p,int length){static const char digits[]="0123456789ABCDEF";const unsigned char *v=p;int i;sqlite3_str_appendchar(b,1,'"');for(i=0;i<length;i++){char pair[2];pair[0]=digits[v[i]>>4];pair[1]=digits[v[i]&15];sqlite3_str_append(b,pair,2);}sqlite3_str_appendchar(b,1,'"');}
static int cell(sqlite3_str *b,sqlite3_value *v,sqlite3_int64 remaining){
  int kind=sqlite3_value_type(v),length;const void *p;
  if(kind==SQLITE_NULL){sqlite3_str_appendall(b,"{\"native_type\":\"null\",\"data\":null}");return SQLITE_OK;}
  if(kind==SQLITE_INTEGER){sqlite3_str_appendf(b,"{\"native_type\":\"integer\",\"data\":\"%lld\"}",sqlite3_value_int64(v));return SQLITE_OK;}
  if(kind==SQLITE_FLOAT){sqlite3_str_appendf(b,"{\"native_type\":\"real\",\"data\":\"%!.17g\"}",sqlite3_value_double(v));return SQLITE_OK;}
  p=kind==SQLITE_TEXT ? (const void*)sqlite3_value_text(v) : sqlite3_value_blob(v);length=sqlite3_value_bytes(v);
  if(length && !p)return SQLITE_NOMEM;
  if((sqlite3_int64)length*2+80>remaining)return SQLITE_TOOBIG;
  sqlite3_str_appendf(b,"{\"native_type\":\"%s\",\"hex\":",kind==SQLITE_TEXT ? "text":"blob");hex(b,p,length);sqlite3_str_appendchar(b,1,'}');return SQLITE_OK;
}
static void observe(void *opaque,sqlite3 *db,int operation,const char *database,const char *table,sqlite3_int64 oldrow,sqlite3_int64 newrow){
  State *s=opaque;sqlite3_str *b;Event *e;int count=sqlite3_preupdate_count(db),side,index,result=SQLITE_OK;char *json;
  if(s->seen==LLONG_MAX){s->last_error=SQLITE_FULL;return;}
  s->seen++;
  if(s->records>=s->max_records || s->bytes>=s->max_bytes){s->dropped++;return;}
  b=sqlite3_str_new(db);
  sqlite3_str_appendf(b,"{\"sequence\":\"%lld\",\"operation\":\"%s\",\"column_count\":%d,\"depth\":%d,\"blobwrite_column\":%d,\"native_old_rowid\":\"%lld\",\"native_new_rowid\":\"%lld\",\"database_hex\":",s->seen,operation==SQLITE_INSERT ? "insert":operation==SQLITE_UPDATE ? "update":"delete",count,sqlite3_preupdate_depth(db),sqlite3_preupdate_blobwrite(db),oldrow,newrow);
  hex(b,database,(int)strlen(database));sqlite3_str_appendall(b,",\"table_hex\":");hex(b,table,(int)strlen(table));
  for(side=0;side<2 && result==SQLITE_OK;side++){
    sqlite3_str_appendall(b,side ? ",\"new_values\":" : ",\"old_values\":");
    if((!side && operation==SQLITE_INSERT) || (side && operation==SQLITE_DELETE)){sqlite3_str_appendall(b,"null");continue;}
    sqlite3_str_appendchar(b,1,'[');
    for(index=0;index<count && result==SQLITE_OK;index++){
      sqlite3_value *v=0;
      if(index)sqlite3_str_appendchar(b,1,',');
      result=side ? sqlite3_preupdate_new(db,index,&v) : sqlite3_preupdate_old(db,index,&v);
      if(result==SQLITE_OK)result=cell(b,v,s->max_bytes-s->bytes-sqlite3_str_length(b));
      if(result==SQLITE_OK && sqlite3_str_length(b)>s->max_bytes-s->bytes)result=SQLITE_TOOBIG;
    }
    sqlite3_str_appendchar(b,1,']');
  }
  sqlite3_str_appendchar(b,1,'}');
  if(result==SQLITE_OK)result=sqlite3_str_errcode(b);
  if(result==SQLITE_OK && sqlite3_str_length(b)>s->max_bytes-s->bytes)result=SQLITE_TOOBIG;
  json=sqlite3_str_finish(b);
  if(!json && result==SQLITE_OK)result=SQLITE_NOMEM;
  if(result!=SQLITE_OK){sqlite3_free(json);s->dropped++;s->last_error=result;return;}
  e=sqlite3_malloc64(sizeof(*e));if(!e){sqlite3_free(json);s->dropped++;s->last_error=SQLITE_NOMEM;return;}
  e->sequence=s->seen;e->json=json;e->bytes=(int)strlen(json);e->next=0;
  if(s->last)s->last->next=e;else s->first=e;s->last=e;s->records++;s->bytes+=e->bytes;
}
static void status(sqlite3_context *c,State *s){char *r=sqlite3_mprintf("{\"enabled\":%s,\"observed_events\":\"%lld\",\"dropped_events\":\"%lld\",\"retained_events\":%d,\"retained_json_bytes\":\"%lld\",\"max_events\":%d,\"max_json_bytes\":\"%lld\",\"last_native_result_code\":%d}",s->enabled?"true":"false",s->seen,s->dropped,s->records,s->bytes,s->max_records,s->max_bytes,s->last_error);if(!r)failure(c,SQLITE_NOMEM);else sqlite3_result_text(c,r,-1,sqlite3_free);}
static void control(sqlite3_context *c,int count,sqlite3_value **v){
  State *s=sqlite3_user_data(c);const char *op;int result;
  if(count<2 || !admitted(s,v[0]) || !(op=text(v[1]))){failure(c,SQLITE_AUTH);return;}
  if(strcmp(op,"identity")==0 && count==2){char *r=sqlite3_mprintf("{\"adapter_abi\":1,\"native_preupdate_revision\":1,\"sqlite_version\":\"%s\",\"sqlite_source_id\":\"%s\"}",sqlite3_libversion(),sqlite3_sourceid());if(!r)failure(c,SQLITE_NOMEM);else sqlite3_result_text(c,r,-1,sqlite3_free);return;}
  if(strcmp(op,"status")==0 && count==2){status(c,s);return;}
  if(strcmp(op,"close_all")==0 && count==2){stop(s);discard(s);return;}
  if(strcmp(op,"stop")==0 && count==2){stop(s);status(c,s);return;}
  if(strcmp(op,"clear")==0 && count==2){discard(s);status(c,s);return;}
  if(strcmp(op,"start")==0 && count==4){
    sqlite3_int64 events=sqlite3_value_int64(v[2]),bytes=sqlite3_value_int64(v[3]);
    if(s->enabled || s->records || events<1 || events>INT_MAX || bytes<1 || bytes>INT_MAX){failure(c,SQLITE_MISUSE);return;}
    if(sqlite3_get_clientdata(s->db,CDEADMIN_SESSION_ACTIVE) || (sqlite3_get_clientdata(s->db,"org.cdeadmin.sqlite.sessions.v1") && !sqlite3_get_clientdata(s->db,CDEADMIN_SESSION_GUARD))){failure(c,SQLITE_BUSY);return;}
    result=sqlite3_set_clientdata(s->db,CDEADMIN_PREUPDATE_ACTIVE,s,0);if(result!=SQLITE_OK){failure(c,result);return;}
    discard(s);s->max_records=(int)events;s->max_bytes=bytes;sqlite3_preupdate_hook(s->db,observe,s);s->enabled=1;status(c,s);return;
  }
  if(strcmp(op,"events")==0 && count==4){
    sqlite3_int64 after=sqlite3_value_int64(v[2]);int limit=sqlite3_value_int(v[3]),written=0;Event *e;sqlite3_str *b;char *r;
    if(after<0 || limit<1 || limit>100){failure(c,SQLITE_MISUSE);return;}
    b=sqlite3_str_new(s->db);sqlite3_str_appendall(b,"{\"events\":[");
    for(e=s->first;e && written<limit;e=e->next)if(e->sequence>after){if(written++)sqlite3_str_appendchar(b,1,',');sqlite3_str_appendall(b,e->json);}
    sqlite3_str_appendf(b,"],\"more\":%s}",e?"true":"false");r=sqlite3_str_finish(b);if(!r)failure(c,SQLITE_NOMEM);else sqlite3_result_text(c,r,-1,sqlite3_free);return;
  }
  failure(c,SQLITE_MISUSE);
}
#ifdef _WIN32
__declspec(dllexport)
#endif
int sqlite3_cdeadminpreupdate_init(sqlite3 *db,char **error,const sqlite3_api_routines *api){
  State *s;int result,fresh,index;unsigned char random[16];const char digits[]="0123456789abcdef";char suffix[33],binding[96],calling[96];
  if(api->libversion!=sqlite3_libversion || sqlite3_libversion_number()<SQLITE_VERSION_NUMBER || !sqlite3_compileoption_used("ENABLE_PREUPDATE_HOOK")){*error=sqlite3_mprintf("Native preupdate adapter requires its own connection library at SQLite " SQLITE_VERSION " or later and the public preupdate API");return SQLITE_MISMATCH;}
  s=sqlite3_get_clientdata(db,"org.cdeadmin.sqlite.preupdate.v1");fresh=s==0;
  if(fresh){s=sqlite3_malloc64(sizeof(*s));if(!s)return SQLITE_NOMEM;memset(s,0,sizeof(*s));s->db=db;s->refs=1;}else s->refs++;
  sqlite3_randomness(sizeof(random),random);for(index=0;index<16;index++){suffix[index*2]=digits[random[index]>>4];suffix[index*2+1]=digits[random[index]&15];}suffix[32]=0;
  sqlite3_snprintf(sizeof(binding),binding,"_cdeadmin_preupdate_bind_%s",suffix);sqlite3_snprintf(sizeof(calling),calling,"_cdeadmin_preupdate_call_%s",suffix);
  s->refs++;result=sqlite3_create_function_v2(db,binding,1,SQLITE_UTF8|SQLITE_DIRECTONLY,s,bind_token,0,0,release);
  if(result==SQLITE_OK){s->refs++;result=sqlite3_create_function_v2(db,calling,-1,SQLITE_UTF8|SQLITE_DIRECTONLY,s,control,0,0,release);}
  if(result==SQLITE_OK && fresh){s->refs++;result=sqlite3_set_clientdata(db,"org.cdeadmin.sqlite.preupdate.v1",s,release);}
  if(result!=SQLITE_OK){sqlite3_create_function_v2(db,binding,1,SQLITE_UTF8,0,0,0,0,0);sqlite3_create_function_v2(db,calling,-1,SQLITE_UTF8,0,0,0,0,0);}
  release(s);return result;
}
