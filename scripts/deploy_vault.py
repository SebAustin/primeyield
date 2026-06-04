"""Deploy mock ERC-20s + PrimeYieldVault + DecisionLog to the active network.

Reads compiled Foundry artifacts from contracts/out (run `forge build` first),
deploys via web3.py 7.x, funds the vault, and writes addresses to
state/deployments.json.

Usage:
  forge build --evm-version paris
  uv run python scripts/deploy_vault.py
  # Override signer/RPC via env (PRIVATE_KEY, MANTLE_ACTIVE_RPC). To dry-run
  # locally:  anvil  (in another shell), then point MANTLE_ACTIVE_RPC at it.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent.config import get_account, get_settings, get_w3, mantlescan_address

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "contracts" / "out"
DEPLOYMENTS_OUT = ROOT / "state" / "deployments.json"

# Day-1 funding amounts (mock units, all 18 decimals).
FUND_METH = 1 * 10**18
FUND_USDY = 1_000 * 10**18
FUND_USDE = 1_000 * 10**18


def load_artifact(sol_file: str, name: str) -> tuple[list, str]:
    """Return (abi, bytecode) for a compiled Foundry artifact."""
    path = OUT / sol_file / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"Artifact missing: {path}. Run `forge build --evm-version paris` first.")
    data = json.loads(path.read_text())
    return data["abi"], data["bytecode"]["object"]


def _send(w3, acct, tx) -> dict:
    """Sign and broadcast an already-built transaction, returning the receipt."""
    signed = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return w3.eth.wait_for_transaction_receipt(tx_hash)


def _tx_opts(w3, acct) -> dict:
    """Common legacy-gas tx options (Mantle uses legacy gas pricing)."""
    return {
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address),
        "gasPrice": w3.eth.gas_price,
    }


def deploy(w3, acct, sol_file: str, name: str, *args) -> tuple[str, list]:
    abi, bytecode = load_artifact(sol_file, name)
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx = contract.constructor(*args).build_transaction(_tx_opts(w3, acct))
    receipt = _send(w3, acct, tx)
    addr = w3.to_checksum_address(receipt["contractAddress"])
    print(f"  deployed {name} -> {addr}")
    return addr, abi


def main() -> None:
    settings = get_settings()
    w3 = get_w3()
    acct = get_account(w3)
    deployer = acct.address

    # On testnet the deployer doubles as the agent; guardian from env or deployer.
    agent_addr = deployer
    guardian_addr = (
        w3.to_checksum_address(settings.guardian_address)
        if settings.guardian_address and settings.guardian_address.startswith("0x")
        and not settings.guardian_address.startswith("0xYOUR")
        else deployer
    )

    print(f"deploying from {deployer} on chainId {w3.eth.chain_id}")

    meth, meth_abi = deploy(w3, acct, "MockERC20.sol", "MockERC20", "Mock mETH", "mETH", 18)
    usdy, _ = deploy(w3, acct, "MockERC20.sol", "MockERC20", "Mock USDY", "USDY", 18)
    usde, _ = deploy(w3, acct, "MockERC20.sol", "MockERC20", "Mock USDe", "USDe", 18)

    vault, _ = deploy(
        w3, acct, "PrimeYieldVault.sol", "PrimeYieldVault",
        meth, usdy, usde, agent_addr, guardian_addr, deployer,
    )
    decision_log, _ = deploy(w3, acct, "DecisionLog.sol", "DecisionLog", agent_addr)

    # Fund the vault by minting mock tokens to it.
    print("funding vault...")
    for token_addr, amount in ((meth, FUND_METH), (usdy, FUND_USDY), (usde, FUND_USDE)):
        token = w3.eth.contract(address=token_addr, abi=meth_abi)
        tx = token.functions.mint(vault, amount).build_transaction(_tx_opts(w3, acct))
        _send(w3, acct, tx)
    print(f"  funded vault {vault} with mETH/USDY/USDe mocks")

    deployments = {
        "chainId": w3.eth.chain_id,
        "deployer": deployer,
        "agent": agent_addr,
        "guardian": guardian_addr,
        "tokens": {"mETH": meth, "USDY": usdy, "USDe": usde},
        "vault": vault,
        "decisionLog": decision_log,
    }
    DEPLOYMENTS_OUT.write_text(json.dumps(deployments, indent=2))
    print(f"wrote {DEPLOYMENTS_OUT.relative_to(ROOT)}")
    print(f"vault: {mantlescan_address(vault)}")


if __name__ == "__main__":
    main()
