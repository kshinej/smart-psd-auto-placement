import logging
from pathlib import Path
from typing import Any, Tuple, Optional

logger = logging.getLogger("photoshop.image")


class ImageReplacerError(Exception):
    """일반 이미지 레이어 교체 처리 예외"""
    pass


class ImageReplacer:
    """Photoshop 이미지 레이어 처리 클래스 (가공/크롭 없이 winner/ 원본 보존 사용)"""

    def __init__(self, app: Any, doc: Any):
        self.app = app
        self.doc = doc

    def process_image(
        self,
        image_path: str | Path,
        target_size: Optional[Tuple[int, int]] = None,
        mode: str = "none",
        temp_dir: Optional[str | Path] = None
    ) -> Path:
        """
        크롭 및 이미지 가공 없이 winner/ 내의 원본 이미지를 그대로 사용합니다.
        :param image_path: 원본/winner 이미지 경로
        :return: 가공 없는 이미지 파일 경로
        """
        src_path = Path(image_path).resolve()
        if not src_path.exists():
            raise ImageReplacerError(f"이미지 파일을 찾을 수 없습니다: {src_path}")
        return src_path
