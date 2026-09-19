import os
import sys
import time
import logging
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

from analyzer.layer_analyzer import PSDLayerAnalyzer
from analyzer.layer_reader import LayerAnalysisReader
from config.loader import ConfigLoader
from matcher.image_matcher import ImageMatcher, PRODUCT_SLOT_REGEX
from ai.ai_matcher import OllamaVisionMatcher
from photoshop.connection import PhotoshopConnection, PhotoshopConnectionError
from photoshop.document import PhotoshopDocument, DocumentError
from photoshop.text import TextReplacer
from photoshop.smart_object import SmartObjectReplacer
from photoshop.image import ImageReplacer
from utils.filename import generate_output_psd_path
from utils.image_utils import is_thumbnail_file

logger = logging.getLogger("gui.main_window")


class QTextHandler(logging.Handler):
    """Tkinter Text 위젯에 로그를 실시간 출력하는 커스텀 핸들러"""

    def __init__(self, text_widget: scrolledtext.ScrolledText):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        def append():
            self.text_widget.insert(tk.END, msg + "\n")
            self.text_widget.see(tk.END)
        self.text_widget.after(0, append)


class PSDGeneratorGUI:
    """PSD 상품 상세페이지 사진 자동 배치하기 Tkinter GUI"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PSD 상품 상세페이지 사진 자동 배치하기")
        self.root.geometry("840x780")
        self.root.minsize(800, 720)

        self.psd_path_var = tk.StringVar()
        self.main_image_var = tk.StringVar()
        self.product_name_var = tk.StringVar()
        self.product_code_var = tk.StringVar()
        self.img_dir_var = tk.StringVar()
        self.image_mode_var = tk.StringVar(value="crop")
        self.use_ai_var = tk.BooleanVar(value=True)
        self.ai_model_var = tk.StringVar(value="qwen3-vl:4b")
        self.output_dir_var = tk.StringVar(value="output")

        candidates = list(Path(".").glob("*.psd")) + list(Path("input").glob("*.psd"))
        if candidates:
            self.psd_path_var.set(str(candidates[0].resolve()))

        self._build_ui()
        self._setup_logging()

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", font=("Malgun Gothic", 10))
        style.configure("TButton", font=("Malgun Gothic", 10, "bold"))
        style.configure("Header.TLabel", font=("Malgun Gothic", 15, "bold"), foreground="#2C3E50")

        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 15))
        ttk.Label(header_frame, text="🛒 전용 PSD 상품 상세페이지 사진 자동 배치하기", style="Header.TLabel").pack(side=tk.LEFT)

        form_frame = ttk.LabelFrame(main_frame, text=" 작업 설정 및 파일 정보 ", padding="12")
        form_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(form_frame, text="PSD 템플릿 :").grid(row=0, column=0, sticky=tk.W, pady=4)
        ttk.Entry(form_frame, textvariable=self.psd_path_var, width=55).grid(row=0, column=1, padx=5, pady=4, sticky=tk.EW)
        ttk.Button(form_frame, text="찾아보기...", command=self._browse_psd).grid(row=0, column=2, padx=2, pady=4)

        ttk.Label(form_frame, text="⭐ 메인 사진 :").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Entry(form_frame, textvariable=self.main_image_var, width=55).grid(row=1, column=1, padx=5, pady=4, sticky=tk.EW)
        ttk.Button(form_frame, text="찾아보기...", command=self._browse_main_image).grid(row=1, column=2, padx=2, pady=4)

        ttk.Label(form_frame, text="제품 이름 :").grid(row=2, column=0, sticky=tk.W, pady=4)
        ttk.Entry(form_frame, textvariable=self.product_name_var, width=55).grid(row=2, column=1, padx=5, pady=4, sticky=tk.EW)

        ttk.Label(form_frame, text="제품 코드 :").grid(row=3, column=0, sticky=tk.W, pady=4)
        ttk.Entry(form_frame, textvariable=self.product_code_var, width=55).grid(row=3, column=1, padx=5, pady=4, sticky=tk.EW)

        ttk.Label(form_frame, text="이미지 폴더 :").grid(row=4, column=0, sticky=tk.W, pady=4)
        ttk.Entry(form_frame, textvariable=self.img_dir_var, width=55).grid(row=4, column=1, padx=5, pady=4, sticky=tk.EW)
        ttk.Button(form_frame, text="폴더 선택...", command=self._browse_img_dir).grid(row=4, column=2, padx=2, pady=4)

        ttk.Label(form_frame, text="이미지 가공 :").grid(row=5, column=0, sticky=tk.W, pady=4)
        mode_frame = ttk.Frame(form_frame)
        mode_frame.grid(row=5, column=1, sticky=tk.W, padx=5, pady=4)
        ttk.Radiobutton(mode_frame, text="Crop (채우기/크롭)", variable=self.image_mode_var, value="crop").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(mode_frame, text="Fit (전체맞춤)", variable=self.image_mode_var, value="fit").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(mode_frame, text="Stretch (강제맞춤)", variable=self.image_mode_var, value="stretch").pack(side=tk.LEFT, padx=5)

        ttk.Label(form_frame, text="Vision AI :").grid(row=6, column=0, sticky=tk.W, pady=4)
        ai_frame = ttk.Frame(form_frame)
        ai_frame.grid(row=6, column=1, sticky=tk.W, padx=5, pady=4)
        ttk.Checkbutton(ai_frame, text="Ollama Vision AI 착용 여부 사용", variable=self.use_ai_var).pack(side=tk.LEFT)
        ttk.Label(ai_frame, text=" (모델:").pack(side=tk.LEFT, padx=(10, 2))
        ttk.Entry(ai_frame, textvariable=self.ai_model_var, width=15).pack(side=tk.LEFT)
        ttk.Label(ai_frame, text=")").pack(side=tk.LEFT)

        form_frame.columnconfigure(1, weight=1)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(5, 10))

        self.analyze_btn = ttk.Button(btn_frame, text="🔍 PSD 레이어 분석", command=self._on_analyze)
        self.analyze_btn.pack(side=tk.LEFT, padx=5, ipadx=10, ipady=4)

        self.run_btn = ttk.Button(btn_frame, text="🚀 자동 제작 시작", command=self._on_start_generate)
        self.run_btn.pack(side=tk.RIGHT, padx=5, ipadx=15, ipady=4)

        self.progressbar = ttk.Progressbar(main_frame, mode="indeterminate")
        self.progressbar.pack(fill=tk.X, pady=(0, 10))

        log_frame = ttk.LabelFrame(main_frame, text=" 진행 상황 및 로그 ", padding="8")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=("Consolas", 9), bg="#1E1E1E", fg="#D4D4D4")
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _setup_logging(self):
        handler = QTextHandler(self.log_text)
        handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%H:%M:%S"))
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

    def _browse_psd(self):
        filename = filedialog.askopenfilename(
            title="PSD 템플릿 파일 선택",
            filetypes=[("Photoshop 파일", "*.psd"), ("모든 파일", "*.*")]
        )
        if filename:
            self.psd_path_var.set(filename)

    def _browse_main_image(self):
        filename = filedialog.askopenfilename(
            title="product01 직통 교체용 전용 메인 사진 선택",
            filetypes=[("이미지 파일", "*.jpg;*.jpeg;*.png;*.webp"), ("모든 파일", "*.*")]
        )
        if filename:
            self.main_image_var.set(filename)
            if not self.img_dir_var.get().strip():
                self.output_dir_var.set(str(Path(filename).parent / "output"))

    def _browse_img_dir(self):
        dirname = filedialog.askdirectory(title="상품/착용/사이즈 이미지 폴더 선택")
        if dirname:
            self.img_dir_var.set(dirname)
            self.output_dir_var.set(str(Path(dirname) / "output"))

    def _log(self, msg: str):
        logger.info(msg)

    def _on_analyze(self):
        psd_path = self.psd_path_var.get().strip()
        if not psd_path or not Path(psd_path).exists():
            messagebox.showerror("오류", "올바른 PSD 템플릿 파일 경로를 지정하세요.")
            return

        def task():
            self.progressbar.start(10)
            self.analyze_btn.config(state=tk.DISABLED)
            self._log(f"--- PSD 레이어 분석 시작 ({Path(psd_path).name}) ---")
            try:
                analyzer = PSDLayerAnalyzer()
                layers = analyzer.analyze(psd_path, json_output_path="layer_analysis.json")
                self._log(f"✓ PSD 분석 완료! 'layer_analysis.json' 최신화 완료 (총 {len(layers)}개 루트 레이어)")
            except Exception as e:
                self._log(f"[!] PSD 분석 실패: {e}")
                messagebox.showerror("분석 오류", str(e))
            finally:
                self.progressbar.stop()
                self.analyze_btn.config(state=tk.NORMAL)

        threading.Thread(target=task, daemon=True).start()

    def _on_start_generate(self):
        psd_path = self.psd_path_var.get().strip()
        main_img = self.main_image_var.get().strip()
        name = self.product_name_var.get().strip()
        code = self.product_code_var.get().strip()
        img_dir = self.img_dir_var.get().strip()

        if not psd_path or not Path(psd_path).exists():
            messagebox.showerror("오류", "올바른 PSD 템플릿 파일을 지정해야 합니다.")
            return

        if not name and not code and not img_dir and not main_img:
            messagebox.showwarning("경고", "변경할 메인사진, 상품명, 상품코드 또는 이미지 폴더 중 하나 이상을 지정하세요.")
            return

        def task():
            self.progressbar.start(10)
            self.run_btn.config(state=tk.DISABLED)
            self.analyze_btn.config(state=tk.DISABLED)

            self._log("\n" + "=" * 65)
            self._log("  🚀 [자동 제작 파이프라인 시작]")
            self._log("=" * 65)

            try:
                self._log("[1/5] PSD 전체 레이어 재귀 분석 및 JSON 갱신 중...")
                analyzer = PSDLayerAnalyzer()
                analyzer.analyze(psd_path, json_output_path="layer_analysis.json")

                self._log("[2/5] layer_analysis.json 데이터 파싱...")
                reader = LayerAnalysisReader("layer_analysis.json")
                flat_layers = reader.load()

                text_targets = []
                if name:
                    name_layers = reader.find_all_text_layers_by_field("product_name", target_hint="product name")
                    if not name_layers:
                        self._log("[안내] PSD 내에 상품명 텍스트 레이어가 없어 텍스트 교체를 스킵합니다.")
                    for l in name_layers:
                        text_targets.append({"field": "상품명", "layer": l, "new_text": name})

                if code:
                    code_layers = reader.find_all_text_layers_by_field("product_code", target_hint="product code")
                    if not code_layers:
                        self._log("[안내] PSD 내에 상품코드 텍스트 레이어가 없어 텍스트 교체를 스킵합니다.")
                    for l in code_layers:
                        text_targets.append({"field": "상품코드", "layer": l, "new_text": code})

                image_targets = []
                orig_files = []
                if img_dir and Path(img_dir).exists():
                    self._log(f"[3/5] 이미지 폴더 탐색: {img_dir}")
                    raw_img_files = []
                    for ext in ["*.jpg", "*.jpeg", "*.png", "*.webp"]:
                        raw_img_files.extend(list(Path(img_dir).glob(ext)))
                        raw_img_files.extend(list(Path(img_dir).glob(ext.upper())))

                    orig_files = [f for f in raw_img_files if not is_thumbnail_file(f)]
                    if main_img:
                        main_p = Path(main_img).resolve()
                        orig_files = [f for f in orig_files if Path(f).resolve() != main_p]
                        self._log(f"[메인 사진 제외] '{main_p.name}'은 썸네일 생성 및 AI 분류 대상에서 제외하고 product01 직통 배치합니다.")

                matcher = ImageMatcher()
                best_files = []
                ai_classifications = {}

                if orig_files:
                    matcher_ai = None
                    if self.use_ai_var.get():
                        matcher_ai = OllamaVisionMatcher(model=self.ai_model_var.get())
                        if not matcher_ai.is_ollama_available():
                            self._log("[!] Ollama Vision AI 연결 실패 ➔ 기본 모드로 진행")
                            matcher_ai = None

                    self._log(f" -> [Phase 1~4] 썸네일 전량 생성(thumb/) ➔ Vision AI 분류 ➔ product(winner/) / wear(유사도) 진행 중 ({len(orig_files)}장)...")
                    best_files, _, ai_classifications = matcher.process_images_with_ai(
                        orig_files, ai_matcher=matcher_ai
                    )

                matched_pairs = matcher.match_images_with_ai(
                    best_files, flat_layers, ai_classifications, main_image_path=main_img
                )
                for f_path, slot in matched_pairs:
                    image_targets.append({
                        "image_path": f_path,
                        "layer": slot,
                        "category": ai_classifications.get(Path(f_path).resolve(), "product"),
                    })

                self._log(f" -> 사전 검증 완료: 텍스트 {len(text_targets)}개, 이미지 {len(image_targets)}개 준비됨")

                self._log("[4/5] Photoshop COM 연동 및 자동 교체 실행 중...")
                conn = PhotoshopConnection()
                app = conn.connect()
                doc_mgr = PhotoshopDocument(app)
                doc = doc_mgr.open_psd(psd_path)

                try:
                    text_replacer = TextReplacer(doc)
                    so_replacer = SmartObjectReplacer(app, doc)
                    img_processor = ImageReplacer(app, doc)

                    # 사진 폴더 하위 output 폴더 결정
                    if img_dir and Path(img_dir).exists():
                        target_out_dir = Path(img_dir) / "output"
                    elif main_img and Path(main_img).exists():
                        target_out_dir = Path(main_img).parent / "output"
                    else:
                        target_out_dir = Path(self.output_dir_var.get())
                    target_out_dir.mkdir(parents=True, exist_ok=True)
                    temp_out_dir = target_out_dir / "temp"

                    # 텍스트 변경 (개별 안전 예외 격리)
                    for item in text_targets:
                        full_path = item["layer"]["full_name"]
                        try:
                            text_replacer.replace_text_by_path(full_path, item["new_text"])
                        except Exception as e_text:
                            self._log(f"[!] 텍스트 레이어 교체 경고 ({full_path}): {e_text} ➔ 스킵하고 진행")

                    # 이미지 변경 (개별 안전 예외 격리)
                    mode = self.image_mode_var.get()
                    for item in image_targets:
                        img_p = item["image_path"]
                        slot = item["layer"]
                        category = item.get("category", "product")
                        full_path = slot["full_name"]
                        l_type = slot["type"]

                        try:
                            target_l = text_replacer.find_layer_by_full_path(full_path)
                            if target_l is None:
                                self._log(f"[!] 레이어 미발견 ({full_path}) ➔ 스킵 후 진행")
                                continue

                            if category == "product":
                                p_img = img_processor.process_image(
                                    img_p, (slot.get("width", 500), slot.get("height", 500)),
                                    mode=mode, temp_dir=temp_out_dir
                                )
                                so_replacer.replace_content(target_l, p_img)
                            elif l_type == "smart_object":
                                so_replacer.replace_content(target_l, img_p)
                            else:
                                p_img = img_processor.process_image(
                                    img_p, (slot.get("width", 500), slot.get("height", 500)), mode=mode, temp_dir=temp_out_dir
                                )
                                so_replacer.replace_content(target_l, p_img)
                        except Exception as e_img:
                            self._log(f"[!] 이미지 레이어 교체 경고 ({full_path}): {e_img} ➔ 스킵하고 계속 진행")

                    # 배치되지 않은 남은 이미지 슬롯 레이어(product02..., wear01... 등) 자동 숨김 (Visible = False)
                    unused_slots = matcher.get_unused_image_slots(flat_layers, matched_pairs)
                    if unused_slots:
                        self._log(f" -> [미배치 레이어 숨김] 총 {len(unused_slots)}개 미사용 이미지 슬롯 레이어 숨김 처리 중...")
                        for slot in unused_slots:
                            full_path = slot["full_name"]
                            try:
                                target_l = text_replacer.find_layer_by_full_path(full_path)
                                if target_l is not None:
                                    target_l.Visible = False
                                    self._log(f"  ✓ 레이어 숨김 완료: {full_path}")
                            except Exception as e_hide:
                                self._log(f"[!] 미배치 레이어 ({full_path}) 숨김 실패: {e_hide} ➔ 스킵")

                    base_out_name = name if name else (code if code else "generated_product")
                    out_path = generate_output_psd_path(base_out_name, output_dir=target_out_dir)
                    saved_path = doc_mgr.save_as(out_path)

                    self._log("[5/5] 🎉 [자동 제작 완성] 새 PSD 사본 생성 완료!")
                    self._log(f"     저장 위치: {saved_path}")
                    messagebox.showinfo("성공", f"새 PSD 파일이 성공적으로 생성되었습니다!\n\n저장 위치:\n{saved_path}")

                finally:
                    doc_mgr.close_document(save_changes=False)

            except Exception as e:
                self._log(f"[!] 작업 중 오류 발생: {e}")
                messagebox.showerror("작업 오류", str(e))
            finally:
                self.progressbar.stop()
                self.run_btn.config(state=tk.NORMAL)
                self.analyze_btn.config(state=tk.NORMAL)

        threading.Thread(target=task, daemon=True).start()


def launch_gui():
    root = tk.Tk()
    app = PSDGeneratorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
