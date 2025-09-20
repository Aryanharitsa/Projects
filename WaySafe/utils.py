
import math, hashlib
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlmb/2)**2
    return 2*R*math.asin(math.sqrt(a))
def point_in_polygon(lat, lon, polygon):
    x, y = lon, lat; inside = False; n = len(polygon)
    for i in range(n):
        x1,y1 = polygon[i]; x2,y2 = polygon[(i+1)%n]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / ((y2 - y1) if (y2 - y1)!=0 else 1e-12) + x1):
            inside = not inside
    return inside
def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()
def build_merkle(leaves):
    if not leaves: return "", {}
    proofs = {h: [] for h in leaves}; level = leaves[:]
    while len(level) > 1:
        nxt=[]
        for i in range(0,len(level),2):
            a=level[i]; b=level[i+1] if i+1<len(level) else a
            parent = sha256_hex((a+b).encode()); nxt.append(parent)
            proofs[a].append(b); proofs[b].append(a if i+1<len(level) else b)
        level=nxt
    return level[0], proofs
