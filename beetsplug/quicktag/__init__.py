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
                "autoplay_next": False,  # Default value if not in config
                "autoplay_start": False,  # Default value if not in config
                "autosave_on_quit": False,  # Default value if not in config
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
        autoplay_next_enabled = self.config["autoplay_next"].get(bool)
        autoplay_start_enabled = self.config["autoplay_start"].get(bool)
        autosave_on_quit_enabled = self.config["autosave_on_quit"].get(bool)

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
            autoplay_next_enabled,
            autoplay_start_enabled,
            autosave_on_quit_enabled,
        )
        app.run()
