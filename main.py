import sys
import argparse
import logging
from pathlib import Path
from typing import List

from analyzer.layer_analyzer import PSDLayerAnalyzer
from analyzer.layer_reader import LayerAnalysisReader, LayerAnalysisReaderError
from config.loader import ConfigLoader
from matcher.image_matcher import ImageMatcher, PRODUCT_SLOT_REGEX
from ai.ai_matcher import OllamaVisionMatcher
from photoshop.connection import PhotoshopConnection, PhotoshopConnectionError
from photoshop.document import PhotoshopDocument, DocumentError
from photoshop.text import TextReplacer, TextReplacerError
from photoshop.smart_object import SmartObjectReplacer, SmartObjectReplacerError
from photoshop.image import ImageReplacer
from utils.filename import generate_output_psd_path
from utils.image_utils import is_thumbnail_file

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


def main():
    parser = argparse.ArgumentParser(
        description="PSD 상품 상세페이지 사진 자동 배치하기"
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Tkinter GUI 화면 실행",
    )
    parser.add_argument(
        "--psd",
        type=str,
        help="분석 또는 처리할 PSD 파일 경로 (예: input/sample.psd)",
        default=None,
    )
    parser.add_argument(
        "--main-image",
        type=str,
        help="product01 슬롯에 AI 분류 없이 직통 배치할 전용 메인 사진 파일 경로",
        default=None,
    )
    parser.add_argument(
        "--text", "--name",
        type=str,
        help="새로 변경할 상품명 텍스트 (예: '프리미엄 무선 이어폰')",
        default=None,
    )
    parser.add_argument(
        "--code",
        type=str,
        help="새로 변경할 상품코드 텍스트 (예: 'EAR-2026-PRO')",
        default=None,
    )
    parser.add_argument(
        "--images",
        nargs="+",
        help="교체할 이미지 파일 목록 (예: --images 01.jpg 02.jpg 03.jpg)",
        default=None,
    )
    parser.add_argument(
        "--img-dir",
        type=str,
        help="이미지 파일들이 있는 디렉토리 경로 (예: input/images)",
        default=None,
    )
    parser.add_argument(
        "--image-mode",
        type=str,
        choices=["crop", "fit", "stretch"],
        default="crop",
        help="이미지 비율 가공 모드 (crop, fit, stretch / 기본값: crop)",
    )
    parser.add_argument(
        "--use-ai",
        action="store_true",
        help="Ollama Vision AI (qwen3-vl:4b) 이미지 자동 분류 사용",
    )
    parser.add_argument(
        "--ai-model",
        type=str,
        default="qwen3-vl:4b",
        help="Ollama Vision AI 모델 이름 (기본값: qwen3-vl:4b)",
    )
    parser.add_argument(
        "--text-layer",
        type=str,
        help="상품명 지정 레이어 이름",
        default=None,
    )
    parser.add_argument(
        "--code-layer",
        type=str,
        help="상품코드 지정 레이어 이름",
        default=None,
    )
    parser.add_argument(
        "--config",
        type=str,
        help="템플릿 매핑 설정 JSON 파일 경로",
        default="config/template.json",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="저장할 결과 PSD 파일 경로 또는 디렉토리",
        default=None,
    )
    parser.add_argument(
        "--analysis-json",
        type=str,
        help="레이어 분석 JSON 파일 저장/로드 경로",
        default="layer_analysis.json",
    )

    args = parser.parse_args()

    if args.gui or len(sys.argv) == 1:
        logger.info("GUI 모드로 시작합니다...")
        from gui.main_window import launch_gui
        launch_gui()
        return

    config_loader = ConfigLoader(args.config)
    config = config_loader.load()

    psd_path = args.psd
    if not psd_path:
        candidates = list(Path(".").glob("*.psd")) + list(Path("input").glob("*.psd"))
        if candidates:
            psd_path = str(candidates[0])
            logger.info(f"발견된 PSD 파일 자동 선택: {psd_path}")
        else:
            print("\n[!] 처리할 PSD 파일이 지정되지 않았습니다.")
            print("사용법: python main.py --psd <PSD경로> --text '상품명' --code '코드' --img-dir input/images\n")
            sys.exit(1)

    json_path = args.analysis_json
    print("\n[Phase 1] PSD 전체 레이어 재귀 분석 실행 중...")
    try:
        analyzer = PSDLayerAnalyzer()
        analyzer.analyze(psd_path, json_output_path=json_path)
    except Exception as e:
        print(f"\n[오류] PSD 레이어 분석 실패:\n{e}", file=sys.stderr)
        sys.exit(1)

    raw_image_files: List[Path] = []
    if args.images:
        raw_image_files.extend([Path(p) for p in args.images])
    if args.img_dir:
        img_dir_path = Path(args.img_dir)
        if img_dir_path.exists():
            for ext in ["*.jpg", "*.jpeg", "*.png", "*.webp"]:
                raw_image_files.extend(list(img_dir_path.glob(ext)))
                raw_image_files.extend(list(img_dir_path.glob(ext.upper())))

    orig_image_files = [f for f in raw_image_files if not is_thumbnail_file(f)]
    if args.main_image:
        main_p = Path(args.main_image).resolve()
        orig_image_files = [f for f in orig_image_files if Path(f).resolve() != main_p]
        logger.info(f"[메인 사진 제외] '{main_p.name}'은 썸네일 생성 및 AI 분류 대상에서 제외되고 product01 직통 교체로 보호됩니다.")

    has_text_work = bool(args.text or args.code)
    has_image_work = bool(orig_image_files or args.main_image)

    if not has_text_work and not has_image_work:
        print("\n[Phase 1 완료] layer_analysis.json 생성이 완료되었습니다.")
        sys.exit(0)

    print("\n[Phase 2~5] 텍스트 & 이미지 검증 및 자동 교체 시작...")
    try:
        reader = LayerAnalysisReader(json_path)
        flat_layers = reader.load()

        text_targets = []
        image_targets = []

        if args.text:
            t_hint = args.text_layer or config.get("text", {}).get("product_name", "product name")
            name_layers = reader.find_all_text_layers_by_field("product_name", target_hint=t_hint)
            if not name_layers:
                logger.warning("[안내] PSD 문서 내에 상품명 텍스트 레이어가 없어 텍스트 교체를 스킵합니다.")
            for l in name_layers:
                text_targets.append({"field": "상품명 (Product Name)", "layer": l, "new_text": args.text})

        if args.code:
            c_hint = args.code_layer or config.get("text", {}).get("product_code", "product code")
            code_layers = reader.find_all_text_layers_by_field("product_code", target_hint=c_hint)
            if not code_layers:
                logger.warning("[안내] PSD 문서 내에 상품코드 텍스트 레이어가 없어 텍스트 교체를 스킵합니다.")
            for l in code_layers:
                text_targets.append({"field": "상품코드 (Product Code)", "layer": l, "new_text": args.code})

        matcher = ImageMatcher(config.get("images"))
        best_files = []
        ai_classifications = {}

        if orig_image_files:
            matcher_ai = None
            if args.use_ai:
                matcher_ai = OllamaVisionMatcher(model=args.ai_model)
                if not matcher_ai.is_ollama_available():
                    logger.warning("[안내] Ollama Vision AI를 사용할 수 없어 기본 모드로 진행합니다.")
                    matcher_ai = None

            print(f" -> [Phase 1~4] 썸네일 전량 생성(thumb/) ➔ Vision AI 분류 ➔ product(winner/) / wear(유사도) 실행 중 ({len(orig_image_files)}장)...")
            best_files, _, ai_classifications = matcher.process_images_with_ai(
                orig_image_files, ai_matcher=matcher_ai
            )

        matched_pairs = matcher.match_images_with_ai(
            best_files, flat_layers, ai_classifications, main_image_path=args.main_image
        )
        for img_path, slot_dict in matched_pairs:
            image_targets.append({
                "image_path": img_path,
                "layer": slot_dict,
                "category": ai_classifications.get(Path(img_path).resolve(), "product"),
            })

        print("\n" + "=" * 65)
        print("  [자동 제작 사전 검증 정보]")
        print("=" * 65)
        if text_targets:
            print("  ■ [텍스트 레이어 변경 목록]")
            for idx, item in enumerate(text_targets, 1):
                l = item["layer"]
                print(f"    {idx}. [{item['field']}] {l.get('full_name')} ➔ '{item['new_text']}'")
        if image_targets:
            print("  ■ [이미지 레이어 교체 목록]")
            for idx, item in enumerate(image_targets, 1):
                l = item["layer"]
                print(f"    {idx}. {item['image_path'].name} ➔ {l.get('full_name')} [{l.get('type').upper()}]")
        print("=" * 65 + "\n")

        conn = PhotoshopConnection()
        app = conn.connect()
        doc_mgr = PhotoshopDocument(app)
        doc = doc_mgr.open_psd(psd_path)

        try:
            text_replacer = TextReplacer(doc)
            so_replacer = SmartObjectReplacer(app, doc)
            img_processor = ImageReplacer(app, doc)

            base_name = args.text if args.text else (args.code if args.code else "generated_product")

            if args.output:
                output_arg = Path(args.output)
                if output_arg.suffix.lower() == ".psd":
                    target_output_dir = output_arg.parent
                    out_psd_path = output_arg
                else:
                    target_output_dir = output_arg
                    out_psd_path = generate_output_psd_path(base_name, output_dir=target_output_dir)
            else:
                if args.img_dir and Path(args.img_dir).exists():
                    target_output_dir = Path(args.img_dir) / "output"
                elif args.main_image and Path(args.main_image).exists():
                    target_output_dir = Path(args.main_image).parent / "output"
                else:
                    target_output_dir = Path("output")
                out_psd_path = generate_output_psd_path(base_name, output_dir=target_output_dir)

            target_output_dir.mkdir(parents=True, exist_ok=True)
            temp_output_dir = target_output_dir / "temp"

            # 텍스트 변경 (개별 안전 예외 격리)
            for item in text_targets:
                full_path = item["layer"]["full_name"]
                try:
                    text_replacer.replace_text_by_path(full_path, item["new_text"])
                except Exception as e_text:
                    logger.warning(f"[안내] 텍스트 레이어 ({full_path}) 교체 중 예외 발생: {e_text} ➔ 스킵하고 진행")

            # 이미지 변경 (개별 안전 예외 격리)
            for item in image_targets:
                img_path = item["image_path"]
                slot = item["layer"]
                category = item.get("category", "product")
                full_path = slot["full_name"]
                l_type = slot["type"]

                try:
                    target_layer = text_replacer.find_layer_by_full_path(full_path)
                    if target_layer is None:
                        logger.warning(f"[안내] Photoshop 레이어 미발견 ({full_path}) ➔ 스킵 후 진행")
                        continue

                    if category == "product":
                        processed_img = img_processor.process_image(
                            img_path, (slot.get("width", 500), slot.get("height", 500)),
                            mode=args.image_mode, temp_dir=temp_output_dir
                        )
                        so_replacer.replace_content(target_layer, processed_img)
                    elif l_type == "smart_object":
                        so_replacer.replace_content(target_layer, img_path)
                    else:
                        processed_img = img_processor.process_image(
                            img_path, (slot.get("width", 500), slot.get("height", 500)), mode=args.image_mode, temp_dir=temp_output_dir
                        )
                        so_replacer.replace_content(target_layer, processed_img)
                except Exception as e_img:
                    logger.warning(f"[안내] 이미지 레이어 ({full_path}) 교체 중 예외 발생: {e_img} ➔ 스킵하고 계속 진행")

            # 배치되지 않은 남은 이미지 슬롯 레이어(product02..., wear01... 등) 자동 숨김 (Visible = False)
            unused_slots = matcher.get_unused_image_slots(flat_layers, matched_pairs)
            if unused_slots:
                logger.info(f" -> [미배치 레이어 숨김] 총 {len(unused_slots)}개 사용되지 않은 이미지 슬롯 레이어 숨김 처리 중...")
                for slot in unused_slots:
                    full_path = slot["full_name"]
                    try:
                        target_layer = text_replacer.find_layer_by_full_path(full_path)
                        if target_layer is not None:
                            target_layer.Visible = False
                            logger.info(f"  ✓ 레이어 숨김 완료: {full_path}")
                    except Exception as e_hide:
                        logger.warning(f"[안내] 미배치 레이어 ({full_path}) 숨김 처리 중 예외 발생: {e_hide} ➔ 스킵")

            saved_path = doc_mgr.save_as(out_psd_path)
            print("\n" + "=" * 65)
            print("  🎉 [자동 제작 완료] 새 PSD 사본 생성이 완료되었습니다!")
            print(f"  - 저장 경로: {saved_path}")
            print("=" * 65 + "\n")

        finally:
            doc_mgr.close_document(save_changes=False)

    except Exception as e:
        print(f"\n[오류] 처리 실패: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
