# Check whether the deployed API is reachable, correct, and allowed to talk
# to the frontend. Answers the three questions that otherwise get conflated:
#
#   1. is the backend up?                  (a status at all)
#   2. is it the right backend?            (our JSON, not a CDN/404 page)
#   3. will the browser accept it?         (Access-Control-Allow-Origin)
#
# The third is the one that bites: a blocked CORS response is reported by the
# browser as a network failure, so it looks exactly like a dead backend.
#
#   python scripts/check_api.py
#   python scripts/check_api.py --api https://tailorup-api.onrender.com/api \
#                               --origin https://match-score.vercel.app

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_API = os.environ.get("VITE_API_URL", "").rstrip("/")


def request(url: str, origin: str | None, timeout: int = 60) -> tuple[int | None, object, str]:
    """Return (status, headers, body).

    The header object is returned as-is rather than as a dict: HTTP header
    names are case-insensitive, and ``dict(headers)`` preserves whatever case
    the server sent (``access-control-allow-origin`` from a WSGI server, say).
    Looking those up as ``Access-Control-Allow-Origin`` then silently misses,
    and the checker reports a perfectly good CORS setup as blocked.
    """
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    if origin:
        req.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return (
                response.status,
                response.headers,
                response.read().decode("utf-8", "replace"),
            )
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read().decode("utf-8", "replace")
    except Exception as exc:  # DNS, TLS, timeout, free-tier wake-up
        return None, {}, f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default=DEFAULT_API, help="API base, including /api")
    parser.add_argument(
        "--origin", default="https://match-score.vercel.app", help="frontend origin"
    )
    args = parser.parse_args()

    api = args.api.rstrip("/")
    if not api:
        print("No API URL. Pass --api or set VITE_API_URL.", file=sys.stderr)
        return 2

    print(f"API     : {api}")
    print(f"Origin  : {args.origin}")
    print()

    # 1. reachable at all?
    status, headers, body = request(f"{api}/auth/me/", args.origin)

    if status is None:
        print(f"UNREACHABLE            {body}")
        print()
        print("A free-tier service sleeps. The first request after ~15 minutes")
        print("idle can take 30-60s while it wakes; retry once before debugging.")
        return 1

    if status >= 500:
        print(f"SERVER ERROR           HTTP {status}")
        return 1

    # 2. is it actually our API?
    try:
        payload = json.loads(body)
        ours = "authenticated" in payload
    except ValueError:
        ours = False

    # 3. will a browser accept it?
    allow = headers.get("Access-Control-Allow-Origin")
    allow_credentials = headers.get("Access-Control-Allow-Credentials")

    ok = True

    if status == 200 and ours:
        print(f"backend up             HTTP 200, correct JSON")
    else:
        ok = False
        print(f"UNEXPECTED RESPONSE    HTTP {status}  {body[:120]}")

    if allow:
        print(f"CORS allowed           Access-Control-Allow-Origin: {allow}")
    else:
        ok = False
        print("CORS BLOCKED           no Access-Control-Allow-Origin header")
        print()
        print("The backend is serving requests fine, but the browser will")
        print("refuse to hand the response to the page. Add your exact frontend")
        print("origin to CORS_ALLOWED_ORIGINS on the server:")
        print()
        print(f"  CORS_ALLOWED_ORIGINS={args.origin}")
        print(f"  FRONTEND_ORIGIN={args.origin}")
        print()
        print("The value must match character for character: https:// included,")
        print("no trailing slash, no www.")
        print()
        print("NOTE: if you are on a Vercel *preview* URL the origin looks like")
        print("  match-score-<hash>-<team>.vercel.app")
        print("and changes on every push, so it cannot be hardcoded. Test on the")
        print("production URL, or set CORS_ALLOWED_ORIGINS_REGEX on the server:")
        print()
        print(r"  CORS_ALLOWED_ORIGINS_REGEX=https://match-score.*\.vercel\.app")

    if allow and allow_credentials:
        print(f"credentials            Access-Control-Allow-Credentials: {allow_credentials}")

    print()
    print("OK - signup should work." if ok else "NOT READY - see above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
