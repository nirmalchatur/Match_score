import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement> & { size?: number }

function Svg({ size = 18, children, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  )
}

/**
 * The TailorUp mark: a resume sheet being fitted to a role.
 *
 * History, because it explains the constraints
 * ---------------------------------------------
 * Three previous marks: a lightning bolt, a four-pointed sparkle, and a plain
 * document with a cut corner. The bolt and the sparkle were the universal
 * "AI product" glyphs and said nothing about what this tool does. The document
 * was better but too generic -- it read as "file viewer", and with a high-
 * contrast serif wordmark beside it the whole lockup drifted toward editorial
 * or lifestyle branding rather than a hiring tool.
 *
 * What the mark has to do
 * -----------------------
 * Name the product's actual subject in one shape: a resume, checked against a
 * role. So the mark is a sheet on the left and a crosshair on the right, and
 * the crosshair's centre dot sits on the sheet's edge -- the sheet is what is
 * being aimed at, which is the entire product in one image.
 *
 * Why a crosshair and not a checkmark
 * ----------------------------------
 * A tick says "approved". A crosshair says "matched against something", which
 * is what actually happens: the resume is compared to a posting and scored, and
 * the honest answer is usually a range, not a verdict. It also avoids the
 * checkmark that half the applicant-tracking tools on the market already use.
 *
 * Geometric, not ornamental
 * -------------------------
 * Every element is axis-aligned or a true circle, and the only diagonal in the
 * mark is the crosshair. That is what separates it from the "beauty brand"
 * register -- soft curves, thin scripts, high-contrast serif -- that this mark
 * was previously reading as. Stroke weight is 1.9 rather than 1.5 so the
 * silhouette survives at favicon size, where a thinner line greys out.
 */
export const IconLogo = (p: IconProps) => (
  <Svg {...p} strokeWidth={1.9}>
    {/* The resume sheet. A rect rather than a cut-corner path: the dog-ear was
        the old mark's only distinguishing feature and it read as stationery.
        A plain rect is what a resume looks like to anyone who has ever made
        one. */}
    <rect x="2.75" y="4.75" width="12" height="14.5" rx="1.5" />
    {/* Three rules at decreasing width: the shape of a filled-in document
        rather than a rectangle of nothing. The third is the shortest, which
        reads as a closing line and keeps the block from looking like a
        table. */}
    <path d="M5.75 9h6" />
    <path d="M5.75 12.25h6" />
    <path d="M5.75 15.5h3.5" />
    {/* The crosshair. Two short rules and a closed circle, centred on the
        sheet's right edge so the two halves visibly relate. */}
    <circle cx="18" cy="12" r="3.25" />
    <path d="M18 6.5v2.25" />
    <path d="M18 15.25v2.25" />
  </Svg>
)

/**
 * A matching "job posting" sheet, used beside the logo where the pairing is
 * the point -- the tailoring view's before/after header.
 *
 * Built on the same geometry as IconLogo (rect, decreasing rules, one circle)
 * so the two read as a set rather than as the same icon twice. The difference
 * is the target: the posting is what the resume gets measured against, and
 * this is the posting's own view of itself.
 */
export const IconLogoTarget = (p: IconProps) => (
  <Svg {...p} strokeWidth={1.9}>
    <rect x="4" y="6.5" width="12" height="13" rx="1.5" />
    <path d="M7 11.5h4.5" />
    <path d="M7 14.75h6" />
    <circle cx="17.25" cy="8.75" r="2" />
  </Svg>
)

/**
 * The mark on its rounded tile.
 *
 * The bare `IconLogo` is a stroked glyph that inherits `currentColor`, which is
 * right inside a text run but wrong as a standalone brand object: at 17px in a
 * sidebar it disappears into whatever it sits next to, and there is no shape to
 * recognise before the wordmark resolves.
 *
 * This wraps it in the tile treatment used across the marketing pages and the
 * footer, so the same mark is the same object everywhere it appears. The tile
 * is sized by the same `size` prop as the glyph and the glyph is inset, so a
 * caller does not have to know the ratio.
 *
 * The `tone` prop exists for one reason: on the dark marketing sections the
 * brand tile has to invert with them, and a fixed dark tile on a dark
 * background reads as a hole.
 */
export function BrandTile({
  size = 40,
  tone = 'light',
  className,
}: {
  size?: number
  tone?: 'light' | 'dark'
  className?: string
}) {
  // The glyph is inset to roughly 62% of the tile, which leaves the padding the
  // marketing pages already use by hand. BrandMark draws on a 64 grid, so it is
  // the right primitive to wrap rather than the 24-grid IconLogo.
  const glyph = Math.round(size * 0.62)

  return (
    <span
      className={[
        'brand-tile',
        tone === 'dark' ? 'brand-tile-dark' : 'brand-tile-light',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <BrandMark size={glyph} />
    </span>
  )
}

export const IconDashboard = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="3" width="7" height="9" rx="1.5" />
    <rect x="14" y="3" width="7" height="5" rx="1.5" />
    <rect x="14" y="12" width="7" height="9" rx="1.5" />
    <rect x="3" y="16" width="7" height="5" rx="1.5" />
  </Svg>
)

export const IconRadar = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <circle cx="12" cy="12" r="4.5" />
    <path d="M12 12 20 6" />
  </Svg>
)

