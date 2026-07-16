# Virtual Face Cam

사진 한 장, 사진 폴더 또는 영상 한 개를 **가상 웹캠**으로 내보내는 앱입니다.
Zoom, Teams, Chrome 같은 앱에서 카메라를 고를 때 `OBS Virtual Camera`를 선택하면
내가 고른 사진이나 반복 영상이 웹캠 화면처럼 보입니다. 영상은 끝까지 재생되면
자동으로 처음부터 다시 시작합니다.

## 실행 화면

![Virtual Face Cam macOS browser UI](docs/mac-browser-ui.png)

## OBS 없이 Mac 앱 자체만으로 쓰고 싶다면

OBS Virtual Camera를 설치하지 않고 `Virtual Face Cam`이 macOS 카메라 목록에 직접
나오게 만드는 네이티브 Mac 버전은 아래 저장소를 보세요.

https://github.com/TaeHuiKKIM/virtual-face-cam-mac

이 방식은 Apple Developer Team, App Group, macOS System Extension 승인이 필요합니다.

## Mac에서 가장 쉬운 사용법

### 1. OBS Studio 설치

1. https://obsproject.com/ 에 들어갑니다.
2. macOS용 OBS Studio를 설치합니다.
3. OBS를 한 번 실행합니다.
4. OBS에서 **Start Virtual Camera**를 한 번 누릅니다.
5. macOS가 시스템 확장 허용을 물어보면 허용합니다.
6. 필요하다고 나오면 Mac을 재시동합니다.

OBS는 가상 카메라 드라이버를 등록하기 위해 필요합니다.
드라이버 등록 후에는 Virtual Face Cam을 쓸 때 OBS 창을 계속 켜둘 필요는 없습니다.
OBS 안의 **Start Virtual Camera**는 등록 확인용입니다. 실제 미디어 송출은 아래에서
Virtual Face Cam 앱의 **Start Live** 버튼으로 시작하세요.

### 2. 이 저장소 다운로드

1. 이 GitHub 페이지의 초록색 **Code** 버튼을 누릅니다.
2. **Download ZIP**을 누릅니다.
3. 받은 ZIP 파일을 압축 해제합니다.
4. 압축을 푼 폴더에서 `mac` 폴더를 엽니다.

### 3. 앱 실행

1. `Virtual Face Cam.app`을 오른쪽 클릭합니다.
2. **열기**를 누릅니다.
3. 경고창이 나오면 다시 **열기**를 누릅니다.
4. 브라우저 창이 열릴 때까지 기다립니다.

이 앱은 별도 Mac 앱 창이 뜨는 방식이 아니라, 뒤에서 작은 서버를 켜고 브라우저
조작 화면을 여는 방식입니다. Dock에서 앱 창이 안 보이더라도 브라우저 탭이 열리면
정상입니다.

처음 실행할 때 필요한 Python 패키지를 자동으로 설치합니다. 네트워크 상태에 따라
조금 걸릴 수 있습니다. 영상 기능에 필요한 패키지가 추가되어 첫 실행은 이전 버전보다
조금 더 오래 걸릴 수 있지만, 두 번째 실행부터는 다시 설치하지 않습니다.

터미널에서 실행하고 싶으면:

```bash
cd mac
./run-mac.command
```

### 4. 사진 또는 영상 보내기

앱을 처음 열면 기본 이미지가 미리 준비되어 있습니다. 그대로 써도 되고, 원하는
사진이나 영상으로 바꾸려면 아래 순서대로 진행하세요.

1. 브라우저 창에서 **Photos / Video** 또는 **Folder**를 누릅니다.
2. 사진은 여러 장을 선택할 수 있고, 영상은 한 번에 한 개만 선택할 수 있습니다.
3. 영상과 사진을 동시에 선택하지 마세요.
4. **Upload**를 누릅니다. 다음 실행을 위해 앱 전용 폴더에도 저장됩니다.
5. **Start Live**를 누릅니다.
6. Zoom, Teams, Chrome 같은 앱을 엽니다.
7. 카메라 선택에서 `OBS Virtual Camera`를 고릅니다.

영상은 별도 설정 없이 무한 반복됩니다. 사진 폴더를 선택한 경우에는 **Photo interval**에
적힌 초마다 다음 사진으로 넘어갑니다.

다음에 앱을 다시 열면 마지막으로 업로드했던 사진이나 영상이 자동으로 준비되어
있습니다. 파일 선택과 Upload를 다시 할 필요 없이 **Start Live**만 누르면 됩니다.

Live 상태에서는 브라우저 탭을 닫아도 송출이 계속됩니다. 얼굴인식이나 화상회의 중에는
탭을 닫아도 괜찮지만, 끝낼 때는 반드시 **Stop Live** 또는 **Quit App**을 누르세요.

Live가 아닌 상태에서 브라우저 탭을 닫으면 몇 초 뒤 앱 서버가 자동으로 종료됩니다.

## Windows에서 가장 쉬운 사용법

1. https://obsproject.com/ 에서 Windows용 OBS Studio를 설치합니다.
2. OBS를 한 번 실행해서 가상 카메라 기능을 준비합니다.
3. https://www.python.org/downloads/ 에서 Python을 설치합니다.
4. Python 설치 화면에서 **Add Python to PATH**를 꼭 체크합니다.
5. 이 저장소를 **Code > Download ZIP**으로 다운로드하고 압축 해제합니다.
6. `실행_Windows.bat`을 더블클릭합니다.
7. **사진 / 영상 선택**에서 사진 또는 영상 한 개를 고르거나, **폴더 선택**에서 사진 폴더를 고릅니다.
8. **시작**을 누릅니다. 영상은 끝나면 자동으로 처음부터 반복됩니다.
9. 다음 실행부터는 마지막으로 선택했던 파일이나 폴더가 자동으로 다시 선택됩니다.
10. 사용할 앱에서 `OBS Virtual Camera`를 선택합니다.

