// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {ERC4626} from "@openzeppelin/contracts/token/ERC20/extensions/ERC4626.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";

/// @title PrimeYieldVault
/// @notice ERC-4626 vault for the PrimeYield RWA yield-rotation agent.
/// @dev    ERC-4626 is single-asset by spec, so USDe is the accounting asset
///         (`asset()`); mETH and USDY are tracked as rotation targets that the
///         agent rebalances into/out of. Controls:
///           - `rebalance(bytes)` is callable only by the agent EOA.
///           - `emergencyExit(address)` requires a 2-of-2 owner+guardian
///             confirmation (realized as on-chain confirmations).
///           - owner can `pause()`/`unpause()`; deposits halt while paused.
///
///         Compile with `--evm-version paris` (Mantle: no PUSH0).
contract PrimeYieldVault is ERC4626, Ownable, Pausable {
    using SafeERC20 for IERC20;

    /// @notice The agent EOA permitted to trigger rebalances.
    address public immutable agent;
    /// @notice The guardian half of the 2-of-2 emergency control.
    address public immutable guardian;

    /// @notice mETH rotation target (Mantle LSP).
    IERC20 public immutable meth;
    /// @notice USDY rotation target (Ondo Treasuries).
    IERC20 public immutable usdy;
    /// @notice USDe — the ERC-4626 accounting asset (also `asset()`).
    IERC20 public immutable usde;

    /// @notice 2-of-2 emergency-exit confirmations.
    bool public ownerConfirmedExit;
    bool public guardianConfirmedExit;

    event RebalanceExecuted(address indexed agent, bytes plan);
    event EmergencyExitConfirmed(address indexed signer);
    event EmergencyExit(address indexed to);

    error NotAgent();
    error NotGuardian();
    error NotAuthorized();
    error ExitNotApproved();

    modifier onlyAgent() {
        if (msg.sender != agent) revert NotAgent();
        _;
    }

    /// @param meth_     mETH token address.
    /// @param usdy_     USDY token address.
    /// @param usde_     USDe token address (becomes the ERC-4626 asset).
    /// @param agent_    Agent EOA allowed to rebalance.
    /// @param guardian_ Guardian for the 2-of-2 emergency exit.
    /// @param owner_    Vault owner (other half of the 2-of-2, plus pausing).
    constructor(
        address meth_,
        address usdy_,
        address usde_,
        address agent_,
        address guardian_,
        address owner_
    )
        ERC20("PrimeYield Vault Share", "pyUSDe")
        ERC4626(IERC20(usde_))
        Ownable(owner_)
    {
        require(
            meth_ != address(0) && usdy_ != address(0) && usde_ != address(0)
                && agent_ != address(0) && guardian_ != address(0) && owner_ != address(0),
            "zero address"
        );
        meth = IERC20(meth_);
        usdy = IERC20(usdy_);
        usde = IERC20(usde_);
        agent = agent_;
        guardian = guardian_;
    }

    // -----------------------------------------------------------------------
    // Rebalancing (agent-gated)
    // -----------------------------------------------------------------------

    /// @notice Execute a rebalance plan produced by the off-chain agent.
    /// @dev    Skeleton: validates the caller and emits the plan. Day 2-3 wires
    ///         the encoded swap routing (Agni / Merchant Moe) into this body.
    /// @param plan ABI-encoded swap instructions for this rebalance cycle.
    function rebalance(bytes calldata plan) external onlyAgent whenNotPaused {
        emit RebalanceExecuted(agent, plan);
    }

    // -----------------------------------------------------------------------
    // Emergency exit (2-of-2 owner + guardian)
    // -----------------------------------------------------------------------

    /// @notice Confirm an emergency exit. Must be called once by the owner and
    ///         once by the guardian before `emergencyExit` can run.
    function confirmEmergencyExit() external {
        if (msg.sender == owner()) {
            ownerConfirmedExit = true;
        } else if (msg.sender == guardian) {
            guardianConfirmedExit = true;
        } else {
            revert NotAuthorized();
        }
        emit EmergencyExitConfirmed(msg.sender);
    }

    /// @notice Sweep all vault assets to `to`. Requires the 2-of-2 confirmation.
    /// @dev    Callable by owner or guardian once both have confirmed. Resets
    ///         the confirmations afterward.
    function emergencyExit(address to) external whenNotPaused {
        if (msg.sender != owner() && msg.sender != guardian) revert NotAuthorized();
        if (!ownerConfirmedExit || !guardianConfirmedExit) revert ExitNotApproved();
        require(to != address(0), "to=0");

        ownerConfirmedExit = false;
        guardianConfirmedExit = false;

        _sweep(meth, to);
        _sweep(usdy, to);
        _sweep(usde, to);

        emit EmergencyExit(to);
    }

    function _sweep(IERC20 token, address to) private {
        uint256 bal = token.balanceOf(address(this));
        if (bal > 0) {
            token.safeTransfer(to, bal);
        }
    }

    // -----------------------------------------------------------------------
    // Pausing (owner)
    // -----------------------------------------------------------------------

    /// @notice Pause deposits and rebalances.
    function pause() external onlyOwner {
        _pause();
    }

    /// @notice Resume normal operation.
    function unpause() external onlyOwner {
        _unpause();
    }

    /// @dev Block deposits/mints while paused (withdrawals stay open by design).
    function _deposit(address caller, address receiver, uint256 assets, uint256 shares)
        internal
        override
        whenNotPaused
    {
        super._deposit(caller, receiver, assets, shares);
    }
}
