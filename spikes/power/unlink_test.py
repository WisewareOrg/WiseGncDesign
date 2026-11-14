"""Does unlinking each copy after load let the next copy reuse the inode and alias the handle?"""
import sys, os, numpy as np
sys.argv = ["x", "shared", "0"]
src = open("drive.py").read().replace("\nmain()\n", "\n")
src = src.replace("    return mod\n", "    inodes.append(os.stat(dst).st_ino); dst.unlink()\n    return mod\n", 1)
inodes = []
exec(compile(src, "drive.py", "exec"))
ms = [fresh_copy(k) for k in range(4)]
print("inodes:", inodes)
mu = 3.986004360e14
for m in ms: m.boot(mu=mu, dcm_PB=np.eye(3))
ms[0].step(t_ns=10**9, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))
print("telemetry writes per copy (only copy 0 stepped):", [len(m.telemetry()) for m in ms])
