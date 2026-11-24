"""The Python build's CDH: its ground link, commands, telemetry, parameters, inputs and outputs.

`ground_link` holds what the ground uplinks and drains, `commands` dispatches by name, `telemetry`
logs a telemetry tuple as an entry per component per frame and reads one as writes, `parameters`
reads the case's record, `inputs` pairs each sensor role from FPP and converts its bus struct to the
GNC's type, and `outputs` pairs each actuator role and converts the GNC's output to its bus struct.
"""
