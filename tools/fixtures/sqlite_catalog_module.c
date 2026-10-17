/* Native unavailable-module catalog fixture; no product extension is installed. */
#include "sqlite3.h"
#include <stdio.h>
#include <string.h>
typedef struct {sqlite3_vtab base;} Table;
typedef struct {sqlite3_vtab_cursor base;} Cursor;
static int connect_table(sqlite3 *db,void *unused,int argc,const char *const*argv,sqlite3_vtab **table,char **error){
 int rc=sqlite3_declare_vtab(db,"CREATE TABLE x(value TEXT)");
 if(rc!=SQLITE_OK)return rc;
 Table *p=sqlite3_malloc(sizeof(*p));if(!p)return SQLITE_NOMEM;
 memset(p,0,sizeof(*p));*table=&p->base;return SQLITE_OK;
}
static int disconnect_table(sqlite3_vtab *p){sqlite3_free(p);return SQLITE_OK;}
static int best_index(sqlite3_vtab *p,sqlite3_index_info *info){return SQLITE_OK;}
static int open_cursor(sqlite3_vtab *table,sqlite3_vtab_cursor **cursor){
 Cursor *p=sqlite3_malloc(sizeof(*p));if(!p)return SQLITE_NOMEM;
 memset(p,0,sizeof(*p));p->base.pVtab=table;*cursor=&p->base;return SQLITE_OK;
}
static int close_cursor(sqlite3_vtab_cursor *p){sqlite3_free(p);return SQLITE_OK;}
static int filter(sqlite3_vtab_cursor *p,int index,const char *value,int argc,sqlite3_value **argv){return SQLITE_OK;}
static int next(sqlite3_vtab_cursor *p){return SQLITE_OK;}
static int eof(sqlite3_vtab_cursor *p){return 1;}
static int column(sqlite3_vtab_cursor *p,sqlite3_context *context,int column){sqlite3_result_null(context);return SQLITE_OK;}
static int rowid(sqlite3_vtab_cursor *p,sqlite3_int64 *rowid){*rowid=1;return SQLITE_OK;}
static sqlite3_module module={.iVersion=3,.xCreate=connect_table,.xConnect=connect_table,.xBestIndex=best_index,
 .xDisconnect=disconnect_table,.xDestroy=disconnect_table,.xOpen=open_cursor,.xClose=close_cursor,.xFilter=filter,
 .xNext=next,.xEof=eof,.xColumn=column,.xRowid=rowid};
int main(int argc,char **argv){
 sqlite3 *db=0;char *error=0;int rc;
 if(argc!=2 || sqlite3_libversion_number()!=3053000)return 2;
 rc=sqlite3_open(argv[1],&db);
 if(rc==SQLITE_OK)rc=sqlite3_create_module(db,"cde_catalog_probe",&module,0);
 if(rc==SQLITE_OK)rc=sqlite3_exec(db,"CREATE TABLE healthy(id INTEGER PRIMARY KEY,body TEXT); CREATE VIRTUAL TABLE unavailable USING cde_catalog_probe;",0,0,&error);
 if(rc!=SQLITE_OK)fprintf(stderr,"%s\n",error?error:sqlite3_errmsg(db));
 else printf("%s\n%s\n",sqlite3_libversion(),sqlite3_sourceid());
 sqlite3_free(error);sqlite3_close(db);return rc;
}
