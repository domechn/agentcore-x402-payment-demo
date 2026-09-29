"""x402 buyer agent: Strands + the AgentCore Payments plugin.

The plugin's http_request tool sees the 402, calls ProcessPayment (AgentCore signs with the
Privy wallet, within the session budget), then retries the request with PAYMENT-SIGNATURE.
Run it as the AgentRole from infra.yaml: it can spend, but can't create sessions or wallets.
"""
import json
import os
import sys
from pathlib import Path

from bedrock_agentcore.payments.integrations.config import AgentCorePaymentsPluginConfig
from bedrock_agentcore.payments.integrations.strands.plugin import AgentCorePaymentsPlugin
from strands import Agent
from strands.models import BedrockModel

state = json.loads(Path("payments.json").read_text())
url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4021/premium"

payments = AgentCorePaymentsPlugin(config=AgentCorePaymentsPluginConfig(
    payment_manager_arn=state["paymentManagerArn"],
    user_id=state["userId"],
    payment_instrument_id=state["paymentInstrumentId"],
    payment_session_id=state["paymentSessionId"],
    region=state["region"],
))

agent = Agent(
    model=BedrockModel(model_id=os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-5"), region_name=state["region"]),
    system_prompt="You fetch paid web content for the user with http_request. Payments are handled for you.",
    plugins=[payments],
)
agent(f"Fetch {url} and tell me what it says.")
