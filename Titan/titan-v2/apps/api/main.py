from fastapi import FastAPI, UploadFile, File, Form
from pydantic import BaseModel
import os, httpx, json
from web3 import Web3

KYC_SVC = os.getenv("KYC_SVC", "http://ai-ocr:8001")  # use container name
AML_SVC = os.getenv("AML_SVC", "http://ai-aml:8002")
CHAIN_RPC = os.getenv("CHAIN_RPC", "http://hardhat:8545")
PRIV = os.getenv("ATTESTER_PRIV_KEY")
REGISTRY_FILE = os.getenv("REGISTRY_ADDRESS_FILE", "/blk/registry_address.txt")

w3 = Web3(Web3.HTTPProvider(CHAIN_RPC))
with open(REGISTRY_FILE) as f:
    REGISTRY_ADDR = f.read().strip()

ABI = json.loads(open("/app/abi.json").read())
contract = w3.eth.contract(address=Web3.to_checksum_address(REGISTRY_ADDR), abi=ABI)
acct = w3.eth.account.from_key(PRIV)

app = FastAPI()

class KYCResp(BaseModel):
    ipfsCid: str
    docHash: str
    onchainTx: str

@app.post("/kyc/verify", response_model=KYCResp)
async def kyc_verify(file: UploadFile = File(...), subject_wallet: str = Form(...), verifier_id: str = Form("VERIFIER-1")):
    async with httpx.AsyncClient() as client:
        files = {"file": (file.filename, await file.read(), "application/pdf")}
        data = {"subject_wallet": subject_wallet, "verifier_id": verifier_id}
        r = await client.post(f"{KYC_SVC}/kyc/verify", files=files, data=data)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(data.get("reason", "KYC failed"))

    # On-chain attestation
    doc_hash_bytes32 = Web3.to_bytes(hexstr=data["docHash"])
    nonce = w3.eth.get_transaction_count(acct.address)
    tx = contract.functions.attest(doc_hash_bytes32, Web3.to_checksum_address(subject_wallet), verifier_id).build_transaction(
        {"from": acct.address, "nonce": nonce, "gas": 500000}
    )
    signed = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    return KYCResp(ipfsCid=data["ipfsCid"], docHash=data["docHash"], onchainTx=receipt.transactionHash.hex())