export const IconBriefcase = (p: IconProps) => (
  <Svg {...p}>
    <rect x="2.5" y="7" width="19" height="13" rx="2.5" />
    <path d="M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7" />
    <path d="M2.5 12.5h19" />
  </Svg>
)

export const IconFile = (p: IconProps) => (
  <Svg {...p}>
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
    <path d="M14 3v5h5" />
    <path d="M9 13h6M9 17h4" />
  </Svg>
)

export const IconLink = (p: IconProps) => (
  <Svg {...p}>
    <path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7" />
    <path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7" />
  </Svg>
)

export const IconSearch = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.5-3.5" />
  </Svg>
)

export const IconRefresh = (p: IconProps) => (
  <Svg {...p}>
    <path d="M21 12a9 9 0 1 1-2.6-6.4" />
    <path d="M21 4v5h-5" />
  </Svg>
)

export const IconCheck = (p: IconProps) => (
  <Svg {...p} strokeWidth={2.4}>
    <path d="m4.5 12.5 5 5 10-11" />
  </Svg>
)

/**
 * The TailorUp brand mark: a resume sheet being cut to fit a posting.
 *
 * This replaces an impossible tribar, which was a genuinely interesting idea
 * and the wrong mark. A Penrose tribar says "clever puzzle", which is a
 * statement about the logo rather than about the product, and it is a shape
 * several dozen brands already use. It also rendered as a dense dark shape
 * with a small white inlay, so at sidebar size it read as a smudge rather than
 * as a document.
 *
 * What the product does is narrower and much more legible: one document, cut
 * so it fits one role. That is drawn literally here --
 *
 *   - the sheet outline, with a corner cut away (the "tailoring")
 *   - two text rules, the resume's own content
 *   - a dashed incoming edge on the right, the posting it is being fitted to
 *
 * The cut corner is the only diagonal, so the silhouette stays a document at
 * 16px. Drawn stroked, not filled, because the parts must stay separate: a
 * filled path welds them together and the mark becomes a blob.
 *
 * Rendered on a 64 grid with generous padding rather than 24, so the strokes
 * land on whole pixels at the sizes it is actually used at (22px sidebar,
 * 26px boot, favicon).
 *
 * The geometry below is the same sheet-plus-crosshair as `IconLogo`, lifted to
 * a 64-unit grid. The previous version of this component still drew the old
 * cut-corner document with a dashed edge, which is why the sidebar, the 404 and
 * the thank-you page were showing a different mark from the one on the
 * marketing pages and the favicon: the rebrand updated `IconLogo` and left this
 * one behind. The stroke width is scaled to the 64 grid so it reads at the
 * same weight as the 24-grid glyph.
 */
export const BrandMark = ({
  size = 28,
  className,
  ...rest
}: SVGProps<SVGSVGElement> & { size?: number }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 64 64"
    fill="none"
    className={className}
    role="img"
    aria-label="TailorUp"
    {...rest}
  >
    {/* The resume sheet, as a rect. */}
    <rect
      x="7.5"
      y="12.5"
      width="32"
      height="39"
      rx="4"
      stroke="var(--brand-accent, #245F73)"
      strokeWidth="4.5"
    />
    {/* The three rules, decreasing in width. */}
    <path
      d="M15 25h16M15 36h16M15 47h9.5"
      stroke="var(--brand-accent, #245F73)"
      strokeWidth="4.5"
      strokeLinecap="round"
    />
    {/* The crosshair, centred on the sheet's right edge. */}
    <circle
      cx="48"
      cy="32"
      r="9"
      stroke="var(--brand-accent, #245F73)"
      strokeWidth="4.5"
    />
    <path
      d="M48 16v7M48 41v7"
      stroke="var(--brand-accent, #245F73)"
      strokeWidth="4.5"
      strokeLinecap="round"
    />
  </svg>
)

export default BrandMark

export const IconClose = (p: IconProps) => (
  <Svg {...p} strokeWidth={2}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Svg>
)

export const IconAlert = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7.5v5.5" />
    <path d="M12 16.3h.01" />
  </Svg>
)

export const IconMapPin = (p: IconProps) => (
  <Svg {...p}>
    <path d="M20 10.5c0 5.5-8 11.5-8 11.5s-8-6-8-11.5a8 8 0 1 1 16 0z" />
    <circle cx="12" cy="10.3" r="2.8" />
  </Svg>
)

