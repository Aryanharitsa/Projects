from fastapi import FastAPI, UploadFile, File, Form
from pydantic import BaseModel
import hashlib, httpx, os

IPFS_API = os.getenv("IPFS_API", "http://localhost:5001")
app = FastAPI(title="TITAN AI-OCR (PAN stub)")

class KYCResp(BaseModel):
    ipfsCid: str
    docHash: str
    ok: bool
    reason: str | None = None

@app.post("/kyc/verify", response_model=KYCResp)
async def verify_pan(file: UploadFile = File(...), subject_wallet: str = Form(...), verifier_id: str = Form("VERIFIER-1")):
    content = await file.read()
    if not file.filename.lower().endswith(".pdf"):
        return KYCResp(ipfsCid="", docHash="", ok=False, reason="Only PDF supported in MVP.")

    # Hash document
    doc_hash = hashlib.sha256(content).hexdigest()

    # Add to IPFS (Kubo)
    async with httpx.AsyncClient() as client:
        files = {"file": (file.filename, content, "application/pdf")}
        r = await client.post(f"{IPFS_API}/api/v0/add", files=files)
        r.raise_for_status()
        cid = r.json()["Hash"]

    return KYCResp(ipfsCid=cid, docHash="0x"+doc_hash, ok=True, reason=None)
