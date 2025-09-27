# ml/eval_consensus.py
from pathlib import Path
import torch, torch.nn.functional as F
from train_gnn import GATv2, load_split
from score_case import build_adj, consensus_mask   # reuse your scorer code

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "graphs"
MODEL_PATH = DATA / "fintrace_gatv2.pt"

def eval_split(split="test", tau=0.56, neighbor_tau=0.45, min_neighbors=2):
    graphs = load_split(split)
    in_dim = graphs[0].x.size(1)
    model = GATv2(in_dim)
    model.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
    model.eval()

    tp0=fp0=fn0=tn0=0  # plain threshold
    tp1=fp1=fn1=tn1=0  # threshold + consensus

    for g in graphs:
        with torch.no_grad():
            probs = F.softmax(model(g.x, g.edge_index), dim=-1)[:,1].cpu()
        y = g.y.cpu()

        # --- plain threshold ---
        pred0 = (probs > tau).long()
        tp0 += int(((pred0==1)&(y==1)).sum())
        fp0 += int(((pred0==1)&(y==0)).sum())
        tn0 += int(((pred0==0)&(y==0)).sum())
        fn0 += int(((pred0==0)&(y==1)).sum())

        # --- consensus filter ---
        # Rebuild adj from g (simplify: use edge_index)
        N = g.num_nodes
        adj = [[] for _ in range(N)]
        ei = g.edge_index.t().tolist()
        for s,t in ei:
            adj[s].append(t); adj[t].append(s)
        keep = consensus_mask(adj, probs.tolist(), tau=tau, neighbor_tau=neighbor_tau, min_neighbors=min_neighbors)
        pred1 = torch.tensor([1 if k else 0 for k in keep])

        tp1 += int(((pred1==1)&(y==1)).sum())
        fp1 += int(((pred1==1)&(y==0)).sum())
        tn1 += int(((pred1==0)&(y==0)).sum())
        fn1 += int(((pred1==0)&(y==1)).sum())

    def metrics(tp,fp,tn,fn):
        prec = tp/(tp+fp+1e-9)
        rec = tp/(tp+fn+1e-9)
        f1 = 2*prec*rec/(prec+rec+1e-9)
        return prec, rec, f1

    print(f"== {split.upper()} ==")
    p0,r0,f0 = metrics(tp0,fp0,tn0,fn0)
    p1,r1,f1 = metrics(tp1,fp1,tn1,fn1)
    print(f" Plain τ={tau}: precision={p0:.3f}, recall={r0:.3f}, f1={f0:.3f}")
    print(f" +Consensus : precision={p1:.3f}, recall={r1:.3f}, f1={f1:.3f}")
    print(f" Reduction: FP {fp0} → {fp1} (-{fp0-fp1}) | TP {tp0} → {tp1} | FN {fn0} → {fn1}")

if __name__ == "__main__":
    eval_split("test", tau=0.56, neighbor_tau=0.45, min_neighbors=2)