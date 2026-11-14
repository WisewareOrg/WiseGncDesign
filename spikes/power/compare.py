import pickle
def load(p): return pickle.load(open(p,"rb"))["results"]
def same(a, b):
    (da, ca), (db, cb) = a, b
    assert ca == cb, "command log differs"
    assert sorted(da) == sorted(db)
    rows = 0
    for n in da:
        va, ua = da[n]; vb, ub = db[n]
        assert ua == ub and va.dtype == vb.dtype and va.shape == vb.shape, n
        assert va.tobytes() == vb.tobytes(), f"{n} differs"   # bitwise, every row
        rows += va.shape[0] if va.ndim else 1
    return len(da), rows
A = load("res/fresh_3_alone.pkl")[0]
for name, f in [("fresh 7 then 3", "res/fresh_7_then_3.pkl"), ("fresh 3,7,3 (first 3)", "res/fresh_3_7_3.pkl"),
                ("shared 3 alone (today's build)", "res/shared_3_alone.pkl")]:
    print(name, "vs fresh 3 alone: bitwise equal; datasets, rows =", same(A, load(f)[{"res/fresh_7_then_3.pkl":1,"res/fresh_3_7_3.pkl":0}.get(f,0)]))
B = load("res/fresh_3_7_3.pkl")
print("fresh 3,7,3: third-position 3 vs first 3:", same(B[0], B[2]), "| case 7 differs from 3 (check can fail):", B[1][0]["tlm/nav.bodyEciPos"][0].tobytes() != B[0][0]["tlm/nav.bodyEciPos"][0].tobytes())
print("tlm datasets:", [n for n in A[0] if n.startswith("tlm/")], "| nav rows", A[0]["tlm/nav.bodyEciPos"][0].shape)
