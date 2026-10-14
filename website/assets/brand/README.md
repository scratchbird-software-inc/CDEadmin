# Family icon source

These SVGs come from named groups in the owner-maintained
`/home/dcalford/Sandbox/ScratchBirdLogos.svg`. The DDN sister project's
`tools/build-brand.mjs` produced the checked-in SVG copies at DDN revision
`babd5f8a`; revision `92daf754` added the ICO exports.
Each `-dark.svg` swaps blue and white for use against the navy family background.
Do not edit a copied path independently of its source group and paired variant.

Each normal and `-dark` ICO contains transparent 16, 24, 32, 48, 64, 128 and
256 px frames. `favicon.ico` is a copy of `scratchrobin.ico`. Regenerate the
ICO files from the checked-in SVGs with the sister project's
`python3 tools/build-ico.py --source-dir /path/to/website/assets/brand --favicon scratchrobin`,
or copy a freshly generated family set from DDN and reset the favicon alias.
