import tkinter as tk
from tkinter import filedialog, messagebox, ttk, Menu, Toplevel
import os
import json
import re
import platform
import sys
from PIL import Image, ImageTk
from tkinterdnd2 import DND_FILES, TkinterDnD

# --- 1. 获取当前系统类型 ---
CURRENT_SYSTEM = platform.system()

# --- 2. 跨平台兼容性处理 ---
try:
    if CURRENT_SYSTEM == "Darwin":
        from tkmacosx import Button as MacButton
    else:
        MacButton = tk.Button
except ImportError:
    MacButton = tk.Button

if CURRENT_SYSTEM == "Windows":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass

if CURRENT_SYSTEM == "Windows":
    FONT_TITLE = ("Microsoft YaHei UI", 20, "bold")
    FONT_BODY = ("Microsoft YaHei UI", 10)
    FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")
    FONT_MONO = ("Consolas", 9)
    FONT_BIG_BTN = ("Microsoft YaHei UI", 12, "bold")
    CURSOR_DRAG = "fleur"
    CURSOR_HAND = "hand2"
else:
    FONT_TITLE = ("Avenir Next", 28, "bold")
    FONT_BODY = ("PingFang SC", 11)
    FONT_BOLD = ("PingFang SC", 11, "bold")
    FONT_MONO = ("Menlo", 9)
    FONT_BIG_BTN = ("PingFang SC", 15, "bold")
    CURSOR_DRAG = "closedhand"
    CURSOR_HAND = "pointinghand"

CONFIG_FILE = os.path.join(os.path.expanduser("~"), "Documents", "aoi_stitcher_config.json")

# --- iOS 极简配色 ---
BG_MAIN = "#000000"
SIDEBAR_BG = "#1C1C1E"
ACCENT_BLUE = "#0A84FF"
ACCENT_GREEN = "#32D74B"
ACCENT_RED = "#FF453A"
TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#8E8E93"
INPUT_BG = "#2C2C2E"

# --- 裁剪比例定义 ---
CROP_RATIOS = [
    ("自由", None),
    ("1:1", 1.0),
    ("2:3", 2/3),
    ("3:2", 3/2),
    ("9:16", 9/16),
    ("16:9", 16/9),
    ("4:3", 4/3),
    ("3:4", 3/4),
]


class DraggableTile(tk.Frame):
    def __init__(self, master, image_path, pil_img, index, controller, **kwargs):
        super().__init__(master, bd=0, highlightthickness=0, bg=BG_MAIN, **kwargs)
        self.image_path = image_path
        self.raw_pil = pil_img
        self.index = index
        self.controller = controller
        self.is_dragging = False

        self.inner_frame = tk.Frame(self, bd=0, bg=BG_MAIN, highlightthickness=0)
        self.inner_frame.pack(fill="both", expand=True, padx=2, pady=2)

        self.image_label = tk.Label(self.inner_frame, bd=0, highlightthickness=0, bg=BG_MAIN)
        self.image_label.pack(fill="both", expand=True)

        del_font = ("Arial", 9, "bold") if CURRENT_SYSTEM != "Windows" else ("Arial", 8, "bold")
        self.del_btn = tk.Label(self, text="✕", fg="white", bg="#333", font=del_font,
                                width=2, height=1, cursor=CURSOR_HAND)
        self.del_btn.place(relx=1.0, x=-8, y=8, anchor="ne")
        self.del_btn.bind("<Button-1>", lambda e: self.controller.delete_specific(self.index))
        self.del_btn.bind("<Enter>", lambda e: self.del_btn.config(bg=ACCENT_RED))
        self.del_btn.bind("<Leave>", lambda e: self.del_btn.config(bg="#333"))

        for widget in (self.image_label, self.inner_frame):
            widget.bind("<Button-1>", self.on_click)
            widget.bind("<ButtonPress-1>", self.start_drag, add="+")
            widget.bind("<B1-Motion>", self.do_drag)
            widget.bind("<ButtonRelease-1>", self.stop_drag)
            widget.bind("<Button-3>", self.on_right_click)

    def on_right_click(self, event):
        self.controller.show_crop_menu(self, event)

    def on_click(self, event):
        self.controller.set_selected(self)

    def start_drag(self, event):
        if self.controller.crop_mode:
            return
        self.is_dragging = False
        self.start_mouse_y = event.y_root
        self.start_widget_y = self.winfo_y()
        self.lift()
        self.config(cursor=CURSOR_DRAG)
        self.controller.prepare_magnetic_slots()

    def do_drag(self, event):
        if self.controller.crop_mode:
            return
        delta_y = event.y_root - self.start_mouse_y
        if not self.is_dragging and abs(delta_y) > 2:
            self.is_dragging = True
            self.controller.set_selected(self)

        if self.is_dragging:
            new_y = self.start_widget_y + delta_y
            self.place(y=new_y)
            center_y = new_y + (self.winfo_height() / 2)
            self.controller.preview_magnetic_shift(self, center_y)

    def stop_drag(self, event):
        if self.controller.crop_mode:
            return
        if self.is_dragging:
            self.controller.apply_new_order(self)
        self.is_dragging = False
        self.config(cursor="arrow")
        self.master.after_idle(self.controller.realign_all)


