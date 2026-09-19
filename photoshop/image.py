import logging
from pathlib import Path
from typing import Any, Tuple, Optional
from PIL import Image, ImageOps

logger = logging.getLogger("photoshop.image")


class ImageReplacerError(Exception):
    """일반 이미지 레이어 교체 처리 예외"""
    pass


class ImageReplacer:
    """일반 이미지 레이어 교체 및 Pillow 기반 Fit/Crop/Stretch 처리 클래스"""

    def __init__(self, app: Any, doc: Any):
        self.app = app
        self.doc = doc

    def process_image(
        self,
        image_path: str | Path,
        target_size: Tuple[int, int],
        mode: str = "crop",
        temp_dir: Optional[str | Path] = "output/temp"
    ) -> Path:
        """
        Pillow를 사용하여 새 이미지를 대상 레이어 크기(target_size)에 맞춰 Fit / Crop / Stretch 처리합니다.
        :param image_path: 원본 이미지 경로
        :param target_size: (width, height) 픽셀 단위
        :param mode: 'fit', 'crop', 'stretch' 중 선택
        :param temp_dir: 변환 이미지 임시 저장 폴더
        :return: 변환 처리된 가공 이미지 파일 경로
        """
        src_path = Path(image_path).resolve()
        if not src_path.exists():
            raise ImageReplacerError(f"이미지 파일을 찾을 수 없습니다: {src_path}")

        target_w, target_h = int(target_size[0]), int(target_size[1])
        if target_w <= 0 or target_h <= 0:
            target_w, target_h = 500, 500  # 예외 안전 기본값

        out_dir = Path(temp_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"processed_{mode}_{src_path.stem}.png"

        try:
            with Image.open(src_path) as img:
                img = ImageOps.exif_transpose(img).convert("RGB")
                img = img.convert("RGBA")
                src_w, src_h = img.size

                if mode == "stretch":
                    # 강제 맞춤
                    resized = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

                elif mode == "fit":
                    # 축소하여 영역 내 전체 표시 (비율 유지)
                    ratio = min(target_w / src_w, target_h / src_h)
                    new_w = max(1, int(src_w * ratio))
                    new_h = max(1, int(src_h * ratio))
                    scaled = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                    # 여백 생성 (투명 배경)
                    resized = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
                    paste_x = (target_w - new_w) // 2
                    paste_y = (target_h - new_h) // 2
                    resized.paste(scaled, (paste_x, paste_y))

                else:  # 'crop' 기본값
                    # 비율을 유지하며 영역 가득 채우고 넘치는 중앙 크롭
                    ratio = max(target_w / src_w, target_h / src_h)
                    new_w = max(1, int(src_w * ratio))
                    new_h = max(1, int(src_h * ratio))
                    scaled = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                    # 중앙 크롭 영역 계산
                    crop_x = (new_w - target_w) // 2
                    crop_y = (new_h - target_h) // 2
                    resized = scaled.crop((crop_x, crop_y, crop_x + target_w, crop_y + target_h))

                resized.save(out_path, format="PNG")
                logger.info(f"이미지 {mode.upper()} 처리 완료: {out_path.name} ({target_w}x{target_h})")
                return out_path

        except Exception as e:
            raise ImageReplacerError(f"이미지 비율 가공 실패 ({src_path.name}): {e}") from e
