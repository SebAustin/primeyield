"""Register the PrimeYield agent's ERC-8004 identity on Mantle Sepolia.

Flow:
  1. Pin demo/agent-card.json to IPFS via Pinata REST (POST /pinning/pinFileToIPFS).
  2. Call register(agentURI) on the IdentityRegistry (web3.py 7.x).
  3. Parse the Registered event for the agentId.
  4. Write {agentId, tokenURI, registry, txHash} to state/identity.json.
  5. Print agentId + mantlescan URL.

Usage:
  uv run python scripts/register_agent.py            # full live registration
  uv run python scripts/register_agent.py --encode-only
        # build + print the register() calldata without sending (no funds needed)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests

from agent.config import (
    IDENTITY_REGISTRY_ABI,
    MANTLE_SEPOLIA_CHAIN_ID,
    MANTLE_SEPOLIA_IDENTITY_REGISTRY,
    get_account,
    get_settings,
    get_w3,
    mantlescan_tx,
)

ROOT = Path(__file__).resolve().parents[1]
AGENT_CARD = ROOT / "demo" / "agent-card.json"
IDENTITY_OUT = ROOT / "state" / "identity.json"
PINATA_PIN_URL = "https://api.pinata.cloud/pinning/pinFileToIPFS"


def load_agent_card(owner_address: str) -> dict:
    card = json.loads(AGENT_CARD.read_text())
    # Substitute the owner placeholder with the real EOA.
    if card.get("owner") in (None, "$OWNER_ADDRESS"):
        card["owner"] = owner_address
    return card


def pin_to_ipfs(card: dict) -> str:
    """Pin the agent card to IPFS via Pinata; return an ipfs:// URI."""
    jwt = get_settings().pinata_jwt
    if not jwt or jwt.startswith("YOUR_"):
        raise RuntimeError("PINATA_JWT is not set in the environment.")
    files = {"file": ("agent-card.json", json.dumps(card).encode(), "application/json")}
    resp = requests.post(
        PINATA_PIN_URL,
        headers={"Authorization": f"Bearer {jwt}"},
        files=files,
        timeout=60,
    )
    resp.raise_for_status()
    cid = resp.json()["IpfsHash"]
    return f"ipfs://{cid}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Register PrimeYield ERC-8004 identity")
    parser.add_argument(
        "--encode-only",
        action="store_true",
        help="Build + print register() calldata without pinning or sending.",
    )
    args = parser.parse_args()

    w3 = get_w3()
    acct = get_account(w3)
    registry = w3.eth.contract(
        address=w3.to_checksum_address(MANTLE_SEPOLIA_IDENTITY_REGISTRY),
        abi=IDENTITY_REGISTRY_ABI,
    )

    if args.encode_only:
        # Use a deterministic placeholder URI so the calldata is reproducible.
        calldata = registry.encode_abi("register", args=["ipfs://<agent-card-cid>"])
        print(f"register() calldata: {calldata}")
        print(f"to: {MANTLE_SEPOLIA_IDENTITY_REGISTRY}")
        print(f"from: {acct.address}")
        return

    card = load_agent_card(acct.address)
    token_uri = pin_to_ipfs(card)
    print(f"pinned agent card: {token_uri}")

    fn = registry.functions.register(token_uri)
    tx = fn.build_transaction(
        {
            "from": acct.address,
            "nonce": w3.eth.get_transaction_count(acct.address),
            "chainId": MANTLE_SEPOLIA_CHAIN_ID,
            "gas": int(fn.estimate_gas({"from": acct.address}) * 1.3),
            "gasPrice": w3.eth.gas_price,
        }
    )
    signed = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"register tx sent: {tx_hash.hex()}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    events = registry.events.Registered().process_receipt(receipt)
    if not events:
        raise SystemExit("No Registered event in receipt — registration may have failed.")
    agent_id = events[0]["args"]["agentId"]

    IDENTITY_OUT.write_text(
        json.dumps(
            {
                "agentId": int(agent_id),
                "tokenURI": token_uri,
                "registry": MANTLE_SEPOLIA_IDENTITY_REGISTRY,
                "txHash": tx_hash.hex(),
            },
            indent=2,
        )
    )

    print(f"✅ agentId = {agent_id}")
    print(f"   tx: {mantlescan_tx(tx_hash.hex())}")
    print(f"   wrote {IDENTITY_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
