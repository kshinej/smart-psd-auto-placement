import re
from pathlib import Path


def sanitize_filename(name: str, replacement: str = "_") -> str:
    r"""
    Windows 및 주요 OS에서 파일명으로 사용할 수 없는 금지 문자를 제거/치환합니다.
    금지 문자: / \ : * ? " < > |
    """
    if not name:
        return "untitled"

    # 파일명 금지 문자 패턴 치환
    clean_name = re.sub(r'[/\\:*?"<>|]', replacement, name)
    
    # 연속된 치환 문자 정리
    clean_name = re.sub(r'_+', '_', clean_name)
    
    # 앞뒤 공백 및 점 제거
    clean_name = clean_name.strip(" .")
    
    return clean_name if clean_name else "untitled"


def generate_output_psd_path(product_name: str, output_dir: str | Path = "output") -> Path:
    """
    상품명을 기반으로 안전한 사본 PSD 저장 경로를 생성합니다.
    """
    safe_name = sanitize_filename(product_name)
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{safe_name}.psd"
