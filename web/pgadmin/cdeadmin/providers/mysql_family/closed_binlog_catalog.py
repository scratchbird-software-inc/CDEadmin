"""Observe native closed logs without classifying a rotated active file as closed."""
from .mysql_clone import rows
from .mysql_binlog_archives import BinlogArchiveError


def observe(connection,status_statement):
    if status_statement not in {'SHOW MASTER STATUS','SHOW BINARY LOG STATUS'}:
        raise BinlogArchiveError('Select the native binary-log status contract')
    for _attempt in range(3):
        before=rows(connection,status_statement)
        logs=rows(connection,'SHOW BINARY LOGS')
        after=rows(connection,status_statement)
        if len(before)!=1 or len(after)!=1 or not logs:continue
        current=after[0];names=[row['Log_name'] for row in logs]
        if before[0]['File']!=current['File'] or names[-1]!=current['File'] or len(set(names))!=len(names):continue
        current['Position']=str(current['Position'])
        for row in logs:
            row['File_size']=str(row['File_size']);row['closed']=row['Log_name']!=current['File']
        return current,logs
    raise BinlogArchiveError('Native binary-log catalog changed during observation; inspect it again before selecting closed logs')
