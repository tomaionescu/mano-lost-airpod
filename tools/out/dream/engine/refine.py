"""Local search around the best candidates of search.py: refine.py <search json> <index>... -> refine_<n>.json"""
import json
import sys
import search

if __name__ == "__main__":
    src = json.load(open(sys.argv[1]))
    out = []
    for k in map(int, sys.argv[2:]):
        print("candidate", k)
        best = search.refine(src[k]["q"], seed=k + 3)
        if best:
            out.append({"from": k, "q": best[0], "s": best[1], "cost": best[2]})
    json.dump(out, open("refine_%s.json" % "_".join(sys.argv[2:]), "w"), indent=1)
