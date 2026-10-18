/* Protected native CARRAY values through public APIs only. The driver owns
 * array lifetime and stops query workers before finalizing bound value boxes. */
#include <sqlite3ext.h>
#include <limits.h>
#include <string.h>
#ifdef _WIN32
struct iovec { void *iov_base; size_t iov_len; };
#else
#include <sys/uio.h>
#endif

typedef struct Array Array;
struct Array { char *id; int type,count; sqlite3_int64 bytes; void *values;sqlite3_stmt *box;Array *next; };
typedef struct State State;
struct State { sqlite3 *db;unsigned char token[32];int bound,refs;Array *arrays; };

static void free_values(void *opaque){
  Array *array=(Array*)opaque;int index;
  if(array->values){
    if(array->type==SQLITE_CARRAY_TEXT){for(index=0;index<array->count;index++)sqlite3_free(((char**)array->values)[index]);}
    else if(array->type==SQLITE_CARRAY_BLOB){for(index=0;index<array->count;index++)sqlite3_free(((struct iovec*)array->values)[index].iov_base);}
    sqlite3_free(array->values);array->values=0;
  }
}
static void destroy_array(Array *array){
  if(array->box)sqlite3_finalize(array->box);
  free_values(array);sqlite3_free(array->id);sqlite3_free(array);
}
static void clear(State *state){
  Array *array=state->arrays;state->arrays=0;
  while(array){Array *next=array->next;destroy_array(array);array=next;}
}
static void release(void *opaque){
  State *state=opaque;
  /* Held prepared boxes must have been finalized by the driver before close. */
  if(--state->refs==0){memset(state->token,0,32);sqlite3_free(state);}
}
static void failure(sqlite3_context *context,int code){
  char *result=sqlite3_mprintf("{\"native_result_code\":%d,\"message\":\"Native CARRAY operation did not complete\"}",code);
  if(!result)sqlite3_result_error_nomem(context);else sqlite3_result_text(context,result,-1,sqlite3_free);
}
static const char *text(sqlite3_value *value){
  const char *result=(const char*)sqlite3_value_text(value);
  return result && sqlite3_value_type(value)==SQLITE_TEXT && strlen(result)==(size_t)sqlite3_value_bytes(value) ? result : 0;
}
static int admitted(State *state,sqlite3_value *value){
  const unsigned char *bytes=sqlite3_value_blob(value);unsigned char different=0;int index;
  if(!state->bound || sqlite3_value_type(value)!=SQLITE_BLOB || sqlite3_value_bytes(value)!=32 || !bytes)return 0;
  for(index=0;index<32;index++)different|=bytes[index]^state->token[index];
  return different==0;
}
static void bind_token(sqlite3_context *context,int count,sqlite3_value **values){
  State *state=sqlite3_user_data(context);const void *token;(void)count;
  if(state->bound || sqlite3_value_type(values[0])!=SQLITE_BLOB || sqlite3_value_bytes(values[0])!=32){failure(context,SQLITE_AUTH);return;}
  token=sqlite3_value_blob(values[0]);if(!token){sqlite3_result_error_nomem(context);return;}
  memcpy(state->token,token,32);state->bound=1;sqlite3_result_int(context,1);
}
static Array *find(State *state,const char *id){
  Array *array;for(array=state->arrays;array;array=array->next)if(strcmp(array->id,id)==0)return array;return 0;
}
static void pointer_value(sqlite3_context *context,int count,sqlite3_value **values){
  State *state=sqlite3_user_data(context);const char *id=text(values[0]);Array *array=id ? find(state,id) : 0;(void)count;
  if(!array){sqlite3_result_error(context,"Native CARRAY belongs to another or closed query connection",-1);return;}
  /* Public result_value preserves the native protected binding. carray() owns
   * its count/type interpretation; a caller cannot supply a larger raw count. */
  sqlite3_result_value(context,sqlite3_column_value(array->box,0));
}
static int fill(Array *array,const unsigned char *data,int length){
  sqlite3_uint64 width,array_bytes;sqlite3_int64 offset=0;int index;
  width=array->type==SQLITE_CARRAY_INT32 ? sizeof(int) : array->type==SQLITE_CARRAY_INT64 ? sizeof(sqlite3_int64) :
      array->type==SQLITE_CARRAY_DOUBLE ? sizeof(double) : array->type==SQLITE_CARRAY_TEXT ? sizeof(char*) : sizeof(struct iovec);
  array_bytes=(sqlite3_uint64)array->count*width;
  if(array_bytes>LLONG_MAX)return SQLITE_TOOBIG;
  if(array->type<=SQLITE_CARRAY_DOUBLE && array_bytes!=(sqlite3_uint64)length)return SQLITE_MISMATCH;
  if(array->type>=SQLITE_CARRAY_TEXT && array->count>length/8)return SQLITE_CORRUPT;
  array->values=sqlite3_malloc64(array_bytes ? array_bytes : 1);if(!array->values)return SQLITE_NOMEM;
  memset(array->values,0,(size_t)(array_bytes ? array_bytes : 1));array->bytes=(sqlite3_int64)array_bytes;
  if(array->type<=SQLITE_CARRAY_DOUBLE){
    if(length)memcpy(array->values,data,(size_t)length);
    return SQLITE_OK;
  }
  for(index=0;index<array->count;index++){
    sqlite3_int64 size;void *copy;
    if((sqlite3_int64)length-offset<8)return SQLITE_CORRUPT;
    memcpy(&size,data+offset,8);offset+=8;
    if(size<-1 || size>(sqlite3_int64)length-offset)return SQLITE_CORRUPT;
    if(size<0)continue;
    if(array->type==SQLITE_CARRAY_TEXT && memchr(data+offset,0,(size_t)size))return SQLITE_MISMATCH;
    copy=sqlite3_malloc64((sqlite3_uint64)size+1);if(!copy)return SQLITE_NOMEM;
    if(size)memcpy(copy,data+offset,(size_t)size);
    ((unsigned char*)copy)[size]=0;
    if(array->type==SQLITE_CARRAY_TEXT)((char**)array->values)[index]=copy;
    else{((struct iovec*)array->values)[index].iov_base=copy;((struct iovec*)array->values)[index].iov_len=(size_t)size;}
    array->bytes+=size+1;offset+=size;
  }
  return offset==length ? SQLITE_OK : SQLITE_CORRUPT;
}
static void control(sqlite3_context *context,int count,sqlite3_value **values){
  State *state=sqlite3_user_data(context);const char *operation,*id;Array *array;int result;
  if(count<2 || !admitted(state,values[0])){failure(context,SQLITE_AUTH);return;}
  operation=text(values[1]);if(!operation){failure(context,SQLITE_MISUSE);return;}
  if(strcmp(operation,"identity")==0 && count==2){
    char *result_text=sqlite3_mprintf("{\"adapter_abi\":1,\"sqlite_version\":\"%s\",\"sqlite_source_id\":\"%s\",\"native_array_revision\":1}",sqlite3_libversion(),sqlite3_sourceid());
    if(!result_text)sqlite3_result_error_nomem(context);else sqlite3_result_text(context,result_text,-1,sqlite3_free);return;
  }
  if(strcmp(operation,"close_all")==0 && count==2){clear(state);return;}
  if(count<3 || !(id=text(values[2])) || !*id || strlen(id)>255){failure(context,SQLITE_MISUSE);return;}
  array=find(state,id);
  if(strcmp(operation,"create")==0 && count==6){
    sqlite3_int64 amount=sqlite3_value_int64(values[4]);int type=sqlite3_value_int(values[3]),length=sqlite3_value_bytes(values[5]);const unsigned char *data=sqlite3_value_blob(values[5]);
    if(array || type<0 || type>4 || amount<0 || amount>INT_MAX || sqlite3_value_type(values[5])!=SQLITE_BLOB){failure(context,SQLITE_MISUSE);return;}
    array=sqlite3_malloc64(sizeof(*array));if(!array){failure(context,SQLITE_NOMEM);return;}
    memset(array,0,sizeof(*array));array->type=type;array->count=(int)amount;array->id=sqlite3_mprintf("%s",id);
    if(!array->id){destroy_array(array);failure(context,SQLITE_NOMEM);return;}
    result=fill(array,data,length);
    if(result==SQLITE_OK)result=sqlite3_prepare_v2(state->db,"SELECT ?1,(SELECT count(*) FROM carray(?1) WHERE 0)",-1,&array->box,0);
    if(result==SQLITE_OK)result=sqlite3_carray_bind_v2(array->box,1,array->values,array->count,array->type,free_values,array);
    if(result==SQLITE_OK){result=sqlite3_step(array->box);if(result==SQLITE_ROW)result=SQLITE_OK;}
    if(result!=SQLITE_OK){destroy_array(array);failure(context,result);return;}
    array->next=state->arrays;state->arrays=array;sqlite3_result_int(context,1);return;
  }
  if(!array){failure(context,SQLITE_NOTFOUND);return;}
  if(strcmp(operation,"status")==0 && count==3){
    char *result_text=sqlite3_mprintf("{\"native_type\":%d,\"element_count\":\"%d\",\"native_data_bytes\":\"%lld\"}",array->type,array->count,array->bytes);
    if(!result_text)sqlite3_result_error_nomem(context);else sqlite3_result_text(context,result_text,-1,sqlite3_free);return;
  }
  if(strcmp(operation,"close")==0 && count==3){
    Array **link=&state->arrays;while(*link!=array)link=&(*link)->next;*link=array->next;destroy_array(array);return;
  }
  failure(context,SQLITE_MISUSE);
}

