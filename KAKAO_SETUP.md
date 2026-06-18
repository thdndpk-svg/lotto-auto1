# KakaoTalk Setup

이 문서는 LottoAuto 분석 결과를 매주 수요일 12:00(KST)에 카카오톡 `나와의 채팅`으로 받기 위한 설정입니다.

## 1. 카카오 개발자 앱 만들기

1. https://developers.kakao.com 접속
2. 애플리케이션 추가
3. 앱 키에서 `REST API 키` 확인
4. 카카오 로그인 활성화
5. Redirect URI 등록

```text
http://localhost:8766/callback
```

6. 동의항목에서 `카카오톡 메시지 전송(talk_message)` 설정

## 2. Refresh Token 발급

Mac에서:

```bash
cd /Users/mac/Documents/Codex/2026-06-18/new-chat/outputs/lotto-auto
python3 kakao_auth_helper.py --rest-api-key YOUR_REST_API_KEY
```

REST API 키의 클라이언트 시크릿이 ON이면 아래처럼 함께 입력합니다.

```bash
python3 kakao_auth_helper.py --rest-api-key YOUR_REST_API_KEY --client-secret YOUR_CLIENT_SECRET
```

브라우저에서 카카오 로그인 후 동의하면 터미널에 아래 값이 출력됩니다.

```text
KAKAO_REST_API_KEY=...
KAKAO_REFRESH_TOKEN=...
```

`kakao_token.local.json` 파일도 생성되지만 이 파일은 절대 GitHub에 올리지 마세요.

## 3. GitHub Secrets 등록

GitHub 저장소에서:

```text
Settings > Secrets and variables > Actions > New repository secret
```

등록할 값:

```text
KAKAO_REST_API_KEY
KAKAO_REFRESH_TOKEN
```

클라이언트 시크릿을 사용하는 앱이면 이것도 등록합니다.

```text
KAKAO_CLIENT_SECRET
```

## 4. 자동 실행

`.github/workflows/lotto-kakao-weekly.yml`이 매주 수요일 12:00(KST)에 실행됩니다.

수동 실행:

```text
GitHub > Actions > Lotto Kakao Weekly > Run workflow
```

## 5. 로컬 테스트

카톡 발송 없이 메시지만 확인:

```bash
python3 weekly_kakao_report.py --dry-run --skip-refresh
```

실제 카톡 발송 테스트:

```bash
python3 weekly_kakao_report.py --skip-refresh
```

`kakao_auth_helper.py`로 만든 `kakao_token.local.json`이 현재 폴더에 있으면 위 명령은 환경변수 없이도 실행됩니다.

## 참고

- 카카오 로그인 REST API: https://developers.kakao.com/docs/latest/ko/kakaologin/rest-api
- 카카오톡 메시지 REST API: https://developers.kakao.com/docs/latest/ko/message/rest-api
