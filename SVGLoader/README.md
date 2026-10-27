# SVG Loader — vector edition / Cinema 4D 2026 / Windows

Find **SVG Loader** using Shift+C or its toolbar icon. Import one SVG as one
editable Bezier SplineObject containing closed outer contours and holes.
The object uses Adaptive interpolation and the SVG filename as its name.

## Vector pipeline

The importer never rasterizes or traces the artwork. The bundled resvg/usvg
parser normalizes SVG shapes, CSS, transforms, references and text to paths.
Skia PathKit expands strokes and performs curve union, difference and intersection.
Black shapes add to the visible result; white shapes remove underlying black
artwork in SVG painting order. White areas remain transparent in the final spline.
Group compositing preserves white cutouts against artwork outside the group.

- Source cubic Bezier controls are retained through normalization, except where
  Boolean intersections split or simplify curves.
- Circles, ellipses and SVG arcs become cubic Bezier arcs, not traced polygons.
  As with normal Bezier circles, these are polynomial approximations of conics.
- Stroke widths, round/butt/square caps, miter/round/bevel joins, miter limits,
  dash arrays, dash offsets and paint order are supported. Stroke expansion occurs
  before object transforms, including nonuniform scaling.
- Nonzero/even-odd fills, clipping paths, hard black/white luminance masks and
  hard alpha masks are evaluated with vector operations. User-space and
  object-bounding-box mask/clip coordinates and mask regions are supported.
- Hole directions are normalized for Cinema 4D. Quadratics are elevated to cubic
  curves; rational conics from round stroke caps/joins use adaptive cubic fitting.
- There is no raster resolution setting, circle guessing or tracing fallback.

Only opaque solid black/white artwork and binary masks have a solid spline
representation here. Visible gradients, patterns, gray/color paints, partial
opacity, soft masks, filters and embedded raster images produce an explanatory
error. Outline unsupported effects in the source editor first. Alpha-mask paint
may have any solid RGB color because only its alpha controls visibility.
SVG normalization follows the bundled usvg feature support; scripts, interactive
animation and HTML foreignObject are not supported. Fonts must be installed for
text normalization; outlining text in the source is safest for portability.
Only artwork inside the SVG viewport is imported.

## Placement

The axis is at the geometric bounding-box center calculated from Bezier extrema.
Local +X points down (reference -Y), local +Y points toward the front
(reference -Z), and local +Z points right (reference +X). Points and tangents
are compensated so the artwork keeps its visible orientation in the reference XY
plane. A selected object's world position and orthonormalized orientation are used
as the reference, without its scale. Otherwise the object is placed at the origin.
The new object is selected and import supports Undo. One SVG CSS pixel equals
one Cinema 4D coordinate unit (normally one cm).

## Runtime and verification

Node and PathKit WebAssembly are bundled locally. The command uses Cinema 4D's
bundled Python; no installs or downloads occur during import. render.cjs remains
only as a reference-rendering helper for regression tests; convert.py does not
call it. Old Potrace files, if present from the previous installation, are unused.

Run tests/test_svg_loader.py with Python on Windows. Tests verify source cubic
controls, curve continuity, Booleans, winding, masks, clips, transformed/dashed
strokes and explicit unsupported-effect errors. Raster comparisons are used only
as a test oracle, never to generate imported geometry.

Third-party dependencies and licenses are listed in vendor/THIRD-PARTY.txt.
This local plugin uses ID 1069989. Public redistribution requires reviewing
license obligations and obtaining a registered Cinema 4D plugin ID.
