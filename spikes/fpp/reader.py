"""Spike reader: native `fpp to-json` output -> instances, connections, constants, annotations."""
import json, sys

def q(n):
    return ".".join(n["qualifiedName"]["qualifier"] + [n["qualifiedName"]["base"]])

def walk(ast):
    """yield (annotations_pre, node_kind, node_data, annotations_post) for every AST member, recursively"""
    def rec(o):
        if isinstance(o, list):
            if len(o) in (2, 3) and isinstance(o[0], list) and isinstance(o[1], dict) and len(o[1]) == 1 \
               and all(isinstance(s, str) for s in o[0]) and (len(o) == 2 or all(isinstance(s, str) for s in o[2])):
                k, v = next(iter(o[1].items()))
                if isinstance(v, dict) and "node" in v:
                    yield o[0], k, v["node"]["AstNode"], (o[2] if len(o) == 3 else [])
            for x in o: yield from rec(x)
        elif isinstance(o, dict):
            for x in o.values(): yield from rec(x)
    yield from rec(ast)

def main(d):
    an = json.load(open(f"{d}/fpp-analysis.json"))["analysis"]
    ast = json.load(open(f"{d}/fpp-ast.json"))["ast"]
    inst = {k: v for k, v in an["componentInstanceMap"].items()}
    comp = {n: i for n, i in inst.items()}
    nodes = {}
    for pre, kind, n, post in walk(ast):
        nodes[n["id"]] = (kind, n["data"], pre, post)
    out = {"instances": {}, "constants": {}, "connections": {}, "annotations": {}}
    for nid, i in inst.items():
        cid = i["component"]["astNodeId"]
        out["instances"][q(i)] = {"type": nodes[cid][1]["name"], "baseId": i["baseId"]}
        out["annotations"][q(i)] = {"pre": nodes[int(nid)][2], "post": nodes[int(nid)][3]}
        out["annotations"][nodes[cid][1]["name"]] = {"pre": nodes[cid][2], "post": nodes[cid][3]}
    for nid, v in an["valueMap"].items():
        nid = int(nid)
        if nid in nodes and nodes[nid][0] == "DefConstant":
            (val,) = v.values()
            out["constants"][nodes[nid][1]["name"]] = val["value"]
    for tid, t in an["topologyMap"].items():
        tn = q(t)
        nm = lambda p: q(inst[str(p["interfaceInstance"]["InterfaceComponentInstance"]["astNodeId"])]) + "." + p["portInstance"]["General"]["specifier"]["name"]
        key = lambda c: json.dumps(c, sort_keys=True)
        fnum = {key(c): n for c, n in t["fromPortNumberMap"]}
        tnum = {key(c): n for c, n in t["toPortNumberMap"]}
        for grp, conns in t["connectionMap"].items():
            for c in conns:
                f, to = c["from"], c["to"]
                pn, tpn = fnum[key(c)], tnum[key(c)]
                out["connections"].setdefault(tn, []).append(
                    {"group": grp, "from": nm(f["port"]), "fromNum": pn, "to": nm(to["port"]), "toNum": tpn})
        # topology annotations
        out["annotations"][tn] = {"pre": nodes[int(tid)][2], "post": nodes[int(tid)][3]}
    for c in out["connections"].values(): c.sort(key=lambda x: (x["from"], x["fromNum"]))
    print(json.dumps(out, indent=1))

main(sys.argv[1])
