"""Minimal x402 v2 seller: GET /premium costs 0.001 USDC on Base Sepolia.

No payment header      -> 402 + PAYMENT-REQUIRED (base64 JSON of what to pay).
PAYMENT-SIGNATURE set  -> facilitator /verify, then /settle (on-chain), then 200 + content.
"""
import base64
import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dotenv import load_dotenv

load_dotenv()
PORT = int(os.environ.get("SELLER_PORT", "4021"))
FACILITATOR = "https://www.x402.org/facilitator"
REQUIREMENT = {
    "scheme": "exact",
    "network": "eip155:84532",                              # Base Sepolia
    "amount": "1000",                                       # 0.001 USDC (6 decimals)
    "asset": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",  # USDC on Base Sepolia
    "payTo": os.environ["SELLER_ADDRESS"],
    "maxTimeoutSeconds": 60,
    "extra": {"name": "USDC", "version": "2"},
}
CONTENT = {"title": "Premium report", "body": "Agents paying agents: x402 turns HTTP 402 into a checkout."}


def b64(obj):
    return base64.b64encode(json.dumps(obj).encode()).decode()


def facilitator(path, payment):
    # We send OUR requirement, so the facilitator enforces our amount/asset/payTo, not the buyer's claim.
    body = json.dumps({"x402Version": 2, "paymentPayload": payment, "paymentRequirements": REQUIREMENT}).encode()
    # Cloudflare in front of x402.org rejects urllib's default User-Agent (error 1010).
    req = urllib.request.Request(FACILITATOR + path, body, {"Content-Type": "application/json", "User-Agent": "x402-demo"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace")
        try:
            return json.loads(text)
        except ValueError:
            return {"invalidReason": f"facilitator HTTP {e.code}: {text[:200]}"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/premium":
            return self.reply(404, {"error": "not found"})

        signature = self.headers.get("PAYMENT-SIGNATURE")
        if not signature:
            print("[seller] no payment -> 402")
            return self.reply(402, {"error": "payment required"}, {"PAYMENT-REQUIRED": b64({
                "x402Version": 2,
                "error": "Payment required",
                "resource": {"url": f"http://{self.headers['Host']}{self.path}",
                             "description": CONTENT["title"], "mimeType": "application/json"},
                "accepts": [REQUIREMENT],
            })})

        try:
            payment = json.loads(base64.b64decode(signature))
        except ValueError:
            return self.reply(400, {"error": "malformed PAYMENT-SIGNATURE"})

        verified = facilitator("/verify", payment)
        if not verified.get("isValid"):
            print(f"[seller] verify failed: {verified}")
            return self.reply(402, {"error": verified.get("invalidReason", "invalid payment")})

        settled = facilitator("/settle", payment)
        if not settled.get("success"):
            print(f"[seller] settle failed: {settled}")
            return self.reply(402, {"error": settled.get("errorReason", "settlement failed")})

        print(f"[seller] paid by {settled.get('payer')}: https://sepolia.basescan.org/tx/{settled['transaction']}")
        self.reply(200, CONTENT, {"PAYMENT-RESPONSE": b64(settled)})

    def reply(self, status, body, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())


if __name__ == "__main__":
    print(f"[seller] http://localhost:{PORT}/premium -> pay {REQUIREMENT['payTo']}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
