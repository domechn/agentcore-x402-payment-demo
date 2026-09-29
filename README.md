# AgentCore Payments × x402 最小示例

```
agent.py ──GET /premium──▶ seller.py
   │   ◀── 402 + PAYMENT-REQUIRED ──┘
   │
   ├─ ProcessPayment ──▶ AgentCore Payments ──▶ Privy 钱包签名 (EIP-3009, 受 session 预算限制)
   │
   └─GET + PAYMENT-SIGNATURE──▶ seller.py ──verify/settle──▶ x402.org facilitator ──▶ Base Sepolia 链上结算
                     ◀── 200 + 内容 ──┘
```

| 文件 | 作用 |
|---|---|
| `infra/infra.yaml` | CloudFormation：PaymentsServiceRole（服务读 Privy 凭证）、AgentRole（agent 能付钱，但不能建 session/钱包） |
| `src/setup_payments.py` | 一次性配置：凭证 → payment manager → connector → 钱包 → session，结果写进 `payments.json` |
| `src/seller.py` | 卖家服务，`/premium` 收 0.001 USDC |
| `src/agent.py` | Strands agent + `AgentCorePaymentsPlugin`，402 → 付款 → 重试这一套全自动 |
| `examples/cdp-wallet.ts` | 独立的 CDP 钱包小例子，跟主流程无关，仅验证 Coinbase CDP SDK |

> 所有命令都从项目根目录运行。`payments.json` 和 `.env` 也读写在根目录，脚本按 `src/xxx.py` 调用即可。

## 0. 手动前置（只做一次）

1. **Privy Dashboard**（https://dashboard.privy.io）新建一个专用 app：
   - Settings → API keys：拿 **App ID**、**App secret**
   - Wallet infrastructure → Authorization → New key：拿 **Key ID**（Authorization ID）和**私钥**
   - App Settings → Basics → Domains：加上 `http://localhost:3000`
2. **Bedrock** 在 us-west-2 开通 Claude Sonnet 5 的模型访问。
3. `.env` 里加这几行（原来的 CDP 三个 key 用不到了，可以删掉）：
   ```
   PRIVY_APP_ID=...
   PRIVY_APP_SECRET=...
   PRIVY_AUTHORIZATION_ID=...
   PRIVY_AUTHORIZATION_PRIVATE_KEY=...   # 带不带 wallet-auth: 前缀都行
   WALLET_EMAIL=你的邮箱                   # 在 Privy 前端登录、给 agent 授权用
   SELLER_ADDRESS=0x...                   # 卖家收款地址，任意一个你自己的 EVM 地址（不要用 agent 钱包地址）
   ```

## 1. 部署 IAM（用你的管理员 profile）

```bash
export AWS_REGION=us-west-2 AWS_PROFILE=<你的管理员profile>
aws cloudformation deploy --stack-name agentcore-x402-payment-demo --template-file infra/infra.yaml --capabilities CAPABILITY_IAM
```

## 2. 配置 Payments（还是用管理员 profile）

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python src/setup_payments.py
```

脚本跑到第 4 步会停下来等你。另开一个终端，启动 Privy 官方的授权/充值前端：

```bash
git clone https://github.com/privy-io/aws-agentcore-sdk.git && cd aws-agentcore-sdk
cp .env.example .env.local   # 填 NEXT_PUBLIC_PRIVY_APP_ID / PRIVY_APP_SECRET / NEXT_PUBLIC_PRIVY_SIGNER_ID(=Authorization ID)
                             # 并设 NEXT_PUBLIC_NETWORK_MODE=testnet
pnpm install && pnpm dev
```

打开 http://localhost:3000，用 `WALLET_EMAIL` 登录 → **Connect agent → Give access** → 去 https://faucet.circle.com 选 Base Sepolia，给脚本打印的钱包地址领 USDC（不需要 ETH，gas 由 facilitator 出）。完成后回脚本终端按回车。

session 有效期 8 小时，过期了重新跑一遍 `src/setup_payments.py` 就行（已经做完的步骤会跳过）。

## 3. 运行

```bash
# 终端 1
.venv/bin/python src/seller.py

# 终端 2：用 AgentRole 跑 agent（这个角色只能在预算内付款，自己加不了预算）
aws configure set profile.x402-agent.role_arn $(aws cloudformation describe-stacks --stack-name agentcore-x402-payment-demo \
  --query "Stacks[0].Outputs[?OutputKey=='AgentRoleArn'].OutputValue" --output text)
aws configure set profile.x402-agent.source_profile <你的管理员profile>
AWS_PROFILE=x402-agent .venv/bin/python src/agent.py
```

seller 终端会打印一个 BaseScan 交易链接，那就是链上结算记录。
