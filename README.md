# QR Scanner

다른 QR 스캐너 프로그램 설치하기 귀찮아서 그냥 만들었습니다.

PC에서 스크린샷 찍고 `Ctrl+V` 하면 바로 QR 코드 정보를 보여주는 Windows 데스크톱 프로그램입니다.

## 사용법

1. `QR Scanner.exe` 실행
2. QR 코드가 보이는 화면에서 `Win+Shift+S`로 캡처
3. 프로그램에서 `Ctrl+V`
4. 결과 확인 — URL이면 클릭해서 바로 열기 가능

## 기능

- 클립보드 이미지에서 QR 코드 자동 인식
- URL 자동 감지 및 브라우저 열기
- 결과 클립보드 복사
- 다중 QR 코드 동시 인식
- 스캔 애니메이션

## 빌드

```bash
pip install pillow opencv-python numpy pyinstaller
python -m PyInstaller --onefile --windowed --name "QR Scanner" --icon=icon.ico --add-data "icon.ico;." qr_reader.py
```

## 기술 스택

- Python + tkinter
- OpenCV (QR 디코딩)
- Pillow (클립보드 이미지)
