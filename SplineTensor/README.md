# SplineTensor 0.10.0 — experimental XOR masking

Calculations report their current stage in Cinema 4D's bottom-left status bar.
Long union/meshing stages use a busy indicator rather than an estimated time
percentage. Updates are delivered on the main thread; cached redraws do not
touch the status bar. Completion and errors clear it. UI updates depend on
Cinema 4D servicing its main-thread messages during evaluation.

The icon is a thin white ring with a bold blue glow, on transparency.

Cinema 4D relief generator. The first closed spline defines the planar outer
surface. All following closed spline children are projected along the base
normal and combined using even-odd (XOR) masking. Child 2 supplies the common signed
height for the entire united relief.

Every generated surface includes a UVW tag. The projected bounding box of the
first spline maps independently in U and V to the full 0–1 square. All relief
faces use that same planar mapping, regardless of height. Non-square bases
therefore stretch to fill the square; vertical walls have zero UV area.

Growing bevel layers now merge and weld where they collide, including between
separate relief islands and around inward collapses. Regular regions retain
quads where possible; topology changes use triangles.

## Installation and update

This version is installed in the Cinema 4D 2026 user plugins folder. Restart
Cinema 4D to load updated Python code, then reopen your scene. For installation
elsewhere, extract the complete SplineTensor folder into the user plugins folder
or add its parent directory under Preferences > Plugins, then restart.
Use Shift+C and search for SplineTensor.

The original 17-knot default and the earlier 2-knot quarter-circle default are
automatically replaced with the new screenshot-matched 2-knot Bezier curve when
an old scene is loaded. Custom curves are preserved. The new handles are 0.35
horizontally from the start and 0.25 vertically below the end.
The optional examples/reset_selected_curve.py script resets selected generators
explicitly and supports Undo.

## Hierarchy

    SplineTensor
        Base boundary
        Relief spline â€” controls the height of the whole union
        Additional relief spline
        Additional relief spline ...

The first child must produce one closed base boundary. Relief children can be
editable or parametric splines, multi-segment splines, Outline, or Connect with
closed splines beneath it. Each contour uses Cinema 4D's interpolation at LOD 1.

## Controls

| Control | Default | Behavior |
|---|---|---|
| Closed | On | Filled raised interior. Off: two-sided ridge, with inner bevel returning to the base plane. |
| Spathe Width | 0 | Outward bevel width. With Closed off, this width applies on EACH side. |
| Subdivision | 3 | Interior band lines: 3 creates 4 strips. Range 0â€“64. |
| Curve | 2 Bezier endpoints | Flat starting tangent, vertical ending tangent: reversed roundness. |

Curve X runs from the base-level foot (0) to the raised contour (1). Endpoints
are pinned in geometry; intermediate Y values are clamped to [0,1]. Spathe strips
are actual four-sided polygons. Around curves these are generally trapezoidal,
not literal rectangles. Base and cap fills are triangulated. Nonplanar quads
are internally tessellated by Cinema 4D.

## Union and height

Every relief spline segment and separate relief child participates in XOR:
areas covered by an odd number of contours are filled; an even number mask out.
This handles crossing overlaps and nested cutouts with the same rule, regardless
of winding or list order. Identical contours cancel. Separate islands remain parts
of the same relief and share its height. The height is the projection of
(child-2 object origin minus base-child object origin) onto the base normal.
Moving any later child along that normal does not change height. Moving it
sideways changes the united footprint. Reordering children changes the height
driver. Tilted contours are projected along the same normal and then raised to
the common height; they no longer retain independent per-vertex heights.

The base normal's largest component in generator space is oriented positive.
Width is measured in generator-local units. Nonuniform generator scale stretches
the final geometry. Keep the base spline's local plane at its object origin for
the most direct interpretation of origin-based height.

If child 2 has zero distance along the normal, no relief edging or extra points
are generated: the result is just the filled base shape. With several children,
this zero-distance rule applies to the whole union.

## Phong and updates

The generator's Phong tag settings are copied to the output, and edits to that
tag refresh the result. Explicit Phong breaks are set on the projected union
contour edges only. Neither the inner nor outer foot has an explicit break,
allowing smooth shading into the base surface on both sides.
Use Edge Breaks is enabled on the output to honor those breaks.
New generators receive a Phong tag; older objects can use an existing tag or add
one. A default angle is used if the generator has no Phong tag.

Unchanged evaluations reuse the cached mesh. A cheap fingerprint checks child
identity/order, local transforms, geometry/parameter dirtiness, generator
parameters, Curve shape and Phong settings. No spline sampling, boolean union,
offsetting or triangulation runs when that fingerprint is unchanged. Geometry
errors are cached too. Moving a child or editing its shape invalidates the cache.