class WatermarkItem(tk.Frame):
    def __init__(self, master, wm_data, controller, **kwargs):
        super().__init__(master, bd=0, highlightthickness=0, bg=BG_MAIN, **kwargs)
        self.wm_data = wm_data
        self.controller = controller
        self.is_dragging = False
        self.is_resizing = False

        self.img_tk = None
        self._load_thumbnail()

        self.label = tk.Label(self, image=self.img_tk, bd=0, bg=BG_MAIN, cursor=CURSOR_HAND)
        self.label.pack()
        self.label.bind("<Button-1>", self.on_click)
        self.label.bind("<ButtonPress-1>", self.start_drag, add="+")
        self.label.bind("<B1-Motion>", self.do_drag)
        self.label.bind("<ButtonRelease-1>", self.stop_drag)

        self.resize_handles = []
        self._create_resize_handles()
        self.hide_handles()

    def _load_thumbnail(self):
        try:
            with Image.open(self.wm_data["path"]) as img:
                thumb = img.convert("RGBA")
                thumb.thumbnail((80, 80), Image.Resampling.LANCZOS)
                self.img_tk = ImageTk.PhotoImage(thumb)
        except:
            pass

    def _create_resize_handles(self):
        handle_size = 8
        corners = ["nw", "ne", "sw", "se"]
        for pos in corners:
            h = tk.Frame(self, width=handle_size, height=handle_size, bg=ACCENT_BLUE, cursor="sizing")
            h.place(anchor=pos)
            h.bind("<Button-1>", lambda e, c=pos: self.start_resize(e, c))
            h.bind("<B1-Motion>", self.do_resize)
            h.bind("<ButtonRelease-1>", self.stop_resize)
            self.resize_handles.append((pos, h))

    def on_click(self, event):
        self.controller.select_watermark(self)
        return "break"

    def start_drag(self, event):
        self.is_dragging = True
        self.controller.select_watermark(self)
        self.start_mouse_x = event.x_root
        self.start_mouse_y = event.y_root
        self.start_x = self.wm_data["x"]
        self.start_y = self.wm_data["y"]
        self.lift()

    def do_drag(self, event):
        if self.is_dragging:
            dx = event.x_root - self.start_mouse_x
            dy = event.y_root - self.start_mouse_y
            self.wm_data["x"] = self.start_x + dx
            self.wm_data["y"] = self.start_y + dy
            self.controller.update_watermark_position(self)

    def stop_drag(self, event):
        self.is_dragging = False

    def start_resize(self, event, corner):
        self.is_resizing = True
        self.resize_corner = corner
        self.start_mouse_x = event.x_root
        self.start_mouse_y = event.y_root
        self.start_scale = self.wm_data["scale"]

    def do_resize(self, event):
        if self.is_resizing:
            dy = event.y_root - self.start_mouse_y
            delta = dy / 100.0
            new_scale = max(0.1, min(3.0, self.start_scale + delta))
            self.wm_data["scale"] = new_scale
            self.controller.update_watermark_position(self)

    def stop_resize(self, event):
        self.is_resizing = False

    def show_handles(self):
        for pos, h in self.resize_handles:
            h.place(anchor=pos)

    def hide_handles(self):
        for pos, h in self.resize_handles:
            h.place_forget()


class WatermarkFolderDialog(tk.Toplevel):
    def __init__(self, controller):
        super().__init__(controller.root)
        self.controller = controller
        self.title("水印文件夹管理")
        self.geometry("400x450")
        self.configure(bg=SIDEBAR_BG)
        self.resizable(False, False)

        x = self.winfo_screenwidth() // 2 - 200
        y = self.winfo_screenheight() // 2 - 225
        self.geometry(f"+{x}+{y}")

        header = tk.Frame(self, bg=SIDEBAR_BG)
        header.pack(fill="x", padx=15, pady=15)
        tk.Label(header, text="水印文件夹", font=FONT_TITLE, fg=TEXT_PRIMARY, bg=SIDEBAR_BG).pack(side="left")
        MacButton(header, text="＋ 新建", bg=ACCENT_BLUE, fg="white", borderless=1,
                  command=self.create_folder).pack(side="right")

        scroll = tk.Scrollbar(self)
        scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        self.folder_list = tk.Frame(self, bg=SIDEBAR_BG, yscrollcommand=scroll.set)
        scroll.config(command=self.folder_list.yview)
        self.folder_list.pack(fill="both", expand=True)
        self._redraw_folders()

    def _redraw_folders(self):
        for w in self.folder_list.winfo_children():
            w.destroy()
        folders = self.controller.config.get("watermark_folders", {"默认": []})
        for name, paths in folders.items():
            self._draw_folder_row(name, paths)

    def _draw_folder_row(self, name, paths):
        row = tk.Frame(self.folder_list, bg="#252527", padx=10, pady=8)
        row.pack(fill="x", pady=2)
        expanded = tk.BooleanVar(value=False)
        arrow = tk.Label(row, text="▶", fg=TEXT_SECONDARY, bg="#252527", font=("Arial", 8), cursor=CURSOR_HAND)
        arrow.pack(side="left", padx=(0, 5))

        def toggle():
            expanded.set(not expanded.get())
            arrow.config(text="▼" if expanded.get() else "▶")
            for w in content.winfo_children():
                w.destroy()
            if expanded.get():
                for p in paths:
                    if os.path.exists(p):
                        fp = tk.Frame(content, bg="#1C1C1E")
                        fp.pack(fill="x", pady=1)
                        tk.Label(fp, text=os.path.basename(p), fg=TEXT_SECONDARY, bg="#1C1C1E",
                                 font=FONT_BODY, anchor="w").pack(side="left", padx=5)
                        tk.Label(fp, text="✕", fg=ACCENT_RED, bg="#1C1C1E", cursor=CURSOR_HAND,
                                 font=("Arial", 9, "bold")).pack(side="right", padx=5)
                        fp.bind("<Button-1>", lambda e, path=p: self.remove_watermark(name, path))
                add_btn = tk.Frame(content, bg="#1C1C1E", cursor=CURSOR_HAND)
                add_btn.pack(fill="x", pady=1)
                tk.Label(add_btn, text="＋ 添加水印", fg=ACCENT_BLUE, bg="#1C1C1E", font=FONT_BODY).pack(padx=10, pady=4)
                add_btn.bind("<Button-1>", lambda e, fn=name: self.add_watermark_to_folder(fn))

        tk.Label(row, text=name, fg=TEXT_PRIMARY, bg="#252527", font=FONT_BOLD, cursor=CURSOR_HAND,
                 width=20, anchor="w").pack(side="left", padx=5)
        row.bind("<Button-1>", lambda e: toggle())
        tk.Label(row, text=f"{len(paths)} 个", fg=TEXT_SECONDARY, bg="#252527", font=FONT_BODY).pack(side="right")

        content = tk.Frame(self.folder_list, bg=SIDEBAR_BG)
        content.pack(fill="x")
        arrow.bind("<Button-1>", lambda e: toggle())

    def create_folder(self):
        dialog = tk.Toplevel(self)
        dialog.configure(bg=SIDEBAR_BG)
        dialog.geometry("250x100")
        dialog.resizable(False, False)
        x = self.winfo_screenwidth() // 2 - 125
        y = self.winfo_screenheight() // 2 - 50
        dialog.geometry(f"+{x}+{y}")
        tk.Label(dialog, text="文件夹名称:", fg=TEXT_PRIMARY, bg=SIDEBAR_BG, font=FONT_BODY).pack(pady=5)
        entry = tk.Entry(dialog, bg=INPUT_BG, fg=TEXT_PRIMARY, insertbackground="white", font=FONT_BODY)
        entry.pack(fill="x", padx=20)
        entry.focus()

        def do_create():
            name = entry.get().strip()
            if name:
                folders = self.controller.config.get("watermark_folders", {})
                if name not in folders:
                    folders[name] = []
                    self.controller.config["watermark_folders"] = folders
                    self.controller.save_settings()
                dialog.destroy()
                self._redraw_folders()

        entry.bind("<Return>", lambda e: do_create())
        MacButton(dialog, text="创建", bg=ACCENT_BLUE, fg="white", borderless=1, command=do_create).pack(pady=10)

    def add_watermark_to_folder(self, folder_name):
        p = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg")])
        if p:
            folders = self.controller.config.get("watermark_folders", {})
            if folder_name in folders and p not in folders[folder_name]:
                folders[folder_name].append(p)
                self.controller.config["watermark_folders"] = folders
                self.controller.save_settings()
                self._redraw_folders()

    def remove_watermark(self, folder_name, path):
        folders = self.controller.config.get("watermark_folders", {})
        if folder_name in folders and path in folders[folder_name]:
            folders[folder_name].remove(path)
            self.controller.config["watermark_folders"] = folders
            self.controller.save_settings()
            self._redraw_folders()


