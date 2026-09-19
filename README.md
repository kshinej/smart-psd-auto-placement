친구가 원해서 바이브코딩 해봤습니다.

# AI PSD 상품 상세페이지 자동 배치 도구 (ai-pds)

`ai-pds`는 온라인 쇼핑몰 상품 상세페이지 제작 시 다단 레이어 PSD 템플릿에 **상품명/상품코드 텍스트** 및 **상품 사진들**을 자동으로 교체하고 배치해주는 Python 기반 데스크톱 자동화 프로그램입니다.

Adobe Photoshop COM API 연동을 통해 원본 PSD의 레이어 위치, 마스크, 스마트 오브젝트(Smart Object) 구조를 보존하면서 정밀하게 교체 작업을 수행하며, **Ollama Vision AI**를 활용하여 상품 사진(메인컷, 모델 착용컷, 상세 상세컷 등)을 자동으로 분류하여 레이어 슬롯에 매칭합니다.

---

## 🌟 주요 기능

- **PSD 레이어 구조 재귀 분석**: 템플릿 내 텍스트, 일반 이미지, 스마트 오브젝트 레이어 정보를 추출하여 분석 데이터(`layer_analysis.json`)를 생성합니다.
- **자동 이미지 & 텍스트 교체**:
  - 상품명(`product_name`), 상품코드(`product_code`) 텍스트 자동 변경.
  - 메인 이미지 전용 직통 배치 (`--main-image`) 및 상세 이미지 자동 슬롯 배치.
  - 스마트 오브젝트 및 일반 이미지 레이어 교체 지원.
  - 이미지 비율 처리 모드 지원 (`crop`, `fit`, `stretch`).
- **Ollama Vision AI 이미지 자동 분류**:
  - 썸네일을 자동 생성(`thumb/`)하여 로컬 Vision LLM (예: `qwen3-vl:4b`)을 통해 이미지 특성을 분석.
  - 메인 상품컷(`winner/`), 모델 착용컷, 상세 컷 등을 자동 분류하여 PSD 내 적절한 슬롯에 배치.
- **GUI 및 CLI 모드 동시 지원**:
  - 직관적인 Tkinter 데스크톱 GUI 화면 제공.
  - 대량 처리 및 스크립트 연동을 위한 다양한 CLI 명령어 지원.

---

## 🛠️ 시스템 요구 사항

- **운영체제**: Windows 10 / 11 (Photoshop COM 연동 필수)
- **Python**: Python 3.10 이상
- **Adobe Photoshop**: Photoshop CS6 / CC 이상 설치 필수
- **(선택 사항) Ollama**: Vision AI 이미지 자동 분류 기능 사용 시 필요 (`qwen3-vl:4b` 등 Vision 모델 필요)

---

## 📦 설치 방법

1. **저장소 클론 또는 다운로드**
   ```bash
   git clone https://github.com/your-repo/ai-pds.git
   cd ai-pds
   ```

2. **필수 의존성 패키지 설치**
   ```bash
   pip install -r requirements.txt
   ```

---

## 🚀 사용 방법

### 1. GUI 모드 (권장)

다음 명령어를 실행하거나 파라미터 없이 실행하면 Tkinter GUI 화면이 열립니다.

```bash
python main.py
# 또는
python main.py --gui
```

GUI 화면에서 PSD 파일 선택, 메인/상세 이미지 디렉토리 선택, 상품명/코드 입력 후 **[작업 시작]** 버튼을 눌러 손쉽게 진행할 수 있습니다.

### 2. CLI 모드

터미널/명령 프롬프트에서 파라미터를 지정하여 작업을 자동화할 수 있습니다.

#### 기본 실행 예시
```bash
python main.py --psd input/sample.psd --text "프리미엄 무선 이어폰" --code "EAR-2026-PRO" --img-dir input/images
```

#### Vision AI 자동 분류 옵션 적용
```bash
python main.py --psd input/sample.psd --text "프리미엄 무선 이어폰" --code "EAR-2026-PRO" --img-dir input/images --use-ai --ai-model qwen3-vl:4b
```

