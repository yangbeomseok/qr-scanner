import tkinter as tk
import ctypes
import re
import webbrowser
import threading
import numpy as np
import cv2
from PIL import Image, ImageGrab, ImageTk

# High-DPI awareness
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# --- White Theme ---
BG = "#f5f5f7"
BG_CARD = "#ffffff"
BG_IMAGE = "#eef0f4"
BORDER = "#e0e0e6"
ACCENT = "#4a6cf7"
ACCENT_HOVER = "#3b5de7"
ACCENT_LIGHT = "#eef1ff"
TEXT_PRIMARY = "#1d1d1f"
TEXT_SECONDARY = "#6e6e73"
TEXT_DIM = "#aaabb3"
URL_COLOR = "#0066cc"
URL_HOVER = "#0040a0"
SUCCESS = "#34c759"
SUCCESS_BG = "#eafbf0"
WARNING = "#ff9500"
WARNING_BG = "#fff8ee"
ERROR_COLOR = "#ff3b30"
SCAN_LINE = "#4a6cf7"
SHADOW = "#d8d8dc"
FONT = "Pretendard"

URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^~\[\]`]+')


def round_rect(canvas, x1, y1, x2, y2, radius=20, **kwargs):
    points = [
        x1 + radius, y1, x2 - radius, y1, x2 - radius, y1,
        x2, y1, x2, y1 + radius, x2, y2 - radius, x2, y2 - radius,
        x2, y2, x2 - radius, y2, x1 + radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class ScanAnimator:
    def __init__(self, canvas, width, height):
        self.canvas = canvas
        self.width = width
        self.height = height
        self.line_y = 0
        self.running = False
        self.items = []

    def start(self):
        self.running = True
        self.line_y = 0
        self._animate()

    def stop(self):
        self.running = False
        for item in self.items:
            self.canvas.delete(item)
        self.items.clear()

    def _animate(self):
        if not self.running:
            return
        for item in self.items:
            self.canvas.delete(item)
        self.items.clear()

        for i in range(3):
            spread = (3 - i) * 5
            stipple = ["gray12", "gray25", "gray50"][i]
            gid = self.canvas.create_rectangle(
                20, self.line_y - spread, self.width - 20, self.line_y + spread,
                fill=ACCENT_LIGHT, outline="", stipple=stipple)
            self.items.append(gid)

        lid = self.canvas.create_line(
            20, self.line_y, self.width - 20, self.line_y,
            fill=ACCENT, width=2)
        self.items.append(lid)

        bsize, bw = 30, 3
        for cx, cy in [(25, 25), (self.width - 25, 25),
                        (25, self.height - 25), (self.width - 25, self.height - 25)]:
            dx = 1 if cx < self.width // 2 else -1
            dy = 1 if cy < self.height // 2 else -1
            self.items.append(self.canvas.create_line(
                cx, cy, cx + dx * bsize, cy, fill=ACCENT, width=bw))
            self.items.append(self.canvas.create_line(
                cx, cy, cx, cy + dy * bsize, fill=ACCENT, width=bw))

        self.line_y += 4
        if self.line_y > self.height:
            self.line_y = 0
        self.canvas.after(16, self._animate)


class QRReaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("QR Scanner")
        self.root.geometry("520x740")
        self.root.minsize(440, 640)
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        # Set window icon
        import sys, os
        if getattr(sys, 'frozen', False):
            base = sys._MEIPASS
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        ico_path = os.path.join(base, 'icon.ico')
        if not os.path.exists(ico_path):
            ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.ico')
        if os.path.exists(ico_path):
            self.root.iconbitmap(ico_path)

        self.photo = None
        self.animator = None
        self.result_widgets = []

        self._build_ui()
        self._bind_keys()
        self.root.focus_force()

    def _build_ui(self):
        # --- Header ---
        header = tk.Frame(self.root, bg=BG, pady=18)
        header.pack(fill="x")

        tk.Label(header, text="QR Scanner", font=(FONT, 24, "bold"),
                 fg=TEXT_PRIMARY, bg=BG).pack()

        self.subtitle = tk.Label(
            header, text="Ctrl+V \ub85c \uc2a4\ud06c\ub9b0\uc0f7\uc744 \ubd99\uc5ec\ub123\uc73c\uc138\uc694",
            font=(FONT, 11), fg=TEXT_SECONDARY, bg=BG)
        self.subtitle.pack(pady=(2, 0))

        # --- Image Area (rounded card) ---
        self.img_card = tk.Canvas(self.root, bg=BG, highlightthickness=0, height=350)
        self.img_card.pack(fill="x", padx=20, pady=(0, 12))

        self.canvas = tk.Canvas(self.img_card, bg=BG_IMAGE, highlightthickness=0)
        self.img_card.bind("<Configure>", self._on_img_card_resize)
        self._showing_placeholder = True
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # --- Status pill ---
        self.status_canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0, height=36)
        self.status_canvas.pack(fill="x", padx=30, pady=(0, 8))
        self._set_status("", "\ub300\uae30 \uc911...", TEXT_SECONDARY)

        # --- Results Area (rounded card) ---
        self.results_outer = tk.Canvas(self.root, bg=BG, highlightthickness=0)
        self.results_outer.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        self.results_inner = tk.Frame(self.results_outer, bg=BG_CARD)
        self.results_outer.bind("<Configure>", self._on_results_resize)

        tk.Label(self.results_inner, text="\uc2a4\uce94 \uacb0\uacfc", font=(FONT, 10, "bold"),
                 fg=TEXT_DIM, bg=BG_CARD, anchor="w").pack(fill="x", pady=(0, 4))

        self.results_container = tk.Frame(self.results_inner, bg=BG_CARD)
        self.results_container.pack(fill="both", expand=True)

        self.empty_label = tk.Label(
            self.results_container,
            text="\uc544\uc9c1 \uc2a4\uce94\ub41c QR \ucf54\ub4dc\uac00 \uc5c6\uc2b5\ub2c8\ub2e4",
            font=(FONT, 10), fg=TEXT_DIM, bg=BG_CARD)
        self.empty_label.pack(pady=30)

        # --- Bottom Bar ---
        bottom = tk.Frame(self.root, bg=BG, pady=10)
        bottom.pack(fill="x", padx=20)

        self.clear_canvas = tk.Canvas(bottom, bg=BG, highlightthickness=0,
                                      width=110, height=36)
        self.clear_canvas.pack(side="right")
        self._draw_clear_btn()
        self.clear_canvas.bind("<Button-1>", lambda e: self.clear())
        self.clear_canvas.bind("<Enter>", lambda e: self._draw_clear_btn(hover=True))
        self.clear_canvas.bind("<Leave>", lambda e: self._draw_clear_btn(hover=False))

    def _draw_clear_btn(self, hover=False):
        c = self.clear_canvas
        c.delete("all")
        bg = "#d4d4da" if hover else "#e8e8ed"
        round_rect(c, 0, 0, 110, 36, radius=18, fill=bg, outline="")
        c.create_text(55, 18, text="\u21bb  \ucd08\uae30\ud654",
                      font=(FONT, 10, "bold"), fill=TEXT_PRIMARY)
        if hover:
            c.config(cursor="hand2")

    def _on_img_card_resize(self, event):
        c = self.img_card
        c.delete("bg")
        w, h = event.width, 350
        # Shadow
        round_rect(c, 4, 4, w - 1, h - 1, radius=20, fill=SHADOW, outline="", tags="bg")
        # Card
        round_rect(c, 0, 0, w - 5, h - 5, radius=20, fill=BG_IMAGE, outline=BORDER, tags="bg")
        # Place inner canvas
        c.delete("inner_win")
        c.create_window(14, 14, window=self.canvas, anchor="nw",
                        width=w - 33, height=h - 33, tags="inner_win")
        c.tag_raise("inner_win")

    def _on_results_resize(self, event):
        c = self.results_outer
        c.delete("bg")
        w, h = event.width, event.height
        round_rect(c, 4, 4, w - 1, h - 1, radius=20, fill=SHADOW, outline="", tags="bg")
        round_rect(c, 0, 0, w - 5, h - 5, radius=20, fill=BG_CARD, outline=BORDER, tags="bg")
        c.delete("inner_win")
        c.create_window(18, 16, window=self.results_inner, anchor="nw",
                        width=w - 41, height=h - 37, tags="inner_win")
        c.tag_raise("inner_win")

    def _on_canvas_resize(self, event=None):
        if self._showing_placeholder:
            self._draw_placeholder()

    def _draw_placeholder(self):
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 50 or h < 50:
            return
        cx, cy = w // 2, h // 2
        size = 55

        self.canvas.create_rectangle(
            cx - size, cy - size, cx + size, cy + size,
            outline=BORDER, width=2, dash=(8, 5))

        ms = 18
        for dx, dy in [(-1, -1), (1, -1), (-1, 1)]:
            ox = cx + dx * (size - ms // 2 - 4)
            oy = cy + dy * (size - ms // 2 - 4)
            self.canvas.create_rectangle(
                ox - ms // 2, oy - ms // 2, ox + ms // 2, oy + ms // 2,
                outline=TEXT_DIM, width=2)
            self.canvas.create_rectangle(
                ox - ms // 4, oy - ms // 4, ox + ms // 4, oy + ms // 4,
                fill=TEXT_DIM, outline="")

        pw, ph = 90, 32
        round_rect(self.canvas, cx - pw // 2, cy + size + 14,
                   cx + pw // 2, cy + size + 14 + ph,
                   radius=16, fill=ACCENT, outline="")
        self.canvas.create_text(
            cx, cy + size + 14 + ph // 2,
            text="Ctrl+V", font=(FONT, 11, "bold"), fill="white")

    def _bind_keys(self):
        self.root.bind("<Control-v>", self.paste_image)
        self.root.bind("<Control-V>", self.paste_image)

    def paste_image(self, event=None):
        try:
            img = ImageGrab.grabclipboard()
        except Exception:
            self._set_status("\u274c", "\ud074\ub9bd\ubcf4\ub4dc\ub97c \uc77d\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4", ERROR_COLOR)
            return

        if img is None:
            self._set_status("\u26a0", "\ud074\ub9bd\ubcf4\ub4dc\uc5d0 \uc774\ubbf8\uc9c0\uac00 \uc5c6\uc2b5\ub2c8\ub2e4 \u2014 Win+Shift+S로 캡처하세요", WARNING)
            return
        if isinstance(img, list):
            self._set_status("\u26a0", "\ud30c\uc77c\uc774 \uc544\ub2cc \uc2a4\ud06c\ub9b0\uc0f7\uc744 \ubd99\uc5ec\ub123\uc73c\uc138\uc694", WARNING)
            return

        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")

        self._showing_placeholder = False
        self._display_image(img)
        self._set_status("\u26a1", "\uc2a4\uce94 \uc911...", ACCENT)
        self.subtitle.config(text="\ubd84\uc11d \uc911...")

        cw = self.canvas.winfo_width() or 440
        ch = self.canvas.winfo_height() or 300
        self.animator = ScanAnimator(self.canvas, cw, ch)
        self.animator.start()
        threading.Thread(target=self._decode_worker, args=(img,), daemon=True).start()

    def _display_image(self, pil_image):
        display_img = pil_image.copy()
        cw = self.canvas.winfo_width() or 440
        ch = self.canvas.winfo_height() or 300
        display_img.thumbnail((cw, ch), Image.LANCZOS)
        self.photo = ImageTk.PhotoImage(display_img)
        self.canvas.delete("all")
        self.canvas.create_image(cw // 2, ch // 2, image=self.photo, anchor="center")

    def _decode_worker(self, pil_image):
        img_array = np.array(pil_image)
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        detector = cv2.QRCodeDetector()

        retval, decoded_info, points, _ = detector.detectAndDecodeMulti(img_bgr)
        results = [s for s in (decoded_info or []) if s] if retval else []

        if not results:
            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            retval2, decoded_info2, _, _ = detector.detectAndDecodeMulti(binary)
            results = [s for s in (decoded_info2 or []) if s] if retval2 else []

        import time
        time.sleep(0.8)
        self.root.after(0, self._on_decode_complete, results)

    def _on_decode_complete(self, results):
        if self.animator:
            self.animator.stop()
            self.animator = None
        self._clear_results()

        if results:
            count = len(results)
            self._set_status("\u2713", f"QR \ucf54\ub4dc {count}\uac1c \ubc1c\uacac!", SUCCESS)
            self.subtitle.config(text=f"{count}\uac1c\uc758 QR \ucf54\ub4dc\ub97c \uc778\uc2dd\ud588\uc2b5\ub2c8\ub2e4")
            for i, text in enumerate(results):
                self._add_result(i + 1, text)
        else:
            self._set_status("\u26a0", "QR \ucf54\ub4dc\ub97c \ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4", WARNING)
            self.subtitle.config(text="\ub2e4\ub978 \uc2a4\ud06c\ub9b0\uc0f7\uc744 \uc2dc\ub3c4\ud574\ubcf4\uc138\uc694")
            lbl = tk.Label(self.results_container,
                           text="QR \ucf54\ub4dc\uac00 \ud3ec\ud568\ub41c \uc2a4\ud06c\ub9b0\uc0f7\uc744 \ub2e4\uc2dc \uc2dc\ub3c4\ud574\ubcf4\uc138\uc694",
                           font=(FONT, 10), fg=TEXT_DIM, bg=BG_CARD)
            lbl.pack(pady=30)
            self.result_widgets.append(lbl)

    def _add_result(self, index, text):
        is_url = bool(URL_PATTERN.fullmatch(text.strip()))
        card_bg = ACCENT_LIGHT if is_url else "#f7f7f9"

        # Card canvas for rounded bg
        card_h = 120
        card_c = tk.Canvas(self.results_container, bg=BG_CARD,
                           highlightthickness=0, height=card_h)
        card_c.pack(fill="x", pady=(0, 8))
        self.result_widgets.append(card_c)

        def draw_bg(evt=None):
            card_c.delete("cardbg")
            w = card_c.winfo_width()
            round_rect(card_c, 0, 0, w, card_h, radius=16,
                       fill=card_bg, outline=BORDER, tags="cardbg")
            card_c.tag_lower("cardbg")
        card_c.bind("<Configure>", draw_bg)

        inner = tk.Frame(card_c, bg=card_bg)
        card_c.create_window(16, 12, window=inner, anchor="nw")

        # Badge
        top = tk.Frame(inner, bg=card_bg)
        top.pack(fill="x", anchor="w")

        badge_c = tk.Canvas(top, highlightthickness=0, bg=card_bg, width=36, height=22)
        badge_c.pack(side="left")
        round_rect(badge_c, 0, 0, 36, 22, radius=11,
                   fill=ACCENT if is_url else TEXT_DIM, outline="")
        badge_c.create_text(18, 11, text=f"#{index}",
                            font=(FONT, 8, "bold"), fill="white")

        type_text = "URL" if is_url else "\ud14d\uc2a4\ud2b8"
        tk.Label(top, text=f"  {type_text}", font=(FONT, 9, "bold"),
                 fg=ACCENT if is_url else TEXT_SECONDARY, bg=card_bg).pack(side="left")

        # Content
        cf = tk.Frame(inner, bg=card_bg)
        cf.pack(fill="x", pady=(6, 0), anchor="w")

        if is_url:
            content = tk.Label(cf, text=text, font=(FONT, 11, "underline"),
                               fg=URL_COLOR, bg=card_bg, cursor="hand2",
                               anchor="w", wraplength=380, justify="left")
            content.pack(side="left")
            content.bind("<Button-1>", lambda e, u=text: webbrowser.open(u))
            content.bind("<Enter>", lambda e: content.config(fg=URL_HOVER))
            content.bind("<Leave>", lambda e: content.config(fg=URL_COLOR))
        else:
            tk.Label(cf, text=text, font=(FONT, 11), fg=TEXT_PRIMARY,
                     bg=card_bg, anchor="w", wraplength=380,
                     justify="left").pack(side="left")

        # Buttons
        bf = tk.Frame(inner, bg=card_bg)
        bf.pack(fill="x", pady=(8, 0), anchor="w")

        copy_c = tk.Canvas(bf, highlightthickness=0, bg=card_bg, width=70, height=30)
        copy_c.pack(side="left", padx=(0, 6))
        self._draw_pill_btn(copy_c, "\ubcf5\uc0ac", 70, 30, "#e0e7ff", ACCENT)
        copy_c.bind("<Button-1>", lambda e, t=text, c=copy_c: self._copy(t, c))
        copy_c.bind("<Enter>", lambda e: (
            copy_c.delete("all"),
            self._draw_pill_btn(copy_c, "\ubcf5\uc0ac", 70, 30, "#c7d2fe", ACCENT),
            copy_c.config(cursor="hand2")))
        copy_c.bind("<Leave>", lambda e: (
            copy_c.delete("all"),
            self._draw_pill_btn(copy_c, "\ubcf5\uc0ac", 70, 30, "#e0e7ff", ACCENT)))

        if is_url:
            open_c = tk.Canvas(bf, highlightthickness=0, bg=card_bg, width=70, height=30)
            open_c.pack(side="left")
            self._draw_pill_btn(open_c, "\uc5f4\uae30", 70, 30, ACCENT, "white")
            open_c.bind("<Button-1>", lambda e, u=text: webbrowser.open(u))
            open_c.bind("<Enter>", lambda e: (
                open_c.delete("all"),
                self._draw_pill_btn(open_c, "\uc5f4\uae30", 70, 30, ACCENT_HOVER, "white"),
                open_c.config(cursor="hand2")))
            open_c.bind("<Leave>", lambda e: (
                open_c.delete("all"),
                self._draw_pill_btn(open_c, "\uc5f4\uae30", 70, 30, ACCENT, "white")))

    def _draw_pill_btn(self, canvas, text, w, h, bg, fg):
        round_rect(canvas, 0, 0, w, h, radius=15, fill=bg, outline="")
        canvas.create_text(w // 2, h // 2, text=text,
                           font=(FONT, 9, "bold"), fill=fg)

    def _set_status(self, icon, text, color):
        c = self.status_canvas
        c.delete("all")
        c.update_idletasks()
        display = f"  {icon}  {text}" if icon else f"  {text}"

        tmp = c.create_text(0, 0, text=display, font=(FONT, 10), anchor="nw")
        bbox = c.bbox(tmp)
        c.delete(tmp)
        tw = (bbox[2] - bbox[0]) + 28 if bbox else 200

        if color == SUCCESS:
            pill_bg = SUCCESS_BG
        elif color == WARNING:
            pill_bg = WARNING_BG
        elif color == ERROR_COLOR:
            pill_bg = "#fff0f0"
        elif color == ACCENT:
            pill_bg = ACCENT_LIGHT
        else:
            pill_bg = "#f0f0f3"

        round_rect(c, 0, 2, tw, 32, radius=16, fill=pill_bg, outline="")
        c.create_text(tw // 2, 17, text=display, font=(FONT, 10, "bold"), fill=color)

    def _copy(self, text, canvas):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        canvas.delete("all")
        self._draw_pill_btn(canvas, "\u2713 \ubcf5\uc0ac\ub428!", 70, 30, SUCCESS, "white")
        canvas.after(1500, lambda: (
            canvas.delete("all"),
            self._draw_pill_btn(canvas, "\ubcf5\uc0ac", 70, 30, "#e0e7ff", ACCENT)))

    def _clear_results(self):
        for w in self.result_widgets:
            w.destroy()
        self.result_widgets.clear()
        if hasattr(self, 'empty_label') and self.empty_label.winfo_exists():
            self.empty_label.destroy()

    def clear(self):
        self._clear_results()
        self._showing_placeholder = True
        self._draw_placeholder()
        self._set_status("", "\ub300\uae30 \uc911...", TEXT_SECONDARY)
        self.subtitle.config(text="Ctrl+V \ub85c \uc2a4\ud06c\ub9b0\uc0f7\uc744 \ubd99\uc5ec\ub123\uc73c\uc138\uc694")
        self.empty_label = tk.Label(
            self.results_container,
            text="\uc544\uc9c1 \uc2a4\uce94\ub41c QR \ucf54\ub4dc\uac00 \uc5c6\uc2b5\ub2c8\ub2e4",
            font=(FONT, 10), fg=TEXT_DIM, bg=BG_CARD)
        self.empty_label.pack(pady=30)
        if self.animator:
            self.animator.stop()
            self.animator = None


if __name__ == "__main__":
    root = tk.Tk()
    app = QRReaderApp(root)
    root.mainloop()
