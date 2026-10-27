# NoiseSpread 1.0.2

Dense surface packing with native Cinema 4D Noise and render instances. Python generator for Cinema 4D 2026, with no external runtime dependencies.

## Use

Create **NoiseSpread** with Commander (Shift+C), then arrange children in this order:

1. Surface: a polygon object, primitive, or evaluated polygon hierarchy.
2. Source object.
3. Optional additional source objects.

Each source's local **+Y axis** aligns with the polygon normal. Its origin lies on the surface; place the source geometry above its own origin when you want it to sit on the surface. Source root position and rotation are replaced by placement/alignment. Source scale and nested geometry transforms contribute to the footprint. **The first child stays visible as the surface.** Only the source originals are hidden. An evaluated copy preserves the surface's geometry, transforms, tags and materials in the output. It also remains visible when no sources are present or packing fails.

The generated objects are native **Render Instances** sharing one hidden evaluated prototype per source in the output cache. Cinema 4D cannot render-instance a source consumed directly by a generator, so this prototype stage is necessary. Geometry is copied once per source, not once per placement. Source selection is deterministic and mixed using Seed.

## Controls

- **Size**, default 1: multiplier of the sources' size.
- **Size Feather**, default 0: proportional variation around Size. Size 1 / Feather 0.5 maps black to 0.5, white to 1.5. Formula: `Size * (1 - Feather + 2 * Feather * noise)`. Limited to 0.99 to avoid zero-radius objects and unbounded packing.
- **Size Noise**: native Cinema 4D Noise shader, initialized to **World** space. Click its thumbnail to open the standard Noise interface. Type, seed, octaves, global/relative scale, movement, animation, color, clipping, cycles, contrast and brightness are evaluated by the native shader. RGB is averaged and clamped to 0–1. Feather 0 bypasses sampling.
- **Polygon Selection**: exact polygon Selection Tag name, case-sensitive. Matching tags in the first child's evaluated hierarchy are combined. Missing names give an empty result and an explanatory status. Selection restricts instance centers; footprints can extend over a selection edge.
- **Packing → Seed**: changes placement/source choices; repeated evaluation at the same inputs is deterministic.
- **Packing → Instance Limit**, default 5000: safety cap, adjustable to 20,000. Status reports when the cap is reached.

## Packing and geometric limits

The solver propagates placements from touching neighbors, tries two-neighbor contacts for varying radii, then searches remaining gaps with area-weighted surface samples. Equal circular sources at Feather 0 form locally hexagonal domains, with a seed-dependent orientation. Curvature, boundaries, and disconnected domains can introduce seams. Unequal source sizes still require variable-radius packing at Feather 0.

Each source footprint is the maximum distance of its evaluated polygon vertices from its local +Y axis in the XZ plane. This includes off-center origins. Long rectangular sources therefore have larger bounding circles and visible empty space between their actual silhouettes. Sources require polygon geometry; put splines under an appropriate surface generator first.

Every accepted pair satisfies `distance between centers >= radius A + radius B` (floating-point tolerance about 1e-10 relative). Distances are measured as straight 3D chords in generator space, which is conservative on curved surfaces. This is a radius-clearance guarantee, **not** a collision test between tall, tilted or concave 3D meshes. Normal alignment uses the evaluated polygon face normals. Increase surface subdivisions for smoother alignment. Nonuniform scale on the NoiseSpread parent distorts the circular footprints; keep parent scale uniform when circular world-space clearance matters.

Packing is a finite heuristic, not an optimal circle-packing proof. Gaps remain at boundaries, sharp folds, narrow areas, and noise discontinuities. Sizes are sampled at the final centers and are never shrunk independently to fill gaps. Consequently a bounded noise range cannot reproduce arbitrary tiny gap-filling circles from a circle-packing illustration. Very small Size, highly detailed meshes, or high Instance Limit increase evaluation time. Limits: 300,000 surface points/triangles, 300,000 points per source, 64 hierarchy levels, 12,000 gap probes, plus a bounded contact-probe count. Escape/cancellation is checked during packing and instance construction.

## Noise coordinates

Sampling uses an evaluation-only shader clone and `InitRender / Sample / FreeRender`. The saved shader stays unchanged. World, Object, Texture, Camera and UV spaces are mapped explicitly because a generator has no render VolumeData. Spatial coordinates use a 100 scene-unit reference size; Global Scale and Relative Scale then modify this through the native shader. Object/Texture space is local to each evaluated surface mesh; there is no material Texture Tag transform. UV space requires a UVW tag. Camera space uses the render/editor camera. Screen/Raster modes require a rendering context and return an explicit unsupported-space status. Environment and bump-only controls have no meaning for a scalar surface-size map. This generator is not a pixel-exact reproduction of a material's texture projection.

Noise animation can change both sizes and the packing layout between frames; persistent particle identities and motion-blur correspondence are not provided.

## Install

Copy the entire `NoiseSpread` folder into the Cinema 4D user `plugins` folder, then restart Cinema 4D. This workstation's target is:

`C:/Users/Pavel/AppData/Roaming/Maxon/Maxon Cinema 4D 2026_1ABCDC12/plugins/NoiseSpread`

Local plugin ID: **1069993**. Obtain an official unique Maxon plugin ID before public distribution. The icon contains four filled, touching circles in **#0198FC**, with a transparent background; editable SVG and 512px PNG are in `res`.

## 1.0.1 changes

Keep the first surface visible, including when a selection name is invalid or sources are missing. Explicitly set generated instances to full-object viewport display. Report conservative generator bounds covering both surface and full source extents at every placement, improving framing and avoiding clipping of protruding instances. Fill the four icon circles.

## 1.0.2 changes

Fix an editor cancellation bug: interrupted packing or instance creation previously returned a valid surface-only cache, which Cinema 4D could keep indefinitely. Interruptions now invalidate the result and request a retry on the next evaluation pass without requiring a parameter edit. Dirty tracking excludes incidental child-cache and description changes to avoid unnecessary rebuilds. Native Cinema 4D regressions cover cancellation at both stages and automatic recovery. The reported primitive-sphere scene generates 182 instances in approximately 1.8 seconds on this workstation.

## Verification

`tests/test_noisespread.py` contains standalone geometry regressions. `tests/noisespread_host_check.py` runs actual registration, resource, evaluated-source, Noise, render-instance, selection and rendering checks in a separate Cinema 4D document using c4dpy. Reports, preview and an example scene are in `artifacts/noisespread` in the project. The GUI application requires a restart to load a newly installed Python plugin.

Verified on Cinema 4D **2026.3.4**: all 11 standalone tests pass; native host checks pass with 114 uniform instances, 111 noise-driven instances, and 134 instances on a curved primitive. Source scaling, mixed sources, translated surfaces, selection handling, default World space, native Noise scale changes and a nonempty Standard Renderer output were checked. Redshift and interactive GUI editing have not been separately verified.

API references: [native shader sampling](https://developers.maxon.net/docs/py/2024_4_0a/modules/c4d/C4DAtom/GeListNode/BaseList2D/BaseShader/index.html), [Noise parameters](https://developers.maxon.net/docs/cpp/2026_3_0/page_resource_xslanoise.html), [render instance modes](https://developers.maxon.net/docs/Cinema4DCPPSDK/page_resource_oinstance.html).
