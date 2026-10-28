# 로컬 서버로 Apple 로그인 · 푸시 검증하기

> 대상: 앱(iOS/Android) 개발자
> 전제: 본인 PC 에서 백엔드를 `docker compose` 로 띄우고, 같은 Wi-Fi 의 휴대폰에서 앱을 실행한다.
> 관련: [users.md §3.2](users.md#32-post-apiv1authapple), [notifications.md §3.6~3.7](notifications.md#36-푸시-기기-등록--해제)

---

## 1. 왜 ngrok 이 필요 없나

Apple 로그인(iOS 네이티브)에서 Apple 과 통신하는 쪽은 **iPhone(Apple SDK)** 과 **서버(Apple 토큰 서버로 나가는 요청)** 뿐이다.
Apple 이 우리 서버를 먼저 찾아오는 일이 없으므로 서버에 공개 주소가 필요 없다. 앱은 지금처럼 같은 Wi-Fi 의 PC 주소(`http://<PC IP>:8080`)로 서버를 부르면 된다.

```
iPhone 앱 ──① Face ID 팝업──▶ Apple ──② id_token + code──▶ iPhone 앱
iPhone 앱 ──③ POST /api/v1/auth/apple/ {code, id_token}──▶ 서버(PC :8080)
서버 ──④ code 교환 (Bundle ID)──▶ Apple ──⑤ id_token + refresh_token──▶ 서버 → JWKS 검증
서버 ──⑥ access / refresh JWT──▶ iPhone 앱
```

Android 는 Apple 로그인을 쓰지 않으므로(카카오만) 웹 콜백·Service ID·ngrok 이 모두 해당 없다.

## 2. 절차

1. **서버 `.env` 준비** — `.env.example` 을 복사해 아래 값을 채운다. 값은 서버 팀이 전달한다.

   | 변수 | 값 |
   | --- | --- |
   | `APPLE_TEAM_ID` | Apple Developer Team ID (10자) |
   | `APPLE_CLIENT_ID` | iOS 앱 **Bundle ID** |
   | `APPLE_KEY_ID` | Sign in with Apple 키의 Key ID |
   | `APPLE_PRIVATE_KEY` | `.p8` 내용. 줄바꿈은 `\n`, 전체를 따옴표로 감싼다 |
   | `FIREBASE_CREDENTIALS_JSON` | (푸시까지 볼 때) Firebase 서비스 계정 JSON 한 줄. `jq -c . serviceAccount.json` |

2. **서버 실행**

   ```bash
   docker compose up -d
   docker compose exec app uv run python manage.py migrate
   open http://localhost:8080/api/docs/      # Swagger 가 뜨면 OK
   ```

3. **PC 의 Wi-Fi IP 확인 후 앱 설정**

   ```bash
   ipconfig getifaddr en0        # 예: 192.168.45.242
   ```

   앱의 `core/common/.../Config.kt` 의 `BASE_URL` 을 `http://<그 IP>:8080/api/v1` 로 맞춘다. iPhone 과 PC 가 같은 Wi-Fi 여야 한다.
   (iOS 는 `NSAllowsArbitraryLoads` 가 켜져 있어 http 도 허용된다.)

4. **iPhone 에서 로그인** — 실기기 권장(시뮬레이터도 Apple ID 로그인 상태면 가능). Apple 버튼 → Face ID → 앱이 `POST /api/v1/auth/apple/` 호출.
   앱은 `ASAuthorizationAppleIDCredential` 의 `authorizationCode` 를 `code` 로, `identityToken` 을 `id_token` 으로 보낸다. 코드는 **5분 · 1회용**이다.

5. **확인**

   ```bash
   docker compose logs -f app            # "POST /api/v1/auth/apple/ ... 200" 확인
   ```

   받은 access 토큰으로 `GET /api/v1/users/me/` 가 200 이면 완료.

6. **(선택) 푸시까지** — 로그인 후 `PUT /api/v1/users/me/devices/` 로 기기를 등록하고 `POST /api/v1/notifications/test/` 를 호출하면 그 기기로 테스트 푸시가 온다. `{"dry_run": true}` 로 보내면 실제 알림 없이 식별자 유효성만 검증한다.
   서버 쪽에서는 `docker compose exec app uv run python manage.py send_test_push --user <id> --dry-run` 으로 같은 검증을 할 수 있다.

## 3. 자주 나는 에러

| 증상 | 원인 | 대처 |
| --- | --- | --- |
| 401 `Apple 토큰 교환 실패: invalid_grant` | 코드 재사용, 5분 경과, 다른 Bundle ID 로 발급된 코드 | 새로 로그인해서 받은 코드를 바로 보낸다. `APPLE_CLIENT_ID` 가 앱 Bundle ID 와 같은지 확인 |
| 401 `Apple 토큰 교환 실패: invalid_client` | client_secret 생성 오류 — Key ID / Team ID 오타, `.p8` 줄바꿈 깨짐 | `.env` 의 `APPLE_PRIVATE_KEY` 를 따옴표로 감싸고 `\n` 을 유지한다 |
| 401 `Apple id_token 검증 실패: ...` | `aud` ≠ Bundle ID, 만료, 서명 불일치 | 앱과 서버의 Bundle ID 일치 확인. 기기 시각이 크게 틀어져 있지 않은지 확인 |
| 앱이 서버에 못 붙음 (timeout) | 다른 Wi-Fi, PC 방화벽, IP 변경 | 같은 Wi-Fi 인지, `ipconfig getifaddr en0` 값이 바뀌지 않았는지 확인 |
| Django 400 `Invalid HTTP_HOST` | `ALLOWED_HOSTS` 에 PC IP 가 없음 | 로컬은 `ALLOWED_HOSTS=*` 로 둔다 |
| 테스트 푸시 503 `push_unavailable` | 서버에 `FIREBASE_CREDENTIALS_JSON` 이 없음 | 1단계에서 값 추가 후 `docker compose restart app` |
| 테스트 푸시 `deactivated` ≥ 1 | 앱이 보낸 식별자가 무효(다른 Firebase 프로젝트, 재설치 후 옛 토큰) | 앱에서 최신 식별자를 다시 `PUT` 한다 |
| iOS 에 푸시가 안 옴 (`sent` 는 1) | Firebase 콘솔에 APNs 키 미등록, 알림 권한 거부 | Firebase 콘솔 > Cloud Messaging > APNs 인증 키 업로드, 기기 설정에서 알림 허용 |

## 4. 그래도 외부 주소가 필요할 때 (ngrok)

iPhone 과 PC 가 다른 네트워크이거나 외부 QA 에게 잠깐 열어 줄 때만 필요하다.

```bash
ngrok config add-authtoken <토큰>      # 최초 1회
ngrok http 8080                        # 출력된 https://xxxx.ngrok-free.dev 를 BASE_URL 로
```

- 앱 → 서버 요청에 `ngrok-skip-browser-warning: 1` 헤더를 붙이면 무료 플랜의 경고 페이지를 건너뛴다.
- 요청 내용은 `http://127.0.0.1:4040` 에서 볼 수 있다.
- 계정 없이 쓰려면 `cloudflared tunnel --url http://localhost:8080` (주소가 매번 바뀜).
