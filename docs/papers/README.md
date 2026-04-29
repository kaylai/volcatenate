# Manuscript PDFs for the wrapped models

This folder holds local copies of the published manuscripts for each model that volcatenate wraps. They are referenced from [`docs/references.md`](../references.md) via the MyST `{download}` role, which causes Sphinx to copy the file into the built site's `_downloads/` tree and emit a working download link on the rendered HTML page.

## Expected files

If a file is missing at build time, the link in the rendered docs will be broken. Add the PDF at the listed path and rebuild.

```
docs/papers/
├── dcompress/
│   ├── Burgisser2015.pdf            # Burgisser, Alleti & Scaillet (2015), Comp. & Geosci.
│   └── DCompress_User_Manual.pdf    # bundled with the D-Compress distribution
├── evo/
│   ├── Liggins2020.pdf              # Liggins, Shorttle & Rimmer (2020), EPSL 550, 116546
│   └── Liggins2022.pdf              # Liggins, Jordan, Rimmer & Shorttle (2022), JGR Planets 127
├── magec/
│   ├── SunLee2022.pdf               # Sun & Lee (2022), GCA 338, 302–321
│   └── SunYao2024.pdf               # Sun & Yao (2024), EPSL 638, 118742
├── sulfurx/
│   └── Ding2023.pdf                 # Ding, Plank, Wallace & Rasmussen (2023), G-Cubed 24
├── vesical/
│   ├── Iacovino2021_PartI.pdf       # Iacovino et al. (2021), Earth & Space Sci.
│   └── Wieser2022_PartII.pdf        # Wieser et al. (2022), Earth & Space Sci.
└── volfe/
    ├── Hughes2023_jgs.pdf           # Hughes et al. (2023), JGS 180(3), jgs2021–125
    └── Hughes_accepted_AmMin.pdf    # Hughes et al. (accepted), Am. Min.
```

This `README.md` itself is not rendered by Sphinx — the global `exclude_patterns` in `conf.py` already filters out `README.md`.
