"""UTF8 DPB text independently of SQL attachment and storage charsets."""


def build(core, options, *, for_create=False):
    requested = options.get('charset')
    options = dict(options, utf8filename=True)
    if requested == 'UTF8':
        return core.DPB(**options).get_buffer(for_create=for_create)
    native = core.DPB(**dict(options, charset='UTF8', utf8filename=True))
    buffer = native.get_buffer(for_create=for_create)
    with core.a.get_api().util.get_xpb_builder(
            core.XpbKind.DPB, buffer) as builder:
        while builder.find_first(core.DPBItem.LC_CTYPE):
            builder.remove_current()
        if requested:
            builder.insert_string(core.DPBItem.LC_CTYPE, requested)
        if for_create:
            while builder.find_first(core.DPBItem.SET_DB_CHARSET):
                builder.remove_current()
            default = options.get('db_charset')
            if default is None:
                default = requested
            if default:
                builder.insert_string(core.DPBItem.SET_DB_CHARSET, default)
        return builder.get_buffer()
