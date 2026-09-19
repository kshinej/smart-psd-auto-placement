import logging
from pathlib import Path
from typing import Any

try:
    import win32com.client
    HAS_PYWIN32 = True
except ImportError:
    HAS_PYWIN32 = False

logger = logging.getLogger("photoshop.smart_object")


class SmartObjectReplacerError(Exception):
    """Smart Object 교체 실패 예외"""
    pass


class SmartObjectReplacer:
    """Photoshop Smart Object 내용 원본 가공 교체 클래스"""

    def __init__(self, app: Any, doc: Any):
        self.app = app
        self.doc = doc

    def replace_content(self, layer: Any, new_image_path: str | Path) -> bool:
        """
        Smart Object 레이어의 내용을 지정된 새 이미지 파일로 교체합니다.
        위치, 크기, 회전, 왜곡, 마스크, 레이어 효과가 100% 보존됩니다.
        """
        img_path = Path(new_image_path).resolve()
        if not img_path.exists():
            raise SmartObjectReplacerError(f"교체할 이미지 파일을 찾을 수 없습니다: {img_path}")

        try:
            # 1. 해당 레이어를 활성 레이어(ActiveLayer)로 설정
            self.doc.ActiveLayer = layer
            logger.info(f"Smart Object 활성 레이어 지정: {layer.Name}")

            # 2. StringID 또는 CharID 구하기
            try:
                action_id = self.app.StringIDToTypeID("placedLayerReplaceContents")
            except Exception:
                action_id = self.app.CharIDToTypeID("placedLayerReplaceContents")

            try:
                null_id = self.app.StringIDToTypeID("null")
            except Exception:
                null_id = self.app.CharIDToTypeID("null")

            # 3. ActionDescriptor에 새 이미지 파일 경로 할당
            desc = win32com.client.Dispatch("Photoshop.ActionDescriptor")
            desc.PutPath(null_id, str(img_path))

            # 4. ExecuteAction 실행 (3 = psDisplayNoDialogs)
            self.app.ExecuteAction(action_id, desc, 3)
            logger.info(f"✓ Smart Object 내용 교체 성공 [{layer.Name} ➔ {img_path.name}]")
            return True

        except Exception as e:
            error_msg = f"Smart Object 내용 교체 중 오류 발생 ({layer.Name}): {e}"
            logger.error(error_msg)
            raise SmartObjectReplacerError(error_msg) from e
