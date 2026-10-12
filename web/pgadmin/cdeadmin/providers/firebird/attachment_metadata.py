"""Attachment-local metadata decoding for the native interface facade."""


class _Interface:
    """Forward native pointer and ownership operations without extra refs."""

    def __init__(self, native, encoding):
        self.native = native
        self.encoding = encoding

    def __getattr__(self, name):
        return getattr(self.native, name)

    def __enter__(self):
        self.native.__enter__()
        return self

    def __exit__(self, *args):
        return self.native.__exit__(*args)


class Metadata(_Interface):
    def _text(self, method, index):
        raw = getattr(self.native.vtable, method)(
            self.native, self.native.status, index)
        self.native._check()
        return raw.decode(self.encoding)

    def get_field(self, index):
        return self._text('getField', index)

    def get_relation(self, index):
        return self._text('getRelation', index)

    def get_owner(self, index):
        return self._text('getOwner', index)

    def get_alias(self, index):
        return self._text('getAlias', index)

    def get_builder(self):
        return Builder(self.native.get_builder(), self.encoding)


class Builder(_Interface):
    def get_metadata(self):
        return Metadata(self.native.get_metadata(), self.encoding)


class Statement(_Interface):
    def _metadata(self, native, *, output=False):
        from .fss_codec import NAME
        if self.encoding != NAME:
            return Metadata(native, self.encoding)
        from firebird.driver.types import SQLDataType
        # FSS SQL/identifiers retain their native encoding; data messages use
        # explicit UTF8 to avoid native FSS validation/narrowing
        # inconsistencies.
        with native, native.get_builder() as builder:
            for index in range(native.get_count()):
                kind = native.get_type(index)
                if output and kind == SQLDataType.BLOB:
                    # Native FSS BLOB output cannot be rebound through a
                    # second conversion without invalidating virtual IDs.
                    continue
                if native.get_charset(index) != 3 or kind not in (
                        SQLDataType.TEXT, SQLDataType.VARYING,
                        SQLDataType.BLOB):
                    continue
                builder.set_charset(index, 4)
                if kind != SQLDataType.BLOB:
                    builder.set_length(
                        index, ((native.get_length(index) + 2) // 3) * 4)
            result = builder.get_metadata()
        return Metadata(result, self.encoding)

    def get_input_metadata(self):
        return self._metadata(self.native.get_input_metadata())

    def get_output_metadata(self):
        return self._metadata(self.native.get_output_metadata(), output=True)

    def get_plan(self, detailed):
        raw = self.native.vtable.getPlan(
            self.native, self.native.status, detailed)
        self.native._check()
        return raw.decode(self.encoding) if raw else raw


class Attachment(_Interface):
    def prepare(self, *args, **kwargs):
        return Statement(self.native.prepare(*args, **kwargs), self.encoding)


def install(connection):
    """Install once on a native owned connection without changing finality."""
    from firebird.driver.core import Connection

    if (isinstance(connection, Connection) and
            not isinstance(connection._att, Attachment)):
        from .attachment_charset import observe
        observe(connection)
        connection._att = Attachment(connection._att, connection._encoding)
        if connection.charset == 'UNICODE_FSS':
            connection._encoding = 'utf8'
            connection._ic._encoding = 'utf8'
