# smartBoolean 1.0.21 — local bevel reconstruction

Requires Cinema 4D 2026 and its modern Boolean generator.
Copy this entire folder into Cinema 4D's user plugins folder, then restart.
Press Shift+C and search for **smartBoolean**. Place operands below it;
the first direct child is A, and the remaining children are the other operands.

| Parameter | Default | Meaning |
| --- | --- | --- |
| Mode | Union | Union, Subtract (A minus others), or Intersect |
| Chamfer Width | 0 | Bevel offset in scene units; zero disables bevel |
| Chamfer Subdivision | 3 | Number of bevel strips, from 1 to 128 |
| Roundness | +1 | Rounded +1, straight 0, inverted -1 |

## Fix in 1.0.3

The tag guard now accepts native Tpoint (5600) and Tpolygon (5604) storage.
These tags were present on the evaluated user mesh and incorrectly forced
version 1.0.2 into the legacy path. A regression test reproduces that exact
tag inventory. The corrected callback still needs loading after restart.

## Changes in 1.0.2

Straight intersection spans are resampled at uniform stations, removing the
closely paired vertices caused by different operand grids. Actual seam corners
are retained. Native bevel uses uniform mitering and explicit corner polygons.

Planar cleanup selects only faces touching a corridor of 1.02 times the bevel
width, plus those faces' existing extent. Faces outside that selection retain
their vertex coordinates. Planar transition n-gons are rebuilt with explicit
triangle edges to retained boundary vertices. Shorter valid diagonals are
preferred to reduce long fans. Transitions are not guaranteed to be all quads.

Unchanged UV corners are copied. New planar corners are interpolated only when
the source plane has a consistent affine UV chart. Discontinuous UV charts,
restricted materials, custom attributes, or unsupported topology use a
conservative native fallback rather than losing their data. Its cleanup radius
is reduced from 2.5 to 1.25 times the width. A console message identifies fallback.
Explicit normals are rebuilt through Phong shading after topology changes.

## Validation and limits

Twenty-three offline regression tests pass, including constrained boundary vertices,
holes, UV interpolation and seam preservation, outside-face preservation, and
closed-mesh checks. On the captured dense two-cube fixture (50 subdivisions per
axis), the seam is reduced from 304 to 44 evenly spaced edges. Native Cinema 4D
modeling commands were tested separately at width 10 and three bevel strips.
An offline transition reconstruction of that native output remains watertight:
24,242 points and 24,467 faces. This is not an end-to-end generator callback test.

The updated installed generator must be loaded by restarting Cinema 4D. Corner
appearance and the actual n-gon/UVW integration still require checking in that
reloaded generator. The native miter setting does not guarantee ideal corners
on every Boolean configuration.

Owned polygon clones are evaluated in a temporary document. Original children
are preserved. Coincident points are welded with a tiny relative tolerance.
The result is one polygon object; separate solids can remain disconnected islands.
Native bevel limiting is disabled. The requested width is never halved on retry.
Collinear zero-area faces left by native bevel at subdivided corners are removed
before validation; the remaining surface must pass the closed-mesh check. If the
requested width still fails, the unchamfered result is returned and the status
reports the failure instead of silently substituting a smaller bevel.
Self-intersections, overlapping bevels, tiny features and nonmanifold
inputs can require manual cleanup. Edge-incidence checks do not prove absence
of geometric self-intersections.