#ifdef _WIN32
__declspec(dllexport)
#endif
int sqlite3_cdeadminarrays_init(sqlite3 *db,char **error,const sqlite3_api_routines *api){
  State *state;int result,fresh,index;unsigned char random[16];const char hex[]="0123456789abcdef";char suffix[33],binding[96],calling[96],getter[96];
  if(api->libversion!=sqlite3_libversion || sqlite3_libversion_number()!=3053000 || strcmp(sqlite3_sourceid(),SQLITE_SOURCE_ID)!=0 || !sqlite3_compileoption_used("ENABLE_CARRAY")){
    *error=sqlite3_mprintf("Native array adapter requires the connection's exact SQLite3.53.0 library and CARRAY API");return SQLITE_MISMATCH;
  }
  state=sqlite3_get_clientdata(db,"org.cdeadmin.sqlite.arrays.v1");fresh=state==0;
  if(fresh){state=sqlite3_malloc64(sizeof(*state));if(!state)return SQLITE_NOMEM;memset(state,0,sizeof(*state));state->db=db;state->refs=1;}
  else state->refs++;
  sqlite3_randomness(sizeof(random),random);for(index=0;index<16;index++){suffix[index*2]=hex[random[index]>>4];suffix[index*2+1]=hex[random[index]&15];}suffix[32]=0;
  sqlite3_snprintf(sizeof(binding),binding,"_cdeadmin_array_bind_%s",suffix);sqlite3_snprintf(sizeof(calling),calling,"_cdeadmin_array_call_%s",suffix);sqlite3_snprintf(sizeof(getter),getter,"_cdeadmin_array_value_%s",suffix);
  state->refs++;result=sqlite3_create_function_v2(db,binding,1,SQLITE_UTF8|SQLITE_DIRECTONLY,state,bind_token,0,0,release);
  if(result==SQLITE_OK){state->refs++;result=sqlite3_create_function_v2(db,calling,-1,SQLITE_UTF8|SQLITE_DIRECTONLY,state,control,0,0,release);}
  if(result==SQLITE_OK){state->refs++;result=sqlite3_create_function_v2(db,getter,1,SQLITE_UTF8|SQLITE_DIRECTONLY,state,pointer_value,0,0,release);}
  if(result==SQLITE_OK && fresh){state->refs++;result=sqlite3_set_clientdata(db,"org.cdeadmin.sqlite.arrays.v1",state,release);}
  if(result!=SQLITE_OK){sqlite3_create_function_v2(db,binding,1,SQLITE_UTF8,0,0,0,0,0);sqlite3_create_function_v2(db,calling,-1,SQLITE_UTF8,0,0,0,0,0);sqlite3_create_function_v2(db,getter,1,SQLITE_UTF8,0,0,0,0,0);}
  release(state);return result;
}
