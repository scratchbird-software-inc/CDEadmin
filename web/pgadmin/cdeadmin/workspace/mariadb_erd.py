"""Map native MariaDB relations into shared public DDN graph notation."""
from .mysql_erd import build_diagram as _build


def build_diagram(resources, provenance):
    return _build(resources, provenance, engine='mariadb')
