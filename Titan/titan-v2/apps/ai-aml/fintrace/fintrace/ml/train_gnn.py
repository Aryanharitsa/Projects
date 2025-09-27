# ml/train_gnn.py
from pathlib import Path
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GATv2Conv
from torch_geometric.loader import DataLoader

# allowlist PyG classes for PyTorch 2.6 safe load
from torch.serialization import add_safe_globals
from torch_geometric.data import Data
from torch_geometric.data.data import DataEdgeAttr
add_safe_globals([Data, DataEdgeAttr])

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "graphs"

def load_split(split: str):
    files = list((DATA / split).glob("*.pt"))
    if not files:
        raise FileNotFoundError(f"No .pt graphs found in {DATA / split}. Run featurizer.")
    graphs = [torch.load(f, weights_only=False) for f in files]
    return graphs

class FocalLoss(nn.Module):
    def __init__(self, alpha=(1.0, 8.0), gamma=2.0):
        super().__init__()
        self.alpha = torch.tensor(alpha)
        self.gamma = gamma
    def forward(self, logits, y):
        ce = F.cross_entropy(logits, y, reduction="none")
        pt = torch.softmax(logits, dim=-1)[torch.arange(len(y), device=logits.device), y]
        alpha = self.alpha.to(logits.device)[y]
        loss = alpha * ((1-pt) ** self.gamma) * ce
        return loss.mean()

class GATv2(nn.Module):
    def __init__(self, in_dim, hid=64, heads=4, out_dim=2, p=0.2):
        super().__init__()
        self.g1 = GATv2Conv(in_dim, hid, heads=heads, dropout=p, concat=True)
        self.g2 = GATv2Conv(hid*heads, hid, heads=1, dropout=p, concat=True)
        self.lin = nn.Linear(hid, out_dim)
        self.p = p
    def forward(self, x, edge_index):
        h = F.elu(self.g1(x, edge_index))
        h = F.dropout(h, p=self.p, training=self.training)
        h = F.elu(self.g2(h, edge_index))
        h = F.dropout(h, p=self.p, training=self.training)
        return self.lin(h)

def show_stats(name, gs):
    pos = sum(int((g.y==1).sum()) for g in gs)
    tot = sum(int(g.num_nodes) for g in gs)
    print(f"{name}: pos {pos} / nodes {tot} (ratio {pos/max(1,tot):.4f})")

def train_epoch(model, loader, device, criterion, opt):
    model.train()
    total_loss, total_nodes = 0.0, 0
    for g in loader:
        g = g.to(device)
        opt.zero_grad()
        logits = model(g.x, g.edge_index)
        loss = criterion(logits, g.y)
        loss.backward(); opt.step()
        total_loss += loss.item() * g.num_nodes
        total_nodes += int(g.num_nodes)
    return total_loss / max(1,total_nodes)

@torch.no_grad()
def eval_epoch(model, loader, device, thr=0.35):
    model.eval()
    tp=fp=tn=fn=0
    for g in loader:
        g = g.to(device)
        probs = F.softmax(model(g.x, g.edge_index), dim=-1)[:,1]
        pred = (probs > thr).long()
        y = g.y
        tp += int(((pred==1)&(y==1)).sum())
        fp += int(((pred==1)&(y==0)).sum())
        tn += int(((pred==0)&(y==0)).sum())
        fn += int(((pred==0)&(y==1)).sum())
    prec = tp/(tp+fp+1e-9); rec = tp/(tp+fn+1e-9)
    f1 = 2*prec*rec/(prec+rec+1e-9)
    return {"precision":float(prec), "recall":float(rec), "f1":float(f1)}

if __name__ == "__main__":
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    train_graphs = load_split("train")
    test_graphs  = load_split("test")

    # oversample graphs that have positives
    pos_cases = [g for g in train_graphs if int((g.y==1).sum())>0]
    if pos_cases:
        train_graphs = train_graphs + pos_cases  # duplicate once

    show_stats("train", train_graphs)
    show_stats("test",  test_graphs)

    train_loader = DataLoader(train_graphs, batch_size=1, shuffle=True)
    test_loader  = DataLoader(test_graphs,  batch_size=1, shuffle=False)

    in_dim = train_graphs[0].x.size(1)
    model = GATv2(in_dim).to(device)
    criterion = FocalLoss(alpha=(1.0, 8.0), gamma=2.0)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)

    for epoch in range(1, 21):
        loss = train_epoch(model, train_loader, device, criterion, opt)
        if epoch % 5 == 0:
            m = eval_epoch(model, test_loader, device, thr=0.35)
            print(f"Epoch {epoch:02d} | loss {loss:.4f} | "
                  f"precision {m['precision']:.3f} | recall {m['recall']:.3f} | f1 {m['f1']:.3f}")
        else:
            print(f"Epoch {epoch:02d} | loss {loss:.4f}")

    out_path = DATA / "fintrace_gatv2.pt"
    torch.save(model.state_dict(), out_path)
    print(f"Saved model to {out_path}")