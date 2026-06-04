"""Central configuration: env loading + on-chain addresses.

Addresses marked `VERIFY` must be confirmed against live docs before use.
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


# ---------------------------------------------------------------------------
# ERC-8004 registries on Mantle Sepolia / Testnet (chainId 5003)
# ---------------------------------------------------------------------------
# Verified 2026-06-04 against the "Mantle Testnet" section of
#   https://github.com/erc-8004/erc-8004-contracts (README, master branch).
# These are deterministic-deploy addresses, identical across every ERC-8004
# testnet. Explorer: https://sepolia.mantlescan.xyz/address/<addr>
MANTLE_SEPOLIA_IDENTITY_REGISTRY = "0x8004A818BFB912233c491871b3d84c89A494BD9e"
MANTLE_SEPOLIA_REPUTATION_REGISTRY = "0x8004B663056A597Dffe9eCcC1965A193B7388713"

# Minimal ABI for the IdentityRegistry calls register_agent.py needs.
# register(string) returns (uint256 agentId); emits
# Registered(uint256 indexed agentId, string agentURI, address indexed owner).
IDENTITY_REGISTRY_ABI = [
    {
        "type": "function",
        "name": "register",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "agentURI", "type": "string"}],
        "outputs": [{"name": "agentId", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "setAgentURI",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "agentId", "type": "uint256"},
            {"name": "newURI", "type": "string"},
        ],
        "outputs": [],
    },
    {
        "type": "event",
        "name": "Registered",
        "anonymous": False,
        "inputs": [
            {"name": "agentId", "type": "uint256", "indexed": True},
            {"name": "agentURI", "type": "string", "indexed": False},
            {"name": "owner", "type": "address", "indexed": True},
        ],
    },
]

# ---------------------------------------------------------------------------
# Protocol addresses (mainnet unless noted) — used by adapters on day 2-3.
# ---------------------------------------------------------------------------
METH_ADDRESS_MAINNET = "0xcDA86A272531e8640cD7F1a92c01839911B90bb0"

AGNI_QUOTER_V2 = "0xc4aaDc921E1cdb66c5300Bc158a313292923C0cb"
AGNI_SWAP_ROUTER = "0x319B69888b0d11cEC22caA5034e25FfFBDc88421"

MERCHANT_MOE_LB_QUOTER = "0x501b8AFd35df20f531fF45F6f695793AC3316c85"
MERCHANT_MOE_LB_ROUTER = "0x013e138EF6008ae5FDFDE29700e3f2Bc61d21E3a"

# USDY RWADynamicOracle — VERIFY at docs.ondo.finance/mantle before use.
USDY_ORACLE_ADDRESS: str | None = None  # VERIFY


class Settings(BaseModel):
    """Runtime settings sourced from the environment."""

    mantle_sepolia_rpc: str = os.getenv("MANTLE_SEPOLIA_RPC", "")
    mantle_mainnet_rpc: str = os.getenv("MANTLE_MAINNET_RPC", "")
    mantle_active_rpc: str = os.getenv("MANTLE_ACTIVE_RPC", os.getenv("MANTLE_SEPOLIA_RPC", ""))
    private_key: str = os.getenv("PRIVATE_KEY", "")
    guardian_address: str = os.getenv("GUARDIAN_ADDRESS", "")
    pinata_jwt: str = os.getenv("PINATA_JWT", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    langsmith_project: str = os.getenv("LANGSMITH_PROJECT", "primeyield")
    database_url: str = os.getenv("DATABASE_URL", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ---------------------------------------------------------------------------
# web3 helpers
# ---------------------------------------------------------------------------
MANTLE_SEPOLIA_CHAIN_ID = 5003
MANTLESCAN_SEPOLIA = "https://sepolia.mantlescan.xyz"


def get_w3(rpc_url: str | None = None):
    """Return a connected Web3 client for the active network.

    Injects the POA/extra-data middleware so Mantle's block headers parse.
    """
    from web3 import Web3
    from web3.middleware import ExtraDataToPOAMiddleware

    url = rpc_url or get_settings().mantle_active_rpc
    if not url:
        raise RuntimeError("No RPC URL set (MANTLE_ACTIVE_RPC / MANTLE_SEPOLIA_RPC).")
    w3 = Web3(Web3.HTTPProvider(url))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def get_account(w3):
    """Return the agent EOA LocalAccount from PRIVATE_KEY."""
    pk = get_settings().private_key
    if not pk or pk.startswith("0xYOUR"):
        raise RuntimeError("PRIVATE_KEY is not set in the environment.")
    return w3.eth.account.from_key(pk)


def mantlescan_tx(tx_hash: str) -> str:
    return f"{MANTLESCAN_SEPOLIA}/tx/{tx_hash}"


def mantlescan_address(addr: str) -> str:
    return f"{MANTLESCAN_SEPOLIA}/address/{addr}"
