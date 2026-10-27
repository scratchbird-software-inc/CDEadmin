from collections import namedtuple

_ColumnMetadata = namedtuple(
    "ColumnMetadata", ["name", "datatype", "foreignkeys", "default",
                       "has_default", "system_column"]
)


def ColumnMetadata(name, datatype, foreignkeys=None, default=None,
                   has_default=False, system_column=False):
    return _ColumnMetadata(name, datatype, foreignkeys or [], default,
                           has_default, system_column)


ForeignKey = namedtuple(
    "ForeignKey",
    [
        "parentschema",
        "parenttable",
        "parentcolumn",
        "childschema",
        "childtable",
        "childcolumn",
    ],
)
TableMetadata = namedtuple("TableMetadata", "name columns")


def parse_defaults(defaults_string):
    """Split native default expressions with PostgreSQL's grammar, not commas."""
    if not defaults_string:
        return
    if not isinstance(defaults_string, str) or len(defaults_string.encode('utf8')) > 1024 * 1024:
        raise ValueError('Native routine defaults exceed the completion limit')
    from pglast import parse_sql, ast
    from pglast.stream import RawStream
    parsed = parse_sql('SELECT ' + defaults_string)
    if len(parsed) != 1 or not isinstance(parsed[0].stmt, ast.SelectStmt):
        raise ValueError('Invalid native routine defaults')
    statement = parsed[0].stmt
    if any(getattr(statement, field) not in (None, False, 0, ())
           for field in statement if field != 'targetList'):
        raise ValueError('Invalid native routine default expressions')
    for target in statement.targetList or ():
        if target.name:
            raise ValueError('Invalid native routine default expression alias')
        yield RawStream()(target.val)


class FunctionMetadata:
    def __init__(
        self,
        schema_name,
        func_name,
        arg_names,
        arg_types,
        arg_modes,
        return_type,
        is_aggregate,
        is_window,
        is_set_returning,
        is_extension,
        arg_defaults,
    ):
        """Class for describing a postgresql function"""

        self.schema_name = schema_name
        self.func_name = func_name

        self.arg_modes = tuple(arg_modes) if arg_modes else None
        self.arg_names = tuple(arg_names) if arg_names else None

        # Be flexible in not requiring arg_types -- use None as a placeholder
        # for each arg. (Used for compatibility with old versions of postgresql
        # where such info is hard to get.
        if arg_types:
            self.arg_types = tuple(arg_types)
        elif arg_modes:
            self.arg_types = tuple([None] * len(arg_modes))
        elif arg_names:
            self.arg_types = tuple([None] * len(arg_names))
        else:
            self.arg_types = None

        self.arg_defaults = tuple(parse_defaults(arg_defaults))

        self.return_type = return_type.strip()
        self.is_aggregate = is_aggregate
        self.is_window = is_window
        self.is_set_returning = is_set_returning
        self.is_extension = bool(is_extension)
        self.is_public = self.schema_name and self.schema_name == "public"

    def __eq__(self, other):
        return isinstance(other, self.__class__) and \
            self.__dict__ == other.__dict__

    def __ne__(self, other):
        return not self.__eq__(other)

    def _signature(self):
        return (
            self.schema_name,
            self.func_name,
            self.arg_names,
            self.arg_types,
            self.arg_modes,
            self.return_type,
            self.is_aggregate,
            self.is_window,
            self.is_set_returning,
            self.is_extension,
            self.arg_defaults,
        )

    def __hash__(self):
        return hash(self._signature())

    def __repr__(self):
        return (
            "%s(schema_name=%r, func_name=%r, arg_names=%r, "
            "arg_types=%r, arg_modes=%r, return_type=%r, is_aggregate=%r, "
            "is_window=%r, is_set_returning=%r, is_extension=%r, "
            "arg_defaults=%r)"
        ) % ((self.__class__.__name__,) + self._signature())

    def has_variadic(self):
        return self.arg_modes and \
            any(arg_mode == "v" for arg_mode in self.arg_modes)

    def args(self):
        """Returns a list of input-parameter ColumnMetadata namedtuples."""
        if not self.arg_names:
            return []
        modes = self.arg_modes or ["i"] * len(self.arg_names)
        args = [
            (name, typ)
            for name, typ, mode in zip(self.arg_names, self.arg_types, modes)
            if mode in ("i", "b", "v")  # IN, INOUT, VARIADIC
        ]

        def arg(name, typ, num):
            num_args = len(args)
            num_defaults = len(self.arg_defaults)
            has_default = num + num_defaults >= num_args
            default = (
                self.arg_defaults[num - num_args + num_defaults]
                if has_default
                else None
            )
            return ColumnMetadata(name, typ, [], default, has_default)

        return [arg(name, typ, num) for num, (name, typ) in enumerate(args)]

    def fields(self):
        """Returns a list of output-field ColumnMetadata namedtuples"""

        if self.return_type.lower() == "void":
            return []
        elif not self.arg_modes:
            # For functions  without output parameters, the function name
            # is used as the name of the output column.
            # E.g. 'SELECT unnest FROM unnest(...);'
            return [ColumnMetadata(self.func_name, self.return_type, [])]

        return [
            ColumnMetadata(name, typ, [])
            for name, typ, mode in zip(self.arg_names, self.arg_types,
                                       self.arg_modes)
            if mode in ("o", "b", "t")
        ]  # OUT, INOUT, TABLE
