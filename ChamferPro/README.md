# chamferPro 1.1.3 — Cinema 4D 2026

Non-destructive spline generator with two controls and a rounded-corner icon
in Mesher Pro blue (#0198FC).

## Use

Restart Cinema 4D after installation. Find **chamferPro** using Shift+C and put
your spline objects beneath it. Nested groups, multiple children and multi-segment
splines are collected into a single Bézier spline. Open endpoints that coincide
within 0.000001 generator units are joined when the junction is unambiguous.
Branches remain separate. Original child objects are never edited.

- **Sharpness Angle (minimum):** Round smaller corner openings greater than or equal to this limit.
  Measures the two rays pointing away from the corner and takes the smaller
  left/right angle, independent of winding. Straight = 180°, right angle = 90°.
  Default 30° includes openings at least 30°. A tiny limit includes almost
  every corner; straight/smooth joins are not corners. An angle equal to the
  limit is included. Existing objects retain their saved numeric setting.
- **Rounding Radius:** Requested circle radius, not distance along an edge. Default 10;
  zero bypasses rounding. Uses the generator's coordinate units, after child
  transforms. Nonuniform scaling of the generator or its parents can stretch
  the finished circles; keep that scale uniform for circular world-space rounds.

The status reports the rounded corner count, requested radius, and corners left
unchanged, inner spans cleaned, and locally limited corners. A corner uses the
requested radius where it fits, otherwise a locally reduced feasible radius.
There is no shared minimum radius across an entire child or hierarchy.
Coincident endpoints across different sources are connected after rounding;
a corner formed only by that connection is not rounded.

## How it addresses the two problems

Nearby points on straight runs do not cap the radius: trimming may cross any
number of redundant knots. Smooth Bézier joins may also be crossed. Existing
curves outside the trim interval are retained by exact Bézier subdivision.
A 0.05° numerical threshold distinguishes straight/smooth joins. Local inward
corner groups can now be reconstructed before rounding as described below.

## Inner corner cleanup

On closed planar contours, consecutive concave corners between nearly straight sides
can be merged into one virtual corner at those sides' intersection. Every control
point of the intervening spans must lie within the requested radius of that
intersection. The resulting corner must pass the angle filter and fit a fillet
of positive radius on the two sides; the requested radius need not fit yet.
Convex turns above 5 degrees stop a group; parallel
sides, open contours and nonplanar contours are left unchanged by this pass.
Concavity is measured relative to each contour's winding, so reversed contours
behave identically. This is contour-based, not a solid-fill classification of holes.

Cleanup is committed only if all reconstructed corners on that contour actually
round without conflicts; otherwise the original contour is rounded normally.
Disjoint groups avoid repeated drift. The status reports removed inner spans.
Input objects remain untouched. Radius reduction is local to constrained corners.

Small flank deviations up to 5 degrees may be consumed within the same
radius-bounded group, allowing extra near-collinear points beside an inner tip.
Slightly curved flanks may be straightened if every control point is within
the smaller of 2% of the requested radius and 1% of the flank length from its
chord. Minor curvature within a consumed bridge no longer blocks cleanup.

Every successful round uses a circular arc at its chosen local radius. On straight sides,
the tangent distance is `radius * tan(turn_angle / 2)`. On curved sides the
solver intersects radius-offset curves and checks tangency and planarity.
Convex and concave corners use the same calculation, in either winding direction.

Cinema 4D's cubic Bézier representation cannot express a circle exactly.
The computed circle is represented with arcs of at most 45°, limiting the
radial approximation error to less than 0.0005% of the radius. This is independent
of the input point spacing; viewport line tessellation is a separate approximation.

## Geometric limits

A radius larger than a feature permits cannot simultaneously preserve that
feature and remain the requested radius. An 18-step numerical search finds a
feasible local radius for constrained corners. Overlapping neighboring rounds
are reduced together proportionally until their trim intervals fit; unrelated
corners retain their radii. Multiple competing neighbors have no unique set of
simultaneous maximum radii. This is a local fit, not a global optimization.
Numerically unsolvable or nonplanar corners can still remain unchanged.

Linear and Bézier inputs receive the most accurate treatment. Other spline types
(B-spline, Akima, cubic) use Cinema 4D's evaluated line representation; their
accuracy depends on the source's intermediate-point settings. Prefer Bézier
inputs for curved-side fillets. A smooth existing round is preserved, not resized.

Planar corners in arbitrary 3D orientations are supported. Nonplanar curved-side
corners and 180° reversals may not admit a circular fillet and remain unchanged.
This is a local fillet solver, not a global self-intersection remover; distant
parts of complex paths can still intersect. Child generators are read through
Cinema 4D's native spline/cache evaluation; no modeling command runs inside
the generator.

## 1.1.3: dense straight runs and independent child timeouts

- Merge collinear monotone straight spans before cleanup and radius fitting,
  including runs across the closed seam. Curved spans and reversals are retained.
  Radius zero bypasses this simplification.
- Each source child has its own two-second processing budget. A timeout retains
  only that child's original contours; other children continue to round.
- Status reports removed redundant points and children whose evaluation stopped.
- Regression: a 4,000-point rectangle simplifies to four sides and all four
  corners round within budget; a first-child timeout preserves the second result.
- Live verification requires a Cinema 4D restart.

## 1.1.2: native curved font spans

- Reproduced the inner-tip failure using Segoe UI's original cubic x outline,
  aligned to the captured C4D x endpoints. Three spans have subtle curvature
  lost in the previous line-only fixture.
- Permit minor curved bridge turns and bounded near-straight flank cleanup.
- Tests cover the native cubic fixture at radii 5, 20, 40 and 1e12 in both
  directions. At request 40, the inner radii are approximately 20.3 and 20.5.
- Native C4D output verification still requires restarting the host.

## 1.1.1: larger inner rounds and huge requests

- Cleanup chooses the longest eligible local group instead of stopping at the
  first short flanks; sampled x inner tips now reach requested radius 20.
- Radius search brackets and cleanup tolerances are bounded by geometry scale,
  so extremely large requests do not defeat the search or disable cleanup.
- Exact straight-side geometry and direct parameter inversion avoid unnecessary
  iterative solves. Shared-edge reductions are applied simultaneously.
- Tests include a 1e15 request on a square (all four radii approach 50), and
  a 1e12 request on the sampled Text completing within the two-second budget.
- Native output verification remains pending after restarting C4D.

## 1.1.0: locally fitted radii and cleanup at smaller requests

- Removed the full-request-fit prerequisite that blocked inner cleanup at radius 5.
- Added per-corner radius fitting and neighboring overlap resolution.
- Tests cover both sampled x tips at radii 5 and 10, crowded rectangles, and
  independence from larger children. Sampled Text completes within two seconds.
- Native host verification remains pending after restart.

## 1.0.9: extra points around inner tips

- Allow minor flank direction changes inside an inward reconstruction group.
- Regression uses a fresh sampled copy of the user's Text: both inner x tips
  reconstruct and round at radius 10, in both traversal directions.
- Outer corners with overlapping requested-radius rounds still remain unchanged.

## 1.0.8: inner corner reconstruction

- Added radius-bounded concave-group cleanup before fixed-radius rounding.
- Tests cover winding, local containment, convex and open exclusions, continuity,
  and retaining successful cleanup despite unrelated unroundable corners.
- Text performance checks remain within the shared two-second geometry budget.
- The new font in the user's scene has not yet been verified in the live host.

## 1.0.7: requested radius without automatic reduction

- Removed the minimum-feature radius cap from the generator.
- Impossible or overlapping rounds remain unchanged and are counted in status.
- Regression checks verify that a tiny contour cannot reduce radius elsewhere.
- Micro-flat reconstruction is a proposed follow-up, not enabled in this version.

## 1.0.6: C4D tangent conversion and inclusive angle

- Corrected the C4D adapter: native handles are 3/4 of standard cubic Bezier
  handles. Reading uses 4/3; writing uses 3/4. This fixes bulging arcs and
  preserves the actual shape of curved input spans.
- Corners equal to the angle limit are included (within 1e-9 radians).
- Callback regression checks evaluate emitted handles with C4D's 4/3 factor,
  verify circle radii, and check reading the resulting spline back into cubics.
- A sampled copy of the live output confirmed the old handle distortion.
  Native patched output still needs checking after restarting C4D.

Maxon reference: https://developers.maxon.net/forum/topic/15594/correct-tangent-values

## 1.0.5: minimum opening filter

- Corrected selection to round smaller-side angles greater than the limit.
- New objects default to 30°; smaller limits select more corners.
- Tests cover tiny limits and values below, equal to, and above each opening.

## 1.0.4: smaller corner angle

- Selection uses the smaller left/right opening between the corner's sides.
- The angle control is now a maximum opening; new objects default to 150°.
- Circular radius geometry still uses the tangent direction change internally.
- Regression checks cover acute/obtuse openings, both turn signs, reversed
  traversal, and threshold boundaries.

## 1.0.3: independent child limits

- Radius limiting is separate for each evaluated source spline, including nested splines.
- Multi-contour sources retain a uniform radius within that source.
- Regression checks verify radius 100 on a large child alongside radius 10 on a
  constrained multi-contour child, and verify source grouping.

## 1.0.2: closure and uniform radius

- Multi-contour text sets the spline's global Closed flag correctly.
- Native input closure comes from the spline's global flag; LineObject inputs
  retain their per-contour closure information.
- Mixed open/closed input uses explicit coincident endpoints for closed contours
  because a single native C4D spline has one global closure switch.
- Radius is limited uniformly across every selected corner in the hierarchy.
- Tests cover closure output, separate contours with different radius limits,
  unchanged smaller requests, and text with no skipped selected corners.

## 1.0.1: text-spline freeze repair

- Removed nested Current State to Object and temporary-document destruction
  from the generator callbacks. Text uses its native spline contour.
- Cache rebuilds no longer dirty the plugin again via CheckDirty.
- Same-thread callback re-entry is blocked to prevent recursive evaluation.
- Geometry work has a shared two-second budget and cancellation checks.
  If interrupted, complete original contours are retained, with a status
  message, rather than returning partially processed text.

Geometry tests include real Arial outlines for “chamferPro”, “TEXT SPLINE”,
and 62 letters/digits at three radii. Callback tests cover recursion, cache
reuse, dirty-state feedback and timeout fallback. These tests do not replace
an in-application test after restarting C4D.

## Files and validation

Copy the entire `ChamferPro` directory into Cinema 4D's plugins folder and restart.
The plugin is independent of the existing chamfer generator. Its local plugin ID
is **1069990**; obtain a registered Maxon ID before public distribution.

The numerical regression suite is `tests/test_chamfer_pro.py` in the workspace.
It covers dense snag points, multiple angles, convex/concave turns, winding and
closed seams, exact fits and conflicts, Bézier preservation, 3D cases, endpoint
connections, branch junctions and angle filtering.

Live UI/cache integration still needs verification after restarting Cinema 4D:
the connected bridge does not permit Python execution and the separate c4dpy
runtime requests a license login. Opening a test scene through the bridge also
encountered a host/Python load deadlock; do not use that route for live validation.

The child-input spline generator follows the dual GetVirtualObjects/GetContour
pattern discussed in Maxon's SDK examples. That pattern has known host integration
complexity; test your downstream Sweep/Extrude/Mesher setup before relying on it
for production scenes.

SDK reference: https://github.com/Maxon-Computer/Cinema-4D-Python-API-Examples/blob/master/plugins/py-osffset_y_spline_r16/py-osffset_y_spline_r16.pyp