## 지원하는 파일과 최근 항목 저장

- 사진: JPG, JPEG, PNG, BMP, WebP
- 영상: MP4, MOV, M4V, AVI, MKV, WebM
- 가장 호환성이 좋은 영상: MP4 + H.264
- 사진은 여러 장 또는 폴더를 사용할 수 있습니다.
- 영상은 한 번에 한 개만 사용할 수 있으며 자동으로 무한 반복됩니다.

Mac은 브라우저 보안 때문에 원본 Finder 경로를 직접 읽을 수 없습니다. Upload를 누르면
파일 복사본을 아래 앱 전용 폴더에 저장하고, 그 경로를 기억합니다.

```text
~/Library/Application Support/VirtualFaceCamMac/
```

Windows는 선택한 원본 파일 또는 폴더 경로를 아래 설정 파일에 기억합니다.

```text
%APPDATA%\VirtualFaceCam\settings.json
```

Windows에서 원본 파일을 옮기거나 삭제하면 다음 실행 때 기본 이미지로 돌아갑니다.
Mac에서 앱 전용 저장 폴더를 직접 지우면 저장한 미디어가 사라질 수 있습니다.

## Linux 사용법

Linux에서는 `v4l2loopback`이 필요합니다.

```bash
sudo apt install v4l2loopback-dkms
sudo modprobe v4l2loopback
python3 -m pip install -r requirements.txt
python3 virtual_cam.py face.jpg
```

## 자주 막히는 부분

### 카메라 목록에 안 보여요

1. OBS Studio를 설치했는지 확인합니다.
2. OBS에서 **Start Virtual Camera**를 한 번 눌렀는지 확인합니다.
3. Mac에서는 시스템 설정 > 일반 > 로그인 항목 및 확장 프로그램 > 카메라 확장에서 OBS Virtual Camera가 켜져 있는지 확인합니다.
4. Virtual Face Cam 앱에서 **Start**를 눌러 상태가 `Live`로 바뀌었는지 확인합니다.
5. Zoom, Teams, Chrome을 완전히 종료했다가 다시 켭니다.
6. 그래도 안 되면 Mac을 한 번 재시동합니다.

Chrome은 카메라 목록을 오래 캐시하는 경우가 있습니다. Chrome에서 안 보이면 주소창에
아래를 입력해서 Chrome을 완전히 재시작하세요.

```text
chrome://restart
```

그 다음 카메라 목록에서 `OBS Virtual Camera`를 다시 선택하세요.

### Mac에서 앱이 안 열려요

처음 실행할 때는 더블클릭 대신 오른쪽 클릭 후 **열기**를 사용하세요.
macOS Gatekeeper 때문에 처음 한 번은 이 과정이 필요할 수 있습니다.

오른쪽 클릭 후 **열기**를 눌러도 아무 일도 안 일어나면 `mac/run-mac.command`를
더블클릭하세요. 그래도 실패하면 아래 로그 파일을 확인하면 원인을 볼 수 있습니다.

```text
~/Library/Application Support/VirtualFaceCamMac/launch.log
```

### Mac에서 Python 오류가 나요

`mac/Virtual Face Cam.app` 또는 `mac/run-mac.command`를 쓰는 것을 권장합니다.
기존 `실행_Mac.command`는 Tkinter가 필요해서 Homebrew Python 환경에서는
`No module named '_tkinter'` 오류가 날 수 있습니다.

### 영상이 선택되지 않거나 재생되지 않아요

1. 영상은 한 번에 한 개만 선택하세요. 사진과 영상을 같이 고르면 업로드되지 않습니다.
2. MP4 + H.264 형식으로 변환해서 다시 시도하세요. 같은 확장자라도 내부 코덱에 따라 열리지 않을 수 있습니다.
3. 영상 파일이 300MB보다 크면 Mac 브라우저 버전에서 업로드되지 않습니다.
4. 앱을 완전히 종료한 뒤 다시 열고 영상을 다시 Upload 해보세요.

## 개발자용 실행

Python 3.10 이상이 필요합니다.

```bash
python3 -m pip install -r requirements.txt
python3 virtual_cam.py assets/default_face.jpg
python3 virtual_cam.py my-video.mp4
```

GUI:

```bash
python3 gui.py
```

macOS 브라우저 UI:

```bash
cd mac
./run-mac.command
```

테스트:

```bash
python3 -m unittest discover -s tests -v
```

`mac/mac_virtual_face_cam.py`, `mac/requirements.txt`, `mac/scripts/launch.sh`를 수정한 뒤에는
`./mac/scripts/build_app.sh`를 실행해 저장소의 `Virtual Face Cam.app` 번들도 갱신하세요.

## 옵션

```bash
python3 virtual_cam.py face.jpg --width 1280 --height 720 --fps 30
python3 virtual_cam.py ./images --interval 5
python3 virtual_cam.py ./video.mp4 --width 1280 --height 720 --fps 30
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--width` | 1280 | 출력 가로 해상도 |
| `--height` | 720 | 출력 세로 해상도 |
| `--fps` | 30 | 프레임레이트 |
| `--interval` | 3.0 | 사진 폴더를 쓸 때 사진이 바뀌는 간격. 영상에는 적용되지 않음 |

## 주의

이 도구는 개발 테스트, 데모, 화상회의용 정적 화면 같은 정당한 용도를 위한 것입니다.
타인의 신원 인증, 화상 시험 감독, 얼굴 로그인 같은 절차를 우회하는 데 사용하지 마세요.

## 라이선스

MIT
