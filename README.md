[⬇ **GodiSpeedMeter.exe 다운로드 · ダウンロード · Download**](https://github.com/GD-fandev/GodiSpeedMeter/releases/latest/download/GodiSpeedMeter.exe)

# GodiSpeedMeter

Godius 이동속도를 화면의 좌표로 측정하는 Windows 오버레이입니다. **KOR / JPN / ENG**를 지원합니다.

[최신 릴리스 / Latest release](https://github.com/GD-fandev/GodiSpeedMeter/releases/latest) · [라이선스 안내 / Notices](THIRD_PARTY_NOTICES.md)

## 한국어

1. 위 링크에서 EXE를 받아 쓰기 가능한 폴더에 저장한 후 실행합니다. Python 설치나 별도 모델 다운로드는 필요 없습니다.
2. 게임 화면을 전면에 두고 **Ctrl+F**를 누릅니다. 게임 창과 좌표 위치는 자동으로 인식합니다.
3. X축 또는 Y축 한 방향으로 길게 이동한 뒤 멈추면 **ms/칸**을 표시합니다. 숫자가 작을수록 빠릅니다.

첫 좌표 변화는 기준점으로만 쓰고 마지막 구간은 제외합니다. 남은 시간 합을 이동 칸 수로 나누며, 최소 세 번의 좌표 변화가 필요합니다. 정지 판정 기본값은 700ms입니다.

- 상단을 드래그해 이동하고 오른쪽 아래 손잡이로 크기를 조절합니다.
- OBS 윈도우 캡처에서 **GodiSpeedMeter · Ctrl+F**를 선택하면 방송에 표시할 수 있습니다. 스크린샷에도 표시됩니다. 측정기 창이 게임 좌표 표시를 가리지 않게 배치하세요.
- **기록 초기화**로 기록·전체 평균을 초기화합니다. 전체 평균은 포함된 각 시도의 평균을 동일한 비중으로 계산합니다.
- 기록 행을 더블클릭하면 최대 캡처 간격, 처리 지연, OCR 시간과 검토 사유를 볼 수 있습니다. **선택 포함 / 제외**로 평균 대상을 변경합니다.
- 설정은 EXE 옆 `preferences.json`, 진단 로그는 `logs/`에 저장됩니다. 기록 초기화는 저장된 로그를 삭제하지 않습니다.

좌표 캡처와 OCR은 별도 스레드로 동작하며 캡처 시각으로 시간을 계산합니다. 동일한 숫자 이미지의 인식 결과는 재사용하므로 OCR 실행 횟수가 0이어도 캡처·시간 측정은 계속됩니다.

화면 갱신·캡처·인식 오차가 있으므로 긴 구간을 여러 번 측정하세요. **캡처 간격은 정확도 보증이 아닙니다.** 검토 권고는 참고 정보이며 자동 제외하거나 원인을 확정하지 않습니다. 장비·조건이 달라지면 기록을 초기화하세요.

## 日本語

上のリンクからEXEをダウンロードし、書き込み可能なフォルダーで実行してください。Pythonや別途OCRモデルのインストールは不要です。

ゲームを最前面にして **Ctrl+F** → 一方向に長めに移動 → 停止すると **ms/マス** を表示します。小さいほど高速です。座標範囲の設定は不要です。

最初の座標変化を基準にし、最後の区間を除外します。全体平均は対象となる各試行の平均値の算術平均です。履歴のダブルクリックで診断と推奨理由を確認でき、「選択を含む / 除外」で対象を変更できます。

上部ドラッグで移動、右下でサイズ変更できます。設定はEXEの隣、ログは `logs/` に保存します。履歴クリアで保存済みログは削除されません。

OBSのウィンドウキャプチャで **GodiSpeedMeter · Ctrl+F** を選択すると配信に表示できます。スクリーンショットにも表示されます。ゲームの座標表示を測定ウィンドウで隠さないようにしてください。

同一の数字画像ではOCR結果を再利用しますが、取得時刻は毎回新しく記録します。画面更新や認識の誤差があるため複数回測定してください。装備・条件を変更したら履歴をクリアしてください。

## English

Download the EXE using the link above and run it from a writable folder. Python and a separate model download are not required.

Bring Godius to the foreground, press **Ctrl+F**, move along one axis, then stop. Coordinates are detected automatically. The result is **ms/tile**; lower means faster.

The first coordinate change sets the baseline and the last interval is excluded. The overall mean equally weights included run averages. Double-click a history row for capture/OCR diagnostics and review suggestions; use **Include / Exclude selected** to change the mean's inputs.

Drag the header to move, and the bottom-right handle to resize. Settings are saved beside the EXE and diagnostic logs in `logs/`. Clearing history does not delete saved logs.

Select **GodiSpeedMeter · Ctrl+F** in OBS Window Capture to show the meter on stream. The meter also appears in screenshots. Keep its window clear of the game's coordinate display.

Capture and OCR run independently. Recognized number images are cached, but timestamps are always captured anew. Display refresh and recognition can introduce error. Use longer repeated runs, and clear history when equipment or conditions change. Review suggestions do not prove the cause of an unusual result or automatically exclude it.

## Run from source / Build

Windows x64, Python 3.12 recommended:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python app.py
```

Build a self-contained EXE:

```powershell
.\.venv\Scripts\python -m pip install pyinstaller==6.22.2
powershell -ExecutionPolicy Bypass -File build.ps1
```

Output: `dist/GodiSpeedMeter.exe`.

Optional packaged smoke check (requires an interactive Windows desktop):

```powershell
.\dist\GodiSpeedMeter.exe --self-test "$PWD\self-test.json"
```

The source repository contains runtime code, the required English OCR model, HUD reference assets, and build/license files. Executables are distributed through GitHub Releases.
