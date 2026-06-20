# WH3 Ancillary Reference

A single-page, searchable reference for every equippable ancillary (item/follower) in
Total War: WARHAMMER III — rarity, effects, set bonuses, character locks, and the *full*
mechanical breakdown of any ability an item grants (active/passive, targeting, conditions,
Winds-of-Magic numbers, stat buffs, named on-hit effects, spell-cost modifiers, and ability
kind: summon / vortex / magic missile / bombardment).

`build_ancillary_page.py` reads an **extracted** copy of the game database and writes a
self-contained `ancillaries.html`.

## ⚠️ No game assets are included in this repository

This repo contains **only** the generator script and the HTML/CSS it produces — **no Creative
Assembly data, text, or images**. To build the icon-rich version you point the script at *your
own* extraction of the game files, which you are licensed to create by owning the game. Nothing
copyrighted is redistributed here or passes through this project.

## Usage

1. With [RPFM](https://github.com/Frodo45127/rpfm), extract the game's `db/`, `text/`, and the
   `ui/` icon folders into a directory (the script expects them under `fullExtraction/`).
2. Point `DB` (and, for icons, the `fullExtraction/` base) at your extraction near the top of
   `build_ancillary_page.py`.
3. Build:

   ```bash
   python3 build_ancillary_page.py            # full version, uses your local CA icons
   python3 build_ancillary_page.py --no-assets # asset-free: CSS placeholder icons, no images
   ```

   - `ancillaries.html` — full icons, for personal use (references your local game files).
   - `index.html` — **zero game assets**, a single portable file safe to host publicly
     (e.g. GitHub Pages). This is the build to share.

## Live demo

**https://seleucid-tools.github.io/wh3-ancillary-reference/**

Served from `index.html` via GitHub Pages. It has no external references and no CA art — just
text, CSS, and rarity-coloured placeholder icons — so it's safe to host publicly. Run the
script without `--no-assets` locally if you want the real game icons.

## Credits & disclaimer

Total War: WARHAMMER III and all associated names, data, and artwork are © Creative Assembly /
SEGA. This is an unofficial, non-commercial fan reference tool and is not affiliated with or
endorsed by Creative Assembly or SEGA. Game icons, when present, are rendered from the user's
own legally-obtained game files and are not distributed with this project.

*(Not legal advice — provided as the rationale for the assets-stay-local design.)*
