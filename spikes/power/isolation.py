"""Two copies in one process hold separate statics: stepping A leaves B untouched."""
import sys, numpy as np
sys.argv = ["x", "shared", "0"]
exec(compile(open("drive.py").read().replace("\nmain()\n", "\n"), "drive.py", "exec"))
A, B = fresh_copy(0), fresh_copy(1)
print("A is B:", A is B)
mu = 3.986004360e14
for m in (A, B): m.boot(mu=mu, dcm_PB=np.eye(3))
A.step(t_ns=10**9, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))
print("B telemetry writes before A's drain (B never stepped):", len(B.telemetry()))
print("A telemetry writes:", len(A.telemetry()))
