# ml/score_case.py
import json, sys, math
from pathlib import Path
import torch
import torch.nn.functional as F

from featurizer import case_to_pyg
from train_gnn import GATv2  # re-use same model class

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "graphs"
MODEL_PATH = DATA / "fintrace_gatv2.pt"

# ---------- Consensus filter ----------
def build_adj(case):
    ids = [int(n["id"]) for n in case["nodes"]]
    id2idx = {nid:i for i,nid in enumerate(ids)}
    adj = [[] for _ in ids]
    edges_idx = []
    for e in case["edges"]:
        s = id2idx.get(int(e["source"])); t = id2idx.get(int(e["target"]))
        if s is None or t is None: 
            continue
        adj[s].append(t); adj[t].append(s)
        edges_idx.append((s,t))
    return ids, id2idx, adj, edges_idx

def consensus_mask(adj, probs, tau=0.56, neighbor_tau=0.45, min_neighbors=2):
    keep = [False]*len(probs)
    for i,p in enumerate(probs):
        if p <= tau: 
            continue
        high_nbrs = sum(1 for j in adj[i] if probs[j] > neighbor_tau)
        if high_nbrs >= min_neighbors:
            keep[i] = True
    return keep

# ---------- Pattern risk ----------
def pattern_risk(keep, probs, edges_idx, top_frac=0.10):
    N = len(probs)
    if N == 0:
        return 0.0, {}
    flagged = [i for i,k in enumerate(keep) if k]
    flagged_frac = len(flagged)/N

    sorted_probs = sorted(probs, reverse=True)
    top_k = max(5, int(math.ceil(top_frac * N)))
    topk_mean = sum(sorted_probs[:top_k]) / top_k

    mean_flagged = sum(probs[i] for i in flagged)/len(flagged) if flagged else 0.0

    both = 0; at_least_one = 0
    for (u,v) in edges_idx:
        fu, fv = keep[u], keep[v]
        if fu or fv: at_least_one += 1
        if fu and fv: both += 1
    cluster_density = both / max(1, at_least_one)

    # Weighted blend, clipped to [0,1]
    score = 0.40*topk_mean + 0.35*mean_flagged + 0.15*flagged_frac + 0.10*cluster_density
    score = max(0.0, min(1.0, score))
    metrics = {
        "topk_mean": topk_mean,
        "mean_flagged": mean_flagged,
        "flagged_frac": flagged_frac,
        "cluster_density": cluster_density
    }
    return score, metrics

def score_case(inp_path, out_path="scored.json", tau=0.56, neighbor_tau=0.45, min_neighbors=2):
    with open(inp_path) as f:
        case = json.load(f)

    g = case_to_pyg(case)
    model = GATv2(g.x.size(1))
    model.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
    model.eval()

    with torch.no_grad():
        probs = F.softmax(model(g.x, g.edge_index), dim=-1)[:,1].cpu().tolist()

    ids, id2idx, adj, edges_idx = build_adj(case)

    # consensus filter to reduce isolated false positives
    keep = consensus_mask(adj, probs, tau=tau, neighbor_tau=neighbor_tau, min_neighbors=min_neighbors)

    # annotate nodes
    for i, node in enumerate(case["nodes"]):
        node["risk"] = float(probs[i])
        node["flagged"] = bool(keep[i])

    # top-K list for UI
    topk = sorted(
        [{"id": int(case["nodes"][i]["id"]), "risk": float(probs[i]), "flagged": bool(keep[i])}
         for i in range(len(case["nodes"]))],
        key=lambda x: x["risk"], reverse=True
    )[:25]
    case["topk"] = topk

    # graph-level aggregate risk
    graph_score, metrics = pattern_risk(keep, probs, edges_idx)
    case["graph_risk"] = float(graph_score)
    case["graph_metrics"] = metrics
    case["thresholds"] = {"tau": float(tau), "neighbor_tau": float(neighbor_tau), "min_neighbors": int(min_neighbors)}

    with open(out_path, "w") as f:
        json.dump(case, f, indent=2)
    print(f"Scored case saved to {out_path} | graph_risk={graph_score:.3f} (tau={tau}, neighbor_tau={neighbor_tau}, min_neighbors={min_neighbors})")

if __name__ == "__main__":
    inp = sys.argv[1] if len(sys.argv) > 1 else str(next((DATA/"test").glob("*.json")))
    tau = float(sys.argv[2]) if len(sys.argv) > 2 else 0.56
    neighbor_tau = float(sys.argv[3]) if len(sys.argv) > 3 else 0.45
    min_neighbors = int(sys.argv[4]) if len(sys.argv) > 4 else 2
    score_case(inp, "scored.json", tau=tau, neighbor_tau=neighbor_tau, min_neighbors=min_neighbors)