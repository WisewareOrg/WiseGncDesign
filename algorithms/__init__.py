"""GNC algorithms, written in numpy and numba, with SciPy for numba's matrix products.

Each is a component of a GNC sub-topology in `fsw/fpp/gnc/`: its `step` takes its inputs in their
FPP types, named for its input ports, and returns its outputs and telemetry as its FPP tuples.
`utils/` holds the math they share, a folder per utility.
"""
