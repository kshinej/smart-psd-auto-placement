import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from utils.image_utils import (
    ensure_thumbnail,
    ensure_winner_copy,
    is_special_folder_file,
    compute_dhash,
    hamming_distance,
    compute_sharpness_score,
    compute_background_brightness,
)

logger = logging.getLogger("matcher.image_matcher")

PRODUCT_SLOT_REGEX = re.compile(r"^(product|main|대표|상품|메인상품)[\s_\-]*\d*", re.IGNORECASE)
WEAR_SLOT_REGEX = re.compile(r"^(wear|착용|착샷|핏|fit)[\s_\-]*\d*", re.IGNORECASE)
SIZE_SLOT_REGEX = re.compile(r"^(size|사이즈|치수)[\s_\-]*\d*", re.IGNORECASE)


def extract_slot_number(layer_name: str, prefix_type: str = "product") -> int:
    """
    레이어 명칭에서 숫자 인덱스 추출 (예: product01 ➔ 1, product02 ➔ 2)
    숫자가 없으면 9999 반환하여 문서 탐색 순서 유지
    """
    regex_str = r"(?:" + prefix_type + r"|main|대표|상품|wear|착용|size|사이즈)[\s_\-]*0*(\d+)"
    m = re.search(regex_str, layer_name, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    m2 = re.search(r"0*(\d+)", layer_name)
    if m2:
        try:
            return int(m2.group(1))
        except ValueError:
            pass
    return 9999


class ImageMatcher:
    """winner/ 이미지 및 전용 메인 사진 지정 자동 매처 (기존 유사도 필터링: max_dhash_dist=12)"""

    def __init__(self, config_images_mapping: Optional[Dict[str, str]] = None):
        self.config_mapping = config_images_mapping or {}

    def filter_best_similar_images(
        self, image_files: List[str | Path], max_dhash_dist: int = 12
    ) -> Tuple[List[Path], List[Path]]:
        """
        [1차 기존 분류] 유사/연사 사진들(dHash 비트거리 <= 12)을 그룹화하여 그 중 가장 잘 나온 사진 1장만 선별하여 winner/ 폴더에 저장합니다.
        
        :param max_dhash_dist: 기존 유사도 해밍 거리 기준 (기본값: 12)
        :return: (winner/ 폴더에 저장된 선별본 목록, 제외된 중복/유사 이미지 목록)
        """
        raw_files = []
        seen_files = set()
        for file_path in image_files:
            path = Path(file_path).resolve()
            # Windows glob is case-insensitive.  Callers that search both *.jpg
            # and *.JPG can therefore pass the same file twice; never send that
            # duplicate through an expensive Vision classification.
            path_key = str(path).casefold()
            if path.exists() and not is_special_folder_file(path) and path_key not in seen_files:
                raw_files.append(path)
                seen_files.add(path_key)

        if not raw_files:
            return [], []

        logger.info(f"[1차 선별] 총 {len(raw_files)}개 원본 대상 유사 사진 탐색 중 (dHash 거리 <= {max_dhash_dist})...")

        file_meta = []
        for f in raw_files:
            thumb_p = ensure_thumbnail(f)
            dhash = compute_dhash(thumb_p)
            sharpness = compute_sharpness_score(thumb_p)
            file_meta.append({
                "orig_path": f,
                "thumb_path": thumb_p,
                "dhash": dhash,
                "sharpness": sharpness,
            })

        # 유사 사진 그룹화 (기존 dHash 해밍 거리 <= 12)
        groups: List[List[Dict[str, Any]]] = []
        visited = set()

        for i, meta1 in enumerate(file_meta):
            if i in visited:
                continue

            current_group = [meta1]
            visited.add(i)

            for j in range(i + 1, len(file_meta)):
                if j in visited:
                    continue
                meta2 = file_meta[j]
                dist = hamming_distance(meta1["dhash"], meta2["dhash"])
                if dist <= max_dhash_dist:
                    current_group.append(meta2)
                    visited.add(j)

            groups.append(current_group)

        winner_files: List[Path] = []
        excluded_files: List[Path] = []

        for group in groups:
            group.sort(key=lambda m: m["sharpness"], reverse=True)
            best_item = group[0]

            winner_path = ensure_winner_copy(best_item["orig_path"])
            winner_files.append(winner_path)

            if len(group) > 1:
                dup_names = [m["orig_path"].name for m in group[1:]]
                logger.info(
                    f"[1차 유사 선별] winner/ 저장 '{winner_path.name}' (선명도: {int(best_item['sharpness'])}) ➔ 제외 컷: {dup_names}"
                )
                for item in group[1:]:
                    excluded_files.append(item["orig_path"])
            else:
                logger.info(f"[1차 단독 선별] winner/ 저장 '{winner_path.name}'")

        logger.info(f"[1차 선별 완료] 원본 {len(raw_files)}장 ➔ winner/ 폴더 {len(winner_files)}장 저장 완료 (제외 {len(excluded_files)}장)")
        return winner_files, excluded_files

    def process_images_with_ai(
        self,
        image_files: List[str | Path],
        ai_matcher: Optional[Any] = None,
        max_dhash_dist: int = 12,
    ) -> Tuple[List[Path], List[Path], Dict[Path, str]]:
        """
        [단계별 명확 분리 파이프라인]
        Phase 1: 대상 모든 이미지의 512px thumb/ 썸네일을 먼저 전량 생성하여 저장
        Phase 2: 썸네일 생성 완료 후, thumb/ 썸네일들을 대상으로 Vision AI 판별(wear vs product) 실행
        Phase 3: product 사진 ➔ 유사도 검사 스킵 후 100% winner/ 복사
        Phase 4: wear 사진 ➔ dHash 유사도 선별 후 베스트 컷만 winner/ 복사
        
        :return: (winner 파일 목록, 제외된 파일 목록, winner 및 원본 경로별 AI 분류 결과 맵)
        """
        raw_files = []
        seen_files = set()
        for file_path in image_files:
            path = Path(file_path).resolve()
            path_key = str(path).casefold()
            if path.exists() and not is_special_folder_file(path) and path_key not in seen_files:
                raw_files.append(path)
                seen_files.add(path_key)

        if not raw_files:
            return [], [], {}

        # -----------------------------------------------------------------
        # Phase 1: 모든 사진의 썸네일을 먼저 다 생성하여 thumb/ 폴더로 전송
        # -----------------------------------------------------------------
        logger.info(f"[Phase 1] 썸네일 전량 생성 시작: 총 {len(raw_files)}장 ➔ thumb/ 폴더 저장 중...")
        thumb_map: Dict[Path, Path] = {}
        for f in raw_files:
            thumb_p = ensure_thumbnail(f, max_dim=getattr(ai_matcher, "max_image_dim", 512))
            thumb_map[f] = thumb_p
        logger.info(f"✓ [Phase 1 완료] 총 {len(thumb_map)}장 썸네일이 thumb/ 폴더에 생성 저장되었습니다.")

        # -----------------------------------------------------------------
        # Phase 2: 썸네일 생성이 완벽히 끝난 후, AI로 썸네일들 판별 (wear vs product)
        # -----------------------------------------------------------------
        ai_classifications: Dict[Path, str] = {}
        if ai_matcher and getattr(ai_matcher, "is_ollama_available", lambda: False)():
            logger.info(f"[Phase 2] Vision AI 판별 시작: thumb/ 썸네일 {len(thumb_map)}장 착용 여부 분석 중...")
            for orig_f, thumb_p in thumb_map.items():
                res = ai_matcher.classify_image(orig_f, thumbnail_path=thumb_p)
                category = res.get("category", "wear") if (res and "category" in res) else "wear"
                ai_classifications[orig_f] = category
        else:
            for orig_f in thumb_map:
                ai_classifications[orig_f] = "product"

        # -----------------------------------------------------------------
        # Phase 3 & 4: product 100% winner/ 저장 vs wear 유사도 선별
        # -----------------------------------------------------------------
        winner_files: List[Path] = []
        excluded_files: List[Path] = []
        wear_meta: List[Dict[str, Any]] = []

        for orig_f, category in list(ai_classifications.items()):
            thumb_p = thumb_map[orig_f]
            if category == "product":
                w_path = ensure_winner_copy(orig_f)
                winner_files.append(w_path)
                ai_classifications[w_path] = "product"
                logger.info(f"  [product] '{orig_f.name}' ➔ 유사도 검사 스킵, winner/ 저장")
            else:
                dhash = compute_dhash(thumb_p)
                sharpness = compute_sharpness_score(thumb_p)
                wear_meta.append({
                    "orig_path": orig_f,
                    "thumb_path": thumb_p,
                    "dhash": dhash,
                    "sharpness": sharpness,
                })

        if wear_meta:
            logger.info(f"[Phase 4] wear 유사도 선별: 착용 사진 {len(wear_meta)}장에 대해 유사도 검사(dHash <= {max_dhash_dist}) 진행 중...")
            groups: List[List[Dict[str, Any]]] = []
            visited = set()

            for i, meta1 in enumerate(wear_meta):
                if i in visited:
                    continue
                current_group = [meta1]
                visited.add(i)

                for j in range(i + 1, len(wear_meta)):
                    if j in visited:
                        continue
                    meta2 = wear_meta[j]
                    dist = hamming_distance(meta1["dhash"], meta2["dhash"])
                    if dist <= max_dhash_dist:
                        current_group.append(meta2)
                        visited.add(j)
                groups.append(current_group)

            for group in groups:
                group.sort(key=lambda m: m["sharpness"], reverse=True)
                best_item = group[0]
                winner_path = ensure_winner_copy(best_item["orig_path"])
                winner_files.append(winner_path)
                ai_classifications[winner_path] = "wear"

                if len(group) > 1:
                    dup_names = [m["orig_path"].name for m in group[1:]]
                    logger.info(f"  [wear 선별 완료] winner/ '{winner_path.name}' (선명도: {int(best_item['sharpness'])}) ➔ 제외: {dup_names}")
                    for item in group[1:]:
                        excluded_files.append(item["orig_path"])
                else:
                    logger.info(f"  [wear 단독 저장] winner/ '{winner_path.name}'")

        wear_count = len([c for c in ai_classifications.values() if c == "wear"]) // 2
        prod_count = len(winner_files) - wear_count
        logger.info(f"[파이프라인 완료] 원본 {len(raw_files)}장 ➔ winner/ {len(winner_files)}장 저장 완료 (product 보존: {prod_count}장, wear 선별: {wear_count}장)")
        return winner_files, excluded_files, ai_classifications

    def match_images_with_ai(
        self,
        image_files: List[str | Path],
        flat_layers: List[Dict[str, Any]],
        ai_classifications: Optional[Dict[Path, str]] = None,
        main_image_path: Optional[str | Path] = None
    ) -> List[Tuple[Path, Dict[str, Any]]]:
        """
        [2차 매칭]
        - main_image_path 지정 시: product01 슬롯에 직통 최우선 할당
        - 착용 사진(wear) ➔ wear01, wear02... 순서대로 교체
        - 미착용 사진(product) ➔ product01, product02... 순서대로 교체
        """
        valid_files = [ensure_winner_copy(Path(f).resolve()) for f in image_files if Path(f).exists()]

        wear_slots, product_slots, other_slots = self._categorize_binary_slots(flat_layers)

        matched_pairs: List[Tuple[Path, Dict[str, Any]]] = []
        used_files_norm = set()
        used_slots_norm = set()

        ai_map = {}
        for k, v in (ai_classifications or {}).items():
            resolved_k = Path(k).resolve()
            ai_map[resolved_k] = v
            ai_map[ensure_winner_copy(resolved_k)] = v

        # 0. 전용 메인 사진(main_image_path) 지정 시 winner/ 폴더로 복사 후 product01 최우선 직통 할당
        if main_image_path:
            raw_main_p = Path(main_image_path).resolve()
            if raw_main_p.exists():
                main_p = ensure_winner_copy(raw_main_p)
                if product_slots:
                    target_p1_slot = product_slots[0]
                    matched_pairs.append((main_p, target_p1_slot))
                    used_files_norm.add(str(raw_main_p).lower())
                    used_files_norm.add(str(main_p).lower())
                    used_slots_norm.add(target_p1_slot["full_name"].lower())
                    logger.info(
                        f"[전용 메인 사진 지정] 'winner/{main_p.name}' ➔ {target_p1_slot['full_name']} (product01 순서 직통 교체)"
                    )

        # 1. 착용한 사진(wear) ➔ wear01~ 슬롯 순차 교체
        wear_files = [f for f in valid_files if str(f).lower() not in used_files_norm and ai_map.get(f) == "wear"]
        for f, slot in zip(wear_files, wear_slots):
            s_name = slot["full_name"].lower()
            if s_name not in used_slots_norm and str(f).lower() not in used_files_norm:
                matched_pairs.append((f, slot))
                used_files_norm.add(str(f).lower())
                used_slots_norm.add(s_name)
                logger.info(f"[착용 사진(wear) 매칭] winner/{f.name} ➔ {slot['full_name']}")

        # 2. 미착용 사진(product) ➔ product01~ 슬롯 순차 교체
        remaining_product_slots = [s for s in product_slots if s["full_name"].lower() not in used_slots_norm]
        product_files = [
            f for f in valid_files
            if str(f).lower() not in used_files_norm and (ai_map.get(f) == "product" or f not in ai_map)
        ]

        for f, slot in zip(product_files, remaining_product_slots):
            s_name = slot["full_name"].lower()
            f_norm = str(f).lower()
            if f_norm not in used_files_norm and s_name not in used_slots_norm:
                matched_pairs.append((f, slot))
                used_files_norm.add(f_norm)
                used_slots_norm.add(s_name)
                logger.info(f"[미착용 상품사진(product) 매칭] winner/{f.name} ➔ {slot['full_name']}")

        # 3. 남은 슬롯/파일 폴백 순서 매칭
        remaining_files = [f for f in valid_files if str(f).lower() not in used_files_norm]
        all_slots = wear_slots + product_slots + other_slots
        remaining_slots = [s for s in all_slots if s["full_name"].lower() not in used_slots_norm]

        for f, slot in zip(remaining_files, remaining_slots):
            s_name = slot["full_name"].lower()
            f_norm = str(f).lower()
            if f_norm not in used_files_norm and s_name not in used_slots_norm:
                matched_pairs.append((f, slot))
                used_files_norm.add(f_norm)
                used_slots_norm.add(s_name)
                logger.info(f"[폴백 순서 매칭] winner/{f.name} ➔ {slot['full_name']}")

        return matched_pairs

    def get_unused_image_slots(
        self,
        flat_layers: List[Dict[str, Any]],
        matched_pairs: List[Tuple[Path, Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """
        이미지 교체 배치가 수행되지 않고 남은 이미지 슬롯 중,
        오직 product... 또는 wear... 명칭을 가진 미사용 레이어만 엄격히 선별하여 구합니다.
        """
        all_slots = self._extract_all_image_slots(flat_layers)
        used_slot_names = {slot["full_name"].lower() for _, slot in matched_pairs}

        unused_slots = []
        for slot in all_slots:
            full_name_lower = slot.get("full_name", "").lower()
            if full_name_lower in used_slot_names:
                continue

            name = slot.get("name", "").strip()
            # product..., wear... 레이어 명칭을 가진 레이어만 숨김 대상으로 지정
            if PRODUCT_SLOT_REGEX.search(name) or WEAR_SLOT_REGEX.search(name):
                unused_slots.append(slot)

        logger.info(f"[미배치 레이어 구하기] 총 {len(all_slots)}개 이미지 슬롯 중 {len(unused_slots)}개 미사용 product/wear 레이어 발견")
        return unused_slots

    def _categorize_binary_slots(self, flat_layers: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        slots = self._extract_all_image_slots(flat_layers)
        wear_slots = []
        product_slots = []
        other_slots = []

        for slot in slots:
            name = slot.get("name", "").strip()
            if WEAR_SLOT_REGEX.search(name):
                wear_slots.append(slot)
            elif PRODUCT_SLOT_REGEX.search(name):
                product_slots.append(slot)
            else:
                other_slots.append(slot)

        wear_slots.sort(key=lambda s: extract_slot_number(s.get("name", ""), "wear"))
        product_slots.sort(key=lambda s: extract_slot_number(s.get("name", ""), "product"))

        return wear_slots, product_slots, other_slots

    def _extract_all_image_slots(self, flat_layers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        slots = []
        for l in flat_layers:
            if l.get("type") == "group":
                continue
            l_type = l.get("type")
            l_name = l.get("name", "").lower()

            if l_type == "smart_object":
                slots.append(l)
            elif l_type == "normal" and not any(skip in l_name for skip in ["배경", "bg", "background", "shadow", "그림자"]):
                if not l.get("is_text"):
                    slots.append(l)

        return slots
