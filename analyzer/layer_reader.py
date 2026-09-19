import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("analyzer.layer_reader")

# 상품명 & 상품코드 유연 정규식 패턴 (오탈자 produnt/produt, 숫자 접미사 허용)
# 예: product name, product name2, produnt name2, product_name_01, product-name-2, productname1
PRODUCT_NAME_REGEX = re.compile(r"^(prod[ucn]*t|prod|pd|상품|제품)?[\s_\-]*name([\s_\-]*\d+)?", re.IGNORECASE)
PRODUCT_CODE_REGEX = re.compile(r"^(prod[ucn]*t|prod|pd|상품|제품)?[\s_\-]*code([\s_\-]*\d+)?", re.IGNORECASE)

PRODUCT_NAME_FALLBACKS = ["상품명", "제품명", "상품 제목", "title", "product_name", "제품제목", "상품타이틀"]
PRODUCT_CODE_FALLBACKS = ["상품코드", "제품코드", "상품 번호", "code", "product_code", "품번"]


class LayerAnalysisReaderError(Exception):
    """layer_analysis.json 로드 및 파싱 관련 오류"""
    pass


class LayerAnalysisReader:
    """layer_analysis.json 분석 결과 파싱 및 텍스트 레이어 검증 클래스"""

    def __init__(self, json_path: str | Path = "layer_analysis.json"):
        self.json_path = Path(json_path).resolve()
        self.layers_tree: List[Dict[str, Any]] = []
        self.flat_layers: List[Dict[str, Any]] = []

    def load(self) -> List[Dict[str, Any]]:
        """
        layer_analysis.json 파일을 로드하고 계층 구조를 평탄화(flatten)합니다.
        """
        if not self.json_path.exists():
            raise LayerAnalysisReaderError(
                f"분석 결과 파일 ({self.json_path})을 찾을 수 없습니다. Phase 1 분석을 먼저 진행하세요."
            )

        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                self.layers_tree = json.load(f)

            self.flat_layers = []
            self._flatten(self.layers_tree)
            logger.info(f"layer_analysis.json 로드 완료 ({len(self.flat_layers)} 개 레이어 수집)")
            return self.flat_layers
        except Exception as e:
            raise LayerAnalysisReaderError(f"layer_analysis.json 파일 읽기 실패: {e}") from e

    def find_all_text_layers_by_field(
        self, field_type: str = "product_name", target_hint: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        필드 타입('product_name' 또는 'product_code')에 일치하는 모든 텍스트 레이어 목록을 반환합니다.
        (예: 'product name'과 'product name2'가 둘 다 존재하는 경우 모두 검출)
        """
        if not self.flat_layers:
            self.load()

        # 1차 후보: type이 'text'이거나 비그룹 레이어
        candidates = [l for l in self.flat_layers if l.get("type") == "text" or (l.get("type") != "group" and "text_content" in l)]
        if not candidates:
            # 안전망: 그룹을 제외한 모든 단일 레이어 대상
            candidates = [l for l in self.flat_layers if l.get("type") != "group"]

        matched_layers: List[Dict[str, Any]] = []
        regex = PRODUCT_NAME_REGEX if field_type == "product_name" else PRODUCT_CODE_REGEX
        fallbacks = PRODUCT_NAME_FALLBACKS if field_type == "product_name" else PRODUCT_CODE_FALLBACKS

        for layer in candidates:
            name = layer.get("name", "").strip()
            full_name = layer.get("full_name", "").strip()

            # 1. target_hint prefix 또는 exact 매칭 (예: 'product name' 힌트 시 'product name', 'product name2' 포함)
            if target_hint:
                target_clean = target_hint.strip().lower()
                name_clean = name.lower()
                if name_clean == target_clean or full_name.lower() == target_clean or name_clean.startswith(target_clean):
                    if layer not in matched_layers:
                        matched_layers.append(layer)
                        logger.info(f"[{field_type} 힌트 매칭] {full_name}")
                        continue

            # 2. 정규식 매칭 (product name, produnt name2, product_name_01 등)
            if regex.search(name):
                if layer not in matched_layers:
                    matched_layers.append(layer)
                    logger.info(f"[{field_type} 정규식 매칭] {full_name} (레이어명: '{name}')")
                    continue

            # 3. 한국어/기타 폴백 키워드 포함 검사
            name_lower = name.lower()
            for kw in fallbacks:
                if kw in name_lower:
                    if layer not in matched_layers:
                        matched_layers.append(layer)
                        logger.info(f"[{field_type} 폴백 키워드 매칭] {full_name}")
                        break

        return matched_layers

    def find_text_layer_by_field(
        self, field_type: str = "product_name", target_hint: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """단일 텍스트 레이어 반환 (첫번째 매칭 항목)"""
        layers = self.find_all_text_layers_by_field(field_type=field_type, target_hint=target_hint)
        return layers[0] if layers else None

    def _flatten(self, layers: List[Dict[str, Any]]) -> None:
        """재귀 구조를 단일 리스트로 평탄화"""
        for layer in layers:
            self.flat_layers.append(layer)
            if "children" in layer and isinstance(layer["children"], list):
                self._flatten(layer["children"])
