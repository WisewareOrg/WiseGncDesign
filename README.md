# WiseGncDesign

WiseGncDesign is the flight home for Wiseware's GNC work. GNC algorithms live under
`algorithms/`, framework-free — no simulation or flight-framework import or include anywhere
under that directory — Python primary with C++ variants, so the same algorithm can be hosted
unmodified wherever it runs. `cdh/` is the C&DH (command and data handling) partition: a
transport-independent data dictionary of each algorithm's input and output fields, resolved by
each transport (Basilisk, an F' host, a cFS host, and others to follow) in its own sibling
directory.

Flight, simulation and analysis are split into three homes so any one can be replaced without
touching the other two: framework-free algorithms live here, in WiseGncDesign; simulation plants
and Monte Carlo campaigns that import those algorithms live in
[WiseDynamics](https://github.com/WisewareOrg/WiseDynamics); analysis of the runs they produce
lives in [WiseGncAnalysis](https://github.com/WisewareOrg/WiseGncAnalysis), which reads the data
contract and knows nothing about which simulation produced it.

## Layout

- `algorithms/` — framework-free GNC algorithms (see its own `README.md`).
- `cdh/` — the C&DH partition: a transport-independent data dictionary, resolved by each
  transport as a sibling directory (see its own `README.md`).
- `scripts/check-no-framework.sh` — the gate that keeps `algorithms/` framework-free.
- `docs/decisions/` — this repository's ADRs (none yet).
