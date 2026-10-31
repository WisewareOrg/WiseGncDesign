"""The Basilisk transport's resolution table: the reader or message/payload type and payload
field each role's signal actually needs."""

from Basilisk.architecture import messaging

# (role, signal) -> (reader type, payload field) for an input role, or
# ((payload type, message type), payload field) for an output role.
SIGNALS: dict[tuple[str, str], tuple] = {
    ("imu", "angular_rate"): (messaging.IMUSensorMsgReader, "AngVelPlatform"),
    ("imu", "specific_force"): (messaging.IMUSensorMsgReader, "AccelPlatform"),
    ("nav_att", "sigma_BN"): ((messaging.NavAttMsgPayload, messaging.NavAttMsg), "sigma_BN"),
    ("nav_trans", "r_N"): ((messaging.NavTransMsgPayload, messaging.NavTransMsg), "r_BN_N"),
    ("nav_trans", "v_N"): ((messaging.NavTransMsgPayload, messaging.NavTransMsg), "v_BN_N"),
}

# The C&DH partition's neutral frame names, translated to AlgorithmModule's own frame tokens.
FRAMES = {"platform_to_body": "P->B"}
