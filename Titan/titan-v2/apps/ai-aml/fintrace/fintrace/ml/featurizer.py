# ml/featurizer.py
from pathlib import Path
import json
import numpy as np
import torch
from torch_geometric.data import Data

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

def load_case(path):
    with open(path) as f: 
        return json.load(f)

def build_maps(nodes):
    ids = [int(n["id"]) for n in nodes]
    id2idx = {nid:i for i,nid in enumerate(ids)}
    return ids, id2idx

def compute_node_features(case):
    ids, id2idx = build_maps(case["nodes"])
    N = len(ids)

    deg = np.zeros(N); in_deg = np.zeros(N); out_deg = np.zeros(N)
    sum_in = np.zeros(N); sum_out = np.zeros(N)
    cnt_in = np.zeros(N); cnt_out = np.zeros(N)
    max_in = np.zeros(N); max_out = np.zeros(N)
    ts_in = [[] for _ in range(N)]; ts_out = [[] for _ in range(N)]
    neighbors = [[] for _ in range(N)]

    for e in case["edges"]:
        s = id2idx.get(int(e["source"])); t = id2idx.get(int(e["target"]))
        if s is None or t is None: 
            continue
        amt = float(e.get("amount",0)); ts = int(e.get("ts",0))
        deg[s]+=1; deg[t]+=1; out_deg[s]+=1; in_deg[t]+=1
        sum_out[s]+=amt; cnt_out[s]+=1; max_out[s]=max(max_out[s], amt)
        sum_in[t]+=amt;  cnt_in[t]+=1;  max_in[t]=max(max_in[t], amt)
        ts_out[s].append(ts); ts_in[t].append(ts)
        neighbors[s].append(t); neighbors[t].append(s)

    mean_in  = np.divide(sum_in,  cnt_in,  out=np.zeros_like(sum_in),  where=cnt_in>0)
    mean_out = np.divide(sum_out, cnt_out, out=np.zeros_like(sum_out), where=cnt_out>0)

    def inter_std(lst):
        if len(lst) < 3: return 0.0
        lst = sorted(lst)
        diffs = np.diff(lst)
        return float(np.std(diffs))

    in_burst  = np.array([inter_std(ts_in[i])  for i in range(N)])
    out_burst = np.array([inter_std(ts_out[i]) for i in range(N)])

    labels = case.get("labels", {})
    id2label = {int(k): int(v) for k,v in labels.items()}
    nn_lab_cnt = np.zeros(N); nn_lab_ratio = np.zeros(N)
    for i, nbrs in enumerate(neighbors):
        if not nbrs:
            nn_lab_cnt[i]=0; nn_lab_ratio[i]=0
        else:
            lc = sum(id2label.get(ids[j], 0) for j in nbrs)
            nn_lab_cnt[i] = lc
            nn_lab_ratio[i] = lc / len(nbrs)

    X = np.vstack([
        deg, in_deg, out_deg,
        mean_in, mean_out,
        max_in, max_out,
        in_burst, out_burst,
        nn_lab_cnt, nn_lab_ratio
    ]).T

    X = (X - X.mean(0, keepdims=True)) / (X.std(0, keepdims=True) + 1e-6)
    return torch.tensor(X, dtype=torch.float)

def build_edge_index(case):
    ids, id2idx = build_maps(case["nodes"])
    src = []; dst = []
    for e in case["edges"]:
        s = id2idx.get(int(e["source"])); t = id2idx.get(int(e["target"]))
        if s is None or t is None: 
            continue
        src.append(s); dst.append(t)
    # undirected for stability
    src_t = torch.tensor(src + dst, dtype=torch.long)
    dst_t = torch.tensor(dst + src, dtype=torch.long)
    return torch.stack([src_t, dst_t], dim=0)

def build_labels(case):
    ids, id2idx = build_maps(case["nodes"])
    y = torch.zeros(len(ids), dtype=torch.long)
    for nid_str, is_f in case.get("labels", {}).items():
        nid = int(nid_str)
        if nid in id2idx:
            y[id2idx[nid]] = 1 if is_f else 0
    return y

def case_to_pyg(case):
    x = compute_node_features(case)
    edge_index = build_edge_index(case)
    y = build_labels(case)
    return Data(x=x, edge_index=edge_index, y=y)

def convert_split(split="train"):
    in_dir = DATA / "graphs" / split
    paths = list(in_dir.glob("*.json"))
    saved = 0
    for p in paths:
        case = load_case(p)
        data = case_to_pyg(case)
        torch.save(data, in_dir / (p.stem + ".pt"))
        saved += 1
    print(f"Saved {saved} {split} graphs to .pt")

if __name__ == "__main__":
    convert_split("train")
    convert_split("test")