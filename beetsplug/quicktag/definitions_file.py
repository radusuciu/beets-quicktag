"""Persistence of :class:`CategoryDefinitions` as a YAML file.

The file has the same shape as the ``quicktag.categories`` config section
(a mapping of category name -> list of options), so it is hand-editable.
Key order is display order. Writes go through a temporary file in the same
directory followed by ``os.replace`` so a crash cannot leave a half-written
file behind.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

import yaml

from .definitions import CategoryDefinitions


class DefinitionsFileError(Exception):
    """The definitions file exists but cannot be used."""

    def __init__(self, path: Path, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path


def read_definitions_file(path: Path) -> CategoryDefinitions:
    """Parse ``path``. An empty file means "no categories"."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise DefinitionsFileError(path, str(error)) from error
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise DefinitionsFileError(path, f"invalid YAML: {error}") from error
    if data is None:
        data = {}
    if not isinstance(data, Mapping):
        raise DefinitionsFileError(
            path, "expected a mapping of category name -> list of options."
        )
    try:
        return CategoryDefinitions.from_config(data)
    except ValueError as error:
        raise DefinitionsFileError(path, str(error)) from error


def write_definitions_file(path: Path, definitions: CategoryDefinitions) -> None:
    """Atomically replace ``path`` with ``definitions``."""
    text = yaml.safe_dump(
        definitions.to_mapping(),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    fd, temp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def load_or_seed(
    path: Path, seed: Mapping[object, object] | None
) -> tuple[CategoryDefinitions | None, bool]:
    """Apply the load rules.

    1. ``path`` exists: it is authoritative, ``seed`` is ignored.
    2. ``path`` missing and ``seed`` non-empty: build from ``seed``, write
       ``path``, return ``created=True``.
    3. Both missing/empty: ``(None, False)``.

    A file that exists but does not parse raises :class:`DefinitionsFileError`
    and is never overwritten.
    """
    if path.exists():
        return read_definitions_file(path), False
    if not seed:
        return None, False
    definitions = CategoryDefinitions.from_config(seed)
    write_definitions_file(path, definitions)
    return definitions, True
