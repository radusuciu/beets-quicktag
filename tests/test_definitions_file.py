"""The YAML definitions file: read, atomic write, seeding rules (§3.2)."""

from pathlib import Path

import pytest
import yaml

from beetsplug.quicktag.definitions import CategoryDefinitions
from beetsplug.quicktag.definitions_file import (
    DefinitionsFileError,
    load_or_seed,
    read_definitions_file,
    write_definitions_file,
)


class TestReadWrite:
    def test_write_then_read_round_trips_in_order(self, tmp_path: Path) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        defs = CategoryDefinitions.from_config(
            {"mood": ["happy", "sad"], "vibe": ["afro"], "fresh": []}
        )
        write_definitions_file(path, defs)
        assert read_definitions_file(path).to_mapping() == defs.to_mapping()

    def test_file_is_plain_block_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        write_definitions_file(
            path, CategoryDefinitions.from_config({"mood": ["happy", "café"]})
        )
        text = path.read_text(encoding="utf-8")
        assert text == "mood:\n- happy\n- café\n"

    def test_write_leaves_no_temp_file_behind(self, tmp_path: Path) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        write_definitions_file(path, CategoryDefinitions.from_config({"m": ["a"]}))
        assert [p.name for p in tmp_path.iterdir()] == ["quicktag_categories.yaml"]

    def test_write_replaces_existing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        write_definitions_file(path, CategoryDefinitions.from_config({"m": ["a"]}))
        write_definitions_file(path, CategoryDefinitions.from_config({"m": ["b"]}))
        assert read_definitions_file(path).options("m") == ["b"]

    def test_write_keeps_the_existing_file_mode(self, tmp_path: Path) -> None:
        """The temp file is 0600; replacing a hand-created file must not
        silently tighten its permissions."""
        path = tmp_path / "quicktag_categories.yaml"
        path.write_text("m: [a]\n", encoding="utf-8")
        path.chmod(0o644)
        write_definitions_file(path, CategoryDefinitions.from_config({"m": ["b"]}))
        assert path.stat().st_mode & 0o777 == 0o644

    def test_write_failure_raises_oserror(self, tmp_path: Path) -> None:
        missing_dir = tmp_path / "nope" / "quicktag_categories.yaml"
        with pytest.raises(OSError):
            write_definitions_file(
                missing_dir, CategoryDefinitions.from_config({"m": ["a"]})
            )

    def test_empty_file_is_empty_definitions(self, tmp_path: Path) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        path.write_text("", encoding="utf-8")
        assert read_definitions_file(path).categories == []

    def test_unparseable_file_raises_with_path(self, tmp_path: Path) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        path.write_text("mood: [happy, sad\n", encoding="utf-8")
        with pytest.raises(DefinitionsFileError) as excinfo:
            read_definitions_file(path)
        assert excinfo.value.path == path
        assert "quicktag_categories.yaml" in str(excinfo.value)

    def test_non_mapping_file_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        path.write_text("- happy\n- sad\n", encoding="utf-8")
        with pytest.raises(DefinitionsFileError, match="mapping"):
            read_definitions_file(path)

    def test_invalid_definitions_raise_file_error(self, tmp_path: Path) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        path.write_text("mood: happy\n", encoding="utf-8")
        with pytest.raises(DefinitionsFileError, match="bare string"):
            read_definitions_file(path)


class TestLoadOrSeed:
    def test_file_wins_over_seed(self, tmp_path: Path) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        path.write_text(yaml.safe_dump({"mood": ["from_file"]}), encoding="utf-8")
        defs, created = load_or_seed(path, {"mood": ["from_config"]})
        assert created is False
        assert defs is not None
        assert defs.options("mood") == ["from_file"]

    def test_missing_file_is_seeded_and_written(self, tmp_path: Path) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        defs, created = load_or_seed(path, {"mood": ["happy"]})
        assert created is True
        assert defs is not None
        assert defs.options("mood") == ["happy"]
        assert read_definitions_file(path).to_mapping() == {"mood": ["happy"]}

    @pytest.mark.parametrize("seed", [None, {}])
    def test_both_missing_returns_none(
        self, tmp_path: Path, seed: dict[object, object] | None
    ) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        assert load_or_seed(path, seed) == (None, False)
        assert not path.exists()

    def test_invalid_seed_propagates_value_error(self, tmp_path: Path) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        with pytest.raises(ValueError, match="bare string"):
            load_or_seed(path, {"mood": "happy"})
        assert not path.exists()

    def test_unparseable_file_is_never_reseeded(self, tmp_path: Path) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        path.write_text("mood: [happy, sad\n", encoding="utf-8")
        with pytest.raises(DefinitionsFileError):
            load_or_seed(path, {"mood": ["happy"]})
        assert path.read_text(encoding="utf-8") == "mood: [happy, sad\n"
