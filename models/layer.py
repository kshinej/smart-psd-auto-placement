from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class LayerInfo:
    """PSD 레이어 정보를 담는 데이터 클래스"""
    name: str
    full_name: str
    layer_type: str  # text, smart_object, normal, group
    visible: bool
    opacity: float
    x: float
    y: float
    width: float
    height: float
    is_text: bool = False
    is_smart_object: bool = False
    text_content: Optional[str] = None
    children: List["LayerInfo"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """JSON 저장용 Dictionary 변환"""
        data: Dict[str, Any] = {
            "name": self.name,
            "full_name": self.full_name,
            "type": self.layer_type,
            "visible": self.visible,
            "opacity": round(self.opacity, 2),
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "width": round(self.width, 2),
            "height": round(self.height, 2),
        }
        if self.is_text and self.text_content is not None:
            data["text_content"] = self.text_content
        if self.children:
            data["children"] = [child.to_dict() for child in self.children]
        return data
