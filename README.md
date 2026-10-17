# 파일 관리 (File Manager)

로컬 파일 정리 도구: 중복 파일 · 큰 파일 · 빈 폴더/0바이트 · 종류·월별 자동 정리 · 일괄 이름 바꾸기 · 기록과 되돌리기. 파이썬 표준 라이브러리만 사용하며 브라우저 화면으로 조작합니다.

> ⚠️ **파일을 옮기거나 휴지통으로 보내는 도구입니다.** 영구 삭제는 하지 않고(Windows·Android의 [휴지통 비우기] 제외) 모든 작업을 기록하지만, 사용 책임은 본인에게 있습니다. 처음에는 작은 폴더에서 시험하세요. 개인용 테스트 버전이며 어떤 보증도 없습니다.

## 설치·실행 (macOS · Windows · Linux · Android)

모든 OS 공통: **127.0.0.1(내 기기) 안에서만** 서버가 열리고 브라우저로 조작합니다. 파일 정보는 밖으로 나가지 않습니다.
화면 위쪽 **[종료]** 버튼으로 끕니다.

| OS | 방법 | 상태 |
|---|---|---|
| macOS (Apple Silicon) | `FileManager.zip` 압축 해제 → 앱 우클릭 → 열기 | 만든 Mac에서 확인 |
| 모든 OS (Python 3.8+) | `python3 filemanager.py --open` (단일 파일) | macOS에서 확인, 다른 OS 미확인 |
| Windows | `run.bat` 더블클릭 또는 `py -3 filemanager.py --open` | **미확인** |
| Linux | `./run.sh` 또는 `python3 filemanager.py --open` | **미확인** |
| Android | Termux에서 아래 절차 | **미확인(기기 테스트 필요)** |

## 휴지통 방식 (OS별)
- macOS: `~/.Trash` · Linux: 표준 휴지통(`~/.local/share/Trash`, 파일 관리자에서도 복원 가능)
- Windows · Android: **앱 전용 휴지통**(`.FileManager-Trash`, 각 루트 폴더 안). 공간을 실제로 늘리려면 화면 위의 **[휴지통 비우기]**(영구 삭제, 확인창 있음)를 누르세요.
- 어디서나 [기록·되돌리기] 탭에서 되돌릴 수 있습니다.

## Windows
1. python.org 에서 Python 3 설치(설치 때 "Add python.exe to PATH" 체크).
2. `filemanager.py`(또는 `server.py`+`index.html`)를 한 폴더에 두고 `run.bat` 더블클릭 / `py -3 filemanager.py --open`.
3. 다룰 수 있는 범위: 내 사용자 폴더(`C:\Users\이름`). `AppData`는 보호됩니다.

## Linux
`python3 filemanager.py --open` (브라우저가 자동으로 열리지 않으면 출력된 주소를 직접 여세요).

## Android (Termux)
1. **F-Droid 또는 GitHub**에서 Termux 설치(Play 스토어 버전은 오래되어 권장하지 않음).
2. Termux에서:
   ```
   pkg update && pkg install python
   termux-setup-storage        # 저장소 접근 허용 팝업 → 허용
   ```
3. `filemanager.py` 를 폰에 복사(예: 다운로드 폴더)한 뒤:
   ```
   cp ~/storage/downloads/filemanager.py ~ && python filemanager.py
   ```
4. 크롬에서 `http://127.0.0.1:8056/` 접속. 폴더 선택 창의 사이드바에 **내장 저장소(/storage/emulated/0)** 가 나옵니다.
5. 한계: Android 11 이후 `Android/data` 등 일부 폴더는 접근 불가, SD 카드·USB는 안 될 수 있음. 이 경로는 실제 기기에서 시험하지 않았습니다.

## 공통 주의
- 중복 파일은 그룹마다 하나는 남겨야 삭제할 수 있습니다.
- 클라우드 동기화 폴더(iCloud·OneDrive 등)에서 지우면 다른 기기에도 반영됩니다.
- 작업 기록 위치: macOS `~/Library/Application Support/파일관리`, Windows `%APPDATA%\FileManager`, Linux/Android `~/.local/share/FileManager`.

## 개발
- `server.py`(서버) + `index.html`(화면). 실행: `python3 server.py --open`
- `build_single.py` → `dist/filemanager.py`(단일 파일), `build_app.sh` → macOS 앱(Apple Silicon), `.github/workflows/build.yml` → OS별 빌드(수동 실행)
- 설계 근거와 벤치마크: `BENCHMARK.md`, 작업 규칙: `CLAUDE.md`
