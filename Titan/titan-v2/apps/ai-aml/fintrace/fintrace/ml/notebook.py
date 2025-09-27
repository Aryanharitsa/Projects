# ml/notebook.py
from pathlib import Path
import torch
import json

DATA = Path(__file__).resolve().parents[1] / "data" / "graphs"

def ratio(split):
    files = list((DATA/split).glob("*.pt"))
    pos=neg=0
    case_counts = []
    for f in files:
        g = torch.load(f, weights_only=False)
        pos_case = int((g.y==1).sum())
        neg_case = int((g.y==0).sum())
        pos += pos_case; neg += neg_case
        case_counts.append((f.stem, pos_case, neg_case, g.num_nodes))
    ratio = pos/max(1,(pos+neg))
    print(f"{split.upper()} total -> pos:{pos} neg:{neg} ratio:{ratio:.4f}")
    # show a few sample cases
    for name,p,n,nodes in case_counts[:5]:
        print(f"  {name}: pos={p}, neg={n}, nodes={nodes}")
    if len(case_counts) > 5:
        print(f"  ... {len(case_counts)-5} more cases")

def inspect_json(split="train", k=2):
    """Optional: peek into raw JSON labels to debug"""
    jdir = DATA.parent / "graphs" / split
    jfiles = list(jdir.glob("*.json"))
    for jf in jfiles[:k]:
        with open(jf) as f:
            case = json.load(f)
        pos = sum(1 for _,lab in case["labels"].items() if lab)
        print(f"[JSON] {jf.stem}: {pos} positives out of {len(case['nodes'])} nodes")

if __name__ == "__main__":
    ratio("train")
    ratio("test")
    # optional deeper inspection:
    # inspect_json("train")