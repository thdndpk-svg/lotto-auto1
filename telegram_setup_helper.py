#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def get_json(url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram API HTTP {error.code}: {body}") from error


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
        raise RuntimeError(f"Telegram API HTTP {error.code}: {body}") from error


def list_chat_ids(bot_token: str) -> list[dict[str, Any]]:
    payload = get_json(f"https://api.telegram.org/bot{bot_token}/getUpdates")
    chats: dict[int, dict[str, Any]] = {}
    for update in payload.get("result", []):
        message = update.get("message") or update.get("channel_post") or update.get("edited_message")
        if not message:
            continue
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            continue
        chats[int(chat_id)] = chat
    return list(chats.values())


def send_test(bot_token: str, chat_id: str) -> dict[str, Any]:
    return post_form(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        {
            "chat_id": chat_id,
            "text": "LottoAuto 텔레그램 연결 테스트입니다.",
            "disable_web_page_preview": "true",
        },
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Find Telegram chat id for LottoAuto.")
    parser.add_argument("--bot-token", required=True, help="Telegram BotFather bot token.")
    parser.add_argument("--chat-id", help="Optional chat id for sending a test message.")
    parser.add_argument("--send-test", action="store_true", help="Send a test message to --chat-id.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.send_test:
        if not args.chat_id:
            raise SystemExit("--send-test requires --chat-id.")
        response = send_test(args.bot_token, args.chat_id)
        print(f"Telegram test response: {response}")
        return 0

    chats = list_chat_ids(args.bot_token)
    if not chats:
        print("아직 받은 메시지가 없습니다.")
        print("텔레그램에서 만든 봇 채팅방에 아무 메시지나 보낸 뒤 다시 실행하세요.")
        return 1

    print("GitHub Secrets에 아래 값을 저장하세요.")
    print("TELEGRAM_BOT_TOKEN=(BotFather가 준 bot token)")
    for chat in chats:
        title = chat.get("title") or chat.get("username") or chat.get("first_name") or "unknown"
        print(f"TELEGRAM_CHAT_ID={chat['id']}  ({chat.get('type', '-')}: {title})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
