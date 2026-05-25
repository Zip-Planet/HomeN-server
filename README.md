# HomeN-server

HomeN 서비스의 백엔드 REST API 서버입니다. (Django 5 / DRF / PostgreSQL)

소셜 로그인(카카오·애플), 집 생성·참여, 집안일 관리 등의 API를 제공하며 API 명세는 Swagger UI로 확인할 수 있습니다.

---

## 사전 준비물

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Docker + Docker Compose v2)
- Git

> Python/PostgreSQL를 로컬에 직접 설치할 필요는 없습니다. 전부 컨테이너로 실행됩니다.

---

## 빠른 시작 (Docker Compose)

```bash
# 1. 저장소 클론
git clone https://github.com/Zip-Planet/HomeN-server.git
cd HomeN-server

# 2. 환경변수 파일 생성 (예시 복사 후 값 채우기)
cp .env.example .env

# 3. 빌드 & 실행
docker compose up --build
```

- 첫 실행 시 PostgreSQL이 준비되면 **DB 마이그레이션이 자동 적용**된 뒤 서버가 뜹니다.
- 종료는 `Ctrl + C`, 백그라운드 실행은 `docker compose up -d --build`.

### `.env` 설정

`.env.example`을 복사해 값을 채웁니다. 컨테이너로 실행하면 `DATABASE_URL`은 `docker-compose.yml`이 자동 주입하므로 비워둬도 됩니다.

| 키 | 설명 |
| --- | --- |
| `SECRET_KEY` | Django 시크릿 키 (아무 임의 문자열) |
| `DEBUG` | 로컬은 `True` |
| `ALLOWED_HOSTS` | 로컬은 `*` |
| `KAKAO_REST_API_KEY` / `KAKAO_CLIENT_SECRET` / `KAKAO_REDIRECT_URI` | 카카오 로그인 테스트 시 **실제 값 필요** (placeholder로는 로그인 실패) |
| `APPLE_*` | 애플 로그인 테스트 시 필요 |

---

## 접속 주소

서버가 뜨면 호스트의 **8080 포트**로 접근합니다 (컨테이너 내부 8000 → 호스트 8080 매핑).

| 용도 | URL |
| --- | --- |
| **Swagger UI (API 문서)** | http://localhost:8080/api/docs/ |
| OpenAPI 스키마 (raw) | http://localhost:8080/api/schema/ |
| API Base | http://localhost:8080/api/v1 |
| Django Admin | http://localhost:8080/admin/ |

---

## 📱 안드로이드(FE)에서 접속하기

기기/에뮬레이터에서는 `localhost`가 **자기 자신**을 가리키므로 서버에 닿지 않습니다. 상황에 맞는 호스트 주소를 쓰세요.

| 실행 환경 | BASE_URL |
| --- | --- |
| **실기기** (서버 PC와 같은 WiFi) | `http://<서버 PC의 LAN IP>:8080/api/v1` (예: `http://192.168.45.214:8080/api/v1`) |
| Android 에뮬레이터 | `http://10.0.2.2:8080/api/v1` |

서버 PC의 LAN IP 확인:

```bash
# macOS
ipconfig getifaddr en0
# Windows
ipconfig   # IPv4 주소 확인
```

> 실기기로 붙으려면 서버 PC와 폰이 **같은 네트워크**에 있어야 하고, PC 방화벽에서 8080 포트가 열려 있어야 합니다.

---

## 자주 쓰는 명령어

```bash
docker compose up -d --build        # 백그라운드 실행
docker compose logs -f app          # 앱 로그 실시간 확인
docker compose down                 # 중지 (DB 데이터 유지)
docker compose down -v              # 중지 + DB 볼륨 삭제 (완전 초기화)

# 컨테이너 안에서 manage.py 실행
docker compose exec app uv run python manage.py migrate
docker compose exec app uv run python manage.py createsuperuser
docker compose exec app uv run python manage.py test
```

---

## 트러블슈팅

| 증상 | 원인 / 해결 |
| --- | --- |
| `relation "..." does not exist` | 마이그레이션 미적용. 보통 자동 적용되지만, 안 되면 `docker compose exec app uv run python manage.py migrate` 또는 `docker compose down -v` 후 재기동 |
| 카카오 로그인 `ip mismatched! callerIp=...` | 카카오 디벨로퍼스 → 앱 → 보안 → **호출 허용 IP**에 서버의 공인 IP 추가(또는 제한 해제). 가정용 유동 IP는 바뀌면 재등록 필요 |
| 카카오 로그인 401 `authorization code not found` | 인가코드는 **1회용**. 같은 코드로 재요청 금지 (FE에서 중복 전송 여부 확인) |
| `8080` / `5432` 포트 충돌 | 해당 포트를 쓰는 프로세스를 종료하거나 `docker-compose.yml`의 포트 매핑 변경 |
