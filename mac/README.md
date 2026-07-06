# Virtual Face Cam for Mac

Mac에서 이미지나 이미지 폴더를 `OBS Virtual Camera`로 보내는 앱입니다.
Tkinter를 쓰지 않고 브라우저 화면으로 조작합니다.

## 제일 쉬운 순서

### 1. OBS Studio 먼저 설치

1. https://obsproject.com/ 에서 OBS Studio를 설치합니다.
2. OBS를 한 번 실행합니다.
3. **Start Virtual Camera**를 한 번 누릅니다.
4. macOS가 시스템 확장 허용을 물어보면 허용합니다.
5. 필요하면 Mac을 재시동합니다.

### 2. 앱 실행

Finder에서 `Virtual Face Cam.app`을 오른쪽 클릭한 뒤 **열기**를 누르세요.

터미널에서 실행하려면:

```bash
./run-mac.command
```

처음 실행할 때 필요한 Python 패키지를 자동 설치합니다.

### 3. 사용

1. 브라우저가 열리면 이미지 또는 폴더를 선택합니다.
2. **Upload**를 누릅니다.
3. **Start**를 누릅니다.
4. Zoom, Teams, Chrome 같은 앱에서 `OBS Virtual Camera`를 선택합니다.

## OBS 없이 쓰고 싶다면

카메라 장치로 보일 필요가 없고, 이미지를 화면에 띄우거나 슬라이드쇼로 보여주기만
하면 된다면 아래 앱이 더 단순합니다.

https://github.com/TaeHuiKKIM/virtual-face-cam-mac

## 문제 해결

- 앱이 안 열리면 더블클릭 대신 오른쪽 클릭 > **열기**를 사용하세요.
- `OBS Virtual Camera is not installed`가 나오면 OBS에서 **Start Virtual Camera**를 한 번 누르세요.
- 다른 앱에 카메라가 안 보이면 그 앱을 완전히 종료했다가 다시 켜세요.
- 그래도 안 보이면 Mac을 재시동하세요.

## 앱 번들 갱신

소스 파일을 수정한 뒤 앱 번들 안의 파일을 다시 채우려면:

```bash
./scripts/build_app.sh
```
