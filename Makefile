.PHONY: install test day1 day7 submit lint fmt

# Install Python deps (uv) + Solidity deps (forge).
install:
	uv sync --extra dev
	forge install foundry-rs/forge-std --no-commit || true
	forge install OpenZeppelin/openzeppelin-contracts --no-commit || true
	@echo "install complete"

# Run the full test suite: Solidity (Paris EVM) + Python.
test:
	forge test --evm-version paris
	uv run pytest

# Day 1: tests green, then register the agent's ERC-8004 identity.
day1: test
	uv run python scripts/register_agent.py

# Day 7: tests green, then deploy the vault + DecisionLog to Sepolia.
day7: test
	uv run python scripts/deploy_vault.py

# Submission: produce the judge-replay audit and print the checklist.
submit:
	uv run python scripts/judge_replay.py --agent-id $${AGENT_ID:-0}
	@echo ""
	@echo "================ SUBMISSION CHECKLIST ================"
	@echo "[ ] forge test --evm-version paris  -> green"
	@echo "[ ] uv run pytest                   -> green"
	@echo "[ ] register_agent.py               -> agentId confirmed"
	@echo "[ ] deploy_vault.py                 -> vault + DecisionLog on Sepolia"
	@echo "[ ] one full agent cycle            -> mantlescan URLs captured"
	@echo "[ ] judge_replay.py --agent-id <id> -> markdown audit confirmed"
	@echo "[ ] demo video (YouTube unlisted + Loom backup)"
	@echo "[ ] DoraHacks BUIDL submitted (>=250 words, 3W1H)"
	@echo "[ ] HackQuest cross-registration"
	@echo "[ ] X thread posted after submission timestamp"
	@echo "====================================================="

lint:
	uv run ruff check .
	uv run mypy agent api

fmt:
	uv run ruff format .
	uv run ruff check --fix .
