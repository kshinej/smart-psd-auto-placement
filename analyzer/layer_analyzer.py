import json
import logging
from pathlib import Path
from typing import List, Dict, Any

from photoshop.connection import PhotoshopConnection
from photoshop.document import PhotoshopDocument
from photoshop.layers import LayerExtractor
from models.layer import LayerInfo

logger = logging.getLogger("analyzer.layer_analyzer")


class PSDLayerAnalyzer:
    """PSD 전체 레이어 구조 탐색 및 분석 내보내기 클래스"""

    def __init__(self):
        self.connection = PhotoshopConnection()
        self.extractor = LayerExtractor()

    def analyze(
        self, psd_path: str | Path, json_output_path: str | Path = "layer_analysis.json"
    ) -> List[LayerInfo]:
        """
        PSD 파일의 레이어를 탐색하고 JSON 파일로 결과를 저장합니다.
        """
        app = self.connection.connect()
        doc_mgr = PhotoshopDocument(app)
        
        try:
            logger.info(f"분석 대상 PSD 열기: {psd_path}")
            doc = doc_mgr.open_psd(psd_path)

            logger.info("PSD 전체 레이어 재귀 분석 시작...")
            layers_info = self.extractor.extract_layers(doc)

            # 콘솔에 깔끔한 트리 형태로 분석 결과 출력
            print("\n" + "=" * 50)
            print("  PSD 레이어 분석 결과")
            print("=" * 50)
            self._print_tree(layers_info)
            print("=" * 50 + "\n")

            # JSON 파일 저장
            out_file = Path(json_output_path).resolve()
            out_file.parent.mkdir(parents=True, exist_ok=True)
            
            json_data = [layer.to_dict() for layer in layers_info]
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(json_data, f, ensure_ascii=False, indent=4)

            logger.info(f"분석 결과 JSON 저장 완료: {out_file}")
            print(f"✓ 분석 결과가 저장되었습니다: {out_file}")

            return layers_info

        finally:
            # 원본 문서는 수정 없이 닫기 (또는 사용자가 Photoshop에서 확인할 수 있도록 유지 가능)
            # doc_mgr.close_document(save_changes=False)
            pass

    def _print_tree(self, layers: List[LayerInfo], indent: str = "") -> None:
        """콘솔 출력용 계층 구조 트리 렌더러"""
        for i, layer in enumerate(layers):
            is_last = (i == len(layers) - 1)
            branch = " └─ " if is_last else " ├─ "
            next_indent = indent + ("    " if is_last else " │  ")

            type_str = layer.layer_type.upper()
            details = f"[{type_str}]"
            if layer.is_text and layer.text_content:
                # 긴 텍스트 축약
                short_text = layer.text_content.replace("\n", " ")
                if len(short_text) > 20:
                    short_text = short_text[:20] + "..."
                details += f' "{short_text}"'
            details += f" ({int(layer.width)}x{int(layer.height)} @ {int(layer.x)},{int(layer.y)})"

            print(f"{indent}{branch}{layer.name} {details}")

            if layer.children:
                self._print_tree(layer.children, next_indent)
