# Metaspline 1.0.6

Cinema 4D 2026 Python spline generator. No external Python packages required.

Place closed spline objects under Metaspline. Open contours are skipped. Null hierarchies and native spline generators such as Text are read through their evaluated spline/cache. The Object tab has exactly three editable controls; the last line is read-only status.

- **Collapse Distance** (default 20): closed shapes separated by less than this distance form a liquid bridge. Overlapping shapes are united even at zero Collapse Distance.
- **Fallow Distance** (default 40): additional attraction range beyond Collapse Distance, using inverse-square attenuation so larger Fallow values pull the outlines progressively closer to collapse. The spelling is intentional. Shapes in this range bend toward each other while remaining separate, within sampling tolerance.
- **Smooth** (default 15%): liquid rounding, from 0% to 100%. Area-preserving diffusion and a smooth transition to a circular equilibrium make each connected contour progressively become a rounded drop. At 100% each contour becomes circular. Small details are removed as the value increases. One valid child only receives this smoothing; its liquid interactions are disabled. At 0% its original cubic curves are retained.

Output is one native, globally closed Bezier SplineObject with one or more closed segments. Field-generated sections use adaptive least-squares Bezier reconstruction with shared smooth knot tangents; isolated original contours keep their native Bezier handles at Smooth=0. This geometry is intended for Extrude, Sweep, Loft and other spline consumers. Live downstream compatibility still needs confirmation after C4D restart.

## Geometric limits

This is a planar distance-field generator, not an exact CAD boolean or a 3D fluid simulation. Inputs can share any rotated plane. Non-coplanar inputs receive smoothing only; status explains this fallback. All retained control points must lie within 0.01% of the scene extent of the common plane.

Interacting shapes are sampled on a grid with approximately 320 cells across each connected cluster's largest dimension. Read-only status reports the grid spacing. Expect roughly one to two cells of positional/threshold uncertainty. Tiny holes, narrow gaps and features below that size may disappear; an infinitesimal bridge at the collapse threshold cannot be guaranteed. A mandatory filter of approximately two grid cells removes stair steps before Bezier fitting, including at Smooth=0. Fitting targets 0.65 grid-cell residual at the sampled contour points; this is not a strict global Hausdorff bound. Knot counts adapt to outline complexity. For widely different scales, use separate Metaspline objects.

Nested contours within each source use even-odd filling, preserving holes. Distinct outer islands interact. The two nearest islands determine the liquid field at each point; complex three-way junctions are an approximation and can have seams. Smooth approximately preserves each contour's planar area. It rounds each output contour independently; disconnected shapes are not forcibly united by Smooth. Holes are rounded independently too, so high values can change hole clearance or produce overlaps. Cubic fitting introduces small additional area error. Outside the influence range, isolated contours are retained exactly at Smooth=0; remote portions of an interacting contour have grid approximation error.

Geometry processing has a six-second cooperative budget, a 24-island interacting-cluster cap, 350,000 grid-cell cap and 100,000 input-span cap. Completed clusters remain available when later work runs out; unprocessed clusters retain closed originals. Each top-level child read gets a separate 0.6-second cooperative budget. A native C4D evaluation call itself cannot be interrupted from Python. Errors are reported in the status line or Console.

## Installation

Copy the whole `Metaspline` folder into the Cinema 4D user plugins folder and restart Cinema 4D. Create **Metaspline** through Commander (Shift+C). Local plugin ID: **1069991**; obtain an official unique Maxon ID before public redistribution.

Installed target for this workstation:
`C:/Users/Pavel/AppData/Roaming/Maxon/Maxon Cinema 4D 2026_1ABCDC12/plugins/Metaspline`

The icon is an outlined pair of diagonally merged circles with unequal radii, #0198FC (RGB 1,152,252), on transparent background. The editable SVG and 512px PNG are in `res`.

## Validation

Offline tests are in `tests/test_metaspline.py` and `tests/test_metaspline_callbacks.py` in the project. They cover original cubic circles and font contours, overlaps, collapse/fallow behavior, holes, open inputs, rotated planes, non-planar fallback, finite closed output, budgets, native handle conversion, global multi-contour closure, native Text evaluation, cache dirty handling and callback reentry. Stub tests verify callback logic, not host ABI compatibility.

