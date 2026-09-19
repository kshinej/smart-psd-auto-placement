import logging
from typing import List, Any, Optional
from models.layer import LayerInfo

logger = logging.getLogger("photoshop.layers")

# Photoshop COM LayerKind Enums
# 1 = psTextLayer
# 17 = psSmartObject
PS_TEXT_LAYER_KIND = 1
PS_SMART_OBJECT_KIND = 17


class LayerExtractor:
    """Photoshop 문서 레이어 재귀 탐색 및 수집기"""

    def __init__(self):
        pass

    def extract_layers(self, document: Any) -> List[LayerInfo]:
        """
        문서의 루트 레이어들부터 시작하여 전체 레이어 트리를 재귀적으로 탐색합니다.
        """
        result: List[LayerInfo] = []
        try:
            layers = document.Layers
            for i in range(1, layers.Count + 1):
                layer = layers.Item(i)
                layer_info = self._parse_layer(layer, parent_path="")
                if layer_info:
                    result.append(layer_info)
        except Exception as e:
            logger.error(f"레이어 루트 탐색 중 오류 발생: {e}")

        return result

    def _parse_layer(self, layer: Any, parent_path: str) -> Optional[LayerInfo]:
        """
        개별 레이어 또는 레이어 그룹(LayerSet) 정보 파싱 (재귀)
        """
        try:
            name = str(layer.Name)
            full_name = f"{parent_path}/{name}" if parent_path else name
            typename = getattr(layer, "typename", "")

            # 가시성 및 투명도 (오류 발생 시 기본값)
            visible = True
            try:
                visible = bool(layer.Visible)
            except Exception:
                pass

            opacity = 100.0
            try:
                opacity = float(layer.Opacity)
            except Exception:
                pass

            # 레이어 바운딩 박스 (x, y, width, height)
            x, y, width, height = 0.0, 0.0, 0.0, 0.0
            try:
                bounds = layer.Bounds
                left = float(bounds[0])
                top = float(bounds[1])
                right = float(bounds[2])
                bottom = float(bounds[3])
                x = left
                y = top
                width = max(0.0, right - left)
                height = max(0.0, bottom - top)
            except Exception:
                pass

            # 1. 레이어 그룹 (LayerSet) 처리
            if typename == "LayerSet":
                children: List[LayerInfo] = []
                try:
                    sub_layers = layer.Layers
                    for i in range(1, sub_layers.Count + 1):
                        sub_layer = sub_layers.Item(i)
                        child_info = self._parse_layer(sub_layer, parent_path=full_name)
                        if child_info:
                            children.append(child_info)
                except Exception as e:
                    logger.warning(f"그룹 레이어 ({full_name}) 자식 탐색 실패: {e}")

                return LayerInfo(
                    name=name,
                    full_name=full_name,
                    layer_type="group",
                    visible=visible,
                    opacity=opacity,
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    children=children,
                )

            # 2. 일반 레이어 (ArtLayer) 처리
            kind_val = None
            try:
                kind_val = int(layer.Kind)
            except Exception:
                pass

            is_text = (kind_val == PS_TEXT_LAYER_KIND)
            is_smart_object = (kind_val == PS_SMART_OBJECT_KIND)
            text_content: Optional[str] = None

            # 추가 검증: TextItem 속성 존재 시 텍스트 레이어로 강제 인식
            if not is_text:
                try:
                    text_content = str(layer.TextItem.Contents)
                    is_text = True
                except Exception:
                    pass
            else:
                try:
                    text_content = str(layer.TextItem.Contents)
                except Exception as e:
                    logger.warning(f"텍스트 레이어 내용 읽기 실패 ({full_name}): {e}")

            if is_text:
                layer_type = "text"
            elif is_smart_object:
                layer_type = "smart_object"
            else:
                layer_type = "normal"

            return LayerInfo(
                name=name,
                full_name=full_name,
                layer_type=layer_type,
                visible=visible,
                opacity=opacity,
                x=x,
                y=y,
                width=width,
                height=height,
                is_text=is_text,
                is_smart_object=is_smart_object,
                text_content=text_content,
            )

        except Exception as e:
            logger.error(f"레이어 파싱 중 예상치 못한 오류 발생: {e}")
            return None
