// 独立的 CDP 钱包小例子，跟主流程（Privy + AgentCore Payments）无关：
// 用 Coinbase CDP SDK 创建一个托管钱包，从水龙头领测试 ETH，再自转一笔，验证 SDK 跑得通。
import { CdpClient } from "@coinbase/cdp-sdk";
import { http, createPublicClient, parseEther } from "viem";
import { baseSepolia } from "viem/chains";
import dotenv from "dotenv";

dotenv.config(); // 从 .env 读 CDP_API_KEY_ID / CDP_API_KEY_SECRET / CDP_WALLET_SECRET

const cdp = new CdpClient();
// viem 只读客户端，用来等链上交易回执（CDP 负责发交易，viem 负责确认落块）
const publicClient = createPublicClient({ chain: baseSepolia, transport: http() });

// 在 CDP 上新建一个 EVM 托管账户，私钥由 CDP 保管
const account = await cdp.evm.createAccount();
console.log("Wallet address:", account.address);

// 向 Base Sepolia 测试网水龙头领 ETH，并等这笔充值确认
const { transactionHash: faucetHash } = await cdp.evm.requestFaucet({
  address: account.address,
  network: "base-sepolia",
  token: "eth",
});
await publicClient.waitForTransactionReceipt({ hash: faucetHash });
await new Promise(r => setTimeout(r, 3000)); // 等 CDP 侧余额同步，否则下一笔可能报余额不足

// 自己转给自己一笔极小额，纯粹演示"用这个钱包发一笔交易"
const { transactionHash } = await cdp.evm.sendTransaction({
  address: account.address,
  transaction: { to: account.address, value: parseEther("0.000001") },
  network: "base-sepolia",
});
await publicClient.waitForTransactionReceipt({ hash: transactionHash });
console.log("View on BaseScan: https://sepolia.basescan.org/tx/" + transactionHash);
