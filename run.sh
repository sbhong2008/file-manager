#!/bin/sh
# Linux · macOS · Android(Termux) 공용 실행 스크립트
cd "$(dirname "$0")" && exec python3 server.py --open