class AoiStitcher:
    def __init__(self, root):
        self.root = root

        if CURRENT_SYSTEM == "Windows" and os.path.exists("logo.ico"):
            try:
                root.iconbitmap("logo.ico")
            except:
                pass

        self.root.title("AoiStitcher Universal")
        self.root.geometry("900x1000")
        self.root.configure(bg=BG_MAIN)

        self.image_paths = []
        self.tile_widgets = []
        self.img_ratios = []
        self.preview_cache = {}
        self.selected_tile = None
        self.last_p_tw = 0
        self.slot_y_coords = []
        self.potential_idx = 0
        self.img_crops = {}

        self.watermarks = []
        self.watermark_mode = "bottom"
        self.selected_watermark = None
        self.watermark_widgets = []
        self.watermark_id_counter = 0

        self.crop_mode = False
        self.crop_tile = None
        self.crop_rect = None
        self.crop_handles = []
        self.crop_handle_drag = None
        self.crop_drag_start = None
        self.crop_rect_orig = None
        self.crop_canvas = None

        self.config = {
            "width": "2000", "spacing": "20", "bottom_h": "250",
            "logo_path": "", "logo_library": [], "logo_scale": 20,
            "logo_offset_x": 0, "logo_offset_y": 0,
            "bg_theme": "White",
            "last_img_dir": os.path.expanduser("~/Desktop"),
            "last_export_dir": os.path.expanduser("~/Desktop"),
            "last_logo_dir": os.path.expanduser("~/Desktop"),
            "watermark_folders": {"默认": []}
        }
        self.bg_map = {
            "White": {"hex": "#FFFFFF", "rgb": (255, 255, 255)},
            "Black": {"hex": "#000000", "rgb": (0, 0, 0)}
        }

        self.load_settings()
        self.setup_ui()
        self.toggle_placeholder()

        self.root.bind("<BackSpace>", self.delete_selected)
        self.root.bind("<Delete>", self.delete_selected)
        self.root.bind("<Escape>", self._on_escape)

    def _on_escape(self, event=None):
        if self.crop_mode:
            self.exit_crop_mode()

    def load_settings(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.config.update(json.load(f))
            except:
                pass

    def save_settings(self):
        self.config.update({
            "width": self.width_entry.get(),
            "spacing": self.spacing_entry.get(),
            "bottom_h": self.bottom_entry.get(),
            "bg_theme": self.bg_var.get()
        })
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False)
            self.update_path_display()
        except Exception as e:
            print(f"Save error: {e}")

    def setup_ui(self):
        self.sidebar = tk.Frame(self.root, bg=SIDEBAR_BG, width=280, padx=25, pady=35)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        edition_text = "波罗苍 Win/Mac"
        tk.Label(self.sidebar, text="AoiStitcher", font=FONT_TITLE, fg=TEXT_PRIMARY, bg=SIDEBAR_BG).pack(anchor="w")
        tk.Label(self.sidebar, text=edition_text, font=FONT_BODY, fg=TEXT_SECONDARY, bg=SIDEBAR_BG).pack(anchor="w", pady=(0, 30))

        self.width_entry = self.create_input("画布总宽 (px)", "width")
        self.spacing_entry = self.create_input("照片间距", "spacing")
        self.bottom_entry = self.create_input("留白高度", "bottom_h")

        tk.Label(self.sidebar, text="画布颜色", fg=TEXT_SECONDARY, bg=SIDEBAR_BG, font=FONT_BODY).pack(anchor="w", pady=(15, 0))
        self.bg_var = tk.StringVar(value=self.config["bg_theme"])
        bg_frame = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
        bg_frame.pack(fill="x", pady=(8, 15))

        for text in ["White", "Black"]:
            tk.Radiobutton(bg_frame, text=text, variable=self.bg_var, value=text, command=self.realign_all,
                          bg=SIDEBAR_BG, fg=TEXT_PRIMARY, selectcolor="#333", activebackground=SIDEBAR_BG,
                          font=FONT_BODY).pack(side="left", padx=(0, 15))

        self.crop_btn_frame = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
        self.crop_btn_frame.pack(fill="x", pady=(0, 10))
        self.crop_btn = MacButton(self.crop_btn_frame, text="✂ 裁剪选中图片", bg="#444", fg="white",
                                   command=self.crop_selected, borderless=1)
        self.crop_btn.pack(fill="x", ipady=8)
        self.crop_btn.pack_forget()

        btn_kwargs = {"bg": ACCENT_BLUE, "fg": "white"}
        if CURRENT_SYSTEM == "Darwin":
            btn_kwargs["borderless"] = 1
        MacButton(self.sidebar, text="＋ 导入照片", command=self.add_images, **btn_kwargs).pack(fill="x", pady=6, ipady=10)

        btn_kwargs["bg"] = "#3A3A3C"
        MacButton(self.sidebar, text="水印 ▾", command=self.show_logo_menu, **btn_kwargs).pack(fill="x", pady=6, ipady=10)

        btn_kwargs["bg"] = "#444"
        MacButton(self.sidebar, text="水印文件夹", command=self.open_watermark_folders, **btn_kwargs).pack(fill="x", pady=6, ipady=10)

        tk.Label(self.sidebar, text="水印模式", fg=TEXT_SECONDARY, bg=SIDEBAR_BG, font=FONT_BODY).pack(anchor="w", pady=(15, 0))
        self.wm_mode_var = tk.StringVar(value=self.watermark_mode)
        mode_frame = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
        mode_frame.pack(fill="x", pady=(8, 15))
        tk.Radiobutton(mode_frame, text="白边模式", variable=self.wm_mode_var, value="bottom",
                       command=self._on_wm_mode_change, bg=SIDEBAR_BG, fg=TEXT_PRIMARY, selectcolor="#333",
                       activebackground=SIDEBAR_BG, font=FONT_BODY).pack(side="left", padx=(0, 10))
        tk.Radiobutton(mode_frame, text="覆盖模式", variable=self.wm_mode_var, value="overlay",
                       command=self._on_wm_mode_change, bg=SIDEBAR_BG, fg=TEXT_PRIMARY, selectcolor="#333",
                       activebackground=SIDEBAR_BG, font=FONT_BODY).pack(side="left")

        self.watermark_list_frame = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
        self.watermark_list_frame.pack(fill="x", pady=(0, 10))

        self.clear_btn = MacButton(self.sidebar, text="清空画布", bg=ACCENT_RED, fg="white",
                                    command=self.clear_all, borderless=1)
        self.clear_btn.pack(fill="x", pady=6, ipady=10)

        export_container = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
        export_container.pack(side="bottom", fill="x", pady=(20, 0))

        exp_kwargs = {"bg": ACCENT_GREEN, "fg": "black", "font": FONT_BIG_BTN}
        if CURRENT_SYSTEM == "Darwin":
            exp_kwargs["borderless"] = 1
        self.exp_btn = MacButton(export_container, text="导出成品", command=self.export_action, **exp_kwargs)
        self.exp_btn.pack(fill="x", ipady=14)

        tk.Label(export_container, text="输出路径", fg=TEXT_PRIMARY, bg=SIDEBAR_BG, font=FONT_BOLD).pack(anchor="w", pady=(15, 5))
        path_box = tk.Frame(export_container, bg="#252527", padx=10, pady=8)
        path_box.pack(fill="x")
        self.path_label = tk.Label(path_box, text="", fg=TEXT_SECONDARY, bg="#252527", font=FONT_MONO, anchor="w")
        self.path_label.pack(side="left", fill="x", expand=True)
        tk.Label(path_box, text="›", fg="#444", bg="#252527", font=("Arial", 12)).pack(side="right")
        self.update_path_display()

        self.stage = tk.Frame(self.root, bg=BG_MAIN)
        self.stage.pack(side="right", fill="both", expand=True)
        self.stage.drop_target_register(DND_FILES)
        self.stage.dnd_bind('<<Drop>>', self.handle_drop)

        self.placeholder = tk.Frame(self.stage, bg="#000000", highlightbackground="#333336", highlightthickness=2)
        self.placeholder_label = tk.Label(self.placeholder, text="📸\n\n拖拽图片到这里\n或点击导入",
                                          fg="#444446", bg="#000000", font=FONT_BIG_BTN, justify="center")
        self.placeholder_label.place(relx=0.5, rely=0.5, anchor="center")

        self.canvas_bg_frame = tk.Frame(self.stage, bd=0)
        self.logo_label = tk.Label(self.stage, bd=0)
        self.stage.bind("<Configure>", lambda e: self.realign_all())

        self.insert_indicator = tk.Frame(self.stage, bg=ACCENT_BLUE, width=3)

        self.crop_toolbar = tk.Frame(self.stage, bg="#1C1C1E", padx=15, pady=8)

    def _on_wm_mode_change(self):
        self.watermark_mode = self.wm_mode_var.get()
        self.realign_all()

    def open_watermark_folders(self):
        WatermarkFolderDialog(self)

    def update_path_display(self):
        path = self.config.get("last_export_dir", "未选择路径")
        display_path = (path[:10] + "..." + path[-15:]) if len(path) > 28 else path
        self.path_label.config(text=f"📁 {display_path}")

    def toggle_placeholder(self):
        if not self.image_paths:
            self.placeholder.place(relx=0.05, rely=0.05, relwidth=0.9, relheight=0.9)
            self.canvas_bg_frame.place_forget()
        else:
            self.placeholder.place_forget()

    def create_input(self, label, key):
        tk.Label(self.sidebar, text=label, fg=TEXT_SECONDARY, bg=SIDEBAR_BG, font=FONT_BODY).pack(anchor="w", pady=(10, 2))
        entry = tk.Entry(self.sidebar, bg=INPUT_BG, fg=TEXT_PRIMARY, insertbackground="white", relief="flat", font=FONT_BODY, borderwidth=5)
        entry.insert(0, self.config[key])
        entry.pack(fill="x", ipady=4)
        entry.bind("<KeyRelease>", lambda e: self.realign_all())
        return entry

    def prepare_magnetic_slots(self):
        self.slot_y_centers = [t.winfo_y() + t.winfo_height() / 2 for t in self.tile_widgets]
        self.slot_y_coords = [t.winfo_y() for t in self.tile_widgets]

    def preview_magnetic_shift(self, dragging_tile, center_y):
        if not self.slot_y_centers:
            return
        distances = [abs(center_y - cy) for cy in self.slot_y_centers]
        new_p_idx = distances.index(min(distances))
        if new_p_idx != self.potential_idx:
            self.potential_idx = new_p_idx
            temp_order = [idx for idx in range(len(self.tile_widgets)) if idx != dragging_tile.index]
            temp_order.insert(self.potential_idx, dragging_tile.index)
            for pos_in_view, tile_idx in enumerate(temp_order):
                target = self.tile_widgets[tile_idx]
                if not getattr(target, 'is_dragging', False):
                    target.place(y=self.slot_y_coords[pos_in_view])
            if self.potential_idx < len(self.slot_y_coords):
                self.insert_indicator.place(x=self.canvas_bg_frame.winfo_x() - 3,
                                           y=self.slot_y_coords[self.potential_idx],
                                           height=dragging_tile.winfo_height())

    def apply_new_order(self, dragging_tile):
        old_idx = dragging_tile.index
        new_idx = self.potential_idx
        self.insert_indicator.place_forget()
        if old_idx != new_idx:
            self.image_paths.insert(new_idx, self.image_paths.pop(old_idx))
            self.tile_widgets.insert(new_idx, self.tile_widgets.pop(old_idx))
            self.img_ratios.insert(new_idx, self.img_ratios.pop(old_idx))
            for i, t in enumerate(self.tile_widgets):
                t.index = i

    def show_logo_menu(self):
        menu = Menu(self.root, tearoff=0, bg=SIDEBAR_BG, fg="black", activebackground=ACCENT_BLUE, font=FONT_BODY)
        folders = self.config.get("watermark_folders", {})
        for fname, fpaths in folders.items():
            sub = Menu(menu, tearoff=0, bg=SIDEBAR_BG, fg="black", activebackground=ACCENT_BLUE, font=FONT_BODY)
            for p in fpaths:
                if os.path.exists(p):
                    sub.add_command(label=os.path.basename(p), command=lambda path=p: self.add_watermark(path))
            if sub.index("end") is not None:
                menu.add_cascade(label=f"📁 {fname}", menu=sub)
            else:
                menu.add_command(label=f"📁 {fname} (空)", state="disabled")
        menu.add_separator()
        menu.add_command(label="🛠  微调位置与尺寸...", command=self.open_logo_settings)
        menu.add_separator()
        menu.add_command(label="＋  上传新水印", command=self.upload_logo)
        menu.add_command(label="✕  清除所有水印", command=self.clear_all_watermarks)
        if self.config["logo_library"]:
            menu.add_separator()
            for path in list(dict.fromkeys(self.config["logo_library"]))[-6:]:
                if os.path.exists(path):
                    menu.add_command(label=f"🕒 {os.path.basename(path)}", command=lambda p=path: self.add_watermark(p))

        try:
            menu.post(self.root.winfo_pointerx(), self.root.winfo_pointery())
        except:
            pass

    def open_logo_settings(self):
        panel = Toplevel(self.root)
        panel.title("水印配置")
        panel.geometry("300x380")
        panel.configure(bg=SIDEBAR_BG)
        panel.resizable(False, False)
        panel.attributes('-topmost', True)

        root_x = self.root.winfo_x()
        root_y = self.root.winfo_y()
        if root_x < 0:
            root_x = 0
        if root_y < 0:
            root_y = 0

        x = root_x + (self.root.winfo_width() - 300) // 2
        y = root_y + (self.root.winfo_height() - 380) // 2
        panel.geometry(f"+{x}+{y}")

        def create_slider(parent, label, key, from_val, to_val):
            tk.Label(parent, text=label, fg=TEXT_SECONDARY, bg=SIDEBAR_BG, font=FONT_BODY).pack(pady=(15, 0))
            s = tk.Scale(parent, from_=from_val, to=to_val, orient="horizontal", bg=SIDEBAR_BG, fg=TEXT_PRIMARY,
                         highlightthickness=0, troughcolor="#333", activebackground=ACCENT_BLUE,
                         command=lambda v: self.update_logo_config(key, v))
            s.set(self.config.get(key, 0))
            s.pack(fill="x", padx=30)
            return s

        create_slider(panel, "Logo 比例 (%)", "logo_scale", 5, 80)
        create_slider(panel, "水平偏移 (左右)", "logo_offset_x", -500, 500)
        create_slider(panel, "垂直偏移 (上下)", "logo_offset_y", -500, 500)

        btn_args = {"bg": "#444", "fg": "white"}
        if CURRENT_SYSTEM == "Darwin":
            btn_args["borderless"] = 1
        MacButton(panel, text="重置位置", command=lambda: self.reset_logo_pos(panel),
                  **btn_args).pack(pady=30, padx=50, fill="x", ipady=8)

    def update_logo_config(self, key, value):
        self.config[key] = int(value)
        self.realign_all()

    def reset_logo_pos(self, panel):
        self.config["logo_offset_x"] = 0
        self.config["logo_offset_y"] = 0
        self.config["logo_scale"] = 20
        self.save_settings()
        panel.destroy()
        self.realign_all()

    def apply_logo(self, path):
        self.config["logo_path"] = path
        self.save_settings()
        self.realign_all()

    def add_watermark(self, path):
        self.watermark_id_counter += 1
        sw = max(self.stage.winfo_width() - 60, 100)
        sh = max(self.stage.winfo_height() - 40, 100)
        tw = int(self.width_entry.get())
        sp = int(self.spacing_entry.get())
        bh = int(self.bottom_entry.get())
        heights = []
        for i, p in enumerate(self.image_paths):
            if p in self.img_crops:
                heights.append(int(self.img_crops[p]["h"]))
            else:
                heights.append(int(tw * self.img_ratios[i]))
        total_h = sum(heights) + (len(heights) - 1) * sp + bh
        scale = min(sw / tw, sh / total_h) if total_h > 0 else 1
        canvas_top_y = (self.stage.winfo_height() - int(total_h * scale)) // 2
        start_x = (self.stage.winfo_width() - int(tw * scale)) // 2

        wm = {
            "id": self.watermark_id_counter,
            "path": path,
            "x": (tw // 2) / scale if scale > 0 else tw // 2,
            "y": (int(total_h * scale) // 2) / scale if scale > 0 else total_h // 2,
            "scale": 0.5
        }
        self.watermarks.append(wm)
        self._add_watermark_widget(wm)
        self.realign_all()

    def _add_watermark_widget(self, wm):
        wmi = WatermarkItem(self.stage, wm, self)
        wmi.place(x=wm["x"], y=wm["y"])
        wmi.bind("<Button-3>", lambda e: self._delete_watermark(wm["id"]))
        self.watermark_widgets.append(wmi)

    def select_watermark(self, wmi):
        if self.selected_watermark:
            self.selected_watermark.hide_handles()
        self.selected_watermark = wmi
        wmi.show_handles()

    def update_watermark_position(self, wmi):
        sw = max(self.stage.winfo_width() - 60, 100)
        sh = max(self.stage.winfo_height() - 40, 100)
        tw = int(self.width_entry.get())
        sp = int(self.spacing_entry.get())
        bh = int(self.bottom_entry.get())
        heights = []
        for i, p in enumerate(self.image_paths):
            if p in self.img_crops:
                heights.append(int(self.img_crops[p]["h"]))
            else:
                heights.append(int(tw * self.img_ratios[i]))
        total_h = sum(heights) + (len(heights) - 1) * sp + bh
        scale = min(sw / tw, sh / total_h) if total_h > 0 else 1
        canvas_top_y = (self.stage.winfo_height() - int(total_h * scale)) // 2
        start_x = (self.stage.winfo_width() - int(tw * scale)) // 2

        wmi.wm_data["x"] = (wmi.winfo_x() - start_x) / scale if scale > 0 else 0
        wmi.wm_data["y"] = (wmi.winfo_y() - canvas_top_y) / scale if scale > 0 else 0

    def _delete_watermark(self, wm_id):
        self.watermarks = [w for w in self.watermarks if w["id"] != wm_id]
        for w in self.watermark_widgets:
            if w.wm_data["id"] == wm_id:
                w.destroy()
        self.watermark_widgets = [w for w in self.watermark_widgets if w.wm_data["id"] != wm_id]
        if self.selected_watermark and self.selected_watermark.wm_data["id"] == wm_id:
            self.selected_watermark = None

    def clear_all_watermarks(self):
        for w in self.watermark_widgets:
            w.destroy()
        self.watermarks = []
        self.watermark_widgets = []
        self.selected_watermark = None

    def crop_selected(self):
        if self.selected_tile:
            self.enter_crop_mode(self.selected_tile)

    def show_crop_menu(self, tile, event):
        menu = Menu(self.root, tearoff=0)
        for label, val in CROP_RATIOS:
            menu.add_command(label=f"裁剪 ({label})", command=lambda r=val, lbl=label: self._start_crop_with_ratio(tile, r, lbl))
        menu.add_separator()
        menu.add_command(label="清除裁剪", command=lambda: self._clear_crop(tile))
        try:
            menu.post(event.x_root, event.y_root)
        except:
            pass

    def _start_crop_with_ratio(self, tile, ratio, label):
        self.set_selected(tile)
        self.enter_crop_mode(tile, ratio)
        self.crop_ratio_label = label

    def _clear_crop(self, tile):
        if tile.image_path in self.img_crops:
            del self.img_crops[tile.image_path]
            self.realign_all()

    def enter_crop_mode(self, tile, ratio=None):
        if self.crop_mode:
            self.exit_crop_mode()
        self.crop_mode = True
        self.crop_tile = tile
        self.crop_ratio = ratio
        self.crop_ratio_label = "自由"

        tw = tile.winfo_width()
        th = tile.winfo_height()
        tx = tile.winfo_x()
        ty = tile.winfo_y()

        self.crop_rect = {"x": tx, "y": ty, "w": tw, "h": th}
        self.crop_tile_orig = {"x": tx, "y": ty, "w": tw, "h": th}

        if ratio is not None:
            self._apply_ratio_to_crop(ratio)

        if self.crop_canvas is None:
            self.crop_canvas = tk.Canvas(self.stage, bg="", highlightthickness=0, cursor="crosshair")
        self.crop_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._draw_crop_overlay()

        self.crop_canvas.bind("<Button-1>", self._crop_on_click)
        self.crop_canvas.bind("<B1-Motion>", self._crop_on_drag)
        self.crop_canvas.bind("<ButtonRelease-1>", self._crop_on_release)

        self._show_crop_toolbar()

    def _apply_ratio_to_crop(self, ratio):
        if ratio is None or not self.crop_rect:
            return
        orig = self.crop_tile_orig
        cx = orig["x"] + orig["w"] / 2
        cy = orig["y"] + orig["h"] / 2
        if ratio >= 1:
            new_w = orig["w"]
            new_h = orig["w"] / ratio
            if new_h > orig["h"]:
                new_h = orig["h"]
                new_w = orig["h"] * ratio
        else:
            new_h = orig["h"]
            new_w = orig["h"] * ratio
            if new_w > orig["w"]:
                new_w = orig["w"]
                new_h = orig["w"] / ratio
        self.crop_rect["w"] = new_w
        self.crop_rect["h"] = new_h
        self.crop_rect["x"] = cx - new_w / 2
        self.crop_rect["y"] = cy - new_h / 2

    def _show_crop_toolbar(self):
        for w in self.crop_toolbar.winfo_children():
            w.destroy()
        tk.Label(self.crop_toolbar, text="裁剪", fg="white", bg="#1C1C1E", font=FONT_BOLD).pack(side="left", padx=(0, 5))
        for label, val in CROP_RATIOS:
            active = "disabled" if self.crop_mode and self.crop_ratio == val else "normal"
            MacButton(self.crop_toolbar, text=label,
                     command=lambda r=val, lbl=label: self._set_crop_ratio(r, lbl),
                     bg=ACCENT_BLUE if self.crop_mode and self.crop_ratio == val else "#444",
                     fg="white", borderless=1, width=50).pack(side="left", padx=2)
        MacButton(self.crop_toolbar, text="✓ 确认", bg=ACCENT_GREEN, fg="black", borderless=1,
                 command=self.confirm_crop, width=60).pack(side="left", padx=8)
        MacButton(self.crop_toolbar, text="✕ 取消", bg="#444", fg="white", borderless=1,
                 command=self.exit_crop_mode, width=60).pack(side="left", padx=5)
        self.crop_toolbar.place(relx=0.5, y=10, anchor="n")

    def _set_crop_ratio(self, ratio, label):
        self.crop_ratio = ratio
        self.crop_ratio_label = label
        if ratio is not None:
            self._apply_ratio_to_crop(ratio)
        else:
            orig = self.crop_tile_orig
            self.crop_rect = dict(orig)
        self._draw_crop_overlay()
        self._show_crop_toolbar()

    def _draw_crop_overlay(self):
        self.crop_canvas.delete("all")
        if not self.crop_rect:
            return
        r = self.crop_rect
        x1, y1, x2, y2 = r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"]
        sw = self.stage.winfo_width()
        sh = self.stage.winfo_height()
        self.crop_canvas.create_rectangle(0, 0, sw, sh, fill="#000000", stipple="gray25", tags="dim")
        self.crop_canvas.create_rectangle(x1, y1, x2, y2, fill="", outline=ACCENT_BLUE, width=2, tags="crop")
        self.crop_canvas.create_rectangle(x1, y1, x2, y2, fill="", outline="white", width=1, dash=(4, 4), tags="crop")
        for px, py in [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]:
            self.crop_canvas.create_oval(px - 5, py - 5, px + 5, py + 5, fill=ACCENT_BLUE, outline="white", tags="crop")

    def _get_crop_handle(self, x, y):
        r = self.crop_rect
        h_dist = 12
        cx = r["x"] + r["w"] / 2
        cy = r["y"] + r["h"] / 2
        edges = {
            "n": (cx, r["y"]),
            "s": (cx, r["y"] + r["h"]),
            "w": (r["x"], cy),
            "e": (r["x"] + r["w"], cy),
        }
        for name, (hx, hy) in edges.items():
            if abs(x - hx) < h_dist and abs(y - hy) < h_dist:
                return name
        return None

    def _crop_on_click(self, event):
        x, y = event.x, event.y
        self.crop_handle_drag = self._get_crop_handle(x, y)
        self.crop_drag_start = {"x": event.x, "y": event.y}
        self.crop_rect_orig = dict(self.crop_rect)

    def _crop_on_drag(self, event):
        if self.crop_handle_drag is None:
            return
        dx = event.x - self.crop_drag_start["x"]
        dy = event.y - self.crop_drag_start["y"]
        r = self.crop_rect_orig
        cr = self.crop_rect
        h = self.crop_handle_drag

        if h == "n":
            new_h = max(20, r["h"] - dy)
            new_w = new_h * self.crop_ratio if self.crop_ratio else r["w"]
            cr["x"] = r["x"] + r["w"] / 2 - new_w / 2
            cr["y"] = r["y"] + r["h"] - new_h
            cr["w"] = new_w
            cr["h"] = new_h
        elif h == "s":
            new_h = max(20, r["h"] + dy)
            new_w = new_h * self.crop_ratio if self.crop_ratio else r["w"]
            cr["w"] = new_w
            cr["h"] = new_h
            cr["x"] = r["x"] + r["w"] / 2 - new_w / 2
        elif h == "w":
            new_w = max(20, r["w"] - dx)
            new_h = new_w / self.crop_ratio if self.crop_ratio else r["h"]
            cr["x"] = r["x"] + r["w"] - new_w
            cr["y"] = r["y"] + r["h"] / 2 - new_h / 2
            cr["w"] = new_w
            cr["h"] = new_h
        elif h == "e":
            new_w = max(20, r["w"] + dx)
            new_h = new_w / self.crop_ratio if self.crop_ratio else r["h"]
            cr["y"] = r["y"] + r["h"] / 2 - new_h / 2
            cr["w"] = new_w
            cr["h"] = new_h

        orig = self.crop_tile_orig
        cr["x"] = max(orig["x"], min(cr["x"], orig["x"] + orig["w"] - 20))
        cr["y"] = max(orig["y"], min(cr["y"], orig["y"] + orig["h"] - 20))
        self._draw_crop_overlay()

    def _crop_on_release(self, event):
        self.crop_handle_drag = None

    def confirm_crop(self):
        tile = self.crop_tile
        cr = self.crop_rect
        if not tile or not cr:
            self.exit_crop_mode()
            return
        x1 = cr["x"]
        y1 = cr["y"]
        x2 = cr["x"] + cr["w"]
        y2 = cr["y"] + cr["h"]
        orig = self.crop_tile_orig
        orig_w, orig_h = tile.raw_pil.size
        ratio = orig_h / orig_w
        img_x = (x1 - orig["x"]) / orig["w"] * orig_w
        img_y = (y1 - orig["y"]) / orig["h"] * (orig_w * ratio)
        img_w = (x2 - x1) / orig["w"] * orig_w
        img_h = (y2 - y1) / orig["h"] * (orig_w * ratio)
        self.img_crops[tile.image_path] = {
            "x": max(0, img_x),
            "y": max(0, img_y),
            "w": max(1, img_w),
            "h": max(1, img_h),
            "ratio": self.crop_ratio_label if hasattr(self, 'crop_ratio_label') else "自由"
        }
        self.exit_crop_mode()
        self.realign_all()

    def exit_crop_mode(self):
        self.crop_mode = False
        self.crop_tile = None
        self.crop_handle_drag = None
        if self.crop_canvas:
            self.crop_canvas.place_forget()
        self.crop_toolbar.place_forget()
        for tile in self.tile_widgets:
            tile.lower()

    def realign_all(self, event=None):
        self.insert_indicator.place_forget()
        if self.crop_mode:
            self.exit_crop_mode()
            return
        if not self.image_paths:
            self.toggle_placeholder()
            for wm in self.watermark_widgets:
                wm.place_forget()
            return
        self.toggle_placeholder()
        self.root.update_idletasks()

        for wm in self.watermark_widgets:
            wm.place_forget()

        sw = max(self.stage.winfo_width() - 60, 100)
        sh = max(self.stage.winfo_height() - 40, 100)

        try:
            tw, sp, bh = int(self.width_entry.get()), int(self.spacing_entry.get()), int(self.bottom_entry.get())
            bg_hex = self.bg_map[self.bg_var.get()]["hex"]

            heights = []
            for i, p in enumerate(self.image_paths):
                if p in self.img_crops:
                    c = self.img_crops[p]
                    heights.append(int(c["h"]))
                else:
                    heights.append(int(tw * self.img_ratios[i]))

            total_h = sum(heights) + (len(heights) - 1) * sp + bh
            scale = min(sw / tw, sh / total_h)
            p_tw, p_sp, p_bh = int(tw * scale), int(sp * scale), int(bh * scale)
            curr_y = (self.stage.winfo_height() - int(total_h * scale)) // 2
            start_x = (self.stage.winfo_width() - p_tw) // 2

            self.canvas_bg_frame.config(bg=bg_hex, width=p_tw, height=int(total_h * scale))
            self.canvas_bg_frame.place(x=start_x, y=curr_y)

            if p_tw != self.last_p_tw:
                self.preview_cache.clear()
                self.last_p_tw = p_tw

            for i, tile in enumerate(self.tile_widgets):
                ph = heights[i] if i < len(heights) else int(p_tw * self.img_ratios[i])
                ph_scaled = int(ph * scale)
                if not getattr(tile, 'is_dragging', False):
                    cache_key = tile.image_path + f"_{i}_{ph}"
                    if cache_key not in self.preview_cache:
                        src_img = tile.raw_pil
                        if tile.image_path in self.img_crops:
                            c = self.img_crops[tile.image_path]
                            orig_w, orig_h = tile.raw_pil.size
                            crop_box = (int(c["x"]), int(c["y"]), int(c["x"] + c["w"]), int(c["y"] + c["h"]))
                            src_img = tile.raw_pil.crop(crop_box).resize((p_tw - 4, ph_scaled - 4), Image.Resampling.BICUBIC)
                        else:
                            src_img = tile.raw_pil.resize((p_tw - 4, ph_scaled - 4), Image.Resampling.BICUBIC)
                        self.preview_cache[cache_key] = ImageTk.PhotoImage(src_img)

                    tile.inner_frame.config(bg=bg_hex)
                    if self.selected_tile == tile:
                        tile.inner_frame.config(highlightthickness=2, highlightbackground=ACCENT_BLUE)
                        self.crop_btn.pack(fill="x", ipady=8)
                    else:
                        tile.inner_frame.config(highlightthickness=0)
                    tile.image_label.config(image=self.preview_cache[cache_key], bg=bg_hex)
                    tile.place(x=start_x, y=curr_y, width=p_tw, height=ph_scaled)
                curr_y += ph_scaled + p_sp

            if self.watermark_mode == "bottom":
                if self.config["logo_path"] and os.path.exists(self.config["logo_path"]):
                    with Image.open(self.config["logo_path"]).convert("RGBA") as l_img:
                        lw = int(p_tw * (self.config["logo_scale"] / 100))
                        if lw <= 0:
                            lw = 1
                        lh = int(l_img.size[1] * (lw / l_img.size[0]))
                        if lh <= 0:
                            lh = 1
                        tk_l = ImageTk.PhotoImage(l_img.resize((lw, lh), Image.Resampling.LANCZOS))
                        self.logo_label.config(image=tk_l, bg=bg_hex)
                        self.logo_label.image = tk_l
                        base_x = (self.stage.winfo_width() - lw) // 2
                        base_y = curr_y - p_sp + (p_bh - lh) // 2
                        final_x = base_x + int(self.config["logo_offset_x"] * scale)
                        final_y = base_y + int(self.config["logo_offset_y"] * scale)
                        self.logo_label.place(x=final_x, y=final_y)
                else:
                    self.logo_label.place_forget()
            else:
                self.logo_label.place_forget()
                canvas_top_y = (self.stage.winfo_height() - int(total_h * scale)) // 2
                for wm in self.watermark_widgets:
                    wx = start_x + wm.wm_data["x"] * scale
                    wy = canvas_top_y + wm.wm_data["y"] * scale
                    wm.place(x=wx, y=wy)
                    wm.lift()

        except Exception:
            pass

    def delete_specific(self, index):
        if 0 <= index < len(self.image_paths):
            p = self.image_paths.pop(index)
            self.img_ratios.pop(index)
            self.tile_widgets.pop(index).destroy()
            if p in self.preview_cache:
                del self.preview_cache[p]
            if p in self.img_crops:
                del self.img_crops[p]
            self.selected_tile = None
            self.crop_btn.pack_forget()
            for i, t in enumerate(self.tile_widgets):
                t.index = i
            self.realign_all()

    def set_selected(self, tile):
        if self.crop_mode:
            return
        if self.selected_tile:
            try:
                self.selected_tile.inner_frame.config(highlightthickness=0)
            except:
                pass
        self.selected_tile = tile
        if self.selected_tile:
            self.selected_tile.inner_frame.config(highlightthickness=2, highlightbackground=ACCENT_BLUE)

    def delete_selected(self, event=None):
        if self.selected_tile and not self.crop_mode:
            self.delete_specific(self.selected_tile.index)

    def upload_logo(self):
        p = filedialog.askopenfilename(initialdir=self.config.get("last_logo_dir"), filetypes=[("Image", "*.png;*.jpg;*.jpeg")])
        if p:
            self.config["last_logo_dir"] = os.path.dirname(p)
            self.config["logo_library"].append(p)
            self.apply_logo(p)

    def clear_logo(self):
        self.config["logo_path"] = ""
        self.save_settings()
        self.realign_all()

    def handle_drop(self, event):
        raw_data = event.data
        if not raw_data:
            return

        paths = re.findall(r'{(.*?)}|(\S+)', raw_data)
        clean_paths = []
        for match in paths:
            p = match[0] if match[0] else match[1]
            p = p.strip('"').strip("'")
            if os.path.isfile(p) and p.lower().endswith(('.jpg', '.jpeg', '.png', '.tiff', '.bmp')):
                clean_paths.append(p)

        if clean_paths:
            self.image_paths.extend(clean_paths)
            self.config["last_img_dir"] = os.path.dirname(clean_paths[0])
            self.init_load_images()

    def add_images(self):
        ft = [("Images", "*.jpg;*.jpeg;*.png;*.tiff;*.bmp")]
        p = filedialog.askopenfilenames(initialdir=self.config.get("last_img_dir"), filetypes=ft)
        if p:
            self.image_paths.extend(list(p))
            self.config["last_img_dir"] = os.path.dirname(p[0])
            self.init_load_images()

    def init_load_images(self):
        for w in self.tile_widgets:
            w.destroy()
        self.tile_widgets, self.img_ratios, self.preview_cache = [], [], {}
        self.last_p_tw = 0
        for i, p in enumerate(self.image_paths):
            try:
                with Image.open(p) as img:
                    self.img_ratios.append(img.size[1] / img.size[0])
                    prev = img.convert("RGB")
                    prev.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                    self.tile_widgets.append(DraggableTile(self.stage, p, prev, i, self))
            except Exception as e:
                print(f"Error loading {p}: {e}")
        self.realign_all()

    def clear_all(self):
        for w in self.tile_widgets:
            w.destroy()
        self.image_paths, self.img_ratios, self.preview_cache, self.tile_widgets = [], [], {}, []
        self.img_crops = {}
        self.logo_label.place_forget()
        self.canvas_bg_frame.place_forget()
        self.toggle_placeholder()
        self.crop_btn.pack_forget()
        self.clear_all_watermarks()
        self.exit_crop_mode()

    def export_action(self):
        if not self.image_paths:
            return
        self.save_settings()
        try:
            tw, sp, bh = int(self.width_entry.get()), int(self.spacing_entry.get()), int(self.bottom_entry.get())
            bg_rgb = self.bg_map[self.bg_var.get()]["rgb"]
            imgs, th = [], 0
            for i, p in enumerate(self.image_paths):
                img = Image.open(p).convert("RGB")
                if p in self.img_crops:
                    c = self.img_crops[p]
                    img = img.crop((int(c["x"]), int(c["y"]), int(c["x"] + c["w"]), int(c["y"] + c["h"])))
                nh = int(img.size[1] * (tw / img.size[0]))
                imgs.append(img.resize((tw, nh), Image.Resampling.LANCZOS))
                th += nh
            canvas = Image.new("RGB", (tw, th + (len(imgs) - 1) * sp + bh), bg_rgb)
            y = 0
            for img in imgs:
                canvas.paste(img, (0, y))
                y += img.size[1] + sp

            if self.watermark_mode == "bottom":
                if self.config["logo_path"] and os.path.exists(self.config["logo_path"]):
                    logo = Image.open(self.config["logo_path"]).convert("RGBA")
                    lw = int(tw * (self.config["logo_scale"] / 100))
                    lh = int(logo.size[1] * (lw / logo.size[0]))
                    l_res = logo.resize((lw, lh), Image.Resampling.LANCZOS)
                    final_x = (tw - lw) // 2 + self.config["logo_offset_x"]
                    final_y = y - sp + (bh - lh) // 2 + self.config["logo_offset_y"]
                    canvas.paste(l_res, (final_x, final_y), l_res)
            else:
                for wm in self.watermarks:
                    try:
                        logo = Image.open(wm["path"]).convert("RGBA")
                        wm_w = int(logo.size[0] * wm["scale"])
                        wm_h = int(logo.size[1] * wm["scale"])
                        wm_resized = logo.resize((wm_w, wm_h), Image.Resampling.LANCZOS)
                        canvas.paste(wm_resized, (int(wm["x"]), int(wm["y"])), wm_resized)
                    except:
                        pass

            save_p = filedialog.asksaveasfilename(initialdir=self.config.get("last_export_dir"),
                                                   defaultextension=".jpg",
                                                   filetypes=[("JPEG Image", "*.jpg")])
            if save_p:
                self.config["last_export_dir"] = os.path.dirname(save_p)
                canvas.save(save_p, quality=95, dpi=(300, 300))
                self.save_settings()
                messagebox.showinfo("成功", "成品已保存")
        except Exception as e:
            messagebox.showerror("错误", str(e))


if __name__ == "__main__":
    root = TkinterDnD.Tk()

    if hasattr(sys, '_MEIPASS'):
        dnd_path = os.path.join(sys._MEIPASS, 'tkinterdnd2')
        if os.path.isdir(dnd_path):
            root.tk.eval(f'lappend auto_path "{dnd_path.replace(os.sep, "/")}"')

    app = AoiStitcher(root)
    root.mainloop()