The C4D bridge was unavailable (connection refused) during installation. Registration, interactive performance, child hiding, animated updates and Extrude/Sweep behavior have **not** been live-tested. After restart: create two closed Circle children, move their separation across Collapse and Collapse+Fallow; test an open Arc, a Text spline with counters, a single closed spline, and Metaspline under Extrude. No document was opened through the bridge, and no bridge Python execution was used.

The adapter follows the project's proven native spline convention: read C4D Bezier handles at 4/3 and write at 3/4. No Current State to Object, temporary document evaluation or document opening occurs in generator callbacks. Both spline callbacks are provided, consistent with Maxon's spline-generator example:
https://github.com/Maxon-Computer/Cinema-4D-Python-API-Examples/blob/master/plugins/py-osffset_y_spline_r16/py-osffset_y_spline_r16.pyp

## 1.0.1 changes

Dense field polylines are reconstructed as sparse cubic Bezier spans. Smoothed single-child contours also use cubic fitting. Smooth remains a normalized 0..1 C4D percentage parameter displayed as 0–100%; its smoothing radius is multiplied by ten. Existing saved Smooth values therefore produce stronger smoothing. Offline regressions: 25 tests, including reconstruction accuracy, knot tangent continuity and point-count reduction.

## 1.0.2 changes

Smooth now applies area-preserving drop rounding with circular equilibrium at 100%, rather than shrink-only relaxation. Fallow attraction uses squared smooth proximity. One boundary-distance transform replaces separate inside/outside transforms, within the existing grid tolerance. Linear-time sliding filters replace convolution, per-cell sorting is removed, and per-generator/per-thread caches retain distance fields and up to four contour results for fast Smooth edits. Field caching is capped at 500,000 cells. Cache keys include source geometry, grid geometry, Collapse and Fallow as appropriate.

28 offline tests pass. Two-circle benchmark: fresh Smooth=15% evaluation improved from 0.993 s to 0.703 s (new measurement is the median of three runs); cached Smooth edit took 0.071 s. These are standalone Python timings, not live C4D measurements.

## 1.0.3: percentage range correction

Live C4D inspection confirmed the old resource MAX 1 was parsed as runtime 0.01 (1%), preventing the Smooth control from reaching 100%. The resource now uses display-percent MAX 100 and STEP 1; GetDDescription explicitly sets normalized runtime field and slider bounds to 0..1 and step 0.01. Existing scene values are retained. After restart, increase Smooth to 100% to reach the round equilibrium. 29 offline tests pass; a callback regression verifies correction of a stale 1% maximum.

## 1.0.4: inverse-square Fallow

Within the influence band, t=(gap-Collapse)/Fallow and attraction weight=(1/(1+t)^2-1/4)/(3/4). Weight is one at Collapse and zero at the outer boundary. The attraction amplitude now scales with the local gap, so large Fallow values approach collapse instead of saturating at a weak pull limited by Collapse Distance. The analytic field remains separate above Collapse; sub-grid gaps can still disappear at extreme values. 30 offline tests pass, including increasing Fallow from 25 to 100, 1000 and 100000 for a fixed gap.

## 1.0.5: stronger facing-side attraction

The inverse-square proximity is calibrated to contour travel rather than field blend strength. Locally parallel facing boundaries move approximately weight times half the gap. Smoothed distance gradients restrict attraction to facing sides, with continuous blending near Collapse. This gives more visible bulging at large Fallow without inflating the backs. Sub-cell contour artifacts below one quarter grid-cell area are discarded. 32 offline tests pass, including unequal radii and large Fallow=300. Existing grid tolerance still applies; live C4D verification requires restart.

## 1.0.6: near-bridge attraction

The remaining separation is squared: attraction w becomes 1-(1-w)^2. Thus 50% attraction becomes 75%, and 80% becomes 96%. To avoid grid-induced welds above Collapse Distance, the attraction keeps a minimum target slit of 2.5 grid cells. Tiny traced loops below two grid-cell areas are suppressed; very small intentional holes are also below this limit. 32 offline tests pass. Restart C4D to load the update.