Local plugin ID: 1069992 (not an officially assigned distribution ID).
Icon: overlapping blue (#0198FC) and white outlined planes.
Triangulation uses the ISC-licensed earcut-python; see EARCUT-LICENSE.txt.


## Fix in 1.0.4
Unused UV charts no longer cancel rebuilding on objects with no texture tags.
Unchanged face UVs remain exact; rebuilt faces extend a planar source chart.
Textured objects retain strict UV preservation. The UV rejection was reproduced
from the current user scene export; relaxed transfer passes on 18,860 rebuilt
faces. Output container key 1099001 records version and the actual cleanup path
for diagnosis. Live callback verification remains pending after restart.


## Fix in 1.0.5
The native full-width test on the 50-subdivision user fixture produced 16
collinear corner faces. Removing them restores manifold edge incidence without
moving any surface vertices. Measured wall and floor offsets are both 10 units,
matching the requested width. The limiter and width-halving retries are removed.
The native-operation fixture and 17 regression tests pass; the updated generator
callback requires restart and live reevaluation. Extreme widths can still cause
geometric overlap; edge incidence alone does not detect all self-intersections.

## Fix in 1.0.6
Remove redundant collinear hard-corner stations from both adjacent planar
patch boundaries BEFORE native bevel. Vertices belonging to untouched faces
remain protected. The dense native corner test now has zero collapsed faces
and exactly two incident polygons per edge without post-bevel deletion.
The corner wireframe was inspected; 19 tests pass, including a recomputed
fixture assertion for absence of old corner stations inside the bevel footprint.
Full reloaded generator verification remains pending. Native n-gon interiors
are still processed by the existing explicit-transition reconstruction.


## Fix in 1.0.7
Transition diagonal refinement now uses an incremental edge queue until no
shorter valid local diagonal remains. The old 16-pass limit left long fans
on dense strips. The 100-cell regression previously retained an 84-cell
connection; it now has direct cross-strip edges at all 99 interior aligned
stations, with remaining diagonals spanning at most one cell. Existing boundary
vertices are retained. This is local triangulation, not an all-quad guarantee.
20 regression tests pass. Live generator verification requires restart.


## Changes in 1.0.8
Points Remove (parameter 1004) is OFF by default, including scenes without a
stored value. Enable it to run seam resampling, local point cleanup and explicit
transition reconnection. With it disabled, those two heavy preparation/finishing
passes are bypassed; native Boolean/bevel and basic validity checks remain.
The corner cleanup footprint now includes a sqrt(2)-width radius at seam
endpoints, covering the full right-angle miter without widening straight spans.
The native 50-subdivision cube test has no inverted floor faces, no collapsed
faces, and closed edge connectivity. 23 regression tests pass, including default
checkbox state and bypass/enabled behavior. Live reloaded callback verification
is pending. Arbitrary acute-angle miters may need a larger angle-aware footprint.


## Changes in 1.0.9 — independent extrusion-side limits
Only active with Points Remove OFF. With Points Remove ON, the prior cleanup
and full-width bevel path is unchanged.

For a coplanar seam bordering a constant-height extruded wall, detect the first
non-coplanar wall boundary through connected wall faces. Coplanar subdivisions
do not count as boundaries. The short-side profile is compressed independently
when requested width exceeds its clearance; geometry beyond that region is
restored to its original position. The adjacent planar side can keep widening.
Its maximum width is bounded by the nearest unselected feature boundary of its
connected coplanar region. A tiny numerical clearance avoids coincident faces.

This implementation supports constant-height extrusion strips and coplanar
seams. Nonplanar seams or variable-height strips retain native behavior; this
is not a general per-vertex collision solver for arbitrary surfaces. It does
not resolve collisions between separate simultaneously beveled seam loops.

The captured user scene has a 2.568219-unit straight wall before the existing
cap rounding and an 11.558232-unit planar-side boundary distance. Native bevel
at requested width 6 plus the inverse deformation produces a closed mesh.
28 regression tests cover independent limiting, exact restoration of unchanged
geometry, planar boundary limits, checkbox paths and prior cleanup behavior.
Full installed generator verification requires restarting Cinema 4D.

## Changes in 1.0.11 — local collision restrictions
With Points Remove OFF, planar closed seams use two small native reference
bevels to establish point trajectories before self-intersection. Local widths
stop collapsing curves and approaching seam sections. Native point trajectories
also detect contact with real, non-coplanar feature edges, including the inner
outline of the letter e. A local transition spreads a restriction only to nearby
stations. Unrestricted sections retain the requested width. Short extrusion-side
deformation from 1.0.9 is retained. Points Remove ON follows its existing path.

Unlike the rejected 1.0.10 approach, no minimum corner radius is applied to the
whole seam. Unsupported/nonplanar or branched seams retain the previous path.
Ambiguous native point correspondence falls back to the prior full-width path
and reports this in the evaluated mesh status. The feature-edge check is not a
general triangle/triangle collision solver for arbitrary 3D surfaces.

31 regression tests pass. Direct native reference meshes from the user's Text
scene give zero front/back boundary crossings on the letter e at width 10,
retain full width on unaffected sections, and maintain closed connectivity.
The curved scene preserves an 8-unit maximum while limiting tight stations
near 2.06. Installed callback verification remains pending a Cinema 4D restart.

## Changes in 1.0.12 — preserve width at vertical end continuations
When a side trajectory reaches a vertex joining a short slope to an available
vertical feature edge, continue the endpoint along that edge and blend the
profile adjustment by height. Do not treat this vertex contact as a width cap
for the entire profile. True crossings still use the local collision checks.
Restrictions at an exact seam station no longer transfer immediately to the
other endpoint of its adjacent edge; nearby transitions remain distance based.

The Text fixture's right-hand e terminal now retains about 9.2 units of planar
width at requested width 10 (previously about 0.48), with its endpoint on the
vertical wall. Front/back boundary intersection checks remain clear. All 31
tests pass, including assertions for this terminal. Reloaded callback testing
requires restarting Cinema 4D.

## Changes in 1.0.13 — retain the curved offset contour
Curvature-collapse limits now retain 15% of the local offset contour instead
of stopping only 0.1% before collapse. This prevents the near-point fan at the
Flower Extrude's tight rounded turn. The limit activates continuously before
the collapse radius, and unrestricted stations keep the requested width.
This is a local width restriction, not a remesh or a change to the source spline.

The captured Flower fixture retains at least 15% of each projected seam-edge
span, has no planar boundary crossings, and remains closed. Its minimum local
width is approximately 3.376 while unrestricted stations retain width 10.
All 32 regression tests pass. Reloaded callback verification is pending restart.


## Changes in 1.0.14 � coherent inward curve offsets

With Points Remove off, connected inward-curving seam segments share the
smallest curvature clearance for that turn. Previously each station used its
own clearance, tracing a pointed curvature envelope rather than a parallel
offset of the Extrude outline. Other parts of the seam can still grow to the
requested width, and the independent extrusion-side restriction is retained.

The captured native Flower reference mesh now keeps the inner contour edges
parallel to their corresponding source edges. The new regression rejects
1.0.13; existing E terminal, collision, side-limit and cleanup tests also pass.
This validates captured native geometry offline; the reloaded Cinema 4D
generator callback still needs checking after restart. No flat-face melting
is added, and Points Remove remains unchecked by default.


## Changes in 1.0.15 � Convert and hide

The Convert and hide button evaluates Current State to Object, inserts the
editable result immediately after the generator under the same parent, and
selects it. The original generator and every descendant are disabled and
hidden in both viewport and render. The original hierarchy is retained.
The operation has one Undo group. Failed or empty conversion does not hide
the source. Restart Cinema 4D after installing to load the button and handler.

Offline tests cover sibling placement, transform preservation, recursive
disable/visibility flags, undo registration and failed conversion. The new
button callback still needs checking in Cinema 4D after restart.


## Changes in 1.0.16 � progress and collision lookup performance

Calculation status appears in Cinema 4D's bottom-left status bar. Native
Boolean/bevel and cleanup operations use a busy indicator; intersection,
profile and connection loops report completed work as a percentage of that
stage. Worker calculations publish throttled/coalesced updates to a
main-thread message plugin (local ID 1069997). Cached results do not publish
status. Completion, exceptions and cancellation release the status job;
nested jobs retain the outer job. Convert and hide also reports progress.
Cinema 4D controls when queued main-thread UI events can be serviced.

Collision candidates are filtered by bounding-box trees before the existing
exact intersection tests. Original candidate ordering is preserved. This
avoids scanning every feature edge for every bevel point. Geometry and width
restriction rules are unchanged. Benchmarks and validation details are in
artifacts/smartBoolean/benchmark-1.0.16.json in the development workspace;
these measure Python collision work, not complete native generator time.

### Verified 1.0.16 results

44 offline tests passed. An isolated Cinema 4D 2026 c4dpy process completed
the native Boolean/bevel callback, confirmed message-plugin registration and
confirmed cached evaluation makes no progress updates. Desktop status-bar
appearance remains to be visually checked after restart.

Captured-geometry collision benchmarks (median of two runs):

| Fixture | Before | After | Speedup |
| --- | ---: | ---: | ---: |
| Flower | 3.912 s | 0.551 s | 7.10x |
| Letter E | 0.689 s | 0.113 s | 6.11x |
| Dense curved mesh | 311.730 s | 36.824 s | 8.47x |

All three returned exactly identical width caps and point coordinates. These
measure collision planning and expansion, including connection validation,
not native Boolean/bevel execution or the optional Points Remove cleanup.
The dense case still spends substantial time in repeated connection checks;
that is a candidate for a separate, geometry-validated optimization.


## Changes in 1.0.17 � stop outward bevels at wrapped face boundaries

A seam wrapping around several cube faces previously failed the single-plane
collision planner and fell back to an unrestricted native bevel. Such closed,
manifold seams now use the native reference trajectories with local 3D
feature-edge limits. Coplanar grid edges do not restrict width. The established
planar curvature/asymmetric-side path is unchanged, as is Points Remove.

On the captured Flower/cube scene at width 5, the old result had 14 points
past the cube front-face boundary; the new output has zero. The mesh remains
closed, unchanged input points are preserved, and unconstrained sections retain
the requested width. 45 offline regressions pass. This is a targeted boundary
fix, not a general proof against all nonplanar bevel self-intersections.


## Changes in 1.0.18 � welded bevel contact junctions

Reference bevel trajectories identify ordered rows of generated points. When
a row folds into a self-intersecting loop, its enclosed collision lobe is
collapsed to the actual contact point. Connected faces share that vertex;
Cinema 4D Optimize welds coincident points and removes collapsed polygons
while retaining native attribute tags. Ordinary nearby original points are
not merged by a broad distance tolerance. The process uses the same principle
as SplineTensor's collision-resolving layers, adapted to the native bevel.

The proposed topology is checked for closed edges and connected vertex fans
before native welding; a failed native topology check retains the prior mesh.
Progress and cancellation remain active during contact detection. Points
Remove retains its existing scope; this automatic contact repair is local to
the collision-limited reference-bevel path.

On the captured user scene, 65 redundant points are removed. The explicit
remap removes 45 collapsed faces; native n-gon retriangulation leaves 55 fewer
polygons overall (2,111 points / 2,324 polygons). Native verification confirms
shared vertices, a closed surface, matching coordinates and matching volume.
48 offline tests pass, including contact-free planar geometry and
preservation of close original vertices. This repairs self-intersections
within individual supported bevel rows, not arbitrary intersecting solids.

## Fix in 1.0.19

Chamfer rounding, borders and miters no longer inherit explicit Phong breaks. Untouched source-edge breaks and the existing Phong angle limit are retained. Geometry is unchanged.


## Fix in 1.0.20

Points Remove supports edge and polygon selection tags generated by Extrude. Selections are remapped through reconstruction; ambiguous polygon selection boundaries retain the conservative fallback. Collapsed transition triangles reconnect adjacent edge stations before removal, preventing an open surface and the previous rejected cleanup. Split polygons retain boundary UV values. Validated on the saved Flower scene with Points Remove enabled: closed surface, no unused points or zero-area faces. The separate Points Remove-off contact-weld rejection remains guarded.


## Performance in 1.0.21

Selection-edge transfer uses conservative spatial bounds and unchanged-edge matching. Identical selection tags reuse a mapping within each rebuild. Saved Flower fixture: bevel/cleanup measured 42.53 s before and 5.17 s after (8.23x), excluding scene loading and initial Boolean evaluation. Points, polygons, UV data and selection tags matched exactly. 52 tests pass.

