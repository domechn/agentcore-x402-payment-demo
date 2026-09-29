"""One-time AgentCore Payments setup. Run with YOUR admin credentials, not the agent role.

Privy keys (.env) -> credential provider -> payment manager -> connector -> wallet -> session.
Progress is saved to payments.json, so re-running skips finished steps and just issues a fresh session.
"""
import json
import os
import sys
import time
import uuid
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv()
REGION = os.environ.get("AWS_REGION", "us-west-2")
STACK = os.environ.get("STACK_NAME", "agentcore-x402-payment-demo")
USER_ID = "demo-user"
STATE = Path("payments.json")

ctrl = boto3.client("bedrock-agentcore-control", region_name=REGION)
dp = boto3.client("bedrock-agentcore", region_name=REGION)
state = json.loads(STATE.read_text()) if STATE.exists() else {"region": REGION, "userId": USER_ID}


def save():
    STATE.write_text(json.dumps(state, indent=2))


def wait_for(get, want):
    while (status := get()["status"]) != want:
        if "FAILED" in status or "EXPIRED" in status:
            sys.exit(f"status={status}, aborting")
        print(f"   status={status}, waiting...")
        time.sleep(5)


stack = boto3.client("cloudformation", region_name=REGION).describe_stacks(StackName=STACK)["Stacks"][0]
outputs = {o["OutputKey"]: o["OutputValue"] for o in stack["Outputs"]}

if "privyCredentialProviderArn" not in state:
    print("1. Storing Privy credentials in AgentCore Identity")
    cp = ctrl.create_payment_credential_provider(
        name="agentcore-payment-x402-demo-privy",
        credentialProviderVendor="StripePrivy",
        providerConfigurationInput={"stripePrivyConfiguration": {
            "appId": os.environ["PRIVY_APP_ID"],
            "appSecret": os.environ["PRIVY_APP_SECRET"],
            "authorizationId": os.environ["PRIVY_AUTHORIZATION_ID"],
            # Privy's dashboard shows the key as "wallet-auth:<base64>"; the API wants just the base64.
            "authorizationPrivateKey": os.environ["PRIVY_AUTHORIZATION_PRIVATE_KEY"].removeprefix("wallet-auth:"),
        }},
    )
    state["privyCredentialProviderArn"] = cp["credentialProviderArn"]
    cfg = cp["providerConfigurationOutput"]["stripePrivyConfiguration"]
    for key in ("appSecretArn", "authorizationPrivateKeyArn"):
        arn = cfg[key]["secretArn"]
        print(f"   {key}: {arn}")
        if ":secret:bedrock-agentcore-identity!" not in arn:
            print("   WARNING: secret name doesn't match infra.yaml's GetSecretValue scope; update infra.yaml")
    save()

if "paymentManagerArn" not in state:
    print("2. Creating payment manager")
    m = ctrl.create_payment_manager(
        name="x402demo", authorizerType="AWS_IAM", roleArn=outputs["PaymentsServiceRoleArn"],
        clientToken=str(uuid.uuid4()),
    )
    state["paymentManagerId"], state["paymentManagerArn"] = m["paymentManagerId"], m["paymentManagerArn"]
    save()
wait_for(lambda: ctrl.get_payment_manager(paymentManagerId=state["paymentManagerId"]), "READY")

if "paymentConnectorId" not in state:
    print("3. Creating Privy connector")
    c = ctrl.create_payment_connector(
        paymentManagerId=state["paymentManagerId"], name="privy", type="StripePrivy",
        credentialProviderConfigurations=[{"stripePrivy": {"credentialProviderArn": state["privyCredentialProviderArn"]}}],
        clientToken=str(uuid.uuid4()),
    )
    state["paymentConnectorId"] = c["paymentConnectorId"]
    save()
wait_for(lambda: ctrl.get_payment_connector(
    paymentManagerId=state["paymentManagerId"], paymentConnectorId=state["paymentConnectorId"]), "READY")

if "paymentInstrumentId" not in state:
    print("4. Creating the agent's embedded wallet")
    i = dp.create_payment_instrument(
        userId=USER_ID, paymentManagerArn=state["paymentManagerArn"], paymentConnectorId=state["paymentConnectorId"],
        paymentInstrumentType="EMBEDDED_CRYPTO_WALLET",
        paymentInstrumentDetails={"embeddedCryptoWallet": {
            "network": "ETHEREUM",
            "linkedAccounts": [{"email": {"emailAddress": os.environ["WALLET_EMAIL"]}}],
        }},
        clientToken=str(uuid.uuid4()),
    )["paymentInstrument"]
    wallet = i["paymentInstrumentDetails"]["embeddedCryptoWallet"]
    state["paymentInstrumentId"], state["walletAddress"] = i["paymentInstrumentId"], wallet.get("walletAddress")
    save()
    print(f"""
   >>> ACTION NEEDED (Privy frontend, see README step 2):
   1. Open http://localhost:3000 and log in with {os.environ['WALLET_EMAIL']}
   2. Click "Connect agent" -> "Give access"
   3. Get Base Sepolia USDC at https://faucet.circle.com for: {state['walletAddress']}
""")
    input("   Press Enter when done... ")

status = dp.get_payment_instrument(
    userId=USER_ID, paymentManagerArn=state["paymentManagerArn"],
    paymentInstrumentId=state["paymentInstrumentId"])["paymentInstrument"]["status"]
print(f"   wallet status: {status}")

print("5. Creating a payment session ($1 budget, 8h)")
s = dp.create_payment_session(
    userId=USER_ID, paymentManagerArn=state["paymentManagerArn"],
    limits={"maxSpendAmount": {"value": "1.00", "currency": "USD"}},
    expiryTimeInMinutes=480, clientToken=str(uuid.uuid4()),
)["paymentSession"]
state["paymentSessionId"] = s["paymentSessionId"]
save()
print(f"Done. Wallet {state['walletAddress']}, session {state['paymentSessionId']} -> payments.json")
