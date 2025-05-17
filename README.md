# Beets QuickTag Plugin

This is a plugin for [beets](https://beets.io/) that scratches my own itch to categorize my music using custom tags, for DJing, as efficiently as possible.

It's a work in progress though much of the functionality is already there. I initially prototyped this using Claude 3.7 and Gemini 2.5 Pro Preview but ended up re-working quite a bit of it.

TODO:
- add tests
- add rating or energy level widget
- consider bundling libmpv
- automate releases
- test on Windows

## Configuration

Add a `quicktag` section to your beets `config.yaml`. Here's an example:

```yaml

quicktag:
  autoplay_start: yes
  autoplay_next: no
  autosave_on_quit: yes
  categories:
    collection:
      - DJ
      - Sample
    mood:
      - happy
      - sad
      - bright
      - dark
      - angry
```

## Credits

This was inspired by the Quick Tag functionality in [One Tagger](https://onetagger.github.io/), which is an excellent application. One Tagger also has [a spreadsheet](https://docs.google.com/spreadsheets/d/1wYokScjoS5Xb1IvqFMXbSbknrXJ7bySLLihTucOS4qY/edit?gid=0#gid=0) that might provide inspiration from existing systems to categorize tracks in this way. I believe the One Tagger system, or at least the default categories it has, are inspired by [a reddit post by u/nonomomomo](https://www.reddit.com/r/DJs/comments/c3o2jk/my_ultimate_track_tagging_system_the_little_data/).