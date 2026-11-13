"""The C&DH (command and data handling) partition: hosts an algorithm in a simulator.

Each host feeds the algorithm its sensor readings and records its estimate in the run file.
"""

UNITS = {"q_BN": "", "r_BN_N": "m", "v_BN_N": "m/s"}
"""The units of each estimate a host records, `est/<name>`, by its name."""
