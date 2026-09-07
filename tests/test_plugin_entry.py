"""`beet quicktag` startup: categories file resolution and load rules."""

import optparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import confuse
import pytest
import yaml
from beets.library import Library
from beets.ui import UserError

from beetsplug.quicktag import DEFAULT_CONFIG, QuickTagPlugin
from beetsplug.quicktag.definitions import CategoryDefinitions


def make_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **values: object
) -> QuickTagPlugin:
    """A plugin whose config lives in a private confuse root.

    ``confuse.Filename(in_app_dir=True)`` resolves against the root's config
    dir, which for a ``Configuration("quicktagtest")`` is ``$QUICKTAGTESTDIR``.
    """
    monkeypatch.setenv("QUICKTAGTESTDIR", str(tmp_path))
    config = confuse.Configuration("quicktagtest", read=False)
    config.add(DEFAULT_CONFIG)
    config.set(values)
    plugin = QuickTagPlugin()
    plugin.config = config
    return plugin


def run(plugin: QuickTagPlugin, lib: Library) -> MagicMock:
    """Run the command with the app class replaced; returns the mock class."""
    with patch("beetsplug.quicktag.QuickTagApp") as app_class:
        plugin.run_quicktag(lib, optparse.Values(), [])
    return app_class


class TestDefaults:
    def test_categories_file_default(self) -> None:
        plugin = QuickTagPlugin()
        assert plugin.config["categories_file"].get(str) == "quicktag_categories.yaml"


class TestLoadRules:
    def test_seeds_file_from_config_and_says_so(
        self,
        temp_beets_library: Library,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        plugin = make_plugin(
            tmp_path, monkeypatch, categories={"mood": ["happy", "sad"]}
        )
        app_class = run(plugin, temp_beets_library)

        expected_path = tmp_path / "quicktag_categories.yaml"
        assert yaml.safe_load(expected_path.read_text()) == {"mood": ["happy", "sad"]}
        out = capsys.readouterr().out
        assert str(expected_path) in out
        assert "no longer" in out
        kwargs = app_class.call_args.kwargs
        assert isinstance(kwargs["definitions"], CategoryDefinitions)
        assert kwargs["definitions"].options("mood") == ["happy", "sad"]
        assert kwargs["definitions_path"] == expected_path
        app_class.return_value.run.assert_called_once()

    def test_existing_file_wins_silently(
        self,
        temp_beets_library: Library,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (tmp_path / "quicktag_categories.yaml").write_text(
            yaml.safe_dump({"mood": ["from_file"]})
        )
        plugin = make_plugin(tmp_path, monkeypatch, categories={"mood": ["cfg"]})
        app_class = run(plugin, temp_beets_library)
        assert app_class.call_args.kwargs["definitions"].options("mood") == [
            "from_file"
        ]
        assert "no longer" not in capsys.readouterr().out

    def test_absolute_categories_file_path_is_used_as_is(
        self,
        temp_beets_library: Library,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        elsewhere = tmp_path / "elsewhere" / "cats.yaml"
        elsewhere.parent.mkdir()
        plugin = make_plugin(
            tmp_path,
            monkeypatch,
            categories={"mood": ["a"]},
            categories_file=str(elsewhere),
        )
        app_class = run(plugin, temp_beets_library)
        assert elsewhere.exists()
        assert app_class.call_args.kwargs["definitions_path"] == elsewhere

    def test_both_missing_prints_help_and_does_not_launch(
        self,
        temp_beets_library: Library,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        plugin = make_plugin(tmp_path, monkeypatch)
        app_class = run(plugin, temp_beets_library)
        app_class.assert_not_called()
        out = capsys.readouterr().out
        assert "No categories defined" in out
        assert "quicktag_categories.yaml" in out
        assert not (tmp_path / "quicktag_categories.yaml").exists()

    @pytest.mark.parametrize("text", ["", "{}\n", "# nothing yet\n"])
    def test_empty_file_launches_with_a_notice(
        self,
        temp_beets_library: Library,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        text: str,
    ) -> None:
        """The file wins even when empty, so say why the config is ignored."""
        path = tmp_path / "quicktag_categories.yaml"
        path.write_text(text)
        plugin = make_plugin(tmp_path, monkeypatch, categories={"mood": ["cfg"]})
        app_class = run(plugin, temp_beets_library)
        app_class.return_value.run.assert_called_once()
        assert app_class.call_args.kwargs["definitions"].categories == []
        out = capsys.readouterr().out
        assert str(path) in out
        assert "no categories" in out
        assert "ignored" in out
        assert "ctrl+n" in out

    def test_unparseable_file_stops_with_path(
        self,
        temp_beets_library: Library,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        path = tmp_path / "quicktag_categories.yaml"
        path.write_text("mood: [happy\n")
        plugin = make_plugin(tmp_path, monkeypatch, categories={"mood": ["a"]})
        with pytest.raises(UserError, match="quicktag_categories.yaml"):
            run(plugin, temp_beets_library)
        assert path.read_text() == "mood: [happy\n"

    def test_unwritable_seed_target_is_a_user_error(
        self,
        temp_beets_library: Library,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The config dir may not be writable; that must not be a traceback."""
        plugin = make_plugin(
            tmp_path,
            monkeypatch,
            categories={"mood": ["a"]},
            categories_file=str(tmp_path / "missing" / "cats.yaml"),
        )
        with pytest.raises(UserError, match="cannot write"):
            run(plugin, temp_beets_library)

    def test_invalid_seed_is_a_user_error(
        self,
        temp_beets_library: Library,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        plugin = make_plugin(tmp_path, monkeypatch, categories={"mood": "happy"})
        with pytest.raises(UserError, match="bare string"):
            run(plugin, temp_beets_library)

    def test_fixed_field_warning_is_printed(
        self,
        temp_beets_library: Library,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        plugin = make_plugin(tmp_path, monkeypatch, categories={"album": ["a"]})
        run(plugin, temp_beets_library)
        assert "built-in beets field" in capsys.readouterr().out

    def test_no_tracks_short_circuits(
        self,
        temp_beets_library: Library,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        plugin = make_plugin(tmp_path, monkeypatch, categories={"mood": ["a"]})
        with patch("beetsplug.quicktag.QuickTagApp") as app_class:
            plugin.run_quicktag(
                temp_beets_library, optparse.Values(), ["title:nothing-matches"]
            )
        app_class.assert_not_called()
        assert "No tracks found" in capsys.readouterr().out

    def test_query_is_passed_to_the_app(
        self,
        temp_beets_library: Library,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        plugin = make_plugin(tmp_path, monkeypatch, categories={"mood": ["a"]})
        with patch("beetsplug.quicktag.QuickTagApp") as app_class:
            plugin.run_quicktag(temp_beets_library, optparse.Values(), ["artist:Test"])
        assert app_class.call_args.kwargs["query"] == ["artist:Test"]