#### CLI 명령어 옵션 안내

| 파라미터 | 설명 | 기본값 |
| :--- | :--- | :--- |
| `--gui` | Tkinter GUI 화면 실행 | `False` |
| `--psd <경로>` | 분석 및 처리할 PSD 템플릿 파일 경로 | 자동 탐색 (`*.psd`) |
| `--text <텍스트>` | 새로 변경할 상품명 | `None` |
| `--code <코드>` | 새로 변경할 상품코드 | `None` |
| `--img-dir <경로>` | 교체할 이미지들이 있는 디렉토리 경로 | `None` |
| `--images <파일목록>` | 교체할 이미지 파일 목록 지정 (예: `--images 01.jpg 02.jpg`) | `None` |
| `--main-image <경로>` | `product01` 슬롯에 직통 배치할 메인 이미지 경로 | `None` |
| `--image-mode` | 이미지 비율 가공 모드 (`crop`, `fit`, `stretch`) | `crop` |
| `--use-ai` | Ollama Vision AI 이미지 자동 분류 사용 | `False` |
| `--ai-model <모델명>` | Ollama Vision AI 모델 이름 | `qwen3-vl:4b` |
| `--config <경로>` | 템플릿 레이어 매핑 설정 파일 경로 | `config/template.json` |
| `--output <경로>` | 저장할 결과 PSD 파일 경로 또는 디렉토리 | `output/` |

---

## ⚙️ 설정 파일 (`config/template.json`)

PSD 템플릿 내 레이어 이름과 매핑 방식을 설정합니다.

```json
{
    "template_name": "기본 상세페이지 템플릿",
    "text": {
        "product_name": "product name",
        "product_code": "product code"
    },
    "images": {
        "main": "메인상품",
        "detail_01": "이미지01",
        "detail_02": "이미지02",
        "detail_03": "이미지03"
    },
    "image_mode": "crop"
}
```

---

## 📁 프로젝트 구조

```text
ai-pds/
├── main.py                  # CLI 및 GUI 실행 엔트리포인트
├── requirements.txt         # Python 패키지 의존성 목록
├── config/
│   ├── loader.py            # 설정 파일 로더
│   └── template.json        # 레이어 매핑 설정
├── gui/
│   └── main_window.py       # Tkinter GUI 메인 윈도우
├── photoshop/
│   ├── connection.py        # Photoshop COM 연결 관리
│   ├── document.py          # PSD 문서 열기/저장
│   ├── text.py              # 텍스트 레이어 교체
│   ├── smart_object.py      # 스마트 오브젝트 내용 교체
│   └── image.py             # 일반 이미지 레이어 배치 및 비율 가공
├── analyzer/
│   ├── layer_analyzer.py    # PSD 레이어 구조 재귀 분석
│   └── layer_reader.py      # layer_analysis.json 파서 및 조회
├── matcher/
│   └── image_matcher.py     # 이미지 슬롯 매칭 및 비율 처리
├── ai/
│   └── ai_matcher.py        # Ollama Vision AI 연동 및 카테고리 분류
├── models/
│   └── layer.py             # 레이어 데이터 모델 정의
└── utils/
    ├── filename.py          # 저장 파일명 생성 유틸
    └── image_utils.py       # 썸네일 판별 및 이미지 유틸
```

---

## 💡 참고 및 주의 사항

1. **Photoshop 실행**: 본 프로그램 실행 전 Adobe Photoshop이 설치되어 있어야 하며, COM 객체 등록이 정상 완료되어 있어야 합니다.
2. **Ollama 사용 시**: `--use-ai` 옵션을 사용할 경우 로컬에 Ollama가 실행 중이고 해당 Vision 모델(`qwen3-vl:4b` 등)이 다운로드되어 있는지 확인하세요.
3. **Smart Object 보존**: 스마트 오브젝트 레이어의 경우 원본 템플릿의 변형(스케일, 기울임 등) 및 클리핑 마스크가 보존된 채 내부 내용이 교체됩니다.
