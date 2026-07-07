# Virtual Face Cam for Mac

Mac에서 이미지나 이미지 폴더를 `OBS Virtual Camera`로 보내는 앱입니다.
Tkinter를 쓰지 않고 브라우저 화면으로 조작합니다.

## 실행 화면

![Virtual Face Cam browser UI](../docs/mac-browser-ui.png)

## 제일 쉬운 순서

### 1. OBS Studio 먼저 설치

1. https://obsproject.com/ 에서 OBS Studio를 설치합니다.
2. OBS를 한 번 실행합니다.
3. **Start Virtual Camera**를 한 번 눌러 macOS 카메라 확장을 등록합니다.
4. macOS가 시스템 확장 허용을 물어보면 허용합니다.
5. 필요하면 Mac을 재시동합니다.

등록이 끝난 뒤에는 OBS 창을 계속 켜둘 필요가 없습니다. 실제 송출 시작은 이 앱의
**Start** 버튼으로 합니다.

### 2. 앱 실행

Finder에서 `Virtual Face Cam.app`을 오른쪽 클릭한 뒤 **열기**를 누르세요.

이 앱은 별도 Mac 앱 창 대신 브라우저 조작 화면을 엽니다. Dock에 앱 창이 안 떠도
브라우저 탭이 열리면 정상입니다.

터미널에서 실행하려면:

```bash
./run-mac.command
```

처음 실행할 때 필요한 Python 패키지를 자동 설치합니다.

### 3. 사용

앱을 처음 열면 기본 이미지가 미리 준비되어 있습니다.

1. 기본 이미지를 그대로 쓰려면 바로 **Start**를 누릅니다.
2. 다른 이미지를 쓰려면 이미지 또는 폴더를 선택합니다.
3. **Upload**를 누릅니다.
4. **Start**를 누릅니다.
5. Zoom, Teams, Chrome 같은 앱에서 `OBS Virtual Camera`를 선택합니다.

브라우저 탭을 닫으면 몇 초 뒤 앱 서버도 자동으로 종료됩니다. 바로 끝내고 싶으면
화면의 **Quit App**을 누르세요.

## OBS 없이 앱 자체만으로 쓰고 싶다면

OBS Virtual Camera 없이 앱 자체가 macOS 카메라 장치로 보이게 하려면 아래
네이티브 macOS 프로젝트를 보세요.

https://github.com/TaeHuiKKIM/virtual-face-cam-mac

이 방식은 Swift + CoreMediaIO Camera Extension 기반이라 Apple Developer Team,
App Group, macOS System Extension 승인이 필요합니다.

## 문제 해결

- 앱이 안 열리면 더블클릭 대신 오른쪽 클릭 > **열기**를 사용하세요.
- 오른쪽 클릭 > **열기**에도 아무 일도 안 일어나면 `run-mac.command`를 더블클릭하세요.
- 그래도 안 열리면 `~/Library/Application Support/VirtualFaceCamMac/launch.log`를 확인하세요.
- `OBS Virtual Camera is not installed`가 나오면 OBS에서 **Start Virtual Camera**를 한 번 누르세요.
- 앱 상태가 `Live`로 바뀌면 우리 앱은 OBS Virtual Camera에 프레임을 보내고 있는 상태입니다.
- 다른 앱에 카메라가 안 보이면 그 앱을 완전히 종료했다가 다시 켜세요.
- Chrome에서 카메라가 안 보이면 주소창에 `chrome://restart`를 입력해서 Chrome을 완전히 재시작하세요.
- 그래도 안 보이면 Mac을 재시동하세요.

## 앱 번들 갱신

소스 파일을 수정한 뒤 앱 번들 안의 파일을 다시 채우려면:

```bash
./scripts/build_app.sh
```
