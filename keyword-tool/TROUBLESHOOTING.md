# NaverBlogTool - 반복 발생 오류 원인 및 해결 기록

---

## 오류 1: SSL 인증서 오류 (5회 이상 반복)

### 증상
```
검색 오류: Could not find a suitable TLS CA certificate bundle,
invalid path: ...\dist\NaverBlogTool\_internal\certifi\cacert.pem
```

### 근본 원인

PyInstaller로 빌드 시 `certifi/cacert.pem` 파일이 `_internal` 폴더에 포함되지 않아 발생.

**왜 반복됐는가 — spec 파일 중복 충돌**

`NaverBlogTool.spec`에 certifi가 두 군데 중복 정의되어 있었음:

```python
# 중복 ① — 하드코딩 경로 (폴더 전체)
datas = [('templates', 'templates'),
         ('C:\\...\\Python314\\...\\certifi', 'certifi')]

# 중복 ② — collect_all
tmp_ret = collect_all('certifi')
datas += tmp_ret[0]  # 같은 목적지 'certifi' 에 또 추가
```

같은 목적지(`'certifi'`)로 두 번 추가되면 PyInstaller가 충돌 처리 중 데이터 파일 수집을 건너뜀.
결과: `_internal/certifi/` 폴더 자체가 생성되지 않음.

**추가 문제 — app.py 폴백 부재**

certifi 파일이 없을 때 `certifi.where()`를 패치하지 않아, 번들 내부의 certifi가
존재하지 않는 경로를 계속 반환하여 모든 HTTPS 요청이 실패.

### 현재 해결 상태

**spec 파일** — `collect_all` 제거, `certifi.where()`로 직접 지정:
```python
import certifi as _certifi_mod
datas = [('templates', 'templates'), (_certifi_mod.where(), 'certifi')]
# collect_all('certifi') 제거 — 중복 없음
```

**app.py** — certifi 파일 없을 때 안전하게 폴백:
```python
if os.path.exists(_cert):
    # 정상: 환경변수 + certifi.where() 패치
else:
    # 폴백: 잘못된 env var 제거, Windows 시스템 인증서 사용
    for _ev in ('REQUESTS_CA_BUNDLE', 'SSL_CERT_FILE', 'CURL_CA_BUNDLE'):
        os.environ.pop(_ev, None)
    # certifi.where() 도 None으로 패치하여 잘못된 경로 반환 차단
```

### 재발 방지 규칙

- spec에 certifi를 추가할 때 `collect_all('certifi')` 와 직접 경로 **둘 다 쓰지 말 것**
- 빌드 후 반드시 `_internal/certifi/cacert.pem` 존재 확인 (`build.bat`에 검증 로직 포함됨)

---

## 오류 2: exe 실행 중 재빌드 시 _internal 파일 오염

### 증상

빌드 직후 `_internal` 폴더에 파일이 30여 개밖에 없음 (정상: 1,500개 이상).
certifi, templates 등 데이터 파일 전부 누락.

### 근본 원인

`build.bat` 실행 시 `NaverBlogTool.exe`가 **이미 실행 중인 상태**이면:

1. `rmdir /s /q dist\NaverBlogTool` 실행 → exe 파일 잠금으로 **삭제 실패**
2. 실패해도 오류 없이 다음 단계로 넘어감 (기존 dist 잔존)
3. pyinstaller 실행 → 잠긴 파일은 덮어쓰지 못하고 일부만 업데이트
4. 결과: 이전 빌드 + 새 빌드가 **뒤섞인 오염 상태**

### 현재 해결 상태

`build.bat`에 프로세스 강제 종료 및 삭제 실패 감지 추가:

```bat
echo [2/3] Stopping running processes...
taskkill /IM NaverBlogTool.exe /F >nul 2>&1
taskkill /IM NaverBlogTool.exe /T /F >nul 2>&1
timeout /t 1 /nobreak >nul

echo [2/3] Cleaning previous build...
if exist dist\NaverBlogTool rmdir /s /q dist\NaverBlogTool
if exist dist\NaverBlogTool (
  echo [FAIL] Could not delete dist folder. Process may still be running.
  pause
  exit /b 1
)
```

### 재발 방지 규칙

- **항상 `build.bat`으로만 빌드** — 수동으로 `pyinstaller` 직접 실행 금지
- `build.bat`은 실행 중인 프로세스를 자동 종료한 후 빌드 시작

---

## 오류 3: build.bat 파일이 열리지 않음

### 증상

`build.bat` 더블클릭 시 창이 열리지 않거나 즉시 종료됨.

### 근본 원인

bat 파일 내부에 **UTF-8로 인코딩된 한글**이 포함되어 있었음.

Windows cmd는 기본적으로 bat 파일을 **CP949(EUC-KR)** 로 읽음.
UTF-8 한글(3바이트)을 CP949로 읽으면 깨진 문자로 인식되어 파싱 오류 발생.

`chcp 65001` 명령어가 파일 상단에 있어도, cmd가 파일을 파싱한 **이후에** 실행되므로 의미 없음.

```bat
# 문제가 된 라인 (UTF-8 한글)
echo [FAIL] dist 폴더 삭제 실패. 프로세스가 아직 실행 중일 수 있습니다.
```

### 현재 해결 상태

한글을 모두 영문으로 교체 → 순수 ASCII 파일로 유지:

```bat
echo [FAIL] Could not delete dist folder. Process may still be running.
```

### 재발 방지 규칙

- **bat 파일에 한글 절대 사용 금지** — 오류 메시지, 주석 포함 전부 영문으로 작성
- bat 파일 수정 후 반드시 non-ASCII 문자 없는지 확인

---

## 빌드 체크리스트

빌드 전:
- [ ] `NaverBlogTool.exe` 실행 중이면 종료 (build.bat이 자동으로 처리)

빌드 후 자동 검증 (`build.bat` 내장):
- [ ] `dist\NaverBlogTool\NaverBlogTool.exe` 존재
- [ ] `dist\NaverBlogTool\_internal\certifi\cacert.pem` 존재

이상 없으면 자동으로 exe 실행됨.
