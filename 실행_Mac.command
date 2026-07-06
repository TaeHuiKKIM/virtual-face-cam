#!/bin/bash
# 더블클릭 실행용 (최초 1회: 우클릭 > 열기 로 Gatekeeper 허용 필요할 수 있음)
cd "$(dirname "$0")"

echo "Virtual Face Cam 준비 중..."

# Python 확인
if ! command -v python3 >/dev/null 2>&1; then
    echo ""
    echo "[오류] python3가 설치되어 있지 않습니다."
    echo "https://www.python.org/downloads/ 또는 'brew install python' 으로 설치 후 다시 실행하세요."
    echo ""
    read -n 1 -s -r -p "아무 키나 누르면 종료합니다..."
    exit 1
fi

# 의존성 확인 후 필요 시 설치
if ! python3 -c "import pyvirtualcam, cv2, numpy, PIL" >/dev/null 2>&1; then
    echo "필요한 패키지를 설치합니다. 잠시만 기다려 주세요..."
    python3 -m pip install -r requirements.txt
fi

python3 gui.py
