# Mesher Pro — Cinema 4D 2026

Independent custom generator inspired by the Respline Mesher workflow.
This is a fresh implementation, not extracted Respline source. Existing Respline
objects remain separate and are not automatically converted.

Restart Cinema 4D, find **Mesher Pro** in Commander (Shift+C), and place
an editable or parametric spline beneath it. Multiple child splines and spline
segments are supported. Apply materials to the generator as usual. Make Editable
converts the result into polygon objects.

- **Circle:** Radius and exact Circle Segments, constrained to 3–200.
- **Rectangle:** Width, Height, Fillet Radius, and Fillet Segments (1–200 per
  quarter-circle corner). Zero radius gives sharp corners. Fillet radius is
  limited geometrically to half the smaller dimension to avoid overlap.
- **Rope:** Three twisted round strands. Radius controls overall profile size;
  Rotations controls full turns over each spline segment.
- **Chain:** Alternating oval links. Radius controls link centerline half-width;
  Chain Thickness (Diameter) controls the round metal cross-section independently.
  Diameter must be less than twice Radius. Very tight path bends or oversized
  thickness can produce intersecting links; this is a generator, not a simulation.
- **Path Step:** Desired distance between samples (smaller gives more geometry).
  In Chain mode this controls link tessellation; spacing follows link size.
- **Rounded Caps:** Available for Circle and Rectangle only, on open paths.
  Circle uses hemispherical ends with radius equal to the profile radius.
  Rectangle rounds the end perimeter using the existing Fillet Radius and
  Fillet Segments, then fills the remaining center. Zero fillet gives a flat cap.
  Uncheck to leave the ends open. Rope and Chain have no cap option.
- **Rotations:** Full profile turns along the path. Use positive turns for rope.
- **Gaps** (Circle/Rectangle only): Enable to create separate equal-length pieces.
  **Mode: Interval** uses Segment Length and Space Length as before.
  **Mode: Count** uses Segment Length and an exact Piece Count; Space Length is
  disabled and ignored. Open paths place the first/last pieces at the ends; one
  piece is centered. Closed paths center non-overlapping pieces in equal cells.
  If pieces overlap, they are regularly distributed within the full start/end
  span without extending past it. Segment Length cannot exceed the path length.
  Segment Length is each piece's path span including rounded cap allowance;
  Space Length is the empty path span between pieces. Caps use the current cap
  settings. Segments too short for the caps report a status message. Only full
  pieces are generated; unused tail length remains empty. Closed loops reserve
  a gap at the seam, with any remainder added there. The width curve and rotations
  continue along the original spline rather than restarting on each piece.
  On bends, adjacent ends are shifted inward using the tangent at their gap,
  profile extent, width multiplier, and cap depth. This conservatively preserves
  a clearance between their end envelopes; it can shorten the straight body
  relative to its nominal span. Extremely tight bends can still self-intersect.
  Space Length may be negative for overlapping pieces, but Segment Length plus
  Space Length must stay positive. Only complete pieces fit within the path;
  leftover space remains at the end/seam. Piece Tilt X and Piece Tilt Y rotate
  each complete piece around its path midpoint using the two transported axes
  perpendicular to the tangent (X then Y). Both default to 0 degrees. Caps rotate
  with their piece. Tilting can change the visible gap and cause overlaps.
- **Width Along Spline:** Curve multiplier in all four modes. X runs from 0
  (start) to 1 (end) by distance along each spline segment; Y=1 keeps the original
  size, 0.5 halves it, and 2 doubles it. Scales the complete cross-section,
  including rectangle height and fillets, rope strands, and endpoint caps.
  Chain links scale about their centers, including wire diameter and link length;
  spacing stays unchanged. Match endpoint values on closed paths for a smooth
  seam. Zero/negative values use a tiny 0.0001 multiplier to avoid collapsed faces.
  Default is a flat curve at 1; missing curves in older objects also mean 1.
- **UV coordinates:** Every generated mesh carries a UVW tag. U follows profile
  perimeter distance from 0 to 1; V follows length from 0 to 1, with cap regions
  included in that range. Closed meshes stay welded but have a UV seam at V=0/1.
  Gapped pieces keep their original interval of V rather than restarting at 0.
  Flat and rounded caps reserve V space, with a pole/fan at the endpoint.
  Rope strands each use the full path range; chain links occupy successive V
  bands with U wrapping their wire cross-section. Multiple segments of one spline
  share V=0–1 in segment order, apportioned by length. Separate child splines
  each use 0–1. Set the material tag's projection to **UVW Mapping**.

The plugin creates polygon meshes with a Phong tag. Circle's segment count is
actual topology even when shading looks smooth. Child transforms are retained.
A one-million-point budget prevents accidental extreme allocations.

Profiles remain perpendicular to the sampled path tangent. Parallel transport
keeps their orientation continuous; closed paths distribute the residual roll
and share vertex indices at the seam (welded, without duplicate endpoint rings).
Rounded caps extend beyond each endpoint. Sharp turns or profiles wider than a
path bend can still self-intersect, as with a conventional sweep.

The blue icon distinguishes this generator from Respline. Both can coexist.
Plugin ID 1069988 is for this local installation; obtain a registered ID before
public distribution.
