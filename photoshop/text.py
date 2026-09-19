import logging
from typing import Any, Optional, List, Tuple

logger = logging.getLogger("photoshop.text")


class TextReplacerError(Exception):
    """텍스트 레이어 교체 중 발생한 오류"""
    pass


class TextReplacer:
    """Photoshop 텍스트 레이어 교체 클래스 (layer_analysis.json 연동 지원)"""

    def __init__(self, doc: Any):
        self.doc = doc

    def find_layer_by_full_path(self, full_path: str) -> Optional[Any]:
        """
        layer_analysis.json에서 지정된 full_path 경로(예: '상품정보/상품명')로
        Photoshop COM 레이어 객체를 정확히 찾아 반환합니다.
        """
        parts = [p.strip() for p in full_path.split("/") if p.strip()]
        if not parts:
            return None

        current_collection = self.doc.Layers
        current_layer: Optional[Any] = None

        for part in parts:
            found = False
            try:
                for i in range(1, current_collection.Count + 1):
                    item = current_collection.Item(i)
                    if str(item.Name) == part:
                        current_layer = item
                        if getattr(item, "typename", "") == "LayerSet":
                            current_collection = item.Layers
                        found = True
                        break
            except Exception as e:
                logger.warning(f"경로 탐색 중 실패 ({part}): {e}")
                return None

            if not found:
                logger.warning(f"Photoshop DOM에서 계층 경로 요소를 찾지 못함: {part}")
                return None

        return current_layer

    def replace_text_by_path(self, full_path: str, new_text: str) -> str:
        """
        layer_analysis.json 분석 결과에서 확정된 full_path 레이어의 문구를 변경합니다.
        
        :param full_path: 레이어 계층 경로 (예: '상품정보/상품명')
        :param new_text: 교체할 새 상품명 텍스트
        :return: 변경된 레이어 경로
        """
        if not new_text:
            raise TextReplacerError("교체할 새 상품명이 빈 값입니다.")

        layer = self.find_layer_by_full_path(full_path)
        if layer is None:
            raise TextReplacerError(f"layer_analysis.json의 경로 '{full_path}'에 해당하는 Photoshop 레이어를 찾지 못했습니다.")

        try:
            # textItem 객체 확인 및 텍스트 교체
            old_text = layer.TextItem.Contents
            layer.TextItem.Contents = str(new_text)
            logger.info(f"[COM 텍스트 변경 완료] 레이어: '{full_path}' | 기존: '{old_text}' → 새문구: '{new_text}'")
            return full_path
        except Exception as e:
            raise TextReplacerError(f"Photoshop COM 텍스트 변경 적용 실패 ({full_path}): {e}") from e
