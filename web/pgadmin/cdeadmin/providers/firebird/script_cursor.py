"""Native isql-style preparation and auxiliary DDL transaction routing."""
from .query_dialect import DialectCursor
from .temporal_arrays import cursor


class ScriptCursor(DialectCursor):
    def __init__(self, runtime, dialect):
        super().__init__(runtime.handle, dialect)
        self.runtime = runtime
        self.automatic_ddl = False

    def execute(self, source, parameters=None):
        from firebird.driver import StatementType

        main = self.connection.main_transaction
        if not main.is_active():
            main.begin()
        ddl = self.runtime.ddl_transaction()
        statement = self.prepare(source, ddl)
        self.automatic_ddl = statement.type in (
            StatementType.DDL, StatementType.SET_GENERATOR)
        if self.automatic_ddl:
            self.cursor.close()
            self.cursor = cursor(self.connection, ddl)
            self.cursor._dialect = self.dialect
        self.cursor.shared_materialization_budget = self.runtime.budget
        self.cursor.execute(statement, parameters)
        return self
