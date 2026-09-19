import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("photoshop.document")


class DocumentError(Exception):
    """PSD 문서 처리 관련 오류"""
    pass


class PhotoshopDocument:
    """Photoshop PSD 문서 열기, 닫기, 저장 관리자"""

    def __init__(self, app: Any):
        self.app = app
        self.doc: Optional[Any] = None
        self.original_path: Optional[Path] = None

    def open_psd(self, file_path: str | Path) -> Any:
        """
        PSD 파일 경로를 받아 Photoshop에서 열기
        """
        path = Path(file_path).resolve()
        if not path.exists():
            raise DocumentError(f"PSD 파일을 찾을 수 없습니다: {path}")

        try:
            logger.info(f"PSD 파일 열기 시도: {path}")
            self.doc = self.app.Open(str(path))
            self.original_path = path
            logger.info(f"PSD 파일 열기 성공: {self.doc.Name}")
            return self.doc
        except Exception as e:
            raise DocumentError(f"PSD 파일을 열 수 없습니다 ({path}): {e}") from e

    def get_active_document(self) -> Any:
        """현재 활성화된 문서 반환"""
        try:
            self.doc = self.app.ActiveDocument
            return self.doc
        except Exception as e:
            raise DocumentError(f"활성화된 PSD 문서를 가져올 수 없습니다: {e}") from e

    def save_as(self, output_path: str | Path, save_options: Optional[Any] = None) -> Path:
        """
        원본 보호를 위해 항상 별도 사본 파일 경로로 저장
        """
        out_path = Path(output_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if self.doc is None:
            raise DocumentError("저장할 활성 문서가 없습니다.")

        # 원본 PSD 덮어쓰기 방지 검사
        if self.original_path and out_path == self.original_path:
            raise DocumentError(
                "안전 원칙: 원본 PSD 파일에 덮어쓸 수 없습니다. 다른 저장 경로를 지정하세요."
            )

        try:
            logger.info(f"PSD 사본 저장 중: {out_path}")
            if save_options:
                self.doc.SaveAs(str(out_path), save_options, False)
            else:
                self.doc.SaveAs(str(out_path))
            logger.info(f"PSD 저장 완료: {out_path}")
            return out_path
        except Exception as e:
            raise DocumentError(f"PSD 저장 실패 ({out_path}): {e}") from e

    def close_document(self, save_changes: bool = False) -> None:
        """
        문서 닫기 (기본값: 원본 수정 없이 닫기)
        2 = psDoNotSaveChanges (Photoshop COM Enum)
        """
        if self.doc is not None:
            try:
                # 2 = psDoNotSaveChanges
                save_option = 1 if save_changes else 2
                self.doc.Close(save_option)
                logger.info("PSD 문서 닫기 완료")
            except Exception as e:
                logger.warning(f"PSD 문서 닫기 중 경고: {e}")
            finally:
                self.doc = None
