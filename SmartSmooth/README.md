# SmartSmooth 1.1.0

Phong-driven subdivision generator for Cinema 4D 2026.2 or newer. Tested in 2026.3.4 on Windows.

## Use

1. Add **SmartSmooth** from Cinema 4D's Commander (Shift+C).
2. Place your polygon mesh or primitive beneath it.
3. Set **Iterations** (default **3**, range **0–6**). Zero skips smoothing; the optional bevel can still be used.
4. Control creases with the **input object's Phong tag**: **Angle Limit / Phong Angle** and **Use Edge Breaks**. Use Cinema 4D's **Break Phong Shading** command to mark individual edges.

There are no weight controls or extra setup. Existing SDS weights and Normal tags do not control the result. With no Phong tag, the surface subdivides smoothly. Open boundaries remain boundaries and smooth along their length. Separate unwelded polygons remain separate; weld them before subdivision when appropriate.

Viewport and render use the same iteration count and CPU subdivision. A quad becomes four quads per iteration. A two-million-polygon estimate prevents accidental excessive allocation.

## Crease bevel

Bevel is applied after smoothing along the inherited Phong creases. It modifies the same mesh and joins the rim strips to the surrounding faces, including corners.

- **Bevel Width**, default **0**: fixed-distance offset in object units. Zero disables bevel exactly. Native overlap limiting can reduce the offset where there is insufficient room.
- **Bevel Subdivision**, default **3**: intermediate profile loops running along the crease (3 loops make 4 strips across the bevel). Range 0-64.
- **Bevel Roundness**, default **1**: range -1 to 1. Positive values give a rounded outward profile, 0 is a geometrically flat chamfer, and negative values give an inward/recessed profile.

Viewport and render use identical settings. Existing saved objects retain their saved iterations; new objects default to 3. Tests verify flat/concave/convex profiles, increasing loop counts, closed corner connectivity, and curved creases with no new open seams.

## Crease behavior

SmartSmooth reads the evaluated input's Phong information, turns angle-based and explicit breaks into a crease mask, and uses Cinema 4D's native OpenSubdiv Catmull–Clark evaluator. Internally, temporary edge-only SDS weights encode this mask on a private clone; user weight tags are ignored and temporary weight tags are removed from output. No point weights are applied. This lets a two-edge crease chain follow its cubic curve rather than freezing its vertices; multi-crease junctions remain corners. Output inherits explicit Phong breaks, so shading stays sharp across the refined creases.

Angle thresholds are evaluated on the original input, once per rebuild, rather than reapplied to each subdivision level. **Use Edge Breaks** controls explicit breaks independently of the angle threshold. Changes to Phong settings and break selections invalidate the generator cache.

The native evaluator preserves its supported UV and material/selection remapping. N-gons follow native OpenSubdiv triangulation behavior. Inputs with degenerate or non-manifold topology should be cleaned first. Non-polygon objects in an evaluated hierarchy are handled by Cinema 4D's normal hierarchy conversion.

## Installation

Copy the complete `SmartSmooth` folder into your Cinema 4D preferences `plugins` folder and restart Cinema 4D. On this workstation:

`C:/Users/Pavel/AppData/Roaming/Maxon/Maxon Cinema 4D 2026_1ABCDC12/plugins/SmartSmooth`

No external runtime packages are required by the plugin. Local development IDs: generator `1070000`, progress handler `1070001`. Obtain official Maxon IDs before public redistribution.

Calculations show progress in the bottom-left status bar: measurable progress while reading crease data, a busy indicator during native subdivision. UI calls run only on the main thread. Completion, errors, and cancellation clear the status; reuse of cached geometry leaves it untouched. Native subdivision is interruptible at the surrounding stage boundaries; the native call itself may finish before cancellation is observed.

## Validation

`tests/host_check.py` runs in `c4dpy` with this plugin in `g_additionalModulePath`. It uses detached documents and does not modify open scenes. It checks registration/resources, the curved-crease cubic mask, inherited sharp edges, angle thresholds, Phong invalidation, ignored input weights, iteration counts, viewport/render equivalence, primitives/UVs, cancellation, and an actual Standard render.

`python -m unittest discover -s SmartSmooth/tests -p "test_*.py"` checks main-thread status handling, coalescing, cache/idle behavior and cancellation. `tests/build_icon.py` reproduces the icon using Pillow and aggdraw (development-only dependencies).

Native API references: [Phong break extraction](https://developers.maxon.net/docs/py/2026_2_0/modules/c4d/C4DAtom/GeListNode/BaseList2D/BaseObject/PointObject/PolygonObject/index.html), [SDS weights](https://developers.maxon.net/docs/py/2026_2_0/modules/c4d/C4DAtom/GeListNode/BaseList2D/BaseTag/HNWeightTag/index.html), [Subdivision settings](https://developers.maxon.net/docs/py/2026_2_0/cinema_resource/object/osds.html).
