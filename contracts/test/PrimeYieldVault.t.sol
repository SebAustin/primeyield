// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {PrimeYieldVault} from "../src/PrimeYieldVault.sol";
import {DecisionLog} from "../src/DecisionLog.sol";
import {MockERC20} from "../src/mocks/MockERC20.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/// @notice Day-1 Foundry tests. Run with `forge test --evm-version paris`.
contract PrimeYieldVaultTest is Test {
    PrimeYieldVault internal vault;
    DecisionLog internal decisionLog;

    MockERC20 internal meth;
    MockERC20 internal usdy;
    MockERC20 internal usde;

    address internal owner = makeAddr("owner");
    address internal guardian = makeAddr("guardian");
    address internal agent = makeAddr("agent");
    address internal alice = makeAddr("alice");
    address internal safe = makeAddr("safe");

    uint256 internal constant AGENT_ID = 42;

    function setUp() public {
        meth = new MockERC20("Mock mETH", "mETH", 18);
        usdy = new MockERC20("Mock USDY", "USDY", 18);
        usde = new MockERC20("Mock USDe", "USDe", 18);

        vault = new PrimeYieldVault(
            address(meth), address(usdy), address(usde), agent, guardian, owner
        );
        decisionLog = new DecisionLog(agent);
    }

    // ---- deposit / withdraw round-trip ------------------------------------

    function test_deposit_and_withdraw_roundtrip() public {
        uint256 amount = 1_000e18;
        usde.mint(alice, amount);

        vm.startPrank(alice);
        usde.approve(address(vault), amount);
        uint256 shares = vault.deposit(amount, alice);
        assertEq(vault.balanceOf(alice), shares);
        assertEq(usde.balanceOf(address(vault)), amount);

        uint256 assetsBack = vault.redeem(shares, alice, alice);
        vm.stopPrank();

        assertEq(assetsBack, amount);
        assertEq(usde.balanceOf(alice), amount);
        assertEq(vault.balanceOf(alice), 0);
    }

    // ---- rebalance is agent-gated -----------------------------------------

    function test_rebalance_reverts_from_non_agent() public {
        vm.prank(alice);
        vm.expectRevert(PrimeYieldVault.NotAgent.selector);
        vault.rebalance(hex"deadbeef");
    }

    function test_rebalance_succeeds_from_agent() public {
        vm.prank(agent);
        vault.rebalance(hex"deadbeef"); // does not revert
    }

    // ---- emergency exit requires 2-of-2 -----------------------------------

    function test_emergencyExit_reverts_without_both_confirmations() public {
        usde.mint(address(vault), 500e18);

        // No confirmations.
        vm.prank(owner);
        vm.expectRevert(PrimeYieldVault.ExitNotApproved.selector);
        vault.emergencyExit(safe);

        // Only owner confirms.
        vm.prank(owner);
        vault.confirmEmergencyExit();
        vm.prank(owner);
        vm.expectRevert(PrimeYieldVault.ExitNotApproved.selector);
        vault.emergencyExit(safe);
    }

    function test_emergencyExit_succeeds_with_2of2() public {
        meth.mint(address(vault), 1e18);
        usdy.mint(address(vault), 1_000e18);
        usde.mint(address(vault), 1_000e18);

        vm.prank(owner);
        vault.confirmEmergencyExit();
        vm.prank(guardian);
        vault.confirmEmergencyExit();

        vm.prank(guardian);
        vault.emergencyExit(safe);

        assertEq(meth.balanceOf(safe), 1e18);
        assertEq(usdy.balanceOf(safe), 1_000e18);
        assertEq(usde.balanceOf(safe), 1_000e18);
        // Confirmations reset.
        assertFalse(vault.ownerConfirmedExit());
        assertFalse(vault.guardianConfirmedExit());
    }

    function test_confirmEmergencyExit_rejects_strangers() public {
        vm.prank(alice);
        vm.expectRevert(PrimeYieldVault.NotAuthorized.selector);
        vault.confirmEmergencyExit();
    }

    // ---- pausing ----------------------------------------------------------

    function test_deposit_reverts_when_paused() public {
        usde.mint(alice, 100e18);
        vm.prank(owner);
        vault.pause();

        vm.startPrank(alice);
        usde.approve(address(vault), 100e18);
        vm.expectRevert(); // Pausable: EnforcedPause
        vault.deposit(100e18, alice);
        vm.stopPrank();
    }

    // ---- DecisionLog ------------------------------------------------------

    function test_decisionLog_records_and_emits() public {
        bytes32 h = keccak256("rationale-json");

        vm.expectEmit(true, false, false, true);
        emit DecisionLog.DecisionRecorded(AGENT_ID, h, block.timestamp);

        vm.prank(agent);
        decisionLog.record(AGENT_ID, h);

        assertEq(decisionLog.decisionCount(AGENT_ID), 1);
        bytes32[] memory hashes = decisionLog.getDecisions(AGENT_ID);
        assertEq(hashes.length, 1);
        assertEq(hashes[0], h);
    }

    function test_decisionLog_reverts_from_non_agent() public {
        vm.prank(alice);
        vm.expectRevert(DecisionLog.NotAgent.selector);
        decisionLog.record(AGENT_ID, keccak256("x"));
    }
}
