import base64
import json
import logging
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional, List

from utils.image_utils import ensure_thumbnail, is_thumbnail_file

logger = logging.getLogger("ai.ai_matcher")


class OllamaVisionMatcher:
    """Ollama Vision LLM (qwen3-vl:4b 등)을 이용한 2분류(사람 착용 여부: wear vs product) 분류 클래스"""

    def __init__(self, host: str = "http://localhost:11434", model: str = "qwen3-vl:4b", max_image_dim: int = 512):
        self.host = host.rstrip("/")
        self.model = model
        self.max_image_dim = max_image_dim

    def is_ollama_available(self) -> bool:
        """Ollama 서버 연결 및 모델 상태 확인"""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("name", "") for m in data.get("models", [])]
                    logger.info(f"Ollama 서버 연결 성공. 보유 모델 목록: {models}")
                    return True
        except Exception as e:
            logger.warning(f"Ollama 서버 연결 안 됨 ({self.host}): {e}")
        return False

    def classify_image(
        self, image_path: str | Path, thumbnail_path: str | Path | None = None
    ) -> Optional[Dict[str, Any]]:
        """
        단일 이미지에 대해 사람 착용 여부를 AI로 판별 (wear vs product)
        - 사람이 상품을 착용/착샷하고 있는 경우: 'wear'
        - 사람이 착용하지 않은 단품/상세/상품 사진인 경우: 'product'
        
        :return: {"category": "wear"|"product", "confidence": float, "reason": str} 또는 None
        """
        orig_path = Path(image_path).resolve()
        if not orig_path.exists():
            return None

        # 호출자가 Phase 1에서 만든 섬네일을 전달하면 재확인/생성을 하지 않는다.
        # 사람 착용 여부만 판별하므로 512px면 충분하면서 Vision 토큰 수를 줄일 수 있다.
        thumb_path = Path(thumbnail_path).resolve() if thumbnail_path else ensure_thumbnail(
            orig_path, max_dim=self.max_image_dim
        )
        if not thumb_path.exists():
            thumb_path = ensure_thumbnail(orig_path, max_dim=self.max_image_dim)

        try:
            with open(thumb_path, "rb") as f:
                b64_image = base64.b64encode(f.read()).decode("utf-8")

            prompt = (
                "Classify this product photo. If a person is wearing or fitting the product, "
                "return wear; otherwise return product. Return only JSON: "
                '{"category":"wear"|"product"}'
            )

            payload = {
                "model": self.model,
                "prompt": prompt,
                "images": [b64_image],
                "stream": False,
                # qwen3-vl returns structured answers in its `thinking` field.
                # Keep that reasoning path enabled for ambiguous accessory/model shots,
                # while bounding the response to the small JSON schema below.
                "think": True,
                "format": "json",
                "keep_alive": "10m",
                "options": {
                    "num_predict": 16,
                    "temperature": 0,
                },
            }

            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.host}/api/generate",
                data=req_data,
                headers={"Content-Type": "application/json"}
            )

            logger.info(f"[AI 착용 여부 분석] {orig_path.name} (thumb 연결 이미지: {thumb_path.name})...")
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 200:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    # qwen3-vl can place a JSON-only answer in `thinking` and leave
                    # `response` empty.  Parse either field so such photos are not
                    # silently classified as the default product category.
                    raw_response = (
                        resp_data.get("response", "").strip()
                        or resp_data.get("thinking", "").strip()
                    )
                    
                    import re
                    category = "product"
                    confidence = 1.0
                    reason = ""

                    json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
                    parsed = None
                    if json_match:
                        try:
                            parsed = json.loads(json_match.group(0))
                        except Exception:
                            pass

                    if isinstance(parsed, dict):
                        cat_val = str(parsed.get("category", parsed.get("answer", ""))).lower()
                        if cat_val in ["wear", "product"]:
                            category = cat_val
                        elif "wear" in cat_val:
                            category = "wear"
                        elif "product" in cat_val:
                            category = "product"
                        else:
                            all_vals = " ".join(str(v).lower() for v in parsed.values())
                            if "wear" in all_vals:
                                category = "wear"
                        try:
                            confidence = float(parsed.get("confidence", 1.0))
                        except (ValueError, TypeError):
                            confidence = 1.0
                        reason = str(parsed.get("reason", ""))
                    else:
                        raw_lower = raw_response.lower()
                        if "wear" in raw_lower or "fitting" in raw_lower or "model" in raw_lower:
                            category = "wear"
                        else:
                            category = "product"
                        
                    is_wearing_str = "착용샷 (wear)" if category == "wear" else "미착용 단품 (product)"
                    logger.info(f"✓ AI 판별 성공 [{orig_path.name}]: {is_wearing_str} (신뢰도: {confidence})")
                    return {
                        "category": category,
                        "confidence": confidence,
                        "reason": reason,
                        "file_path": orig_path
                    }

        except Exception as e:
            logger.warning(f"Ollama Vision AI 착용 여부 분석 실패 ({orig_path.name}): {e}")

        return None

    def classify_images_batch(self, image_paths: List[str | Path]) -> Dict[Path, str]:
        """
        선별된 최선본 이미지들을 연속 분류하여 Dict[Path, 'wear'|'product'] 반환
        """
        results: Dict[Path, str] = {}
        for path in image_paths:
            res = self.classify_image(path)
            if res and "category" in res:
                results[Path(path).resolve()] = res["category"]
        return results
