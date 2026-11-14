#!/usr/bin/env bash
cd "$(dirname "$0")"; export PYTHONDONTWRITEBYTECODE=1; P=/home/wise/code/WiseGncDesign/.venv/bin/python
$P drive.py fresh 3, --out res/fresh_3_alone.pkl > res/det1.log 2>&1
$P drive.py fresh 7,3 --out res/fresh_7_then_3.pkl > res/det2.log 2>&1
$P drive.py fresh 3,7,3 --out res/fresh_3_7_3.pkl > res/det3.log 2>&1
$P drive.py shared 3, --out res/shared_3_alone.pkl > res/det4.log 2>&1
$P drive.py shared 100 > res/shared100_gc.log 2>&1
$P drive.py fresh 100 > res/fresh100_gc.log 2>&1
$P drive.py shared 100 --no-gc > res/shared100_nogc.log 2>&1
$P drive.py fresh 100 --no-gc > res/fresh100_nogc.log 2>&1
echo done > res/DONE
