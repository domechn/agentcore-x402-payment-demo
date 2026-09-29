English | [简体中文](README.zh-CN.md)

# AgentCore Payments × x402 minimal example

```
agent.py ──GET /premium──▶ seller.py
   │   ◀── 402 + PAYMENT-REQUIRED ──┘
   │
   ├─ ProcessPayment ──▶ AgentCore Payments ──▶ Privy wallet signs (EIP-3009, bounded by the session budget)
   │
   └─GET + PAYMENT-SIGNATURE──▶ seller.py ──verify/settle──▶ x402.org facilitator ──▶ settled on-chain (Base Sepolia)
                     ◀── 200 + content ──┘
```

| File | Role |
|---|---|
| `infra/infra.yaml` | CloudFormation: PaymentsServiceRole (service reads Privy credentials) and AgentRole (agent can pay, but cannot create sessions/wallets) |
| `src/setup_payments.py` | One-time setup: credentials → payment manager → connector → wallet → session, result written to `payments.json` |
| `src/seller.py` | Seller service, `/premium` charges 0.001 USDC |
| `src/agent.py` | Strands agent + `AgentCorePaymentsPlugin`; the 402 → pay → retry loop is fully automatic |

> Run all commands from the project root. `payments.json` and `.env` are read/written in the root, so invoke the scripts as `src/xxx.py`.

## 0. Manual prerequisites (once)

1. **Privy Dashboard** (https://dashboard.privy.io) — create a dedicated app:
   - Settings → API keys: grab the **App ID** and **App secret**
   - Wallet infrastructure → Authorization → New key: grab the **Key ID** (Authorization ID) and the **private key**
   - App Settings → Basics → Domains: add `http://localhost:3000`
2. **Bedrock** — enable model access for Claude Sonnet 5 in us-west-2.
3. Add these lines to `.env`:
   ```
   PRIVY_APP_ID=...
   PRIVY_APP_SECRET=...
   PRIVY_AUTHORIZATION_ID=...
   PRIVY_AUTHORIZATION_PRIVATE_KEY=...   # with or without the wallet-auth: prefix
   WALLET_EMAIL=your-email               # used to log in to the Privy frontend and authorize the agent
   SELLER_ADDRESS=0x...                  # seller payout address, any EVM address you own (not the agent wallet address)
   ```

## 1. Deploy IAM (with your admin profile)

```bash
export AWS_REGION=us-west-2 AWS_PROFILE=<your-admin-profile>
aws cloudformation deploy --stack-name agentcore-x402-payment-demo --template-file infra/infra.yaml --capabilities CAPABILITY_IAM
```

## 2. Configure Payments (still with the admin profile)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python src/setup_payments.py
```

The script pauses at step 4 and waits for you. In another terminal, start Privy's official authorization/funding frontend:

```bash
git clone https://github.com/privy-io/aws-agentcore-sdk.git && cd aws-agentcore-sdk
cp .env.example .env.local   # fill NEXT_PUBLIC_PRIVY_APP_ID / PRIVY_APP_SECRET / NEXT_PUBLIC_PRIVY_SIGNER_ID(=Authorization ID)
                             # and set NEXT_PUBLIC_NETWORK_MODE=testnet
pnpm install && pnpm dev
```

Open http://localhost:3000, log in with `WALLET_EMAIL` → **Connect agent → Give access** → go to https://faucet.circle.com, pick Base Sepolia, and fund the wallet address the script printed with USDC (no ETH needed; gas is covered by the facilitator). When done, return to the script terminal and press Enter.

The session is valid for 8 hours. When it expires, just re-run `src/setup_payments.py` (already-completed steps are skipped).

## 3. Run

```bash
# Terminal 1
.venv/bin/python src/seller.py

# Terminal 2: run the agent as AgentRole (this role can only pay within budget, it cannot raise its own budget)
aws configure set profile.x402-agent.role_arn $(aws cloudformation describe-stacks --stack-name agentcore-x402-payment-demo \
  --query "Stacks[0].Outputs[?OutputKey=='AgentRoleArn'].OutputValue" --output text)
aws configure set profile.x402-agent.source_profile <your-admin-profile>
AWS_PROFILE=x402-agent .venv/bin/python src/agent.py
```

The seller terminal prints a BaseScan transaction link — that's the on-chain settlement record.
