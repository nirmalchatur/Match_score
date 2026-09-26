Typography is loaded from Google Fonts - there are no font binaries in
this repository and none are needed.

The site uses four families (see index.html for the <link> tags):

  Instrument Serif   400 + italic   ->  --serif    (headlines, wordmark)
  Archivo            400-700        ->  --display  (headings, numerals)
  Inter Tight        400-600        ->  --sans     (UI, body copy)
  JetBrains Mono     400-500        ->  --mono     (labels, scores, data)

Each stack in src/index.css ends in a real system face, so a blocked or
offline CDN degrades cleanly instead of leaving text invisible.

A previous iteration referenced "Wavehaus Sans" (a commercial typeface
by Graham Paterson, never licensed into this repo). It was removed
because the @font-face rules pointed at files that do not exist here,
so every page load fired four guaranteed 404s before falling back to a
system font anyway.

To self-host instead, drop .woff2 files in this folder and add
@font-face rules in src/index.css, listing the family name first in the
corresponding custom property.
