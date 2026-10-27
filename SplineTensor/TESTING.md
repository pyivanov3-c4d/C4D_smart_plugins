# SplineTensor 0.7.4 verification

39 geometry tests and 13 boundary-clipping tests pass. Run:

    python tests/test_geometry.py
    python tests/test_clipping.py

Clipping checks cover crossing circles, both Closed modes, negative height,
zero width, enclosing and coincident reliefs, outside shapes, band-only overlap,
united children, concave bases, rotated planes and zero height. They check
projected area, boundary containment, nondegenerate faces and welded seams.

Coverage includes valid manifold seams, quad strips, concave contours, negative
and zero height, profiles, multiple regions, union overlap/containment/identical
loops/shared edges, disjoint unions, common height, and invalid-input rejection.

The 0.5.1 crease-selection check confirms that outer-foot edges have no explicit
break in either Closed mode, while projected-contour breaks remain.

Cinema 4D 2026.3.4 Windows checks are recorded in HOST-TEST.json:

- Original default curve migrates to two Bezier knots; custom curves survive.
- An older saved scene loads with its Curve automatically migrated.
- 100 unchanged direct evaluations cause ZERO new geometry builds.
- 20 unchanged document passes retain the same generated cache.
- Child movement and generator/Curve/Phong changes invalidate the cache.
- Generator Phong angle is copied and projected edges have explicit breaks.
- Child 2 controls height in both Closed modes, including separated islands.
- Overlapping circles produce a united relief without internal contour walls.
- Parametric child edits, reordering and deletion refresh the output.
- Zero distance generates just the base boundary, with no relief edges.
- Crossing children produce clipped geometry in both Closed modes.

For host tests, load the plugin at startup, then run tests/c4d_smoke.py with
Cinema 4D's c4dpy.exe. It uses isolated documents, writes HOST-TEST.json and
regenerates example scenes. It does not modify the user's active document.
A process-local g_additionalModulePath can point to the installed plugin folder.

Unchanged timings measure the cache-check path on this machine, not viewport FPS.
Dense CHANGED inputs can still take time to union, offset and validate. Hole-shaped
relief unions are not supported. No exhaustive GUI interaction,
third-party generator, macOS or Cinema 4D 2025 validation is claimed.

0.6.1 adds the reported two-circle scene (30 cm band, smaller radius about
17.25 cm) as a regression. Convex inward bands close before offset inversion.
CLOSED-OFF-HOST-TEST.json records the saved scene rebuilt in Cinema 4D with
Closed off and its existing Curve, plus 20 unchanged evaluations without rebuilds.

0.7.4 generated-input checks are recorded in GENERATED-INPUT-HOST-TEST.json.
They use the installed Outline plugin and native Connect, check all generated
segments and nested transforms, change nested Circle and Outline settings, and
verify unchanged-input caching and native generator evaluation. Run
`tests/c4d_generated_inputs.py` with c4dpy and the installed plugin folder loaded.

0.7.1 adds the ChuChumfer / Gaming Mini scene regression: zero-area ears
on collinear boundary samples are skipped before boundary-sample restoration
and area/manifold/intersection validation. Source splines are unchanged.

0.7.2 verifies Closed off with Gaming Mini at width 2 and subdivision 6.
Valid inset strips whose direct quad bridges fold are triangulated as constrained
annuli. Unaffected bands retain quads. CURRENT-OPEN-MODE-HOST-TEST.json records
the actual saved-scene check.

0.7.4 checks 1,358 band quads in the Gaming Mini scene: 97 contour samples,
7 strips on each side. Only the 97 ridge edges receive explicit Phong breaks.
Near-coincident point cleanup is bounded to 0.5% of width.

0.7.4 applies interior point sampling and constrained edge flips to the flat
inner fill in Closed-off mode. The quad bands and ridge selections are retained.

0.8.0: all 56 pure Python tests pass, including growing island collisions,
exact diagonal contact, inward collapse, the saved VideoCloud Mini scene at
10 cm width in both Closed modes, and planar UV bounds/height independence.
Additional checks passed for clipped, colliding bands with negative height.
WELD-UV-HOST-TEST.json records Cinema 4D 2026.3.4 checks of both modes in the
saved scene, per-corner UV coordinates, and unchanged-input cache reuse.
Closed on produces 713 points / 950 polygons; Closed off produces
1,108 points / 1,423 polygons. UV comparisons allow the UVW tag's storage precision.
The live user document was not modified; tests load a saved copy in c4dpy.

0.8.1: Cinema 4D 2026.3.4 host smoke tests pass. Four progress bridge tests verify worker-event delivery, main-thread GUI updates, concurrent jobs, idle silence and error cleanup. Live status-bar painting has not been visually verified; requires restarting the desktop host.

0.8.2: the existing 60 tests pass, plus two new general-fill tests. They verify
identical sampling/topology at zero, positive and negative elevation, and
interior points at correct cap height in regular and collision-welded builds.

0.8.3: existing 62 tests and two new topology tests pass. The Gaming Mini
scene at width 10 now has no output edge below 0.05 cm and no twisted quads
in either Closed mode. A synthetic twisted triangle pair remains triangulated.
The checked Closed-on mesh has 865 points, 1163 polygons, 388 planar quads;
its shortest edge is 0.27146 cm (previously 0.00673 cm).

0.8.4: all 67 tests pass. The saved width-20 Gaming Mini scene has no flat
intermediate-band triangles in either Closed mode (previously nine in Closed
on). Constraints are protected. JOIN-UV-HOST-TEST.json verifies both modes
inside Cinema 4D 2026.3.4, UVs and unchanged-input caching.

0.8.5: all 69 tests pass. Flat-fill tests enforce no unconstrained edges
between boundary vertices, welded interior edges, and height preservation.
Short-edge and twisted-quad regressions also pass after interior-point
placement/relaxation. JOIN-UV-HOST-TEST.json verifies the saved width-20
scene in Cinema 4D in both Closed modes, with UVs and unchanged-input caching.

0.9.0 experimental: 69 existing tests and four masking tests pass. The saved
Gaming Mini scene resolves to one outer region and two clockwise cutouts
(round and cross). MASK-UV-HOST-TEST.json confirms both Closed modes, UVs
and cached evaluation inside Cinema 4D 2026.3.4. Nested islands, reversed
winding, input order, overlapping outer shapes and zero-width walls tested.

0.9.1: all 75 tests pass, including sweep candidate equivalence to exhaustive
bounding-box comparisons. Standalone optimized output matches baseline exactly
(points/faces/creases). Updated MASK-UV-HOST-TEST.json passes both Closed modes
in Cinema 4D, including UV coordinates and unchanged-input caching.

0.9.2: all 78 tests pass. Mask tests now require overlap subtraction,
identical-shape cancellation, triple-overlap fill, and crossing-circle
generation in both Closed modes. XOR-UV-HOST-TEST.json verifies the saved
open scene in Cinema 4D, including UVs and cache reuse.

0.10.0: all 82 geometry tests pass. DENSITY-HOST-TEST.json verifies Density
1, 2 and 3 in Cinema 4D 2026 in both Closed modes, increasing quad-band
resolution, UV tags, and unchanged-input caching. Circle sampling doubles
from 36 to 72; inserted samples follow the native curve rather than chord
midpoints. Three-segment imported spline counts double from 99/12/68 to
198/24/136. The saved XOR scene generates at Density 2 (3223 points, 3822
polygons). Exact line-tag curve parameters prevent sampling backtracking.
The shared-edge grid insertion regression verifies welded triangulation.
