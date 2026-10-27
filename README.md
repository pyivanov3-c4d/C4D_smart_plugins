# C4D smart plugins

Latest locally developed Cinema 4D plugin sources, imported on 2026-10-27.

- ChamferPro
- MesherPro
- Metaspline
- NoiseSpread
- Shift90Rotate (90° Rotate, including World/Object coordinate mode)
- smartBoolean 1.0.21
- SmartSmooth 1.1.0 (Phong-driven subdivision and connected crease bevel)
- SplineTensor 0.10.0 (experimental XOR masking)
- SVGLoader (Windows vector edition, bundled runtime dependencies included)

Each plugin folder includes its resources and installation/use notes. Copy the required complete plugin folder into the Cinema 4D user plugins directory and restart Cinema 4D. See each plugin README for requirements and limitations.

Sources were recovered from the C4D plugins development project and compared with installed copies. Shift90Rotate comes from the current installed copy. Existing tests and fixtures are retained. Historical backup folders and Python caches are excluded. SplineTensor remains experimental; inclusion here does not imply production certification.

Run host-independent tests with Python 3.11:

    python -m unittest discover -s tests -p "test_*.py"
    python -m unittest discover -s SplineTensor/tests -p "test_*.py"
    python -m unittest discover -s SmartSmooth/tests -p "test_*.py"

Cinema 4D integration checks require the host runtime; see the individual test scripts and SplineTensor/TESTING.md.
