# Metaspline 2.2.1

Cinema 4D 2026 spline generator for Windows x64. Place closed spline children below Metaspline. Open contours are skipped. Exactly four editable controls are provided; a read-only line reports the result and version.

## Vector pipeline

1. Union overlapping closed shapes, respecting holes within each source.
2. **Fallow Distance:** within Collapse + Fallow, form smooth bulges on the facing sides. Increasing Fallow increases the pull. The shapes stay separate while their original gap is above Collapse Distance.
3. **Collapse Distance:** when the original gap passes below this threshold, join those same shoulders with a thin hourglass neck. The neck grows thicker and its shoulders become smoother as the gap closes. Collapse remains a total gap threshold, consistent with 1.x.
4. **Viscosity (0-100%):** lower values thicken the neck sooner; higher values keep it narrow longer as the source gap decreases. Collapse still determines when contact starts. This controls geometric progression, not time-based simulation.
5. **Smooth (0-100%):** overall area-preserving rounding toward a circular drop for each connected contour. With one valid child, only smoothing operates; at 0% its native cubic controls remain unchanged.
6. Fit sparse cubic Bezier contours into one globally closed native SplineObject for downstream generators.

Defaults: Collapse 20, Fallow 40, Viscosity 25%, Smooth 15%. The spelling Fallow is intentional. Distances use scene units. Percent displays 0-100% and stores normalized 0..1.

There is no bitmap, raster distance field, marching-squares tracing or grid-size threshold. Native Clipper performs vector polygon unions. Curved inputs are adaptively tessellated for polygon operations, then fitted back to Bezier curves. These are approximate vector booleans, not analytic cubic intersections.

## Progress and caching

Calculations report their stage in Cinema 4D's bottom-left status bar: percentages for measurable work, busy indication during child acquisition. Workers queue updates; only a main-thread message plugin touches the UI. Completion, errors and cancellation clear the job. Cached results leave status untouched. Union, bridge, fallow and final-result caches avoid repeating unaffected stages.

## Limits

- Inputs must share a plane, including rotated planes. Non-coplanar inputs receive only overall smoothing.
- Tessellation tolerance is approximately extent/8000; fitting targets four times this tolerance at its samples. Tiny details can be lost. This is not a strict global Hausdorff bound.
- One closest rounded bridge is added per eligible pair of disconnected outer shapes. Multiple separate contacts between the same pair are not all bridged. Holes stay with their outer shape; bridge decisions use outer boundaries.
- Fallow moves facing outer regions, not holes. Smooth rounds holes independently and can change their clearance. Extreme configurations can still self-intersect after fitting or global rounding.
- A six-second cooperative budget, span limit and 96-island limit bound the work. Native clipping calls cannot be interrupted midway. Work limits retain closed originals; failed child reads do not discard siblings. Native child evaluation cannot be interrupted from Python.
- Native dependencies are bundled for Windows x64 CPython 3.11 (C4D 2026) and 3.12 (offline tests). Other platforms need matching binaries.

## Installation

Copy the complete Metaspline folder into the C4D plugins folder and restart. Create Metaspline with Commander (Shift+C).

Workstation target: `C:/Users/Pavel/AppData/Roaming/Maxon/Maxon Cinema 4D 2026_1ABCDC12/plugins/Metaspline`.

Local IDs: generator 1069991; progress message plugin 1070002. Register official IDs before public redistribution. The transparent blue merged-circle icon is unchanged.

## Dependencies

Bundled pyclipper 1.4.0 wraps Clipper 6.4.2. No pip installation is needed. A private package name avoids interfering with other plugins. MIT and Boost licenses and wheel SHA-256 provenance are in `vendor`. [Upstream](https://github.com/fonttools/pyclipper).

## Validation

Tests cover original cubic circles/font outlines, union, bridges, stage ordering, holes, open inputs, unequal shapes, rotated planes, percentage bounds, sparse fitting, native handles, closure, caches, cancellation and main-thread progress.

Run: `python -m unittest discover -s tests -p "test_metaspline*.py" -v`.

Native host check: `tests/metaspline_host_check.py`, run with c4dpy in a separate process. No bridge scene opening or document evaluation inside a generator callback is used.

Offline median times (three runs): union 0.615 to 0.011 s; bridge 0.768 to 0.020 s; fallow 0.706 to 0.248 s; unequal outlines 1.080 to 0.201 s. Cached Smooth edit: 0.053 s. Fixture timings do not guarantee arbitrary-scene performance.


## 2.1.0: progressive liquid neck

Facing shoulders are formed before contact and retained when the topology joins. A four-cubic hourglass neck replaces the abrupt capsule: a narrow neck first appears just inside Collapse Distance, then grows with 1-gap/Collapse. Concave shoulders are progressively rounded as the shapes approach, with this rounding retained after the original shapes overlap. No extra controls are added. Smooth remains overall rounding; the bulge/neck/merge progression works even at Smooth=0. Nearest-edge queries now use a bounding-box tree.

The sequence preview holds Collapse=20, Fallow=60 and Smooth=0 fixed while reducing the source gap from 100 to 35, 19.5, 8 and -5. Regression checks confirm separate contours before contact, a narrow joined neck, increasing neck thickness, and less than 1% area change across the contact threshold for this fixture. These are vector approximations, not a physical fluid simulation.


## 2.1.1: tiny bridge onset

Bridge half-width now grows with penetration depth to the power 2.5, with a much smaller numerical floor. Shoulder rounding ramps in cubically. Fitting precision is tightened only near the throat; body curves keep the normal tolerance. Overall smoothing is delayed around a newly forming bridge so it does not immediately thicken it; Smooth=100% still selects a round drop. A separate rounding bug was fixed: the reference center now uses equal arc-length samples instead of an uneven vertex mean, preventing jumps at very small Smooth values.

39 offline tests pass. With radii 45 and 20, Collapse=20, Fallow=60, Smooth=15%, the fixture has a single initial connection approximately 0.3-0.4 units wide at gaps 19.99-19.5, compared with a 90-unit main diameter. The fit is still approximate; arbitrarily thin geometry is bounded by vector tolerance.


## 2.2.0: adjustable viscosity

Viscosity defaults to 25%. Its 0-100% range adjusts the growth exponent from 1 to 4, together with shoulder rounding and smoothing maturity. Lower values reveal a neck sooner after contact; higher values retain the thin kissing connection longer. Contact onset is unchanged. Viscosity edits reuse the input union and facing attraction. 41 offline regression tests cover growth, contact onset, caching and existing geometry behavior.


## 2.2.1: fourfold viscosity response in both directions

The 0-100% slider now amplifies the viscosity response fourfold in logarithmic space around the unchanged 25% reference. Lower settings grow and round bridges faster; higher settings retain narrow necks longer. Growth and shoulder exponents remain positive, and Collapse still determines onset. The multiplier applies to response sensitivity, not a literal fourfold neck width.
