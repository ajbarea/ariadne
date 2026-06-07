"""Register a ratified mapping.toml as a dataset (ADR-0025, the "apply" step).

A ratified mapping.toml carries a ``[dataset]`` header (name + ``dsn_env``) plus the
structural ``[[entities]]``/``[[relationships]]`` (``mapping/schema.py``). Discovery
scans the opt-in ``ARIADNE_MAPPINGS`` directory and registers one
``MappingDrivenAdapter`` per file, so ``--dataset <name>`` resolves for
``index``/``workup``/``eval`` unchanged. The source DSN is read **lazily** from env
at ``load()`` time (only ``index`` reads rows); ``workup``/``eval`` register the
adapter but never open the source DB. The connection string stays off argv.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ariadne.datasets.base import register as _register
from ariadne.introspect.postgres import postgres_row_reader
from ariadne.mapping.adapter import MappingDrivenAdapter
from ariadne.mapping.schema import load_dataset_header, load_mapping_toml

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


def resolve_source_dsn(env: Mapping[str, str], dsn_env: str) -> str:
    dsn = env.get(dsn_env)
    if not dsn:
        raise RuntimeError(
            f"source DSN env var {dsn_env!r} is unset; export it to the read-only "
            "source connection string before indexing this dataset"
        )
    return dsn


def lazy_row_reader(
    env: Mapping[str, str],
    dsn_env: str,
    schema: str,
    *,
    connect: Callable[[str], Any] | None = None,
) -> Callable[[str], list[dict]]:
    """A ``RowReader`` that opens a short-lived read-only connection per table, lazily.

    Nothing connects until a row is actually read, so ``workup``/``eval`` (which never
    call ``load()``) never touch the source DB; only ``index`` does. The DSN is
    resolved from env at read time and is never placed on argv.
    """
    import psycopg

    open_conn = connect or psycopg.connect

    def read(table: str) -> list[dict]:
        with open_conn(resolve_source_dsn(env, dsn_env)) as conn:
            return postgres_row_reader(conn, schema)(table)

    return read


def discover_and_register(
    env: Mapping[str, str],
    *,
    register: Callable[[Any], None] | None = None,
    connect: Callable[[str], Any] | None = None,
) -> list[str]:
    """Register one ``MappingDrivenAdapter`` per ``*.toml`` under ``ARIADNE_MAPPINGS``.

    Opt-in: unset ``ARIADNE_MAPPINGS`` registers nothing (returns ``[]``). Each file
    must carry a ``[dataset]`` header (it cannot otherwise be named or connected);
    a header-less file is an error. Returns the registered dataset names.
    """
    do_register = register or _register
    mappings_dir = env.get("ARIADNE_MAPPINGS")
    if not mappings_dir:
        return []
    names: list[str] = []
    for path in sorted(Path(mappings_dir).glob("*.toml")):
        text = path.read_text(encoding="utf-8")
        header = load_dataset_header(text)
        if header is None:
            raise ValueError(f"{path}: ratified mapping is missing its [dataset] header")
        reader = lazy_row_reader(env, header.dsn_env, header.schema, connect=connect)
        do_register(
            MappingDrivenAdapter(
                name=header.name, mapping=load_mapping_toml(text), read_rows=reader
            )
        )
        names.append(header.name)
    return names
