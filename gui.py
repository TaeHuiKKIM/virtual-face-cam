"""Virtual Face Cam - GUI. Cross-platform (Tkinter).

    python gui.py
"""
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


def resource_path(rel):
    """번들(PyInstaller)/스크립트 양쪽에서 동작하는 리소스 경로."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / rel
    return Path(__file__).resolve().parent / rel


def enable_hidpi():
    """Windows 고해상도 화면에서 흐릿하게 확대되는 것 방지.

    반환값(성공 여부)까지 확인해, 한 방법이 실패하면 다음 방법으로 넘어간다.
    """
    if sys.platform != "win32":
        return
    import ctypes
    # 1) Per-Monitor-V2 (Win10 1703+). 핸들 인자는 반드시 포인터 크기로 전달.
    try:
        ctx = ctypes.c_void_p(-4)  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctx):
            return
    except Exception:
        pass
    # 2) Per-Monitor (Win8.1+). 단순 int enum이라 핸들 문제 없음.
    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:  # S_OK
            return
    except Exception:
        pass
    # 3) System-aware (구버전 폴백)
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from PIL import Image, ImageTk

from virtual_cam import (
    VIDEO_EXTS,
    create_frame_source,
    load_recent_path,
    preview_image,
    save_recent_path,
)

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

        # 화면 배율에 맞춘 미리보기 크기 (96dpi 기준)
        try:
            self.scale = max(1.0, root.winfo_fpixels("1i") / 96.0)
        except Exception:
            self.scale = 1.0
        self.pv = int(PREVIEW * self.scale)

        self._setup_style()
        self._build()

        # 최근 선택 항목을 먼저 복원하고, 없거나 삭제됐으면 기본 이미지를 사용한다.
        recent = load_recent_path()
        default = resource_path("assets/default_face.jpg")
        if recent:
            self._set_path(str(recent), persist=False, restored=True)
        elif default.exists():
            self._set_path(str(default), persist=False)

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
        s.configure("TEntry", fieldbackground="#33364a", foreground=TEXT,
                    bordercolor="#3d4056", relief="flat")
        s.configure("TSpinbox", fieldbackground="#33364a", background="#33364a",
                    foreground=TEXT, arrowcolor=TEXT, arrowsize=11,
                    bordercolor="#3d4056", relief="flat")
        s.map("TSpinbox", fieldbackground=[("readonly", "#33364a")],
              bordercolor=[("focus", ACCENT)])

    def _build(self):
        pad = 16
        wrap = ttk.Frame(self.root, padding=pad)
        wrap.grid()

        ttk.Label(wrap, text="🎥  Virtual Face Cam", style="Title.TLabel")\
            .grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(wrap, text="사진 또는 반복 영상을 가상 웹캠으로 출력합니다",
                  foreground=MUTED).grid(row=1, column=0, columnspan=2,
                                         sticky="w", pady=(2, 14))

        # 미리보기 카드
        card = ttk.Frame(wrap, style="Card.TFrame", padding=14)
        card.grid(row=2, column=0, columnspan=2, pady=(0, 12))
        self.preview = tk.Canvas(card, width=self.pv, height=self.pv,
                                 bg="#33364a", highlightthickness=0)
        self.preview.grid(row=0, column=0)
        self._draw_placeholder()

        # 파일 선택 버튼
        btns = ttk.Frame(wrap)
        btns.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self._flat_button(btns, "사진 / 영상 선택", self.pick_file)\
            .grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self._flat_button(btns, "📁  폴더 선택", self.pick_dir)\
            .grid(row=0, column=1, sticky="ew", padx=(5, 0))
        btns.columnconfigure(0, weight=1)
        btns.columnconfigure(1, weight=1)

        self.path_lbl = ttk.Label(wrap, text="선택된 파일 없음", foreground=MUTED)
        self.path_lbl.grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 12))

        # 설정 행
        opt = ttk.Frame(wrap, style="Card.TFrame", padding=12)
        opt.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        self._spin(opt, "가로", self.width, 320, 3840, 0)
        self._spin(opt, "세로", self.height, 240, 2160, 2)
        self._spin(opt, "FPS", self.fps, 1, 60, 4)
        self._spin(opt, "전환(초)", self.interval, 0.5, 60, 6, is_float=True)

        # 큰 토글 버튼
        self.toggle_btn = tk.Button(
            wrap, text="▶  시작", command=self.toggle,
            bg=GREEN, fg="#10261c", activebackground="#35b87d",
            font=("Segoe UI Semibold", 13), relief="flat", cursor="hand2",
            bd=0, height=2)
        self.toggle_btn.grid(row=6, column=0, columnspan=2, sticky="ew")

        # 상태
        self.status = ttk.Label(wrap, text="● 정지됨", foreground=RED)
        self.status.grid(row=7, column=0, columnspan=2, pady=(12, 0))

    def _flat_button(self, parent, text, command):
        b = tk.Button(parent, text=text, command=command,
                      bg="#33364a", fg=TEXT, activebackground="#454a63",
                      activeforeground=TEXT, relief="flat", cursor="hand2",
                      font=("Segoe UI", 10), bd=0, padx=10, pady=11)
        b.bind("<Enter>", lambda e: b.config(bg="#3d4157"))
        b.bind("<Leave>", lambda e: b.config(bg="#33364a"))
        return b

    def _spin(self, parent, label, var, lo, hi, col, is_float=False):
        ttk.Label(parent, text=label, style="CardLabel.TLabel")\
            .grid(row=0, column=col, padx=(6, 2))
        inc = 0.5 if is_float else 1
        sp = ttk.Spinbox(parent, from_=lo, to=hi, textvariable=var, width=6,
                         increment=inc)
        sp.grid(row=0, column=col + 1, padx=(0, 8))

    def _draw_placeholder(self):
        self.preview.delete("all")
        self.preview.create_text(self.pv // 2, self.pv // 2,
                                 text="미리보기\n\n사진 또는 영상을 선택하세요",
                                 fill=MUTED, font=("Segoe UI", 11),
                                 justify="center")

    def _show_thumb(self, path):
        p = Path(path)
        try:
            im = preview_image(p)
            im.thumbnail((self.pv, self.pv), Image.LANCZOS)
            self._thumb = ImageTk.PhotoImage(im)
            self.preview.delete("all")
            self.preview.create_image(self.pv // 2, self.pv // 2,
                                      image=self._thumb)
            if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
                self.preview.create_rectangle(
                    12, self.pv - 42, 132, self.pv - 12,
                    fill="#171923", outline="")
                self.preview.create_text(
                    72, self.pv - 27, text="VIDEO · LOOP",
                    fill=TEXT, font=("Segoe UI Semibold", 9))
        except Exception:
            self._draw_placeholder()

    def pick_file(self):
        f = filedialog.askopenfilename(
            filetypes=[("사진 및 영상", "*.jpg *.jpeg *.png *.bmp *.webp *.mp4 *.mov *.m4v *.avi *.mkv *.webm"),
                       ("영상", "*.mp4 *.mov *.m4v *.avi *.mkv *.webm"),
                       ("이미지", "*.jpg *.jpeg *.png *.bmp *.webp"),
                       ("모든 파일", "*.*")])
        if f:
            self._set_path(f, persist=True)

    def pick_dir(self):
        d = filedialog.askdirectory()
        if d:
            self._set_path(d, is_dir=True, persist=True)

    def _set_path(self, path, is_dir=None, persist=False, restored=False):
        media_path = Path(path)
        if is_dir is None:
            is_dir = media_path.is_dir()
        self.path.set(path)
        is_video = media_path.is_file() and media_path.suffix.lower() in VIDEO_EXTS
        prefix = "폴더 · " if is_dir else "반복 영상 · " if is_video else "사진 · "
        suffix = " (최근 항목 복원됨)" if restored else ""
        self.path_lbl.config(text=prefix + media_path.name + suffix,
                             foreground=TEXT)
        self._show_thumb(path)
        if persist:
            try:
                save_recent_path(path)
            except OSError:
                pass

    def toggle(self):
        self.stop() if self.running else self.start()

    def start(self):
        path = self.path.get().strip()
        if not path or not Path(path).exists():
            messagebox.showerror("오류", "유효한 사진, 영상 또는 이미지 폴더를 선택하세요.")
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
        source = None
        try:
            w, h, fps = self.width.get(), self.height.get(), self.fps.get()
            source = create_frame_source(path, w, h, fps, self.interval.get())
            with pyvirtualcam.Camera(width=w, height=h, fps=fps) as cam:
                while self.running:
                    cam.send(source.next_frame())
                    cam.sleep_until_next_frame()
        except Exception as e:
            self.error = str(e)
            self.running = False
            self.root.after(0, self._show_error)
        finally:
            if source:
                source.close()

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
    enable_hidpi()
    root = tk.Tk()
    # 실제 DPI에 맞춰 Tk 위젯 스케일 조정 (선명 + 올바른 크기)
    try:
        dpi = root.winfo_fpixels("1i")
        root.tk.call("tk", "scaling", dpi / 72.0)
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
