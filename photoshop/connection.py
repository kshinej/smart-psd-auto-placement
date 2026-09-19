import sys
import logging
from typing import Optional, Any

logger = logging.getLogger("photoshop.connection")

try:
    import win32com.client
    import pythoncom
    HAS_PYWIN32 = True
except ImportError:
    HAS_PYWIN32 = False


class PhotoshopConnectionError(Exception):
    """Photoshop 연결 관련 사용자 오류"""
    pass


class PhotoshopConnection:
    """Photoshop COM Automation 연결 관리자"""

    def __init__(self):
        self.app: Optional[Any] = None

    def is_pywin32_available(self) -> bool:
        return HAS_PYWIN32

    def connect(self, make_visible: bool = True) -> Any:
        """
        Photoshop COM 객체에 연결합니다.
        
        :param make_visible: Photoshop 창을 표시할지 여부
        :return: win32com Application Dispatch 객체
        """
        if not HAS_PYWIN32:
            raise PhotoshopConnectionError(
                "pywin32 패키지가 설치되지 않았습니다. 'pip install pywin32'를 실행하세요."
            )

        try:
            pythoncom.CoInitialize()
            logger.info("Photoshop COM 연결 시도...")
            self.app = win32com.client.Dispatch("Photoshop.Application")
            
            if make_visible:
                try:
                    self.app.Visible = True
                except Exception as e:
                    logger.warning(f"Photoshop 창 가시성 설정 실패 (무시 가능): {e}")

            # RulerUnits를 Pixels(1)로 고정하여 좌표/크기가 픽셀 단위로 리턴되도록 보장
            try:
                self.app.Preferences.RulerUnits = 1  # 1 = psPixels
            except Exception as e:
                logger.warning(f"Preferences.RulerUnits 설정 실패 (기본 단위 사용): {e}")

            logger.info("Photoshop 연결 성공!")
            return self.app

        except Exception as e:
            error_msg = (
                "Photoshop을 찾을 수 없거나 연결할 수 없습니다.\n"
                "Photoshop 설치 상태와 실행 환경(Windows, 관리자 권한 등)을 확인해주세요.\n"
                f"원인: {str(e)}"
            )
            logger.error(error_msg)
            raise PhotoshopConnectionError(error_msg) from e

    def is_running(self) -> bool:
        """Photoshop이 현재 실행 중이거나 연결 가능한 상태인지 확인"""
        if self.app is None:
            return False
        try:
            _ = self.app.Name
            return True
        except Exception:
            return False

    def get_app(self) -> Any:
        if self.app is None or not self.is_running():
            return self.connect()
        return self.app
