import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("config.loader")


class ConfigLoader:
    """템플릿 매핑 설정 로더"""

    def __init__(self, config_path: str | Path = "config/template.json"):
        self.config_path = Path(config_path).resolve()
        self.config_data: Dict[str, Any] = {}

    def load(self) -> Dict[str, Any]:
        """JSON 설정 파일을 로드합니다."""
        if not self.config_path.exists():
            logger.warning(f"설정 파일을 찾을 수 없어 기본값을 사용합니다: {self.config_path}")
            self.config_data = {
                "text": {"product_name": "상품명"},
                "images": {},
                "image_mode": "crop",
            }
            return self.config_data

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config_data = json.load(f)
            logger.info(f"설정 파일 로드 성공: {self.config_path}")
            return self.config_data
        except Exception as e:
            logger.error(f"설정 파일 읽기 실패 ({self.config_path}): {e}")
            raise

    def get_product_name_layer_name(self) -> Optional[str]:
        return self.config_data.get("text", {}).get("product_name")
