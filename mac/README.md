# virtual-face-cam macOS app

macOS 전용 Virtual Face Cam 앱입니다. Tkinter를 쓰지 않고 로컬 브라우저 UI로
이미지를 업로드한 뒤 OBS Virtual Camera로 송출합니다.

## 필요한 것

1. macOS
2. Python 3.10 이상
3. OBS Studio 30 이상

OBS는 한 번 실행해서 **Start Virtual Camera**를 눌러 macOS 시스템 확장을
등록해야 합니다. 시스템 설정 > 개인정보 보호 및 보안에서 확장을 허용한 뒤
재부팅이 필요할 수 있습니다.

## 실행

원본 저장소의 `mac/` 폴더에서 둘 중 하나를 실행하세요.

```bash
cd mac
./run-mac.command
```

또는 Finder에서 `mac/Virtual Face Cam.app`을 더블클릭합니다.

처음 실행하면 `~/Library/Application Support/VirtualFaceCamMac/.venv`에
필요한 Python 패키지를 설치합니다. 이후에는 로컬 브라우저가 열리고,
이미지를 업로드한 뒤 **Start**를 누르면 다른 앱의 카메라 목록에서
`OBS Virtual Camera`를 선택할 수 있습니다.

## 앱 번들 갱신

소스 파일을 수정한 뒤 앱 번들 안의 리소스를 갱신하려면:

```bash
./scripts/build_app.sh
```

## 문제 해결

- `OBS Virtual Camera is not installed`가 나오면 OBS Studio를 실행해서
  Start Virtual Camera를 한 번 누르고 macOS 시스템 확장을 허용하세요.
- 카메라 목록에 보이지 않으면 Zoom, Teams, 브라우저 같은 대상 앱을 완전히
  종료한 뒤 다시 실행하세요.
- Python을 못 찾으면 python.org의 macOS installer를 설치하거나
  `brew install python`을 실행하세요.

## License

MIT