## Local triangulation

Long outer edges receive additional samples, prioritized by the nearest
projections of relief-boundary points. A spatial-neighbor search spaces up to
256 additional interior points. Constrained Delaunay edge flips improve local
triangle connections while preserving every contour boundary and quad strip.
This replaces long fans without changing the base outline. The improvement is
bounded; it is not a universal minimum-angle guarantee, particularly in narrow
gaps or acute corners. Zero-height shapes still produce just the original base.

See examples/Triangulation-Comparison.png. In this regression case the minimum
flat-triangle angle improves from 0.34 degrees to 12.03 degrees. Generated point
count increases to obtain better triangles; the existing unchanged-input cache
still avoids all union/refinement/triangulation work during unchanged evaluations.

Algorithm references: [constrained Delaunay edge flips](https://doc.cgal.org/latest/Triangulation_2/classCGAL_1_1Constrained__Delaunay__triangulation__2.html),
[mesh refinement principles](https://www.cs.cmu.edu/~quake/tripaper/triangle3.html).
These are algorithm references, not bundled CGAL or Triangle dependencies.

## Outline, Connect and generated spline inputs

Outline and Connect can be used as relief children. Their evaluated output is
read, including every closed spline segment, with nested transforms preserved.
The segments use the same nested-mask rule as separate children;
inner loops cut holes in the raised region, with the underlying base retained. The direct second child's object axis still sets
the common relief height. Move that Outline or Connect object along the projection
axis to change height.

Edits to nested spline points, primitive settings, positions and hierarchy
invalidate the cached result. Unchanged inputs reuse the existing mesh. Generator
evaluation operates on a private clone without making scene objects editable.
The first child may also be a generator, but must output one closed base boundary.
Open segments and generators producing meshes instead of splines are rejected.
Generators relying on links outside their child hierarchy are not covered.

## Crossing the base boundary

Relief children may cross, touch, surround, or lie outside the first spline.
The generated relief and its bands are trimmed to the first spline's projected
area. The cut follows the base boundary without adding a new bevel or Phong
break there. Child 2 still sets the common height. Closed and two-sided bands
both work, including negative heights and zero-width steps in Closed mode.
An outside child's band can still affect the base if the band reaches inside.
If no relief or band reaches the base, the output is the plain base surface.

Intact band quads are retained; cut quads can become triangles. Concave base
boundaries use triangulated clipping regions, with shared cut vertices welded
and split to avoid T junctions. Existing unchanged-input caching also applies
to clipped results.

With Closed off, inward bands on convex contours close at their center when
the requested width exceeds the available interior. The remaining center height
follows Curve at the actual inward distance; width is not silently reduced.
The small meeting region uses triangles instead of overlapping quads.

## Limits

- The base must be a simple planar loop. Reliefs and bands may cross its boundary.
- XOR applies to all projected contours. Ambiguous near-touching boundaries
  may still fail geometric validation.
- Colliding bevels use unions of swept edge regions at each subdivision level.
  Local transitions can be triangulated and change topology as width changes.
  Reversing corners and miters longer than 12 times width remain unsupported.
  Small cutouts can be consumed by wide bevels; reduce width to retain a flat center.
- Closed off requires positive width for nonzero height; zero-width double-sided
  walls would coincide. Closed on supports a sharp vertical step at width zero.
- Up to 1200 total sampled points and 64 interior band lines. Changed dense inputs
  still require potentially expensive validation; the cache eliminates repeat
  work only while inputs are unchanged.
- Tolerance is max(base span * 1e-8, 1e-9). This is validated floating-point
  geometry, not exact arithmetic. Features near tolerance can be rejected.
- Solid thickness and an underside are not implemented. Arbitrary third-party
  generators and deformer combinations require their own compatibility checks.
- Output is an open sheet. Invalid geometry gives an empty named cache and a
  Python Console diagnostic rather than a crossed or stale surface.

## Examples and verification

examples/Rectangle-Circle.c4d â€” filled relief.
examples/Rectangle-Circle-Ridge.c4d â€” two-sided bevel.
examples/Multiple-Reliefs.c4d â€” separated islands sharing child-2 height.
examples/United-Relief.c4d â€” overlapping circles united into one relief.

See HOST-TEST.json and TESTING.md for actual verification. Source targets the
Cinema 4D 2025â€“2026 Python 3 API; Windows Cinema 4D 2026.3.4 is tested. macOS and
2025 have not been executed. No external Python packages are required.

Plugin ID 1069998 is a temporary DEVELOPMENT ID, not a registered allocation.
Obtain a unique Maxon ID before distributing in a shared production pipeline;
update SplineTensor.pyp, the description header and example scripts, then
regenerate scenes. Saved scenes reference the numeric ID.

## Source and licenses

SplineTensor.pyp handles host integration; st_union.py constructs the projected
union; st_geometry.py builds and validates the relief; st_quality.py refines the
flat mesh with local sampling and edge flips; st_earcut.py is the
vendored ISC-licensed Earcut Python port with an integer-conversion fix.
EARCUT-LICENSE.txt is retained. The supplied icon remains the user's reference.

References: [ObjectData cache API](https://developers.maxon.net/docs/py/2024_3_0/manuals/manual_objectdata.html),
[Phong on generators](https://developers.maxon.net/forum/topic/12930/phong-tag-with-objectdata/4),
[PolygonObject edge selections](https://developers.maxon.net/docs/py/2025_1_0/modules/c4d/C4DAtom/GeListNode/BaseList2D/BaseObject/PointObject/PolygonObject/index.html),
[Earcut source](https://github.com/joshuaskelly/earcut-python).

Closed-off bands share one contour and matching quad strips on both sides.
Near-coincident contour steps are merged within 0.5% of Spathe Width (0.01 cm
at width 2 cm), with contour deviation bounded by that tolerance. This avoids
crossed bridges without asymmetric triangle strips. Colliding offsets use the
welded-region fallback. Clipped boundaries and collapsed center caps can use triangles.

With Closed off, the inner flat area uses the same interior point sampling and
constrained triangulation refinement as the outer flat area. Shared band vertices
are preserved, so the quad strips stay welded and retain their topology.

All flat surface fills use the same bounded point sampling and constrained
Delaunay refinement, whether inside/outside, raised/lowered, Closed on/off,
or using collision welding. Sampling spacing is derived from the base extent.
New vertices preserve surface height; shared bevel boundaries stay welded.
The zero-height shortcut still returns the unmodified base topology.

0.8.3 shading/topology correction: both Closed modes and the collision fallback
share bounded short-edge cleanup (maximum contour deviation 0.5% of width).
Collision triangles are merged into quads only when coplanar within geometry
tolerance. Twisted pairs remain triangles to preserve the intended surface.

0.8.4: collision-band triangulation reconnects flat triangular ears to the
next bevel layer, using convex internal diagonal flips. Boundary edges and
projected contours are protected. This removes local flat patches inside
sloped bands without adding points or changing the band footprint.

0.8.5 general flat-fill rule: apart from the actual shared rim edges, boundary
vertices connect to interior flat-surface samples, never to other boundary
vertices across the fill. Boundary-to-boundary diagonals are split with welded
interior samples and subsequent edge flips cannot recreate them. This applies
to inner/outer fills at any elevation in both Closed modes. Bevel strips and
the zero-height base-only shortcut retain their topology.

This is an experimental change to saved-scene behavior. Restore the complete
SplineTensor folder from ../SplineTensor-0.8.5-before-masking.zip and restart
Cinema 4D to return to filled-union behavior. The current scene was saved as
a copy in tests/Mask-experiment.c4d; the live document was not changed.

0.9.1 performance: segment bounding boxes are computed once and sweep-filtered
before exact intersection tests. Border height lookup prunes distant segments
and caches repeated boundary points. Geometry validation remains enabled.
The standalone Gaming Mini benchmark (width 5, subdivision 3, Closed off,
three nested contours, kernel default profile) fell from 16.07 seconds to
5.01–5.06 seconds with identical points, faces and crease edges. This excludes
Cinema 4D startup and spline sampling; timings depend on geometry and hardware.
See PERFORMANCE.json.

0.9.2 applies XOR to crossing shapes as well as nested ones. If all relief
regions cancel, the plain base is returned. Before this change the complete
plugin was backed up as ../SplineTensor-0.9.1-before-xor.zip.

## Density

Density is an integer multiplier with default/minimum 1. Existing scenes use 1.
Density 2 doubles the samples per original spline edge, doubles the bevel strip
count ((Subdivision + 1) * Density), and doubles target flat-area point density
by reducing spacing by sqrt(Density). Flat point counts are approximate because
boundaries, narrow areas and triangulation constraints affect sample placement.
Rim additions evaluate the original spline at intermediate spline parameters;
they are not straight chord midpoints. Original samples and corners are retained.
Outline/Connect outputs follow their evaluated spline curvature; a linear output
contains no additional curve information to recover. Density changes invalidate
the geometry cache and use the existing progress display. Larger values increase
computation and memory use; sample/refinement budgets scale with Density.

0.10.0 also fixes shared-edge point insertion in flat refinement: both incident
triangles split together, avoiding cracks on symmetric grid alignments.
