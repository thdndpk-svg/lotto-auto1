# Telegram Setup

LottoAuto 분석 결과를 텔레그램으로 받기 위한 설정입니다. 카카오톡 설정과 함께 써도 되고, 텔레그램만 써도 됩니다.

## 1. 텔레그램 봇 만들기

1. 텔레그램에서 `@BotFather` 검색
2. `/newbot` 입력
3. 봇 이름과 사용자명을 정함
4. BotFather가 알려주는 bot token을 보관

bot token은 비밀번호처럼 다뤄야 합니다. GitHub 저장소나 채팅에 공개하지 마세요.

## 2. 봇에게 메시지 보내기

텔레그램에서 방금 만든 봇 채팅방을 열고 아무 말이나 한 번 보냅니다.

예:

```text
start
```

## 3. Chat ID 찾기

Mac 터미널에서:

```bash
cd /Users/mac/Documents/Codex/2026-06-18/new-chat/outputs/lotto-auto
python3 telegram_setup_helper.py --bot-token "BOTFATHER가_준_BOT_TOKEN"
```

성공하면 아래처럼 나옵니다.

```text
TELEGRAM_BOT_TOKEN=(BotFather가 준 bot token)
TELEGRAM_CHAT_ID=123456789
```

메시지가 없다고 나오면 텔레그램 봇 채팅방에 아무 메시지나 보낸 뒤 다시 실행하세요.

테스트 메시지를 보내려면:

```bash
python3 telegram_setup_helper.py --bot-token "BOT_TOKEN" --chat-id "CHAT_ID" --send-test
```

## 4. GitHub Secrets 등록

GitHub 저장소에서:

```text
Settings > Secrets and variables > Actions > New repository secret
```

아래 2개를 각각 따로 저장합니다.

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

## 5. 자동 실행 확인

GitHub Actions에서 수동 실행:

```text
Actions > Lotto Weekly Message > Run workflow
```

일요일 결과 확인:

```text
Actions > Lotto Sunday Result Message > Run workflow
```

카카오 Secret이 고장 나도 텔레그램 Secret이 정상이라면 텔레그램으로 메시지가 발송됩니다.
