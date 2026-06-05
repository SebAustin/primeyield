"""Mantle LSP (mETH) adapter.

Source: https://docs.mantle.xyz/meth
mETH contract on Mantle mainnet: 0xcDA86A272531e8640cD7F1a92c01839911B90bb0

The Mantle LSP uses a rebasing-index model: `mETHToETH(1e18)` on the mETH
contract returns how many wei of ETH one mETH is worth. The staking APR is
available from the Mantle LSP subgraph or falls back to a static value.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from langsmith import traceable

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# mETH contract minimal ABI
# ---------------------------------------------------------------------------
METH_ABI = [
    {
        "type": "function",
        "name": "mETHToETH",
        "stateMutability": "view",
        "inputs": [{"name": "mETHAmount", "type": "uint256"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "ethToMETH",
        "stateMutability": "view",
        "inputs": [{"name": "ethAmount", "type": "uint256"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "totalControlled",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "stakingAllowlist",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
    {
        "type": "function",
        "name": "stake",
        "stateMutability": "payable",
        "inputs": [{"name": "minMETHAmount", "type": "uint256"}],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "unstakeRequests",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "mETHLocked", "type": "uint128"},
            {"name": "minETHAmount", "type": "uint128"},
        ],
        "outputs": [],
    },
]

# LSP subgraph — Mantle mainnet.
_LSP_SUBGRAPH = (
    "https://api.goldsky.com/api/public/project_clnbo3e3c16lj33xva5r2bnfa"
    "/subgraphs/mantle-lsp/1.0.0/gn"
)
_APR_FALLBACK = Decimal("0.038")  # 3.8% static fallback


@traceable(name="meth_to_eth_rate")
async def meth_to_eth_rate(w3) -> Decimal:  # noqa: ANN001
    """Return the current mETH → ETH exchange rate (how many wei per 1 mETH).

    Calls mETH.mETHToETH(1e18) view function on-chain.
    """
    from agent.config import METH_ADDRESS_MAINNET

    contract = w3.eth.contract(
        address=w3.to_checksum_address(METH_ADDRESS_MAINNET),
        abi=METH_ABI,
    )
    wei_per_meth = contract.functions.mETHToETH(10**18).call()
    rate = Decimal(str(wei_per_meth)) / Decimal(str(10**18))
    log.debug("mETH→ETH rate: %s", rate)
    return rate


@traceable(name="get_staking_apr")
async def get_staking_apr() -> Decimal:
    """Return the current mETH staking APR from the LSP subgraph.

    Falls back to 3.8% if the subgraph is unreachable.
    """
    import requests

    query = '{ protocolMetrics { apr } }'
    try:
        resp = requests.post(_LSP_SUBGRAPH, json={"query": query}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        raw = data["data"]["protocolMetrics"]["apr"]
        apr = Decimal(str(raw))
        log.debug("mETH staking APR from subgraph: %s", apr)
        return apr
    except Exception as exc:  # noqa: BLE001
        log.warning("LSP subgraph unavailable (%s); using fallback APR %s", exc, _APR_FALLBACK)
        return _APR_FALLBACK


@traceable(name="build_stake_tx")
async def build_stake_tx(amount_wei: int, recipient: str, w3) -> dict:  # noqa: ANN001
    """Build calldata for staking `amount_wei` ETH into mETH.

    The mETH `stake(minMETHAmount)` function is payable; `recipient` must be
    the transaction sender (LSP stakes to msg.sender only).

    Returns a dict suitable for w3.eth.send_transaction.
    """
    from agent.config import METH_ADDRESS_MAINNET

    # Accept 0.5% slippage on the mETH out.
    rate = await meth_to_eth_rate(w3)
    expected_meth = int(Decimal(str(amount_wei)) / rate)
    min_meth_out = int(expected_meth * Decimal("0.995"))

    contract = w3.eth.contract(
        address=w3.to_checksum_address(METH_ADDRESS_MAINNET),
        abi=METH_ABI,
    )
    return {
        "to": METH_ADDRESS_MAINNET,
        "value": amount_wei,
        "data": contract.encode_abi("stake", args=[min_meth_out]),
        "from": recipient,
    }


@traceable(name="build_unstake_request_tx")
async def build_unstake_request_tx(meth_amount_wei: int, w3) -> dict:  # noqa: ANN001
    """Build calldata for requesting an unstake of `meth_amount_wei` mETH.

    Returns a tx dict; the caller must approve the mETH spend first.
    """
    from agent.config import METH_ADDRESS_MAINNET

    rate = await meth_to_eth_rate(w3)
    expected_eth = int(Decimal(str(meth_amount_wei)) * rate)
    min_eth_out = int(expected_eth * Decimal("0.995"))

    contract = w3.eth.contract(
        address=w3.to_checksum_address(METH_ADDRESS_MAINNET),
        abi=METH_ABI,
    )
    return {
        "to": METH_ADDRESS_MAINNET,
        "value": 0,
        "data": contract.encode_abi(
            "unstakeRequests",
            args=[meth_amount_wei, min_eth_out],
        ),
    }
