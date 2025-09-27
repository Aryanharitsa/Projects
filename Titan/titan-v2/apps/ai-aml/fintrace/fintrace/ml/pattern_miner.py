# ml/pattern_miner.py
from pathlib import Path
import pandas as pd
from collections import deque, defaultdict

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

def _coerce_bool_series(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin(["1","true","t","yes","y"])

def load_frames():
    acc = pd.read_csv(DATA / "accounts.csv")
    tx  = pd.read_csv(DATA / "transactions.csv")
    al  = pd.read_csv(DATA / "alerts.csv")

    # normalize columns
    tx = tx.rename(columns={
        "SENDER_ACCOUNT_ID":"sender",
        "RECEIVER_ACCOUNT_ID":"receiver",
        "TX_ID":"tx_id",
        "TX_AMOUNT":"amount",
        "TIMESTAMP":"ts"
    })
    al = al.rename(columns={"TX_ID":"tx_id"})

    # types
    if "tx_id" in tx: tx["tx_id"] = tx["tx_id"].astype(int)
    if "tx_id" in al: al["tx_id"] = al["tx_id"].astype(int)
    if "ACCOUNT_ID" in acc: acc["ACCOUNT_ID"] = acc["ACCOUNT_ID"].astype(int)

    # coerce account fraud flag if present
    if "IS_FRAUD" in acc.columns:
        acc["IS_FRAUD"] = _coerce_bool_series(acc["IS_FRAUD"])
    else:
        acc["IS_FRAUD"] = False

    # alerts may or may not have IS_FRAUD; default True (they're alerts)
    if "IS_FRAUD" in al.columns:
        al["IS_FRAUD"] = _coerce_bool_series(al["IS_FRAUD"])
    else:
        al["IS_FRAUD"] = True

    return acc, tx, al

def index_neighbors(tx: pd.DataFrame):
    nbrs = defaultdict(set)
    for s, r in zip(tx["sender"], tx["receiver"]):
        nbrs[int(s)].add(int(r)); nbrs[int(r)].add(int(s))
    return nbrs

def bfs(nbrs, seeds, max_nodes=350, max_hops=2):
    seen, q = set(), deque()
    for s in seeds:
        if pd.notna(s):
            s = int(s)
            if s not in seen:
                q.append((s,0)); seen.add(s)
    while q and len(seen) < max_nodes:
        u, d = q.popleft()
        if d >= max_hops: continue
        for v in nbrs.get(u, []):
            if v not in seen:
                seen.add(v); q.append((v, d+1))
                if len(seen) >= max_nodes: break
    return seen

def slice_tx(tx, nodes):
    nodes = set(nodes)
    sub = tx[tx["sender"].isin(nodes) & tx["receiver"].isin(nodes)].copy()
    sub["sender"]  = sub["sender"].astype(int)
    sub["receiver"] = sub["receiver"].astype(int)
    return sub

def pick_alert_anchors(alerts: pd.DataFrame, k:int, kind:str=None):
    df = alerts.copy()
    if kind:
        df = df[df["ALERT_TYPE"] == kind]
    df = df.sample(frac=1, random_state=42)
    anchors, seen = [], set()
    for _, row in df.iterrows():
        s, r = int(row["SENDER_ACCOUNT_ID"]), int(row["RECEIVER_ACCOUNT_ID"])
        if (s,r) in seen: 
            continue
        anchors.append(row)
        seen.add((s,r))
        if len(anchors) >= k: break
    return anchors

def build_case(acc, tx, alerts, anchor_row, pattern_hint:str, max_nodes=350):
    s0 = int(anchor_row["SENDER_ACCOUNT_ID"])
    r0 = int(anchor_row["RECEIVER_ACCOUNT_ID"])
    seeds = [s0, r0]

    nbrs  = index_neighbors(tx)
    nodes = bfs(nbrs, seeds, max_nodes=max_nodes, max_hops=2)
    sub_tx = slice_tx(tx, nodes)
    sub_acc = acc[acc["ACCOUNT_ID"].isin(nodes)].copy()

    # positive set from accounts ground truth
    pos_from_accounts = set(sub_acc[sub_acc["IS_FRAUD"] == True]["ACCOUNT_ID"].astype(int).tolist())

    # positive set from alerted edges inside this subgraph
    alerts_subset = alerts.loc[alerts["IS_FRAUD"] == True, ["tx_id"]].drop_duplicates()
    tx_with_alert = sub_tx.merge(alerts_subset, on="tx_id", how="inner")
    pos_from_alerts = set(tx_with_alert["sender"].tolist()) | set(tx_with_alert["receiver"].tolist())

    fraud_accounts = (pos_from_accounts | pos_from_alerts) & set(nodes)

    # fallback: ensure at least one positive (anchor endpoints)
    if len(fraud_accounts) == 0:
        fraud_accounts.update([s0, r0])

    labels = {int(row.ACCOUNT_ID): (int(row.ACCOUNT_ID) in fraud_accounts)
              for _, row in sub_acc.iterrows()}

    edges = [{
        "source": int(row.sender),
        "target": int(row.receiver),
        "tx_id": int(row.tx_id),
        "amount": float(row.amount),
        "ts": int(row.ts)
    } for _, row in sub_tx.iterrows()]

    return {
        "pattern_type": pattern_hint,
        "anchor_alert_id": int(anchor_row["ALERT_ID"]),
        "nodes": [{"id": int(n)} for n in nodes],
        "edges": edges,
        "labels": labels
    }

def mine_cases(n_train=20, n_test=10, per_kind=6):
    acc, tx, al = load_frames()
    anchors = []
    for kind in ["fan_in","fan_out","cycle"]:
        anchors += pick_alert_anchors(al, k=per_kind, kind=kind)
    need = (n_train + n_test) - len(anchors)
    if need > 0:
        anchors += pick_alert_anchors(al, k=need, kind=None)
    cases = [build_case(acc, tx, al, a, str(a["ALERT_TYPE"])) for a in anchors[:(n_train+n_test)]]
    return cases[:n_train], cases[n_train:n_train+n_test]

if __name__ == "__main__":
    train, test = mine_cases()
    out_tr = DATA / "graphs" / "train"
    out_te = DATA / "graphs" / "test"
    out_tr.mkdir(parents=True, exist_ok=True)
    out_te.mkdir(parents=True, exist_ok=True)

    import json, uuid
    for c in train:
        (out_tr / f"{uuid.uuid4().hex}.json").write_text(json.dumps(c))
    for c in test:
        (out_te / f"{uuid.uuid4().hex}.json").write_text(json.dumps(c))
    print(f"Saved {len(train)} train and {len(test)} test cases.")