import os
import shutil
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Any
from PIL import Image, ImageOps, ImageFilter

logger = logging.getLogger("utils.image_utils")


def is_thumbnail_file(file_path: str | Path) -> bool:
    """is_special_folder_file 에 대한 호환성 에이리어스"""
    return is_special_folder_file(file_path)


def is_special_folder_file(file_path: str | Path) -> bool:
    """
    thumb/ 또는 winner/ 하위 폴더에 있는 파일이거나 _thumb.* 파일인지 여부 확인
    (원본 이미지 탐색 시 자동 제외 목적)
    """
    path_obj = Path(file_path).resolve()
    parts = [p.lower() for p in path_obj.parts]
    if "thumb" in parts or "winner" in parts or "output" in parts:
        return True
    return path_obj.stem.lower().endswith("_thumb")


def get_thumbnail_path(original_path: str | Path) -> Path:
    """orig.parent / 'thumb' / f'{orig.stem}_thumb.jpg' 경로 생성"""
    orig = Path(original_path).resolve()
    thumb_dir = orig.parent / "thumb"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    return thumb_dir / f"{orig.stem}_thumb.jpg"


def ensure_thumbnail(original_path: str | Path, max_dim: int = 768) -> Path:
    """
    원본 이미지에 대해 'thumb/' 하위 폴더 내에 768px 축소 섬네일을 자동 생성 및 저장합니다.
    """
    orig_path = Path(original_path).resolve()
    if is_special_folder_file(orig_path):
        return orig_path

    thumb_path = get_thumbnail_path(orig_path)
    if thumb_path.exists():
        # A previous run may have cached a larger thumbnail (for example 768px).
        # Regenerate it when a caller requests a smaller Vision input so the
        # existing cache does not silently defeat the inference-speed setting.
        try:
            with Image.open(thumb_path) as cached:
                if max(cached.size) <= max_dim:
                    return thumb_path
        except Exception:
            # Fall through and replace an unreadable cache entry.
            pass

    try:
        with Image.open(orig_path) as img:
            try:
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass

            img = img.convert("RGB")
            w, h = img.size

            if max(w, h) > max_dim:
                if w > h:
                    new_w = max_dim
                    new_h = max(1, int(h * (max_dim / w)))
                else:
                    new_h = max_dim
                    new_w = max(1, int(w * (max_dim / h)))
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            img.save(thumb_path, format="JPEG", quality=85)
            logger.info(f"thumb/ 폴더 내 섬네일 생성 완료: {thumb_path.name}")
            return thumb_path

    except Exception as e:
        logger.warning(f"섬네일 생성 실패 ({orig_path.name}): {e}")
        return orig_path


def get_winner_path(original_path: str | Path) -> Path:
    """orig.parent / 'winner' / orig.name 경로 생성"""
    orig = Path(original_path).resolve()
    winner_dir = orig.parent / "winner"
    winner_dir.mkdir(parents=True, exist_ok=True)
    return winner_dir / orig.name


def ensure_winner_copy(original_path: str | Path) -> Path:
    """
    1차 선별된 최선본 이미지를 'winner/' 하위 폴더로 복사 저장합니다.
    """
    orig_path = Path(original_path).resolve()
    winner_path = get_winner_path(orig_path)

    try:
        if not winner_path.exists():
            shutil.copy2(orig_path, winner_path)
            logger.info(f"winner/ 폴더 내 최선본 복사 저장 완료: {winner_path.name}")
        return winner_path
    except Exception as e:
        logger.warning(f"winner/ 폴더 저장 실패 ({orig_path.name}): {e}")
        return orig_path


def compute_dhash(image_path: str | Path, hash_size: int = 8) -> int:
    """dHash (Difference Hash) 64-bit 지각 해시값 계산"""
    try:
        with Image.open(image_path) as img:
            img = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.BILINEAR)
            pixels = list(img.getdata())
            
            difference = []
            for row in range(hash_size):
                for col in range(hash_size):
                    pixel_left = pixels[row * (hash_size + 1) + col]
                    pixel_right = pixels[row * (hash_size + 1) + col + 1]
                    difference.append(pixel_left > pixel_right)
                    
            decimal_value = 0
            for idx, val in enumerate(difference):
                if val:
                    decimal_value += 1 << idx
            return decimal_value
    except Exception:
        return 0


def hamming_distance(hash1: int, hash2: int) -> int:
    """해밍 거리 비트 차이 계산"""
    x = hash1 ^ hash2
    return bin(x).count("1")


def compute_sharpness_score(image_path: str | Path) -> float:
    """이미지 선명도 점수 계산 (라플라시안 변형)"""
    try:
        with Image.open(image_path) as img:
            gray = img.convert("L").resize((300, 300))
            edges = gray.filter(ImageFilter.FIND_EDGES)
            pixels = list(edges.getdata())
            
            mean = sum(pixels) / len(pixels)
            variance = sum((p - mean) ** 2 for p in pixels) / len(pixels)
            return variance
    except Exception:
        return 0.0


def compute_background_brightness(image_path: str | Path, margin_ratio: float = 0.15) -> float:
    """
    이미지 테두리 15% 영역(스튜디오 배경 부분)의 평균 휘도/밝기 점수(0.0 ~ 255.0)를 계산합니다.
    product01 대표 상품 컷으로 배경이 가장 밝은 사진을 선별하는 용도입니다.
    """
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB").resize((200, 200))
            w, h = img.size
            margin_w = int(w * margin_ratio)
            margin_h = int(h * margin_ratio)

            pixels = img.load()
            border_luminances = []

            for x in range(w):
                for y in range(h):
                    # 상, 하, 좌, 우 테두리 영역 픽셀 샘플링
                    if x < margin_w or x >= (w - margin_w) or y < margin_h or y >= (h - margin_h):
                        r, g, b = pixels[x, y]
                        lum = 0.299 * r + 0.587 * g + 0.114 * b
                        border_luminances.append(lum)

            if not border_luminances:
                return 0.0
            return sum(border_luminances) / len(border_luminances)
    except Exception:
        return 0.0
