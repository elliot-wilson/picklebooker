import base64
import hashlib
import json
import os
import secrets
from urllib.parse import parse_qs, urlencode

import requests as http_requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUTH_HEADERS_PATH = "auth_headers.json"

# Azure AD B2C configuration (from OIDC discovery)
CLIENT_ID = "27e53cd6-9054-444f-bdfa-b341dcb7263d"
B2C_POLICY = "b2c_1a_webusernamesignin"
B2C_TENANT = "prdltmembersb2c.onmicrosoft.com"
TOKEN_ENDPOINT = f"https://auth.lifetime.life/{B2C_TENANT}/{B2C_POLICY}/oauth2/v2.0/token"
AUTHORIZE_ENDPOINT = f"https://auth.lifetime.life/{B2C_TENANT}/{B2C_POLICY}/oauth2/v2.0/authorize"
REDIRECT_URI = "https://my.lifetime.life/login/landing.html"
SCOPE = f"openid https://{B2C_TENANT}/{CLIENT_ID}/read profile offline_access"

# Public API key embedded in Lifetime's frontend JS — same for all users
PUBLIC_API_KEY = "924c03ce573d473793e184219a6a19bd"


def generate_pkce_pair():
    """Generate a PKCE code_verifier and code_challenge pair."""
    code_verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def extract_authentication_headers():
    print("🔑 Extracting authentication headers...")
    load_dotenv()
    username = os.getenv("ACCOUNT_USERNAME")
    password = os.getenv("ACCOUNT_PASSWORD")

    code_verifier, code_challenge = generate_pkce_pair()
    auth_code = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Capture the 302 response from the confirmSignIn endpoint.
        # Its Location header contains the auth code in the URL fragment.
        def capture_auth_redirect(response):
            nonlocal auth_code
            if auth_code:
                return
            url = response.url
            if "confirmsignin" in url.lower() or "confirmsignup" in url.lower() or response.status == 302:
                location = response.headers.get("location", "")
                if "code=" in location:
                    fragment = location.split("#", 1)[1] if "#" in location else ""
                    params = parse_qs(fragment)
                    if "code" in params:
                        auth_code = params["code"][0]
                        print("✅ Captured authorization code from 302 redirect")

        page.on("response", capture_auth_redirect)

        # Build the authorize URL with our own PKCE challenge
        nonce = secrets.token_hex(16)
        authorize_url = (
            AUTHORIZE_ENDPOINT + "?"
            + urlencode({
                "client_id": CLIENT_ID,
                "scope": SCOPE,
                "redirect_uri": REDIRECT_URI,
                "response_mode": "fragment",
                "response_type": "code",
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "nonce": nonce,
                "state": base64.b64encode(
                    b'{"id":"x","meta":{"interactionType":"redirect"}}'
                ).decode(),
            })
        )

        # Navigate directly to the authorize URL (shows the B2C login form)
        page.goto(authorize_url, wait_until="domcontentloaded")
        page.fill("input#signInName", username)
        page.fill("input#password", password)
        page.click("button#next")

        # Wait for the auth code to be captured from the 302 response
        for _ in range(30):
            page.wait_for_timeout(500)
            if auth_code:
                break

        browser.close()

    if not auth_code:
        print("⚠️ Failed to capture authorization code.")
        print("The login may have failed or the redirect was not captured.")
        raise SystemExit(1)

    # Exchange the authorization code for tokens
    print("🔄 Exchanging authorization code for tokens...")
    token_response = http_requests.post(
        TOKEN_ENDPOINT,
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": code_verifier,
            "scope": SCOPE,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if token_response.status_code != 200:
        print(f"❌ Token exchange failed: {token_response.status_code}")
        print(f"Response: {token_response.text}")
        raise SystemExit(1)

    tokens = token_response.json()
    id_token = tokens.get("id_token", "")

    # Decode the ID token JWT payload to extract LTF claims
    # (no signature verification needed — received directly from IdP over HTTPS)
    parts = id_token.split(".")
    if len(parts) != 3:
        print("❌ Invalid ID token format")
        raise SystemExit(1)

    payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload_b64))

    ssoid = claims.get("LTF_SSOID", "")
    access_token = claims.get("LTF_AccessToken", "")

    if not ssoid or not access_token:
        print("⚠️ Could not find LTF_SSOID or LTF_AccessToken in token claims.")
        print(f"Available claims: {list(claims.keys())}")
        raise SystemExit(1)

    auth_headers = {
        "x-ltf-ssoid": ssoid,
        "x-ltf-jwe": access_token,
        "x-ltf-profile": json.dumps({"ssoId": ssoid}),
        "ocp-apim-subscription-key": PUBLIC_API_KEY,
    }

    with open(os.path.join(BASE_DIR, AUTH_HEADERS_PATH), "w") as f:
        json.dump(auth_headers, f, indent=2)
    print(f"✅ Saved auth headers to {AUTH_HEADERS_PATH}")


if __name__ == "__main__":
    extract_authentication_headers()
