#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


DEFAULT_REDIRECT_URI = "http://localhost:8766/callback"
AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"


def post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Kakao API HTTP {error.code}: {body}") from error


class CallbackState:
    code: str | None = None
    error: str | None = None
    state: str | None = None


def make_handler(callback_state: CallbackState, expected_state: str):
    class KakaoCallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            received_error = params.get("error", [None])[0]
            received_code = params.get("code", [None])[0]
            received_state = params.get("state", [None])[0]

            if received_error:
                callback_state.error = received_error
                message = f"카카오 인증 실패: {received_error}"
            elif received_state != expected_state:
                message = "이전 인증 창에서 돌아온 요청입니다. 이 창은 닫고, 새로 열린 카카오 로그인 창에서 다시 진행하세요."
            elif received_code:
                callback_state.code = received_code
                callback_state.state = received_state
                message = "카카오 인증 완료. 이 창은 닫아도 됩니다."
            else:
                callback_state.error = "missing_code"
                message = "카카오 인증 실패: code가 없습니다."

            body = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>Lotto Auto Kakao Auth</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;margin:48px;line-height:1.6}}</style>
</head><body><h1>{message}</h1><p>터미널로 돌아가 다음 안내를 확인하세요.</p></body></html>""".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return KakaoCallbackHandler


def exchange_code(
    rest_api_key: str,
    redirect_uri: str,
    code: str,
    client_secret: str | None = None,
) -> dict[str, Any]:
    payload = {
        "grant_type": "authorization_code",
        "client_id": rest_api_key,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    if client_secret:
        payload["client_secret"] = client_secret
    return post_form(TOKEN_URL, payload)


def build_authorize_url(rest_api_key: str, redirect_uri: str, state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": rest_api_key,
        "redirect_uri": redirect_uri,
        "scope": "talk_message",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def run_interactive(args: argparse.Namespace) -> int:
    rest_api_key = args.rest_api_key.strip()
    redirect_uri = args.redirect_uri.strip()
    state = secrets.token_urlsafe(18)
    callback_state = CallbackState()

    parsed = urllib.parse.urlparse(redirect_uri)
    if parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise SystemExit("이 도우미는 localhost redirect_uri만 지원합니다.")
    port = parsed.port or 80

    server = ThreadingHTTPServer(
        ("127.0.0.1", port),
        make_handler(callback_state, state),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = build_authorize_url(rest_api_key, redirect_uri, state)
    print("\n1) 아래 주소를 브라우저로 엽니다.")
    print(url)
    print("\n2) 카카오 로그인과 talk_message 동의를 완료하세요.")
    print("브라우저를 자동으로 열어볼게요.\n")
    webbrowser.open(url)

    while callback_state.code is None and callback_state.error is None:
        thread.join(timeout=0.25)

    server.shutdown()
    server.server_close()

    if callback_state.error or not callback_state.code:
        raise SystemExit(f"인증 실패: {callback_state.error or 'missing_code'}")

    token = exchange_code(rest_api_key, redirect_uri, callback_state.code, args.client_secret)
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        raise SystemExit("토큰 응답에 refresh_token이 없습니다. 이미 연결된 앱이면 연결 해제 후 다시 시도해보세요.")

    print("\n카카오 인증 성공.")
    print("\nGitHub Secrets에 아래 값을 저장하세요.")
    print(f"KAKAO_REST_API_KEY={rest_api_key}")
    print(f"KAKAO_REFRESH_TOKEN={refresh_token}")
    if args.client_secret:
        print("KAKAO_CLIENT_SECRET=(입력한 client secret 값)")

    if args.output:
        output = Path(args.output)
        output.write_text(
            json.dumps(
                {
                    "rest_api_key": rest_api_key,
                    "refresh_token": refresh_token,
                    "client_secret": args.client_secret or "",
                    "client_secret_set": bool(args.client_secret),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\n로컬 참고용 파일 저장: {output}")
        print("이 파일은 GitHub에 올리지 마세요.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Get Kakao refresh token for LottoAuto.")
    parser.add_argument("--rest-api-key", required=True, help="Kakao Developers REST API key.")
    parser.add_argument("--redirect-uri", default=DEFAULT_REDIRECT_URI)
    parser.add_argument("--client-secret", default=None, help="Optional Kakao client secret.")
    parser.add_argument("--output", default="kakao_token.local.json", help="Local output file. Do not commit.")
    return parser


if __name__ == "__main__":
    raise SystemExit(run_interactive(build_parser().parse_args()))
