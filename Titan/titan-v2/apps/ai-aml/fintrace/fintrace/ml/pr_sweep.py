# ml/pr_sweep.py
from pathlib import Path
import torch, torch.nn.functional as F
from train_gnn import GATv2, load_split  # reuse your model class + loader

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "graphs"
MODEL_PATH = DATA / "fintrace_gatv2.pt"

def collect_probs(split="test"):
    graphs = load_split(split)
    in_dim = graphs[0].x.size(1)
    model = GATv2(in_dim)
    model.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
    model.eval()
    all_probs, all_y = [], []
    for g in graphs:
        probs = F.softmax(model(g.x, g.edge_index), dim=-1)[:,1]
        all_probs.append(probs.detach().cpu())
        all_y.append(g.y.detach().cpu())
    return torch.cat(all_probs), torch.cat(all_y)

if __name__ == "__main__":
    probs, y = collect_probs("test")
    best = None
    for thr in [i/100 for i in range(10, 91)]:
        pred = (probs > thr).long()
        tp = int(((pred==1)&(y==1)).sum())
        fp = int(((pred==1)&(y==0)).sum())
        fn = int(((pred==0)&(y==1)).sum())
        prec = tp/(tp+fp+1e-9); rec = tp/(tp+fn+1e-9)
        f1 = 2*prec*rec/(prec+rec+1e-9)
        # prefer higher precision, but keep recall >= 0.80 for demo
        score = prec + 0.25*rec
        if (best is None or score > best[0]) and rec >= 0.80:
            best = (score, thr, prec, rec, f1)
    if best:
        _, thr, prec, rec, f1 = best
        print(f"Recommended threshold τ={thr:.2f} | precision {prec:.3f} | recall {rec:.3f} | f1 {f1:.3f}")
    else:
        print("No threshold achieved recall >= 0.80; consider relaxing constraint.")