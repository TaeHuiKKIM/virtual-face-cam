"""Virtual Face Cam - GUI. Cross-platform (Tkinter).

    python gui.py
"""
import threading
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from virtual_cam import load_frames, IMAGE_EXTS

# 색상 팔레트
BG = "#1e1f2b"
CARD = "#282a3a"
ACCENT = "#6c8cff"
GREEN = "#3ecf8e"
RED = "#ff5c7a"
TEXT = "#e8eaf2"
MUTED = "#9aa0b4"
PREVIEW = 300


class App:
    def __init__(self, root):
        self.root = root
        root.title("Virtual Face Cam")
        root.configure(bg=BG)
        root.resizable(False, False)

        self.path = tk.StringVar(value="")
        self.width = tk.IntVar(value=1280)
        self.height = tk.IntVar(value=720)
        self.fps = tk.IntVar(value=30)
        self.interval = tk.DoubleVar(value=3.0)

        self.running = False
        self.worker = None
        self.error = None
        self._thumb = None

        self._setup_style()
        self._build()

        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _setup_style(self):
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("TFrame", background=BG)
        s.configure("Card.TFrame", background=CARD)
        s.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        s.configure("Muted.TLabel", background=CARD, foreground=MUTED,
                    font=("Segoe UI", 9))
        s.configure("Title.TLabel", background=BG, foreground=TEXT,
                    font=("Segoe UI Semibold", 16))
        s.configure("CardLabel.TLabel", background=CARD, foreground=TEXT,
                    font=("Segoe UI", 10))
        s.configure("TButton", font=("Segoe UI", 10), padding=6)
        s.configure("Accent.TButton", font=("Segoe UI Semibold", 11), padding=8)
        s.configure("TEntry", fieldbackground="#33364a", foreground=TEXT)
        s.configure("TSpinbox", fieldbackground="#33364a", foreground=TEXT,
                    arrowsize=12)

    def _build(self):
        pad = 16
        wrap = ttk.Frame(self.root, padding=pad)
        wrap.grid()

        ttk.Label(wrap, text="🎥  Virtual Face Cam", style="Title.TLabel")\
            .grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        # 미리보기 카드
        card = ttk.Frame(wrap, style="Card.TFrame", padding=12)
        card.grid(row=1, column=0, columnspan=2, pady=(0, 12))
        self.preview = tk.Canvas(card, width=PREVIEW, height=PREVIEW,
                                 bg="#33364a", highlightthickness=0)
        self.preview.grid(row=0, column=0)
        self._draw_placeholder()

        # 파일 선택 버튼
        btns = ttk.Frame(wrap)
        btns.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        ttk.Button(btns, text="🖼  이미지 선택", command=self.pick_file)\
            .grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(btns, text="📁  폴더 선택", command=self.pick_dir)\
            .grid(row=0, column=1, sticky="ew", padx=(6, 0))
        btns.columnconfigure(0, weight=1)
        btns.columnconfigure(1, weight=1)

        self.path_lbl = ttk.Label(wrap, text="선택된 파일 없음", foreground=MUTED)
        self.path_lbl.grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 12))

        # 설정 행
        opt = ttk.Frame(wrap, style="Card.TFrame", padding=10)
        opt.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        self._spin(opt, "가로", self.width, 320, 3840, 0)
        self._spin(opt, "세로", self.height, 240, 2160, 2)
        self._spin(opt, "FPS", self.fps, 1, 60, 4)
        self._spin(opt, "전환(초)", self.interval, 0.5, 60, 6, is_float=True)

        # 큰 토글 버튼
        self.toggle_btn = tk.Button(
            wrap, text="▶  시작", command=self.toggle,
            bg=GREEN, fg="#10261c", activebackground="#35b87d",
            font=("Segoe UI Semibold", 13), relief="flat", cursor="hand2",
            height=2)
        self.toggle_btn.grid(row=5, column=0, columnspan=2, sticky="ew")

        # 상태
        self.status = ttk.Label(wrap, text="● 정지됨", foreground=RED)
        self.status.grid(row=6, column=0, columnspan=2, pady=(10, 0))

    def _spin(self, parent, label, var, lo, hi, col, is_float=False):
        ttk.Label(parent, text=label, style="CardLabel.TLabel")\
            .grid(row=0, column=col, padx=(6, 2))
        inc = 0.5 if is_float else 1
        sp = ttk.Spinbox(parent, from_=lo, to=hi, textvariable=var, width=6,
                         increment=inc)
        sp.grid(row=0, column=col + 1, padx=(0, 8))

    def _draw_placeholder(self):
        self.preview.delete("all")
        self.preview.create_text(PREVIEW // 2, PREVIEW // 2,
                                 text="미리보기\n\n이미지를 선택하세요",
                                 fill=MUTED, font=("Segoe UI", 11),
                                 justify="center")

    def _show_thumb(self, path):
        p = Path(path)
        if p.is_dir():
            imgs = sorted(f for f in p.iterdir() if f.suffix.lower() in IMAGE_EXTS)
            if not imgs:
                self._draw_placeholder()
                return
            p = imgs[0]
        try:
            im = Image.open(p)
            im.thumbnail((PREVIEW, PREVIEW), Image.LANCZOS)
            self._thumb = ImageTk.PhotoImage(im)
            self.preview.delete("all")
            self.preview.create_image(PREVIEW // 2, PREVIEW // 2,
                                      image=self._thumb)
        except Exception:
            self._draw_placeholder()

    def pick_file(self):
        f = filedialog.askopenfilename(
            filetypes=[("이미지", "*.jpg *.jpeg *.png *.bmp *.webp"),
                       ("모든 파일", "*.*")])
        if f:
            self._set_path(f)

    def pick_dir(self):
        d = filedialog.askdirectory()
        if d:
            self._set_path(d, is_dir=True)

    def _set_path(self, path, is_dir=False):
        self.path.set(path)
        name = Path(path).name
        self.path_lbl.config(text=("📁 " if is_dir else "🖼 ") + name,
                             foreground=TEXT)
        self._show_thumb(path)

    def toggle(self):
        self.stop() if self.running else self.start()

    def start(self):
        path = self.path.get().strip()
        if not path or not Path(path).exists():
            messagebox.showerror("오류", "유효한 이미지 파일이나 폴더를 선택하세요.")
            return
        self.running = True
        self.error = None
        self.toggle_btn.config(text="■  중지", bg=RED, activebackground="#e04d68",
                               fg="#2a0e14")
        self.status.config(text="● 실행 중 — 카메라 목록에서 'OBS Virtual Camera' 선택",
                           foreground=GREEN)
        self.worker = threading.Thread(target=self._run, args=(path,), daemon=True)
        self.worker.start()

    def stop(self):
        self.running = False
        self.toggle_btn.config(text="▶  시작", bg=GREEN,
                               activebackground="#35b87d", fg="#10261c")
        self.status.config(text="● 정지됨", foreground=RED)

    def _run(self, path):
        import pyvirtualcam
        try:
            w, h, fps = self.width.get(), self.height.get(), self.fps.get()
            frames = load_frames(path, w, h)
            frames_per_image = max(1, int(self.interval.get() * fps))
            with pyvirtualcam.Camera(width=w, height=h, fps=fps) as cam:
                idx, count = 0, 0
                while self.running:
                    cam.send(frames[idx])
                    cam.sleep_until_next_frame()
                    if len(frames) > 1:
                        count += 1
                        if count >= frames_per_image:
                            count = 0
                            idx = (idx + 1) % len(frames)
        except Exception as e:
            self.error = str(e)
            self.running = False
            self.root.after(0, self._show_error)

    def _show_error(self):
        self.stop()
        messagebox.showerror(
            "카메라 오류",
            "가상 카메라를 시작할 수 없습니다.\n"
            "OBS(가상카메라 드라이버)가 설치되어 있는지 확인하세요.\n\n"
            f"세부: {self.error}")

    def on_close(self):
        self.running = False
        self.root.after(200, self.root.destroy)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