export const IconExternal = (p: IconProps) => (
  <Svg {...p}>
    <path d="M14 4h6v6" />
    <path d="M20 4 11 13" />
    <path d="M18 14.5V19a1.5 1.5 0 0 1-1.5 1.5h-12A1.5 1.5 0 0 1 3 19V7a1.5 1.5 0 0 1 1.5-1.5H9" />
  </Svg>
)

export const IconTrend = (p: IconProps) => (
  <Svg {...p}>
    <path d="m3 16 5.5-5.5 3.5 3.5L21 5" />
    <path d="M15.5 5H21v5.5" />
  </Svg>
)

export const IconClock = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5.3l3.2 1.9" />
  </Svg>
)

export const IconTarget = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <circle cx="12" cy="12" r="4.5" />
    <circle cx="12" cy="12" r="1" fill="currentColor" />
  </Svg>
)

export const IconInbox = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 13h4l1.5 3h7L17 13h4" />
    <path d="M5.5 5h13l2.5 8v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4z" />
  </Svg>
)

export const IconZap = (p: IconProps) => (
  <Svg {...p}>
    <path d="M13.5 2 4 13.5h6.5L10 22l9.5-11.5H13z" />
  </Svg>
)

export const IconUpload = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 16V4" />
    <path d="m7.5 8.5 4.5-4.5 4.5 4.5" />
    <path d="M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16" />
  </Svg>
)

export const IconLayers = (p: IconProps) => (
  <Svg {...p}>
    <path d="m12 3 8.5 4.5L12 12 3.5 7.5z" />
    <path d="m3.5 12 8.5 4.5 8.5-4.5" />
    <path d="m3.5 16.5 8.5 4.5 8.5-4.5" />
  </Svg>
)

export const IconSettings = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </Svg>
)

export const IconMenu = (p: IconProps) => (
  <Svg {...p} strokeWidth={2}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </Svg>
)

export const IconArrowRight = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 12h15" />
    <path d="m13 6 6 6-6 6" />
  </Svg>
)

export const IconArrowLeft = (p: IconProps) => (
  <Svg {...p}>
    <path d="M20 12H5" />
    <path d="m11 18-6-6 6-6" />
  </Svg>
)

export const IconGitHub = (p: IconProps) => (
  <Svg {...p} strokeWidth={1.6}>
    <path d="M9 19c-4.3 1.4-4.3-2.5-6-3m12 5v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12 12 0 0 0-6.2 0C6.5 2.8 5.4 3.1 5.4 3.1a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21" />
  </Svg>
)

export const IconHelp = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M9.6 9.5a2.5 2.5 0 0 1 4.9.8c0 1.7-2.5 2.5-2.5 2.5" />
    <path d="M12 17h.01" />
  </Svg>
)

export const IconBell = (p: IconProps) => (
  <Svg {...p}>
    <path d="M18 8.5a6 6 0 1 0-12 0c0 6-2.5 7.5-2.5 7.5h17S18 14.5 18 8.5" />
    <path d="M13.7 20a2 2 0 0 1-3.4 0" />
  </Svg>
)

export const IconLogout = (p: IconProps) => (
  <Svg {...p}>
    <path d="M15 17l5-5-5-5" />
    <path d="M20 12H9" />
    <path d="M12 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h6" />
  </Svg>
)

export const IconKanban = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="4" width="5" height="16" rx="1.5" />
    <rect x="10" y="4" width="5" height="10" rx="1.5" />
    <rect x="17" y="4" width="4" height="13" rx="1.5" />
  </Svg>
)

export const IconPlus = (p: IconProps) => (
  <Svg {...p} strokeWidth={2}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
)

export const IconFilter = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 5h18l-7 8v6l-4 2v-8z" />
  </Svg>
)

export const IconUser = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21a8 8 0 0 1 16 0" />
  </Svg>
)

export const IconPalette = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 3a9 9 0 1 0 0 18 2 2 0 0 0 2-2 2 2 0 0 0-2-2h-1.5a1.5 1.5 0 0 1 0-3H13a8 8 0 0 0 0-16z" />
    <circle cx="7.5" cy="11" r="1" fill="currentColor" stroke="none" />
    <circle cx="10" cy="7.5" r="1" fill="currentColor" stroke="none" />
    <circle cx="15" cy="8" r="1" fill="currentColor" stroke="none" />
  </Svg>
)


export const IconLock = (p: IconProps) => (
  <Svg {...p}>
    <rect x="4.5" y="10.5" width="15" height="9.5" rx="1.5" />
    <path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" />
  </Svg>
)

export const IconKey = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="8" cy="12" r="3.6" />
    <path d="M11.6 12H21" />
    <path d="M17.5 12v3.2" />
    <path d="M20 12v2.2" />
  </Svg>
)

export const IconTerminal = (p: IconProps) => (
  <Svg {...p}>
    <rect x="2.5" y="4" width="19" height="16" rx="2" />
    <path d="M6.5 9.5 9.5 12l-3 2.5" />
    <path d="M12.5 15h5" />
  </Svg>
)
