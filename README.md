# Deck of Many NPCs homebrew extractor

Builds a homebrew file for [Deck of Many NPCs](https://play.google.com/store/apps/details?id=com.roshambo.deckofmanynpcs)
from a local copy of structured D&D 5e rules data. It covers what the app
doesn't ship because it isn't in the SRD 5.2.1: classes, subclasses, species, feats,
spells, backgrounds, equipment and monsters from the books listed below,.

## Requirements

- Python 3, standard library only. Tested with 3.9 and 3.14.
- A local copy of the source data. The script doesn't include or download any
  of it, and expects a `data` folder laid out like this:

  ```
  data/
    backgrounds.json  feats.json  races.json  items.json  items-base.json
    fluff-backgrounds.json  fluff-races.json
    class/     class-*.json, fluff-class-*.json
    spells/    spells-*.json, sources.json
    bestiary/  bestiary-*.json
  ```

## Usage

```
python3 extract_homebrew.py /path/to/data
```

Pass the `data` folder, or the folder that contains it. The script writes
`homebrew.json` to the current directory and prints what it extracted, which
printing it kept when a book reprints something, and anything it skipped.

To load the file, open Homebrew Content in the app and choose
Import/Export Homebrew Content.

## What it extracts

Only entries outside the SRD 5.2.1 are written; the app already includes the
SRD. When the same thing is printed in more than one book, the newest printing
wins, so a 2024-era book beats a 2014-era one.

| Section | Books |
|---|---|
| Classes |EFA, TCE |
| Subclasses, equipment | PHB 2024\*, AU, EFA, RHW, FRHoF, TCE, XGE |
| Spells | PHB 2024\*, AU, EFA, FRHoF, TCE, XGE |
| Feats, backgrounds | PHB 2024\*, AU, EFA, RHW, FRHoF |
| Species | EFA, RHW, MPMM |
| Monsters | MM 2025\*, PHB 2024\*, AU, EFA, FRAiF, FRHoF, RHW, MPMM, TCE, XGE |

\* Non-SRD entries only.

PHB 2024 is the 2024 Player's Handbook, MM 2025 the 2025 Monster Manual, AU
Arcana Unleashed, EFA Eberron: Forge of the Artificer, RHW Ravenloft: The
Horrors Within, FRHoF Forgotten Realms: Heroes of Faerûn, FRAiF Forgotten
Realms: Adventures in Faerûn, TCE Tasha's Cauldron of Everything, XGE
Xanathar's Guide to Everything, and MPMM Mordenkainen Presents: Monsters of the
Multiverse.

Spells a feat, subclass or class grants come out as grants the app hands to
an NPC: a domain's or patron's spell table goes on the feature that confers
it, arriving tier by tier as the NPC levels. Grants the app can't state are
left out, and the feature text still describes them: a spell chosen by school,
a choice between named options (a Genie's kind, say), and spells gated on
spell-slot level, cast only as rituals, or paid for with a resource.

Monsters come out as full stat blocks in the app's format, spellcasting and
legendary actions included. Creatures without fixed statistics are skipped,
mostly summons whose numbers scale with the spell's level; the script lists
each one when it runs.

## Legal

This script contains no game text: everything in `homebrew.json` comes from


## Tests

```
python3 -m doctest extract_homebrew.py
```
