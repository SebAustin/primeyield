// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// @title DecisionLog
/// @notice Append-only on-chain provenance of an agent's decision rationales.
/// @dev    Stores `keccak256(rationale_json)` per agentId. Only the registered
///         agent EOA may write. This is the transparency primitive judges and
///         insurers verify via scripts/judge_replay.py.
///
///         Compile with `--evm-version paris` (Mantle: no PUSH0).
contract DecisionLog {
    /// @notice The agent EOA permitted to record decisions.
    address public immutable agent;

    /// @notice agentId => ordered list of recorded rationale hashes.
    mapping(uint256 => bytes32[]) private _agentDecisions;

    /// @notice Emitted whenever a rationale hash is committed on-chain.
    /// @param agentId   The ERC-8004 agentId the decision belongs to.
    /// @param hash      keccak256 of the canonical rationale JSON.
    /// @param timestamp Block timestamp the decision was recorded.
    event DecisionRecorded(uint256 indexed agentId, bytes32 hash, uint256 timestamp);

    error NotAgent();

    modifier onlyAgent() {
        if (msg.sender != agent) revert NotAgent();
        _;
    }

    /// @param agent_ The EOA (the ERC-8004 agent wallet) allowed to write.
    constructor(address agent_) {
        require(agent_ != address(0), "agent=0");
        agent = agent_;
    }

    /// @notice Record the hash of a decision's rationale for `agentId`.
    /// @param agentId       The ERC-8004 agentId.
    /// @param rationaleHash keccak256 of the canonical rationale JSON.
    function record(uint256 agentId, bytes32 rationaleHash) external onlyAgent {
        _agentDecisions[agentId].push(rationaleHash);
        emit DecisionRecorded(agentId, rationaleHash, block.timestamp);
    }

    /// @notice Return every recorded rationale hash for `agentId`.
    function getDecisions(uint256 agentId) external view returns (bytes32[] memory) {
        return _agentDecisions[agentId];
    }

    /// @notice Number of decisions recorded for `agentId`.
    function decisionCount(uint256 agentId) external view returns (uint256) {
        return _agentDecisions[agentId].length;
    }
}
