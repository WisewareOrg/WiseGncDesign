"""The C&DH (command and data handling) partition: hosts an algorithm in a simulator.

Each host feeds the algorithm its sensor readings; `gnc_cdh.link` states the link a host presents
to the ground.
"""

UNITS = {"q_BN": "", "r_BN_N": "m", "v_BN_N": "m/s"}
"""The units of each estimate the F´ host records, `est/<name>`, by its name."""
