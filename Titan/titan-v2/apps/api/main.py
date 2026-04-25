"""TITAN API gateway.

Speaks to:
- ai-ocr (KYC document → IPFS pin + sha256 hash)
- AttestationRegistry (records the doc hash on-chain)
- ai-aml (delegates AML scoring; exposed here so the frontend has one base URL)

Adds two things this layer didn't have before:
- /attest/{docHash}      verifier-grade lookup of an on-chain attestation
- /attestations/recent   indexed Attested events for the explorer UI
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from web3 import Web3

# ----- config

KYC_SVC = os.getenv("KYC_SVC", "http://ai-ocr:8001")
AML_SVC = os.getenv("AML_SVC", "http://ai-aml:8002")
CHAIN_RPC = os.getenv("CHAIN_RPC", "http://hardhat:8545")
PRIV = os.getenv("ATTESTER_PRIV_KEY")
REGISTRY_FILE = os.getenv("REGISTRY_ADDRESS_FILE", "/blk/registry_address.txt")
EXPLORER_LOOKBACK_BLOCKS = int(os.getenv("EXPLORER_LOOKBACK_BLOCKS", "5000"))

with open(REGISTRY_FILE) as f:
    REGISTRY_ADDR = f.read().strip()

ABI = json.loads(open("/app/abi.json").read())

w3 = Web3(Web3.HTTPProvider(CHAIN_RPC))
contract = w3.eth.contract(address=Web3.to_checksum_address(REGISTRY_ADDR), abi=ABI)
acct = w3.eth.account.from_key(PRIV) if PRIV else None

app = FastAPI(
    title="TITAN API",
    description="KYC ingest + on-chain attestation + AML delegation.",
    version="2.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----- models


class KYCResp(BaseModel):
    ipfsCid: str
    docHash: str
    onchainTx: str
    blockNumber: int
    subject: str
    verifierId: str


class Attestation(BaseModel):
    docHash: str
    subject: str
    verifierId: str
    timestamp: int
    timestampIso: str
    found: bool
    blockNumber: Optional[int] = None
    txHash: Optional[str] = None


class RecentAttestation(BaseModel):
    docHash: str
    subject: str
    verifierId: str
    timestamp: int
    timestampIso: str
    blockNumber: int
    txHash: str


# ----- helpers


_HEX32 = re.compile(r"^0x[0-9a-fA-F]{64}$")


def _ensure_hash(h: str) -> bytes:
    if not _HEX32.match(h):
        raise HTTPException(status_code=400, detail="docHash must be 0x-prefixed 32 bytes (64 hex chars)")
    return Web3.to_bytes(hexstr=h)


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ----- routes


@app.get("/healthz")
def healthz() -> Dict[str, Any]:
    chain_ok = False
    block = None
    try:
        block = w3.eth.block_number
        chain_ok = True
    except Exception:
        pass
    return {
        "ok": True,
        "service": "titan-api",
        "version": "2.0.0",
        "chain": {"connected": chain_ok, "rpc": CHAIN_RPC, "block": block, "registry": REGISTRY_ADDR},
        "attester": getattr(acct, "address", None),
    }


@app.post("/kyc/verify", response_model=KYCResp)
async def kyc_verify(
    file: UploadFile = File(...),
    subject_wallet: str = Form(...),
    verifier_id: str = Form("VERIFIER-1"),
) -> KYCResp:
    if not acct:
        raise HTTPException(status_code=500, detail="ATTESTER_PRIV_KEY not configured")

    async with httpx.AsyncClient(timeout=60) as client:
        files = {"file": (file.filename, await file.read(), file.content_type or "application/pdf")}
        data = {"subject_wallet": subject_wallet, "verifier_id": verifier_id}
        r = await client.post(f"{KYC_SVC}/kyc/verify", files=files, data=data)
        r.raise_for_status()
        body = r.json()
        if not body.get("ok"):
            raise HTTPException(status_code=400, detail=body.get("reason", "KYC failed"))

    doc_hash_bytes32 = Web3.to_bytes(hexstr=body["docHash"])
    nonce = w3.eth.get_transaction_count(acct.address)
    tx = contract.functions.attest(
        doc_hash_bytes32,
        Web3.to_checksum_address(subject_wallet),
        verifier_id,
    ).build_transaction({"from": acct.address, "nonce": nonce, "gas": 500000})
    signed = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    return KYCResp(
        ipfsCid=body["ipfsCid"],
        docHash=body["docHash"],
        onchainTx=receipt.transactionHash.hex(),
        blockNumber=receipt.blockNumber,
        subject=subject_wallet,
        verifierId=verifier_id,
    )


@app.get("/attest/{doc_hash}", response_model=Attestation)
def get_attestation(doc_hash: str) -> Attestation:
    raw = _ensure_hash(doc_hash)
    a = contract.functions.attestations(raw).call()
    # tuple: (docHash, subject, verifierId, timestamp)
    found = int.from_bytes(a[0], "big") != 0
    block_number: Optional[int] = None
    tx_hash: Optional[str] = None
    if found:
        # Pull the originating tx via the Attested event filter (cheap on dev chain).
        try:
            head = w3.eth.block_number
            from_block = max(0, head - EXPLORER_LOOKBACK_BLOCKS)
            logs = contract.events.Attested.create_filter(
                fromBlock=from_block, argument_filters={"docHash": raw}
            ).get_all_entries()
            if logs:
                block_number = logs[-1].blockNumber
                tx_hash = logs[-1].transactionHash.hex()
        except Exception:
            pass

    return Attestation(
        docHash=("0x" + a[0].hex()) if isinstance(a[0], (bytes, bytearray)) else str(a[0]),
        subject=a[1],
        verifierId=a[2],
        timestamp=int(a[3]),
        timestampIso=_iso(int(a[3])) if int(a[3]) > 0 else "",
        found=found,
        blockNumber=block_number,
        txHash=tx_hash,
    )


@app.get("/attestations/recent", response_model=List[RecentAttestation])
def recent_attestations(limit: int = 25) -> List[RecentAttestation]:
    head = w3.eth.block_number
    from_block = max(0, head - EXPLORER_LOOKBACK_BLOCKS)
    logs = contract.events.Attested.create_filter(fromBlock=from_block).get_all_entries()
    out: List[RecentAttestation] = []
    for log in logs[-limit:][::-1]:
        ts = int(log.args["timestamp"])
        out.append(
            RecentAttestation(
                docHash="0x" + log.args["docHash"].hex(),
                subject=log.args["subject"],
                verifierId=log.args["verifierId"],
                timestamp=ts,
                timestampIso=_iso(ts) if ts > 0 else "",
                blockNumber=log.blockNumber,
                txHash=log.transactionHash.hex(),
            )
        )
    return out


# ----- AML pass-through so the frontend has one origin


@app.post("/aml/score")
async def aml_score(payload: Dict[str, Any]) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{AML_SVC}/aml/score", json=payload)
        r.raise_for_status()
        return r.json()


@app.post("/aml/sar")
async def aml_sar(payload: Dict[str, Any]) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{AML_SVC}/aml/sar", json=payload)
        r.raise_for_status()
        return r.json()


@app.get("/aml/rules")
async def aml_rules() -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{AML_SVC}/aml/rules")
        r.raise_for_status()
        return r.json()
