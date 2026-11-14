"""Spike checks A (SimHub on serial ports) and B (PrmDb loads a fprime-prm-write .dat).

Run: <main .venv>/bin/python spike_check.py <check> [prm_path]; each process boots once (no power cycle here).
"""
import struct
import sys

import numpy as np

import _spike_fsw as fsw

IMU = struct.Struct(">Q3d3d")  # F´ serializes big-endian, no padding, no per-field framing


def check_a():
    fsw.boot("/nonexistent.dat")
    t, w, a = 123_456_789_000, [0.01, -0.02, 0.03], [1.5, -2.25, 9.80665]
    py_bytes = IMU.pack(t, *w, *a)
    np_bytes = np.array([(t, w, a)], dtype=[("t", ">u8"), ("w", ">f8", 3), ("a", ">f8", 3)]).tobytes()
    fprime_bytes = fsw.serialize_imu(t, w, a)
    print("IMU_SERIALIZED_SIZE", fsw.IMU_SERIALIZED_SIZE, "struct.calcsize", IMU.size)
    print("python struct.pack:", py_bytes.hex())
    print("python numpy      :", np_bytes.hex())
    print("F´ serializeTo    :", fprime_bytes.hex())
    assert py_bytes == fprime_bytes == np_bytes

    status = fsw.push(0, py_bytes)
    count, tt, rw, ra = fsw.imu_received()
    print("push status", status, "-> imuSink got", count, tt, rw, ra)
    assert status == 0 and count == 1 and (tt, rw, ra) == (t, w, a)

    echoed = fsw.drain(0)
    print("echo via typed imuEcho -> SimHub.busIn[0] serial:", [e.hex() for e in echoed])
    assert echoed == [fprime_bytes]

    # The comparison can fail: little-endian bytes differ and decode to wrong values.
    wrong = struct.pack("<Q3d3d", t, *w, *a)
    assert wrong != fprime_bytes
    fsw.push(0, wrong)
    _, tt2, rw2, _ = fsw.imu_received()
    print("little-endian push decodes as", tt2, rw2)
    assert tt2 != t
    # Malformed lengths, recorded not asserted: with FW_DIRECT_PORT_CALLS (on outside unit tests) the
    # topology's generated busOut_out FW_ASSERTs on a failed deserialize instead of returning the status.
    status = fsw.push(0, py_bytes[:-1])
    print("short push (55 B): status", status, "delivered count", fsw.imu_received()[0])
    status = fsw.push(0, py_bytes + b"\x00")
    print("long push (57 B): status", status, "delivered count", fsw.imu_received()[0])
    print("CHECK A PASS")


def check_b(prm_path):
    fsw.boot(prm_path)
    mu, mu_valid, dcm, dcm_valid, loaded = fsw.nav_params()
    print("nav.mu", mu, "valid" if mu_valid else "INVALID")
    print("nav.dcm_PB", dcm, "valid" if dcm_valid else "INVALID")
    print("parametersLoaded calls", loaded)
    return mu, mu_valid, dcm, dcm_valid


if __name__ == "__main__":
    if sys.argv[1] == "a":
        check_a()
    else:
        mu, mu_valid, dcm, dcm_valid = check_b(sys.argv[2])
        if sys.argv[1] == "b":
            assert mu_valid and dcm_valid
            assert mu == 3.986004418e14 and dcm == [[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
            print("CHECK B PASS")
        else:  # b-missing: no file, so no value can be valid
            assert not mu_valid and not dcm_valid
            print("CHECK B CONTROL PASS (missing file -> INVALID)")
