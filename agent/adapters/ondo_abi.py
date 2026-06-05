"""Minimal ABIs for USDY on Mantle.

The USDY token on Mantle (0x5bE26527e817998A7206475496fDE1E68957c5A6) is a
transfer-restricted ERC-20 with an on-chain blocklist. These ABIs are
sourced from the verified contract on mantlescan.xyz.
"""

from __future__ import annotations

# Minimal USDY token ABI — just the functions the adapter uses.
USDY_ABI = [
    {
        "type": "function",
        "name": "blocklist",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
    {
        "type": "function",
        "name": "balanceOf",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "transfer",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "type": "function",
        "name": "approve",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
]

# Minimal blocklist ABI — exposes isBlocked(address).
USDY_BLOCKLIST_ABI = [
    {
        "type": "function",
        "name": "isBlocked",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "type": "function",
        "name": "addToBlocklist",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [],
    },
]
