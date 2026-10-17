#!/bin/bash
# 지인 배포용 macOS 앱 빌드 (Apple Silicon 전용). 결과: dist/FileManager.zip
set -e
cd "$(dirname "$0")"
python3 -m venv .buildenv
.buildenv/bin/pip install -q pyinstaller
rm -rf build dist
.buildenv/bin/pyinstaller --noconfirm --windowed --name "FileManager" \
  --osx-bundle-identifier com.local.filemanager \
  --add-data "index.html:." server.py
A="dist/FileManager.app"
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string 파일 관리" "$A/Contents/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :NSHumanReadableCopyright string 개인용 테스트 버전" "$A/Contents/Info.plist" 2>/dev/null || true   # 임시(ad-hoc) 서명: 안쪽(dylib·so)부터 서명한 뒤 번들 전체를 서명하고 검증
find "$A/Contents" \( -name "*.dylib" -o -name "*.so" \) -type f -print0 | xargs -0 -n20 codesign --force -s - 2>/dev/null
codesign --force -s - "$A"
codesign --verify --deep --strict "$A" && echo "서명 검증 OK"
ditto -c -k --keepParent "dist/FileManager.app" "dist/FileManager.zip"
rm -rf build "FileManager.spec" .buildenv
ls -lh dist
