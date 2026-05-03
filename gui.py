import os
import subprocess
import hashlib
import platform
from datetime import datetime
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, filedialog

from client import ChatClient
from file_utils import read_file_as_bytes
import history_store

DOT_ONLINE  = "#22c55e"
DOT_OFFLINE = "#4b5563"

AVATAR_PALETTE = [
    "#7c5cff","#ec4899","#f97316","#22c55e","#06b6d4",
    "#eab308","#f43f5e","#8b5cf6","#14b8a6","#3b82f6",
]


def _system_font_family():
    s = platform.system()
    if s == "Darwin":  return "SF Pro Display"
    if s == "Windows": return "Segoe UI"
    return "DejaVu Sans"


# Özel Widget'lar

class RoundedButton(tk.Frame):
    def __init__(self, parent, text, command=None, variant="primary",
                 radius=10, pad_x=18, pad_y=10, canvas_bg=None, **kwargs):
        COLORS = {
            "primary":   {"bg":"#6366f1","hover":"#7c7ff5","press":"#4f46e5","fg":"#ffffff"},
            "secondary": {"bg":"#1c2029","hover":"#252b36","press":"#161b24","fg":"#ececf1"},
            "ghost":     {"bg":"#13171f","hover":"#161b25","press":"#0f1218","fg":"#9aa3b2"},
        }
        self._colors = COLORS.get(variant, COLORS["primary"])
        self._command = command
        ff = _system_font_family()
        self._font = (ff, 11, "bold")
        fnt = tkfont.Font(family=ff, size=11, weight="bold")
        self._btn_w = fnt.measure(text) + pad_x * 2
        self._btn_h = fnt.metrics("linespace") + pad_y * 2
        self._text = text
        self._r = radius

        # Arka plan rengi: canvas_bg veya parent bg
        if canvas_bg is None:
            try:
                canvas_bg = parent.cget("bg")
            except Exception:
                canvas_bg = "#13171f"

        # Frame sarmalayıcı — pack/grid sorununu önler
        frame_bg = kwargs.pop("bg", canvas_bg)
        super().__init__(parent, bg=frame_bg,
                         width=self._btn_w, height=self._btn_h, **kwargs)
        self.pack_propagate(False)

        self._canvas = tk.Canvas(
            self,
            width=self._btn_w, height=self._btn_h,
            highlightthickness=0, bd=0,
            bg=frame_bg,
            cursor="hand2"
        )
        self._canvas.pack(fill="both", expand=True)

        self.after(10, lambda: self._draw(self._colors["bg"]))

        self._canvas.bind("<Enter>",           lambda e: self._draw(self._colors["hover"]))
        self._canvas.bind("<Leave>",           lambda e: self._draw(self._colors["bg"]))
        self._canvas.bind("<ButtonPress-1>",   lambda e: self._draw(self._colors["press"]))
        self._canvas.bind("<ButtonRelease-1>",
                          lambda e: (self._draw(self._colors["hover"]),
                                     self._command() if self._command else None))

    def _draw(self, bg):
        c = self._canvas
        c.delete("all")
        r, w, h = self._r, self._btn_w, self._btn_h
        pts = [r,0, w-r,0, w,0, w,r, w,h-r, w,h, w-r,h, r,h, 0,h, 0,h-r, 0,r, 0,0]
        c.create_polygon(pts, smooth=True, fill=bg, outline=bg)
        c.create_text(w//2, h//2, text=self._text,
                      fill=self._colors["fg"], font=self._font)


class RoundedEntry(tk.Frame):
    def __init__(self, parent, textvariable=None, show=None, width=260, height=46,
                 bg="#1c2029", fg="#ececf1", border="#1c2029", insert="#ececf1",
                 radius=14, **kwargs):
        super().__init__(parent, bg=parent.cget("bg"), **kwargs)
        self._bg=bg; self._fg=fg; self._border=border
        self._width=width; self._height=height; self._radius=radius
        self.canvas = tk.Canvas(self, width=width, height=height,
                                highlightthickness=0, bd=0, bg=parent.cget("bg"))
        self.canvas.pack()
        self._draw_box()
        self.entry = tk.Entry(self.canvas, textvariable=textvariable, show=show,
                              relief="flat", bd=0, highlightthickness=0,
                              bg=bg, fg=fg, insertbackground=insert,
                              font=(_system_font_family(), 11))
        self.canvas.create_window(18, height//2, anchor="w",
                                  window=self.entry, width=width-36, height=height-20)

    def _draw_box(self):
        self.canvas.delete("all")
        r,w,h = self._radius, self._width, self._height
        pts = [r,0, w-r,0, w,0, w,r, w,h-r, w,h, w-r,h, r,h, 0,h, 0,h-r, 0,r, 0,0]
        self.canvas.create_polygon(pts, smooth=True, fill=self._bg, outline=self._border)

    def get(self):              return self.entry.get()
    def insert(self, i, v):     self.entry.insert(i, v)
    def bind_entry(self, s, f): self.entry.bind(s, f)
    def focus_set(self):        self.entry.focus_set()


# Ana GUI

class ChatGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Şifreli Mesaj ve Dosya Transfer Uygulaması")
        self.root.geometry("1280x820")
        self.root.minsize(1020, 700)

        self.bg_main      = "#0a0c10"
        self.bg_sidebar   = "#0f1218"
        self.bg_header    = "#13171f"
        self.bg_chat      = "#0a0c10"
        self.bg_elevated  = "#171b24"
        self.bg_input     = "#1c2029"
        self.bg_composer  = "#13171f"
        self.row_default  = "#0f1218"
        self.row_hover    = "#161b25"
        self.row_selected = "#1f2531"
        self.text_primary   = "#ececf1"
        self.text_secondary = "#9aa3b2"
        self.text_muted     = "#5d6573"
        self.border  = "#1c2029"
        self.divider = "#161a22"
        self.accent       = "#6366f1"
        self.accent_hover = "#7c7ff5"
        self.accent_press = "#4f46e5"
        self.bubble_in       = "#1c2129"
        self.bubble_out      = "#4f46e5"
        self.bubble_in_text  = "#ececf1"
        self.bubble_out_text = "#ffffff"
        self.success            = "#22c55e"
        self.link               = "#7dd3fc"
        self.scroll_thumb       = "#252b36"
        self.scroll_thumb_hover = "#323847"

        base = _system_font_family()
        self.f_display = base
        self.f_body    = base
        self.root.configure(bg=self.bg_main)

        self.client = ChatClient()
        self.client.set_callbacks(
            on_status=lambda msg: self.root.after(0, self.add_status, msg),
            on_message=lambda sender, message, message_id: self.root.after(
                0, self.handle_incoming_message, sender, message, message_id
            ),
            on_user_list=lambda users: self.root.after(0, self.update_user_list, users),
            on_auth_result=lambda success, msg: self.root.after(0, self.handle_auth_result, success, msg),
            on_file_received=lambda sender, path, transfer_id: self.root.after(
                0, self.handle_file_received, sender, path, transfer_id
            ),
            on_file_progress=lambda to_user, transfer_id, percent, done: self.root.after(
                0, self.handle_file_progress, to_user, transfer_id, percent, done
            ),
            on_message_status=lambda peer, message_id, status: self.root.after(
                0, self.handle_message_status, peer, message_id, status
            ),
            on_file_status=lambda peer, transfer_id, status: self.root.after(
                0, self.handle_file_status, peer, transfer_id, status
            ),
        )

        self.selected_user = None
        self.online_users: set[str] = set()

        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.host_var     = tk.StringVar(value="127.0.0.1")
        self.port_var     = tk.StringVar(value="9999")
        self.message_var  = tk.StringVar()

        self.status_text         = None
        self.chat_title_label    = None
        self.chat_subtitle_label = None
        self.empty_state_frame   = None
        self.conversation_frame  = None
        self.message_entry       = None
        self.chat_list_canvas    = None
        self.chat_list_container = None
        self.messages_canvas     = None
        self.messages_container  = None

        self.file_link_counter            = 0
        self.chat_histories: dict[str, list] = {}
        self.unread_counts:  dict[str, int]  = {}
        self.displayed_users: list[str]      = []
        self.file_bubble_refs: dict          = {}
        self.pending_progress_updates: dict  = {}
        self.progress_update_job             = None
        self.last_list_refresh_progress: dict = {}
        self.received_folder = "received_files"

        self._setup_styles()
        self._build_login_screen()

    def _avatar_color(self, u):
        if not u:
            return AVATAR_PALETTE[0]
        return AVATAR_PALETTE[int(hashlib.md5(u.encode()).hexdigest(), 16) % len(AVATAR_PALETTE)]

    def _draw_avatar(self, canvas, x, y, size, username, font_size=16):
        c = self._avatar_color(username)
        canvas.create_oval(x - 1, y - 1, x + size + 1, y + size + 1, fill=c, outline=c)
        canvas.create_oval(x, y, x + size, y + size, fill=c, outline=c)
        canvas.create_text(
            x + size / 2, y + size / 2,
            text=(username[:1].upper() if username else "?"),
            fill="#ffffff", font=(self.f_display, font_size, "bold")
        )

    def _rounded_rect_polygon(self, canvas, x1, y1, x2, y2, radius=14, **kw):
        pts = [
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1
        ]
        return canvas.create_polygon(pts, smooth=True, **kw)

    def _pretty_username(self, u):
        return (u[:1].upper() + u[1:]) if u else ""

    def _current_time_str(self):
        return datetime.now().strftime("%H:%M")

    def _current_timestamp_str(self):
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def _format_date_separator(self, timestamp_str: str) -> str:
        try:
            dt = datetime.fromisoformat(timestamp_str)
            today = datetime.now().astimezone().date()
            msg_date = dt.date()

            if msg_date == today:
                return "Bugün"
            elif msg_date == (today.fromordinal(today.toordinal() - 1)):
                return "Dün"
            else:
                aylar = [
                    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
                    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"
                ]
                return f"{msg_date.day} {aylar[msg_date.month - 1]} {msg_date.year}"
        except Exception:
            return ""

    def _add_date_separator(self, text: str):
        row = tk.Frame(self.messages_container, bg=self.bg_chat)
        row.pack(fill="x", pady=(10, 6))

        wrap = tk.Frame(row, bg=self.bg_chat)
        wrap.pack()

        lbl = tk.Label(
            wrap,
            text=text,
            bg="#232833",
            fg=self.text_secondary,
            font=(self.f_body, 9, "bold"),
            padx=12,
            pady=4
        )
        lbl.pack()

    def _clear_root(self):
        try:
            self.root.unbind_all("<MouseWheel>")
            self.root.unbind_all("<Button-4>")
            self.root.unbind_all("<Button-5>")
        except Exception:
            pass

        for w in self.root.winfo_children():
            w.destroy()

    def _setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Thin.Vertical.TScrollbar",
            background=self.scroll_thumb,
            troughcolor=self.bg_sidebar,
            bordercolor=self.bg_sidebar,
            arrowcolor=self.scroll_thumb,
            gripcount=0,
            relief="flat",
            arrowsize=8
        )
        style.map(
            "Thin.Vertical.TScrollbar",
            background=[("active", self.scroll_thumb_hover)]
        )

    def _build_login_screen(self):
        self._clear_root()
        outer = tk.Frame(self.root, bg=self.bg_main)
        outer.pack(fill="both", expand=True)
        tk.Frame(outer, bg=self.bg_main, height=36).pack(fill="x")
        center = tk.Frame(outer, bg=self.bg_main)
        center.pack(expand=True)

        brand = tk.Frame(center, bg=self.bg_main)
        brand.pack(pady=(0, 22))
        bi = tk.Canvas(brand, width=64, height=64, bg=self.bg_main, highlightthickness=0, bd=0)
        bi.pack()
        self._rounded_rect_polygon(bi, 4, 4, 60, 60, radius=14, fill=self.accent, outline=self.accent)
        bi.create_oval(20, 20, 44, 44, fill="#ffffff", outline="#ffffff")
        bi.create_oval(26, 26, 38, 38, fill=self.accent, outline=self.accent)
        tk.Label(
            brand, text="Aurora Messenger", bg=self.bg_main,
            fg=self.text_primary, font=(self.f_display, 22, "bold")
        ).pack(pady=(14, 4))
        tk.Label(
            brand, text="Uçtan uca şifreli mesajlaşma ve dosya transferi",
            bg=self.bg_main, fg=self.text_secondary, font=(self.f_body, 11)
        ).pack()

        card = tk.Frame(center, bg=self.bg_elevated, padx=34, pady=30,
                        highlightthickness=1, highlightbackground=self.border)
        card.pack()
        tk.Label(
            card, text="Hesabınıza Giriş Yapın", bg=self.bg_elevated,
            fg=self.text_primary, font=(self.f_display, 18, "bold")
        ).pack(anchor="w")
        tk.Label(
            card, text="Devam etmek için sunucuya bağlanın ve giriş yapın.",
            bg=self.bg_elevated, fg=self.text_secondary, font=(self.f_body, 10)
        ).pack(anchor="w", pady=(4, 18))

        form = tk.Frame(card, bg=self.bg_elevated)
        form.pack()

        for ri, (lbl, var, show) in enumerate([
            ("KULLANICI ADI", self.username_var, None),
            ("ŞİFRE", self.password_var, "•"),
        ]):
            tk.Label(
                form, text=lbl, bg=self.bg_elevated, fg=self.text_secondary,
                font=(self.f_body, 10, "bold")
            ).grid(row=ri * 2, column=0, sticky="w", pady=(0, 6))
            RoundedEntry(
                form, textvariable=var, show=show, width=360, height=48,
                bg=self.bg_input, fg=self.text_primary,
                border=self.border, insert=self.text_primary
            ).grid(row=ri * 2 + 1, column=0, pady=(0, 14))

        net = tk.Frame(form, bg=self.bg_elevated)
        net.grid(row=4, column=0, sticky="w")

        for col, (lbl, var, w) in enumerate([
            ("SUNUCU IP", self.host_var, 240),
            ("PORT", self.port_var, 108),
        ]):
            wrap = tk.Frame(net, bg=self.bg_elevated)
            wrap.grid(row=0, column=col, padx=(0, 12) if col == 0 else 0)
            tk.Label(
                wrap, text=lbl, bg=self.bg_elevated, fg=self.text_secondary,
                font=(self.f_body, 10, "bold")
            ).pack(anchor="w", pady=(0, 6))
            RoundedEntry(
                wrap, textvariable=var, width=w, height=48,
                bg=self.bg_input, fg=self.text_primary,
                border=self.border, insert=self.text_primary
            ).pack()

        btn_row = tk.Frame(card, bg=self.bg_elevated)
        btn_row.pack(pady=(22, 6))
        for txt, cmd, variant in [
            ("Sunucuya Bağlan", self.connect_server, "secondary"),
            ("Kayıt Ol", self.signup, "secondary"),
            ("Giriş Yap", self.login, "primary"),
        ]:
            RoundedButton(
                btn_row, text=txt, command=cmd,
                variant=variant, canvas_bg=self.bg_elevated
            ).pack(side="left", padx=6)

        tk.Label(
            card, text="DURUM GÜNLÜĞÜ", bg=self.bg_elevated, fg=self.text_muted,
            font=(self.f_body, 9, "bold")
        ).pack(anchor="w", pady=(18, 6))
        sbox = tk.Canvas(card, width=520, height=150, highlightthickness=0, bd=0, bg=self.bg_elevated)
        sbox.pack()
        self._rounded_rect_polygon(sbox, 0, 0, 520, 150, radius=14, fill=self.bg_input, outline=self.border)
        self.status_text = tk.Text(
            sbox, bg=self.bg_input, fg=self.text_secondary,
            insertbackground=self.text_primary, relief="flat",
            highlightthickness=0, wrap="word",
            font=(self.f_body, 10), padx=12, pady=12
        )
        sbox.create_window(10, 10, anchor="nw", window=self.status_text, width=500, height=130)
        self.status_text.config(state="disabled")

        tk.Label(
            outer, text="© Aurora Messenger · End-to-end encrypted",
            bg=self.bg_main, fg=self.text_muted, font=(self.f_body, 9)
        ).pack(side="bottom", pady=14)

    def _build_chat_screen(self):
        self._clear_root()
        self.selected_user = None
        self.file_link_counter = 0
        self.chat_histories = {}
        self.unread_counts = {}
        self.displayed_users = []
        self.file_bubble_refs = {}
        self.pending_progress_updates = {}
        self.progress_update_job = None
        self.last_list_refresh_progress = {}

        outer = tk.Frame(self.root, bg=self.bg_main)
        outer.pack(fill="both", expand=True)

        lp = tk.Frame(outer, bg=self.bg_sidebar, width=380)
        lp.pack(side="left", fill="y")
        lp.pack_propagate(False)
        tk.Frame(lp, bg=self.border, width=1).pack(side="right", fill="y")

        lh = tk.Frame(lp, bg=self.bg_header, height=78)
        lh.pack(fill="x")
        lh.pack_propagate(False)
        hi = tk.Frame(lh, bg=self.bg_header)
        hi.pack(fill="both", expand=True, padx=20, pady=18)

        me_cv = tk.Canvas(hi, width=42, height=42, bg=self.bg_header, highlightthickness=0, bd=0)
        me_cv.pack(side="left")
        my_username = getattr(self.client, "username", "") or ""
        self._draw_avatar(me_cv, 0, 0, 42, my_username, font_size=14)

        mt = tk.Frame(hi, bg=self.bg_header)
        mt.pack(side="left", padx=12)
        tk.Label(
            mt, text=self._pretty_username(my_username) or "Sohbetler",
            bg=self.bg_header, fg=self.text_primary, font=(self.f_display, 14, "bold")
        ).pack(anchor="w")
        tk.Label(
            mt, text="çevrimiçi · şifreli kanal",
            bg=self.bg_header, fg=self.success, font=(self.f_body, 9)
        ).pack(anchor="w", pady=(2, 0))

        sb = tk.Frame(lp, bg=self.bg_sidebar, height=46)
        sb.pack(fill="x")
        sb.pack_propagate(False)
        tk.Label(
            sb, text="MESAJLAR", bg=self.bg_sidebar, fg=self.text_muted,
            font=(self.f_body, 9, "bold")
        ).pack(anchor="w", padx=22, pady=14)

        lw = tk.Frame(lp, bg=self.bg_sidebar)
        lw.pack(fill="both", expand=True)
        self.chat_list_canvas = tk.Canvas(lw, bg=self.bg_sidebar, highlightthickness=0, bd=0)
        clsb = ttk.Scrollbar(lw, orient="vertical", command=self.chat_list_canvas.yview, style="Thin.Vertical.TScrollbar")
        self.chat_list_canvas.configure(yscrollcommand=clsb.set)
        clsb.pack(side="right", fill="y")
        self.chat_list_canvas.pack(side="left", fill="both", expand=True)
        self.chat_list_container = tk.Frame(self.chat_list_canvas, bg=self.bg_sidebar)
        self.chat_list_window = self.chat_list_canvas.create_window((0, 0), window=self.chat_list_container, anchor="nw")
        self.chat_list_container.bind(
            "<Configure>",
            lambda e: self.chat_list_canvas.configure(scrollregion=self.chat_list_canvas.bbox("all"))
        )
        self.chat_list_canvas.bind(
            "<Configure>",
            lambda e: self.chat_list_canvas.itemconfig(self.chat_list_window, width=e.width)
        )

        rp = tk.Frame(outer, bg=self.bg_chat)
        rp.pack(side="right", fill="both", expand=True)

        header = tk.Frame(rp, bg=self.bg_header, height=78)
        header.pack(fill="x")
        header.pack_propagate(False)
        hir = tk.Frame(header, bg=self.bg_header)
        hir.pack(fill="both", expand=True, padx=22, pady=14)

        self._chat_header_avatar = tk.Canvas(hir, width=44, height=44, bg=self.bg_header, highlightthickness=0, bd=0)
        self._chat_header_avatar.pack(side="left")

        tb = tk.Frame(hir, bg=self.bg_header)
        tb.pack(side="left", padx=14)
        self.chat_title_label = tk.Label(
            tb, text="", bg=self.bg_header, fg=self.text_primary,
            font=(self.f_display, 15, "bold")
        )
        self.chat_title_label.pack(anchor="w")

        subr = tk.Frame(tb, bg=self.bg_header)
        subr.pack(anchor="w", pady=(2, 0))
        self._sub_dot = tk.Canvas(subr, width=8, height=8, bg=self.bg_header, highlightthickness=0, bd=0)
        self._sub_dot.pack(side="left", pady=(2, 0))
        self._sub_dot.create_oval(0, 0, 8, 8, fill=self.success, outline=self.success)

        self.chat_subtitle_label = tk.Label(
            subr, text="", bg=self.bg_header, fg=self.text_secondary,
            font=(self.f_body, 10)
        )
        self.chat_subtitle_label.pack(side="left", padx=6)

        ha = tk.Frame(hir, bg=self.bg_header)
        ha.pack(side="right")

        RoundedButton(
            ha, text="Çıkış Yap",
            command=self.logout, variant="secondary",
            canvas_bg=self.bg_header
        ).pack(side="right", padx=(8, 0))

        RoundedButton(
            ha, text="Klasörde Göster",
            command=self.show_received_folder, variant="secondary",
            canvas_bg=self.bg_header
        ).pack(side="right")

        tk.Frame(rp, bg=self.divider, height=1).pack(fill="x")

        self.empty_state_frame = tk.Frame(rp, bg=self.bg_chat)
        self.empty_state_frame.pack(fill="both", expand=True)
        self._build_empty_state()

        self.conversation_frame = tk.Frame(rp, bg=self.bg_chat)

        maw = tk.Frame(self.conversation_frame, bg=self.bg_chat)
        maw.pack(fill="both", expand=True)
        self.messages_canvas = tk.Canvas(maw, bg=self.bg_chat, highlightthickness=0, bd=0)
        msb = ttk.Scrollbar(maw, orient="vertical", command=self.messages_canvas.yview, style="Thin.Vertical.TScrollbar")
        self.messages_canvas.configure(yscrollcommand=msb.set)
        msb.pack(side="right", fill="y")
        self.messages_canvas.pack(side="left", fill="both", expand=True)
        self.messages_container = tk.Frame(self.messages_canvas, bg=self.bg_chat)
        self.messages_window = self.messages_canvas.create_window((0, 0), window=self.messages_container, anchor="nw")
        self.messages_container.bind(
            "<Configure>",
            lambda e: self.messages_canvas.configure(scrollregion=self.messages_canvas.bbox("all"))
        )
        self.messages_canvas.bind(
            "<Configure>",
            lambda e: self.messages_canvas.itemconfig(self.messages_window, width=e.width)
        )
        self._bind_message_mousewheel()

        co = tk.Frame(self.conversation_frame, bg=self.bg_composer, height=82)
        co.pack(fill="x")
        co.pack_propagate(False)
        tk.Frame(co, bg=self.divider, height=1).pack(fill="x")

        c = tk.Frame(co, bg=self.bg_composer)
        c.pack(fill="both", expand=True, padx=18, pady=14)
        RoundedButton(
            c, text="＋  Dosya", command=self.send_file,
            variant="secondary", canvas_bg=self.bg_composer
        ).pack(side="left")

        ep = tk.Frame(c, bg=self.bg_input, highlightthickness=1, highlightbackground=self.border)
        ep.pack(side="left", fill="both", expand=True, padx=12)
        self.message_entry = tk.Entry(
            ep, textvariable=self.message_var,
            bg=self.bg_input, fg=self.text_primary, insertbackground=self.text_primary,
            relief="flat", font=(self.f_body, 12), highlightthickness=0, bd=0
        )
        self.message_entry.pack(fill="both", expand=True, ipady=12, padx=14)
        self.message_entry.bind("<Return>", lambda e: self.send_message())

        RoundedButton(
            c, text="Gönder  ➤", command=self.send_message,
            variant="primary", canvas_bg=self.bg_composer
        ).pack(side="right")

        self.status_text = None
        self._show_empty_state()
        self._load_history_peers()

    def _load_history_peers(self):
        me = self.client.username
        if not me:
            return
        for peer in history_store.get_peers_with_history(me):
            self.chat_histories.setdefault(peer, [])
            self.unread_counts.setdefault(peer, 0)
        self.refresh_chat_list()

    def _load_conversation_from_disk(self, peer: str):
        me = self.client.username
        if not me:
            return
        disk = history_store.get_conversation(me, peer)
        if disk:
            self.chat_histories[peer] = disk

    def _build_empty_state(self):
        ic = tk.Canvas(self.empty_state_frame, width=120, height=120,
                       bg=self.bg_chat, highlightthickness=0, bd=0)
        ic.place(relx=0.5, rely=0.42, anchor="center")
        self._rounded_rect_polygon(ic, 16, 18, 104, 86, radius=22, fill=self.bg_elevated, outline=self.bg_elevated)
        self._rounded_rect_polygon(ic, 40, 60, 96, 100, radius=16, fill="#1f2531", outline="#1f2531")
        for cx in (44, 60, 76):
            ic.create_oval(cx - 3, 49, cx + 3, 55, fill=self.text_muted, outline=self.text_muted)
        tk.Label(
            self.empty_state_frame, text="Bir sohbet seçin",
            bg=self.bg_chat, fg=self.text_primary, font=(self.f_display, 22, "bold")
        ).place(relx=0.5, rely=0.58, anchor="center")
        tk.Label(
            self.empty_state_frame,
            text="Sol panelden bir kişi seçerek şifreli sohbete başlayın.",
            bg=self.bg_chat, fg=self.text_secondary, font=(self.f_body, 11)
        ).place(relx=0.5, rely=0.63, anchor="center")

    def _show_empty_state(self):
        self.chat_title_label.config(text="")
        self.chat_subtitle_label.config(text="")
        self._sub_dot.delete("all")
        self._chat_header_avatar.delete("all")
        self.conversation_frame.pack_forget()
        self.empty_state_frame.pack(fill="both", expand=True)

    def _show_conversation_state(self):
        self.empty_state_frame.pack_forget()
        self.conversation_frame.pack(fill="both", expand=True)

    def _visible_users(self) -> list[str]:
        visible = set(self.online_users)
        visible.update(self.chat_histories.keys())
        visible.discard(self.client.username or "")
        return sorted(visible)

    def refresh_chat_list(self):
        if self.chat_list_container is None:
            return
        for child in self.chat_list_container.winfo_children():
            child.destroy()
        self.displayed_users = []
        for user in self._visible_users():
            self.displayed_users.append(user)
            self._create_chat_row(user)

    def _bind_click_recursive(self, widget, callback):
        widget.bind("<Button-1>", callback)
        for child in widget.winfo_children():
            self._bind_click_recursive(child, callback)

    def _set_row_bg(self, widget, color, exclude=None):
        try:
            if exclude is None or widget not in exclude:
                widget.configure(bg=color)
        except Exception:
            pass
        for child in widget.winfo_children():
            self._set_row_bg(child, color, exclude)

    def _get_last_preview(self, user: str) -> str:
        history = self.chat_histories.get(user, [])
        if not history:
            return "Henüz mesaj yok"
        last = history[-1]
        if last["type"] == "text":
            pre = "Sen: " if last["sender"] == "Ben" else ""
            txt = pre + last["content"]
        else:
            pre = "Sen: " if last["sender"] == "Ben" else ""
            txt = (
                pre + f"Dosya gönderiliyor... %{last.get('progress', 0)}"
                if last.get("status") == "sending"
                else pre + f"📎 {last['filename']}"
            )
        return (txt[:38] + "…") if len(txt) > 38 else txt

    def _create_chat_row(self, user: str):
        selected = self.selected_user == user
        is_online = user in self.online_users
        row_bg = self.row_selected if selected else self.bg_sidebar

        row = tk.Frame(self.chat_list_container, bg=row_bg, height=86, cursor="hand2")
        row.pack(fill="x")
        row.pack_propagate(False)
        row.grid_columnconfigure(2, weight=1)

        accent_bar = tk.Frame(row, bg=(self.accent if selected else row_bg), width=3)
        accent_bar.grid(row=0, column=0, sticky="ns")

        av_size = 46
        dot_r = 6
        cv_size = av_size + dot_r + 2
        av = tk.Canvas(row, width=cv_size, height=cv_size, bg=row_bg, highlightthickness=0, bd=0)
        av.grid(row=0, column=1, padx=(12, 10), pady=20, sticky="w")
        self._draw_avatar(av, 0, 0, av_size, user, font_size=15)

        dot_x = av_size - dot_r + 2
        dot_y = av_size - dot_r + 2
        av.create_oval(dot_x - dot_r - 2, dot_y - dot_r - 2, dot_x + dot_r + 2, dot_y + dot_r + 2, fill=row_bg, outline=row_bg)
        av.create_oval(
            dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r,
            fill=DOT_ONLINE if is_online else DOT_OFFLINE,
            outline=DOT_ONLINE if is_online else DOT_OFFLINE
        )

        tw = tk.Frame(row, bg=row_bg)
        tw.grid(row=0, column=2, sticky="nsew", pady=18)
        tw.grid_columnconfigure(0, weight=1)

        tk.Label(
            tw, text=self._pretty_username(user), bg=row_bg, fg=self.text_primary,
            font=(self.f_display, 13, "bold"), anchor="w"
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            tw, text="çevrimiçi" if is_online else "çevrimdışı",
            bg=row_bg, fg=self.success if is_online else self.text_muted,
            font=(self.f_body, 9), anchor="w"
        ).grid(row=1, column=0, sticky="w")
        tk.Label(
            tw, text=self._get_last_preview(user), bg=row_bg, fg=self.text_secondary,
            font=(self.f_body, 10), anchor="w"
        ).grid(row=2, column=0, sticky="w", pady=(2, 0))

        rc = tk.Frame(row, bg=row_bg)
        rc.grid(row=0, column=3, padx=(8, 18), sticky="e")
        unread = self.unread_counts.get(user, 0)
        if unread > 0:
            bc = tk.Canvas(rc, width=24, height=22, bg=row_bg, highlightthickness=0, bd=0)
            bc.pack()
            self._rounded_rect_polygon(bc, 0, 0, 24, 22, radius=11, fill=self.accent, outline=self.accent)
            bc.create_text(12, 11, text=str(unread), fill="#ffffff", font=(self.f_display, 9, "bold"))

        tk.Frame(self.chat_list_container, bg=self.divider, height=1).pack(fill="x", padx=(74, 0))

        exclude = {accent_bar}

        def on_enter(e):
            if self.selected_user != user:
                self._set_row_bg(row, self.row_hover, exclude=exclude)

        def on_leave(e):
            self._set_row_bg(
                row,
                self.row_selected if self.selected_user == user else self.bg_sidebar,
                exclude=exclude
            )

        row.bind("<Enter>", on_enter)
        row.bind("<Leave>", on_leave)
        self._bind_click_recursive(row, lambda e, u=user: self.open_chat(u))

    def update_user_list(self, users: list):
        me = (self.client.username or "").strip().lower()
        new_online = {u.strip().lower() for u in users if u and u.strip().lower() != me}

        went_offline = self.online_users - new_online
        history_peers = set(history_store.get_peers_with_history(me))
        for user in went_offline:
            ram_has = bool(self.chat_histories.get(user))
            disk_has = user in history_peers
            if not ram_has and not disk_has:
                self.chat_histories.pop(user, None)
                self.unread_counts.pop(user, None)
                if self.selected_user == user:
                    self.selected_user = None
                    self._show_empty_state()

        self.online_users = new_online

        for user in new_online:
            self.chat_histories.setdefault(user, [])
            self.unread_counts.setdefault(user, 0)

        self.refresh_chat_list()

    def open_chat(self, user: str):
        self.selected_user = user
        self.unread_counts[user] = 0

        is_online = user in self.online_users
        self.chat_title_label.config(text=self._pretty_username(user))
        self.chat_subtitle_label.config(
            text="çevrimiçi · şifreli sohbet" if is_online else "çevrimdışı · geçmiş mesajlar"
        )
        self._chat_header_avatar.delete("all")
        self._draw_avatar(self._chat_header_avatar, 0, 0, 44, user, font_size=15)
        self._sub_dot.delete("all")
        dc = self.success if is_online else DOT_OFFLINE
        self._sub_dot.create_oval(0, 0, 8, 8, fill=dc, outline=dc)

        self._load_conversation_from_disk(user)
        self.refresh_chat_list()
        self.render_chat_for_selected_user()
        unseen_ids = []
        for item in self.chat_histories.get(user, []):
            if (
                item.get("type") == "text"
                and item.get("sender") == user
                and item.get("message_id")
            ):
                unseen_ids.append(item["message_id"])

        if unseen_ids:
            self.client.send_seen(user, unseen_ids)
        unseen_file_ids = []
        for item in self.chat_histories.get(user, []):
            if (
                item.get("type") == "file"
                and item.get("sender") == user
                and item.get("transfer_id")
            ):
                unseen_file_ids.append(item["transfer_id"])

        if unseen_file_ids:
            self.client.send_file_seen(user, unseen_file_ids)
        self._show_conversation_state()

    def _clear_messages(self):
        if self.messages_container is None:
            return
        for child in self.messages_container.winfo_children():
            child.destroy()
        self.file_bubble_refs = {}

    def _scroll_messages_to_bottom(self):
        self.root.after(50, lambda: self.messages_canvas.yview_moveto(1.0))

    def render_chat_for_selected_user(self):
        if self.messages_container is None:
            return

        self._clear_messages()
        tk.Frame(self.messages_container, bg=self.bg_chat, height=12).pack(fill="x")

        last_separator = None

        if self.selected_user and self.selected_user in self.chat_histories:
            for item in self.chat_histories[self.selected_user]:
                item_timestamp = item.get("timestamp", "")
                current_separator = self._format_date_separator(item_timestamp) if item_timestamp else ""

                if current_separator and current_separator != last_separator:
                    self._add_date_separator(current_separator)
                    last_separator = current_separator

                if item["type"] == "text":
                    self._add_bubble(
                        sender=item["sender"],
                        content=item.get("content", ""),
                        path={
                            "time": item.get("time", ""),
                            "msg_status": item.get("status"),
                            "outgoing": item.get("sender") == "Ben"
                        }
                    )
                else:
                    self._add_bubble(
                        sender=item["sender"],
                        is_file=True,
                        filename=item["filename"],
                        path={
                            "path": item.get("path"),
                            "progress": item.get("progress", 100),
                            "status": item.get("status", "done"),
                            "time": item.get("time", ""),
                            "transfer_id": item.get("transfer_id"),
                            "outgoing": item.get("sender") == "Ben"
                        }
                    )

        tk.Frame(self.messages_container, bg=self.bg_chat, height=12).pack(fill="x")
        self._scroll_messages_to_bottom()

    def send_message(self):
        if not self.selected_user:
            messagebox.showwarning("Uyarı", "Önce bir sohbet seçin.")
            return

        text = self.message_var.get().strip()
        if not text:
            messagebox.showwarning("Uyarı", "Boş mesaj gönderilemez.")
            return

        message_id = self.client.send_message(self.selected_user, text)
        if message_id:
            item = {
                "type": "text",
                "sender": "Ben",
                "content": text,
                "time": self._current_time_str(),
                "timestamp": self._current_timestamp_str(),
                "message_id": message_id,
                "status": "sending"
            }
            self.chat_histories.setdefault(self.selected_user, []).append(item)
            history_store.append_message(
                self.client.username,
                self.selected_user,
                "Ben",
                text,
                message_id=message_id,
                status="sending"
            )
            self.render_chat_for_selected_user()
            self.refresh_chat_list()
            self.message_var.set("")

    def send_file(self):
        if not self.selected_user:
            messagebox.showwarning("Uyarı", "Önce bir sohbet seçin.")
            return

        fp = filedialog.askopenfilename()
        if not fp:
            return

        try:
            filename, file_bytes = read_file_as_bytes(fp)
            transfer_id = self.client.send_file(self.selected_user, filename, file_bytes)

            if transfer_id:
                item = {
                    "type": "file",
                    "sender": "Ben",
                    "filename": filename,
                    "path": fp,
                    "progress": 0,
                    "status": "sending",
                    "time": self._current_time_str(),
                    "timestamp": self._current_timestamp_str(),
                    "transfer_id": transfer_id
                }
                self.chat_histories.setdefault(self.selected_user, []).append(item)
                self.render_chat_for_selected_user()
                self.refresh_chat_list()
                self.add_status(f"Dosya gönderimi başladı: {filename}")
        except Exception as e:
            messagebox.showerror("Dosya Hatası", str(e))

    def handle_incoming_message(self, sender: str, message: str, message_id: str):
        sender = sender.strip().lower()
        self.chat_histories.setdefault(sender, [])
        self.unread_counts.setdefault(sender, 0)

        item = {
            "type": "text",
            "sender": sender,
            "content": message,
            "time": self._current_time_str(),
            "timestamp": self._current_timestamp_str(),
            "message_id": message_id
        }
        self.chat_histories[sender].append(item)

        history_store.append_message(
            self.client.username,
            sender,
            sender,
            message,
            message_id=message_id
        )

        if self.selected_user == sender:
            self.render_chat_for_selected_user()
            self.client.send_seen(sender, [message_id])
        else:
            self.unread_counts[sender] += 1

        self.refresh_chat_list()

    def handle_message_status(self, peer: str, message_id: str, status: str):
        peer = peer.strip().lower()
        if peer not in self.chat_histories:
            return

        for item in reversed(self.chat_histories[peer]):
            if (
                    item.get("type") == "text"
                    and item.get("sender") == "Ben"
                    and item.get("message_id") == message_id
            ):
                item["status"] = status
                history_store.update_message_status(
                    self.client.username, peer, message_id, status
                )
                break

        if self.selected_user == peer:
            self.render_chat_for_selected_user()
        self.refresh_chat_list()

    def handle_file_received(self, sender: str, saved_path: str, transfer_id: str):
        sender = sender.strip().lower()
        filename = os.path.basename(saved_path)
        self.chat_histories.setdefault(sender, [])
        self.unread_counts.setdefault(sender, 0)

        item = {
            "type": "file",
            "sender": sender,
            "filename": filename,
            "path": saved_path,
            "progress": 100,
            "status": "done",
            "time": self._current_time_str(),
            "timestamp": self._current_timestamp_str(),
            "transfer_id": transfer_id
        }
        self.chat_histories[sender].append(item)

        history_store.append_file(
            self.client.username,
            sender,
            sender,
            filename,
            saved_path,
            transfer_id=transfer_id,
            status="done"
        )

        self.add_status(f"Dosya kaydedildi: {saved_path}")

        if self.selected_user == sender:
            self.render_chat_for_selected_user()
        else:
            self.unread_counts[sender] += 1

        self.refresh_chat_list()
        messagebox.showinfo("Dosya Alındı", f"Dosya kaydedildi:\n{saved_path}")

    def connect_server(self):
        host = self.host_var.get().strip()
        port = self.port_var.get().strip()
        if not host or not port.isdigit():
            messagebox.showerror("Hata", "Geçerli IP ve port giriniz.")
            return
        try:
            self.client.connect(host, int(port))
        except Exception as e:
            messagebox.showerror("Bağlantı Hatası", str(e))

    def signup(self):
        u = self.username_var.get().strip()
        p = self.password_var.get().strip()
        if not u or not p:
            messagebox.showwarning("Uyarı", "Kullanıcı adı ve şifre boş olamaz.")
            return
        self.client.signup(u, p)

    def login(self):
        u = self.username_var.get().strip()
        p = self.password_var.get().strip()
        if not u or not p:
            messagebox.showwarning("Uyarı", "Kullanıcı adı ve şifre boş olamaz.")
            return
        self.client.login(u, p)

    def logout(self):
        try:
            self.client.disconnect()
        except Exception:
            pass

        self.selected_user = None
        self.online_users = set()
        self.chat_histories = {}
        self.unread_counts = {}
        self.displayed_users = []
        self.file_bubble_refs = {}
        self.pending_progress_updates = {}
        self.progress_update_job = None
        self.last_list_refresh_progress = {}

        self.username_var.set("")
        self.password_var.set("")
        self.message_var.set("")
        self.host_var.set("127.0.0.1")
        self.port_var.set("9999")

        self._build_login_screen()

    def handle_auth_result(self, success: bool, message: str):
        self.add_status(message)
        if success:
            username = self.username_var.get().strip()
            removed = history_store.prune_old_entries(username)
            if removed:
                self.add_status(f"Geçmişten {removed} eski kayıt temizlendi.")
            self.client.register_session(username)
            self._build_chat_screen()

    def handle_file_progress(self, to_user, transfer_id, percent, done):
        self.pending_progress_updates[(to_user, transfer_id)] = (percent, done)
        if self.progress_update_job is None:
            self.progress_update_job = self.root.after(120, self._apply_progress_updates)

    def _update_single_file_bubble(self, to_user, transfer_id):
        key = (to_user, transfer_id)
        ref = self.file_bubble_refs.get(key)
        if not ref:
            return

        item_data = next(
            (
                i for i in reversed(self.chat_histories.get(to_user, []))
                if i.get("type") == "file"
                   and i.get("sender") == "Ben"
                   and i.get("transfer_id") == transfer_id
            ),
            None
        )
        if not item_data:
            return

        old = ref["canvas"]
        parent = ref["parent"]
        if old and old.winfo_exists():
            old.destroy()

        nc = self._draw_bubble_canvas(
            parent, "", True, item_data.get("filename"),
            {
                "path": item_data.get("path"),
                "progress": item_data.get("progress", 100),
                "status": item_data.get("status", "done"),
                "time": item_data.get("time", ""),
                "transfer_id": item_data.get("transfer_id"),
                "outgoing": True
            },
            ref["bg_color"], ref["text_color"], ref["label_color"], ref["link_color"]
        )
        ref["canvas"] = nc
        parent.update_idletasks()

    def _apply_progress_updates(self):
        self.progress_update_job = None
        updates = dict(self.pending_progress_updates)
        self.pending_progress_updates.clear()
        refresh_needed = False

        for (to_user, transfer_id), (percent, done) in updates.items():
            if to_user not in self.chat_histories:
                continue

            target = next(
                (
                    i for i in reversed(self.chat_histories[to_user])
                    if i.get("type") == "file"
                       and i.get("sender") == "Ben"
                       and i.get("transfer_id") == transfer_id
                ),
                None
            )
            if not target:
                continue

            old_status = target.get("status", "sending")
            target["progress"] = percent

            if old_status not in ("delivered", "seen"):
                target["status"] = "sending"

            if self.selected_user == to_user:
                self._update_single_file_bubble(to_user, transfer_id)

            lb = self.last_list_refresh_progress.get((to_user, transfer_id), -1)
            cb = percent // 10
            if done or cb != lb or old_status != target.get("status"):
                self.last_list_refresh_progress[(to_user, transfer_id)] = cb
                refresh_needed = True

        if refresh_needed:
            self.refresh_chat_list()

    def handle_file_status(self, peer: str, transfer_id: str, status: str):
        peer = peer.strip().lower()
        if peer not in self.chat_histories:
            return

        for item in reversed(self.chat_histories[peer]):
            if (
                    item.get("type") == "file"
                    and item.get("sender") == "Ben"
                    and item.get("transfer_id") == transfer_id
            ):
                item["status"] = status
                history_store.update_file_status(
                    self.client.username, peer, transfer_id, status
                )
                break

        if self.selected_user == peer:
            self.render_chat_for_selected_user()
        self.refresh_chat_list()

    def add_status(self, message: str):
        if self.status_text is None:
            return
        self.status_text.config(state="normal")
        self.status_text.insert(tk.END, f"{message}\n")
        self.status_text.config(state="disabled")
        self.status_text.see(tk.END)

    def show_received_folder(self):
        u = self.client.username or "unknown_user"
        fp = os.path.abspath(os.path.join(self.received_folder, u))
        os.makedirs(fp, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(fp)
            else:
                subprocess.Popen(["open", fp])
        except Exception as e:
            messagebox.showerror("Klasör Açma Hatası", str(e))

    def open_file(self, path: str):
        if not os.path.exists(path):
            messagebox.showerror("Hata", f"Dosya bulunamadı:\n{path}")
            return
        try:
            if os.name == "nt":
                os.startfile(path)
            else:
                subprocess.Popen(["open", path])
        except Exception as e:
            messagebox.showerror("Dosya Açma Hatası", str(e))

    def _is_pointer_over_messages_area(self) -> bool:
        if self.messages_canvas is None:
            return False

        try:
            x_root = self.root.winfo_pointerx()
            y_root = self.root.winfo_pointery()

            x1 = self.messages_canvas.winfo_rootx()
            y1 = self.messages_canvas.winfo_rooty()
            x2 = x1 + self.messages_canvas.winfo_width()
            y2 = y1 + self.messages_canvas.winfo_height()

            return x1 <= x_root <= x2 and y1 <= y_root <= y2
        except Exception:
            return False

    def _can_scroll_messages(self) -> bool:
        if self.messages_canvas is None or self.messages_container is None:
            return False

        try:
            self.messages_container.update_idletasks()
            content_height = self.messages_container.winfo_reqheight()
            canvas_height = self.messages_canvas.winfo_height()
            return content_height > canvas_height + 5
        except Exception:
            return False

    def _scroll_messages_units(self, units: int):
        if self.messages_canvas is None:
            return
        if not self._is_pointer_over_messages_area():
            return
        if not self._can_scroll_messages():
            return

        first, last = self.messages_canvas.yview()

        if units < 0 and first <= 0.0:
            return
        if units > 0 and last >= 1.0:
            return

        self.messages_canvas.yview_scroll(units, "units")

    def _on_mousewheel_messages_windows(self, event):
        if event.delta > 0:
            self._scroll_messages_units(-1)
        elif event.delta < 0:
            self._scroll_messages_units(1)

    def _on_mousewheel_messages_macos(self, event):
        if event.delta > 0:
            self._scroll_messages_units(-1)
        elif event.delta < 0:
            self._scroll_messages_units(1)

    def _on_mousewheel_messages_linux_up(self, event):
        self._scroll_messages_units(-1)

    def _on_mousewheel_messages_linux_down(self, event):
        self._scroll_messages_units(1)

    def _bind_message_mousewheel(self):
        system = platform.system()

        if system == "Windows":
            self.root.bind_all("<MouseWheel>", self._on_mousewheel_messages_windows)
        elif system == "Darwin":
            self.root.bind_all("<MouseWheel>", self._on_mousewheel_messages_macos)
        else:
            self.root.bind_all("<Button-4>", self._on_mousewheel_messages_linux_up)
            self.root.bind_all("<Button-5>", self._on_mousewheel_messages_linux_down)

    def _add_bubble(self, sender, content="", is_file=False, filename=None, path=None):
        row = tk.Frame(self.messages_container, bg=self.bg_chat)
        row.pack(fill="x", padx=22, pady=4)
        if sender == "Ben":
            self._render_outgoing_bubble(row, sender, content, is_file, filename, path)
        else:
            self._render_incoming_bubble(row, sender, content, is_file, filename, path)

    def _render_incoming_bubble(self, row, sender, content, is_file, filename, path):
        av = tk.Canvas(row, width=34, height=34, bg=self.bg_chat, highlightthickness=0, bd=0)
        av.pack(side="left", anchor="s", padx=(0, 8), pady=(0, 2))
        self._draw_avatar(av, 0, 0, 34, sender, font_size=12)

        bh = tk.Frame(row, bg=self.bg_chat)
        bh.pack(side="left", anchor="w")
        bc = self._draw_bubble_canvas(
            bh, content, is_file, filename, path,
            self.bubble_in, self.bubble_in_text,
            self.text_secondary, self.link
        )
        if is_file and sender == "Ben":
            self.file_bubble_refs[(self.selected_user, filename)] = {
                "parent": bh,
                "canvas": bc,
                "sender": sender,
                "bg_color": self.bubble_in,
                "text_color": self.bubble_in_text,
                "label_color": self.text_secondary,
                "link_color": self.link
            }

    def _render_outgoing_bubble(self, row, sender, content, is_file, filename, path):
        bh = tk.Frame(row, bg=self.bg_chat)
        bh.pack(side="right", anchor="e")
        bc = self._draw_bubble_canvas(
            bh, content, is_file, filename, path,
            self.bubble_out, self.bubble_out_text,
            "#dcd6ff", "#ffffff"
        )
        if is_file and sender == "Ben":
            transfer_id = path.get("transfer_id") if isinstance(path, dict) else filename
            self.file_bubble_refs[(self.selected_user, transfer_id)] = {
                "parent": bh,
                "canvas": bc,
                "sender": sender,
                "bg_color": self.bubble_out,
                "text_color": self.bubble_out_text,
                "label_color": "#dcd6ff",
                "link_color": "#ffffff"
            }

    def _draw_bubble_canvas(self, parent, content, is_file, filename, path,
                            bg_color, text_color, label_color, link_color):
        MAX_W = 460
        PX = 16
        PY = 11
        RAD = 14
        time_text = path.get("time", "") if isinstance(path, dict) else ""

        def _m(text, font):
            lbl = tk.Label(parent, text=text, font=font, wraplength=MAX_W, justify="left")
            lbl.update_idletasks()
            w, h = lbl.winfo_reqwidth(), lbl.winfo_reqheight()
            lbl.destroy()
            return w, h

        if is_file:
            lw, lh = _m("📎  Dosya", (self.f_body, 9, "bold"))
            fw, fh = _m(filename or "", (self.f_body, 11, "underline"))
            tw, th = _m(time_text, (self.f_body, 8)) if time_text else (0, 0)
            status = path.get("status", "done") if isinstance(path, dict) else "done"
            extra_h = (26 if status == "sending" else 0) + (th + 6 if time_text else 0)
            iw = max(lw, fw, tw, 220)
            ih = lh + 6 + fh + extra_h
        else:
            cw, ch = _m(content or "", (self.f_body, 11))
            tw, th = _m(time_text, (self.f_body, 8)) if time_text else (0, 0)
            iw = max(cw, tw, 100)
            ih = ch + (th + 6 if time_text else 0)

        CW = int(iw + PX * 2)
        CH = int(ih + PY * 2)

        c = tk.Canvas(parent, width=CW, height=CH, bg=self.bg_chat,
                      highlightthickness=0, bd=0)
        c.pack()

        self._rounded_rect_polygon(c, 0, 0, CW, CH, radius=RAD,
                                   fill=bg_color, outline=bg_color)

        if is_file:
            _, lh2 = _m("📎  Dosya", (self.f_body, 9, "bold"))
            _, fh2 = _m(filename or "", (self.f_body, 11, "underline"))

            c.create_text(
                PX, PY,
                text="📎  Dosya",
                anchor="nw",
                fill=label_color,
                font=(self.f_body, 9, "bold")
            )

            fid = c.create_text(
                PX, PY + lh2 + 6,
                text=filename or "",
                anchor="nw",
                fill=link_color,
                font=(self.f_body, 11, "underline"),
                width=iw
            )

            cy = PY + lh2 + 6 + fh2 + 8

            if isinstance(path, dict) and path.get("status") == "sending":
                p2 = path.get("progress", 0)

                c.create_text(
                    PX, cy,
                    text=f"Gönderiliyor... %{p2}",
                    anchor="nw",
                    fill=label_color,
                    font=(self.f_body, 9)
                )

                by = cy + 16
                bw = iw

                c.create_rectangle(PX, by, PX + bw, by + 8,
                                   fill="#2a3140", outline="#2a3140")
                c.create_rectangle(PX, by, PX + int(bw * (p2 / 100)), by + 8,
                                   fill=self.accent, outline=self.accent)

                cy = by + 14

            if time_text:
                status_icon = ""
                if isinstance(path, dict) and path.get("outgoing"):
                    file_status = path.get("status")
                    if file_status == "sending":
                        status_icon = "  🕒"
                    elif file_status == "delivered":
                        status_icon = "  ✓"
                    elif file_status == "seen":
                        status_icon = "  ✓✓"

                c.create_text(
                    PX, cy,
                    text=f"{time_text}{status_icon}",
                    anchor="nw",
                    fill=label_color,
                    font=(self.f_body, 8)
                )

            rp = path.get("path") if isinstance(path, dict) else (path if isinstance(path, str) else None)
            if rp and (not isinstance(path, dict) or path.get("status") == "done"):
                c.tag_bind(fid, "<Enter>", lambda e: c.configure(cursor="hand2"))
                c.tag_bind(fid, "<Leave>", lambda e: c.configure(cursor=""))
                c.tag_bind(fid, "<Button-1>", lambda e, p=rp: self.open_file(p))

        else:
            _, ch2 = _m(content or "", (self.f_body, 11))

            c.create_text(
                PX, PY,
                text=content or "",
                anchor="nw",
                fill=text_color,
                font=(self.f_body, 11),
                width=iw
            )

            if time_text:
                status_icon = ""
                if isinstance(path, dict) and path.get("outgoing"):
                    msg_status = path.get("msg_status")
                    if msg_status == "sending":
                        status_icon = "  🕒"
                    elif msg_status == "delivered":
                        status_icon = "  ✓"
                    elif msg_status == "seen":
                        status_icon = "  ✓✓"

                c.create_text(
                    PX, PY + ch2 + 6,
                    text=f"{time_text}{status_icon}",
                    anchor="nw",
                    fill=label_color,
                    font=(self.f_body, 8)
                )

        return c

if __name__ == "__main__":
    root = tk.Tk()
    app  = ChatGUI(root)
    root.mainloop()