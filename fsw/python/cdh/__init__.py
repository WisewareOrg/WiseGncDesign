"""The Python build's CDH: its ground link, commands, telemetry, parameters and sensor inputs.

`ground_link` holds what the ground uplinks and drains, `commands` dispatches by name, `telemetry`
turns a telemetry tuple into writes, `parameters` reads the case's record, and `inputs` pairs each
sensor role from FPP and converts its bus struct to the GNC's type.
"""
