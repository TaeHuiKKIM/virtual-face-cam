# Virtual Face Cam for Mac

Mac에서 사진, 사진 폴더 또는 반복 영상을 `OBS Virtual Camera`로 보내는 앱입니다.
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
**Start Live** 버튼으로 합니다.

### 2. 앱 실행

Finder에서 `Virtual Face Cam.app`을 오른쪽 클릭한 뒤 **열기**를 누르세요.

이 앱은 별도 Mac 앱 창 대신 브라우저 조작 화면을 엽니다. Dock에 앱 창이 안 떠도
브라우저 탭이 열리면 정상입니다.

터미널에서 실행하려면:

```bash
./run-mac.command
```

처음 실행할 때 필요한 Python 패키지를 자동 설치합니다. 영상 패키지까지 설치하므로
첫 실행은 조금 오래 걸릴 수 있지만, 다음 실행부터는 다시 설치하지 않습니다.

### 3. 사용

앱을 처음 열면 기본 이미지가 미리 준비되어 있습니다.

1. 기본 이미지를 그대로 쓰려면 바로 **Start Live**를 누릅니다.
2. 다른 소스를 쓰려면 **Photos / Video**에서 사진이나 영상 한 개를 선택하거나 **Folder**에서 사진 폴더를 선택합니다.
3. 사진은 여러 장을 선택할 수 있지만 영상은 한 번에 한 개만 선택하세요.
4. **Upload**를 누릅니다.
5. **Start Live**를 누릅니다.
6. Zoom, Teams, Chrome 같은 앱에서 `OBS Virtual Camera`를 선택합니다.

파일을 선택한 직후 보이는 화면은 브라우저 미리보기입니다. 실제 가상카메라에
적용하려면 반드시 **Upload**를 한 번 눌러야 합니다. 선택만 한 상태에서는
**Start Live**가 비활성화됩니다.

영상은 끝까지 재생되면 자동으로 처음부터 무한 반복됩니다. 사진 폴더는
**Photo interval**에 적힌 초마다 다음 사진으로 넘어갑니다.

Upload한 파일은 `~/Library/Application Support/VirtualFaceCamMac/uploads`에 복사되고
마지막 경로가 저장됩니다. 다음 실행 때 최근 사진이나 영상이 자동으로 준비되므로
다시 선택하지 않고 **Start Live**만 누르면 됩니다.

Live 상태에서는 브라우저 탭을 닫아도 미디어 송출이 계속됩니다. 얼굴인식이나
화상회의 중에는 탭을 닫아도 괜찮지만, 끝낼 때는 반드시 **Stop Live** 또는
**Quit App**을 누르세요.

Live가 아닌 상태에서 브라우저 탭을 닫으면 몇 초 뒤 앱 서버가 자동으로 종료됩니다.

## 지원 형식

- 사진: JPG, JPEG, PNG, BMP, WebP
- 영상: MP4, MOV, M4V, AVI, MKV, WebM
- 권장 영상: MP4 + H.264
- Mac 브라우저 업로드 한도: 300MB

영상 확장자가 지원 목록에 있어도 내부 코덱을 읽을 수 없으면 업로드가 거절될 수
있습니다. 이때는 MP4 + H.264로 변환하면 호환성이 가장 좋습니다.

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
- 영상이 업로드되지 않으면 사진과 영상을 같이 선택하지 않았는지 확인하고, MP4 + H.264 파일로 다시 시도하세요.

## 앱 번들 갱신

소스 파일을 수정한 뒤 앱 번들 안의 파일을 다시 채우려면:

```bash
./scripts/build_app.sh
```
