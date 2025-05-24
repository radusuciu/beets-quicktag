import optparse

from beets import ui
from beets.dbcore.db import Results as BeetsResults
from beets.library import Library as BeetsLibrary
from beets.plugins import BeetsPlugin

from .app import QuickTagApp


class QuickTagPlugin(BeetsPlugin):
    def __init__(self):
        super(QuickTagPlugin, self).__init__()
        self.config.add(
            {
                "categories": {},
                "autoplay_on_track_change": False,
                "autoplay_at_launch": False,
                "autonext_at_track_end": False,
                "autosave_on_quit": False,
                "keep_playing_on_track_change_if_playing": True,
            }
        )

    def commands(self):
        cmd = ui.Subcommand(
            "quicktag",
            help="Quickly tag tracks with predefined options.",
            aliases=["qt"],
        )
        cmd.func = self.run_quicktag
        return [cmd]

    def run_quicktag(self, lib: BeetsLibrary, opts: optparse.Values, args):
        query = ui.decargs(args)
        items: BeetsResults = lib.items(query)

        if not items:
            ui.print_("No tracks found to tag.")
            return

        categories_config = self.config["categories"].get(dict)
        autoplay_on_track_change_enabled = self.config["autoplay_on_track_change"].get(
            bool
        )
        autoplay_at_launch_enabled = self.config["autoplay_at_launch"].get(bool)
        autonext_at_track_end_enabled = self.config["autonext_at_track_end"].get(bool)
        autosave_on_quit_enabled = self.config["autosave_on_quit"].get(bool)
        keep_playing_on_track_change_if_playing_enabled = self.config["keep_playing_on_track_change_if_playing"].get(bool)

        if not categories_config:
            ui.print_(
                "No categories defined in the configuration. Please configure the quicktag plugin."
            )
            ui.print_("Example configuration:")
            ui.print_("quicktag:")
            ui.print_("  categories:")
            ui.print_("    mood: [happy, sad, energetic, calm]")
            ui.print_(
                "    genre_custom: [electronic, ambient, experimental, soundtrack]"
            )
            return

        categories = list(categories_config.items())

        app = QuickTagApp(
            lib,
            items,
            categories,
            autoplay_on_track_change_enabled,
            autoplay_at_launch_enabled,
            autonext_at_track_end_enabled,
            autosave_on_quit_enabled,
            keep_playing_on_track_change_if_playing_enabled,
        )
        app.run()
