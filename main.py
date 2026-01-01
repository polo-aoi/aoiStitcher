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
# 'Darwin' 代表 Mac, 'Windows' 代表 Windows
CURRENT_SYSTEM = platform.system()

# --- 2. 跨平台兼容性处理 ---

# A. 按钮控件适配
# Mac 需要 tkmacosx 才能显示按钮背景色
# Windows 原生 tk.Button 就可以，不需要 tkmacosx
try:
    if CURRENT_SYSTEM == "Darwin": 
        from tkmacosx import Button as MacButton
    else: 
        MacButton = tk.Button 
except ImportError:
    MacButton = tk.Button

# B. Windows 高分屏模糊修复 (High DPI Fix)
# 如果不加这段，在 Windows 笔记本上软件会看起来很模糊
if CURRENT_SYSTEM == "Windows":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass

# C. 字体智能适配
# Mac 有苹方，Windows 没有；Windows 有微软雅黑，Mac 没有。
if CURRENT_SYSTEM == "Windows":
    FONT_TITLE = ("Microsoft YaHei UI", 20, "bold") # Win 标题调小一点防止溢出
    FONT_BODY = ("Microsoft YaHei UI", 10)
    FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")
    FONT_MONO = ("Consolas", 9)
    FONT_BIG_BTN = ("Microsoft YaHei UI", 12, "bold")
    CURSOR_DRAG = "fleur"  # Windows 拖拽光标
    CURSOR_HAND = "hand2"  # Windows 手型光标
else:
    FONT_TITLE = ("Avenir Next", 28, "bold")
    FONT_BODY = ("PingFang SC", 11)
    FONT_BOLD = ("PingFang SC", 11, "bold")
    FONT_MONO = ("Menlo", 9)
    FONT_BIG_BTN = ("PingFang SC", 15, "bold")
    CURSOR_DRAG = "closedhand" # Mac 拖拽光标
    CURSOR_HAND = "pointinghand" # Mac 手型光标

# --- 配置文件路径 ---
# 自动存入用户的“文档”文件夹，Win/Mac 通用
CONFIG_FILE = os.path.join(os.path.expanduser("~"), "Documents", "aoi_stitcher_config.json")

# --- iOS 极简配色 (保持不变) ---
BG_MAIN = "#000000"           
SIDEBAR_BG = "#1C1C1E"       
ACCENT_BLUE = "#0A84FF"      
ACCENT_GREEN = "#32D74B"     
ACCENT_RED = "#FF453A"       
TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#8E8E93"   
INPUT_BG = "#2C2C2E"

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

        # 删除按钮微调
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

    def on_click(self, event):
        self.controller.set_selected(self)

    def start_drag(self, event):
        self.is_dragging = False 
        self.start_mouse_y = event.y_root
        self.start_widget_y = self.winfo_y()
        self.lift()
        self.config(cursor=CURSOR_DRAG)
        self.controller.prepare_magnetic_slots()

    def do_drag(self, event):
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
        if self.is_dragging:
            self.controller.apply_new_order(self)
        self.is_dragging = False
        self.config(cursor="arrow")
        self.master.after_idle(self.controller.realign_all)

class AoiStitcher:
    def __init__(self, root):
        self.root = root
        
        # Windows 设置窗口左上角图标 (如果目录里有 logo.ico 的话)
        if CURRENT_SYSTEM == "Windows" and os.path.exists("logo.ico"):
            try: root.iconbitmap("logo.ico")
            except: pass

        self.root.title("AoiStitcher Universal")
        self.root.geometry("800x1000") 
        self.root.configure(bg=BG_MAIN)
        
        self.image_paths = []
        self.tile_widgets = []
        self.img_ratios = [] 
        self.preview_cache = {} 
        self.selected_tile = None 
        self.last_p_tw = 0      
        self.slot_y_coords = [] 
        self.potential_idx = 0  
        
        self.config = {
            "width": "2000", "spacing": "20", "bottom_h": "250", 
            "logo_path": "", "logo_library": [], "logo_scale": 20, 
            "logo_offset_x": 0, "logo_offset_y": 0,
            "bg_theme": "White", 
            "last_img_dir": os.path.expanduser("~/Desktop"),
            "last_export_dir": os.path.expanduser("~/Desktop"),
            "last_logo_dir": os.path.expanduser("~/Desktop")
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

    def load_settings(self):
        # 增加 encoding='utf-8' 防止 Windows 读取中文路径报错
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f: 
                    self.config.update(json.load(f))
            except: pass

    def save_settings(self):
        self.config.update({
            "width": self.width_entry.get(),
            "spacing": self.spacing_entry.get(),
            "bottom_h": self.bottom_entry.get(),
            "bg_theme": self.bg_var.get()
        })
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f: 
                json.dump(self.config, f, ensure_ascii=False)
            self.update_path_display()
        except Exception as e:
            print(f"Save error: {e}")

    def setup_ui(self):
        # --- 侧边栏 ---
        self.sidebar = tk.Frame(self.root, bg=SIDEBAR_BG, width=280, padx=25, pady=35)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        edition_text = "ポロ蒼 Win/Mac"
        tk.Label(self.sidebar, text="AoiStitcher", font=FONT_TITLE, fg=TEXT_PRIMARY, bg=SIDEBAR_BG).pack(anchor="w")
        tk.Label(self.sidebar, text=edition_text, font=FONT_BODY, fg=TEXT_SECONDARY, bg=SIDEBAR_BG).pack(anchor="w", pady=(0, 30))

        self.width_entry = self.create_input("画布总宽 (px)", "width")
        self.spacing_entry = self.create_input("照片间距", "spacing")
        self.bottom_entry = self.create_input("留白高度", "bottom_h")

        tk.Label(self.sidebar, text="画布颜色", fg=TEXT_SECONDARY, bg=SIDEBAR_BG, font=FONT_BODY).pack(anchor="w", pady=(15, 0))
        self.bg_var = tk.StringVar(value=self.config["bg_theme"])
        bg_frame = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
        bg_frame.pack(fill="x", pady=(8, 25))
        
        # 兼容性处理：Windows 的 Radiobutton 样式调整
        for text in ["White", "Black"]:
            tk.Radiobutton(bg_frame, text=text, variable=self.bg_var, value=text, command=self.realign_all, 
                          bg=SIDEBAR_BG, fg=TEXT_PRIMARY, selectcolor="#333", activebackground=SIDEBAR_BG,
                          font=FONT_BODY).pack(side="left", padx=(0, 15))

        # 动态参数：Windows 的按钮不支持 'borderless' 属性
        btn_kwargs = {"bg": ACCENT_BLUE, "fg": "white"}
        if CURRENT_SYSTEM == "Darwin": btn_kwargs["borderless"] = 1
            
        MacButton(self.sidebar, text="＋ 导入照片", command=self.add_images, **btn_kwargs).pack(fill="x", pady=6, ipady=10)
        
        # 调整颜色
        btn_kwargs["bg"] = "#3A3A3C"
        MacButton(self.sidebar, text="配置水印 ▾", command=self.show_logo_menu, **btn_kwargs).pack(fill="x", pady=6, ipady=10)
        
        btn_kwargs["fg"] = ACCENT_RED
        MacButton(self.sidebar, text="清空画布", command=self.clear_all, **btn_kwargs).pack(fill="x", pady=6, ipady=10)

        export_container = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
        export_container.pack(side="bottom", fill="x", pady=(20, 0))
        
        exp_kwargs = {"bg": ACCENT_GREEN, "fg": "black", "font": FONT_BIG_BTN}
        if CURRENT_SYSTEM == "Darwin": exp_kwargs["borderless"] = 1
            
        self.exp_btn = MacButton(export_container, text="导出成品", command=self.export_action, **exp_kwargs)
        self.exp_btn.pack(fill="x", ipady=14)
        
        tk.Label(export_container, text="输出路径", fg=TEXT_PRIMARY, bg=SIDEBAR_BG, font=FONT_BOLD).pack(anchor="w", pady=(15, 5))
        path_box = tk.Frame(export_container, bg="#252527", padx=10, pady=8)
        path_box.pack(fill="x")
        self.path_label = tk.Label(path_box, text="", fg=TEXT_SECONDARY, bg="#252527", font=FONT_MONO, anchor="w")
        self.path_label.pack(side="left", fill="x", expand=True)
        tk.Label(path_box, text="›", fg="#444", bg="#252527", font=("Arial", 12)).pack(side="right")
        self.update_path_display()

        # --- 工作预览区 ---
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
        self.logo_label.bind("<Button-1>", lambda e: self.show_logo_menu())
        self.stage.bind("<Configure>", lambda e: self.realign_all())

    def update_path_display(self):
        path = self.config.get("last_export_dir", "未选择路径")
        # Windows 路径可能很长，调整显示截断逻辑
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
        self.slot_y_centers = [t.winfo_y() + t.winfo_height()/2 for t in self.tile_widgets]
        self.slot_y_coords = [t.winfo_y() for t in self.tile_widgets]

    def preview_magnetic_shift(self, dragging_tile, center_y):
        if not self.slot_y_centers: return
        distances = [abs(center_y - cy) for cy in self.slot_y_centers]
        new_p_idx = distances.index(min(distances))
        if new_p_idx != self.potential_idx:
            self.potential_idx = new_p_idx
            temp_order = [idx for idx in range(len(self.tile_widgets)) if idx != dragging_tile.index]
            temp_order.insert(self.potential_idx, dragging_tile.index)
            for pos_in_view, tile_idx in enumerate(temp_order):
                target = self.tile_widgets[tile_idx]
                if not getattr(target, 'is_dragging', False): target.place(y=self.slot_y_coords[pos_in_view])

    def apply_new_order(self, dragging_tile):
        old_idx = dragging_tile.index
        new_idx = self.potential_idx
        if old_idx != new_idx:
            self.image_paths.insert(new_idx, self.image_paths.pop(old_idx))
            self.tile_widgets.insert(new_idx, self.tile_widgets.pop(old_idx))
            self.img_ratios.insert(new_idx, self.img_ratios.pop(old_idx))
            for i, t in enumerate(self.tile_widgets): t.index = i

    def show_logo_menu(self):
        # Windows 菜单字体适配
        menu = Menu(self.root, tearoff=0, bg=SIDEBAR_BG, fg="black", activebackground=ACCENT_BLUE, font=FONT_BODY)
        menu.add_command(label="🛠  微调位置与尺寸...", command=self.open_logo_settings)
        menu.add_separator()
        menu.add_command(label="＋  上传新 Logo", command=self.upload_logo)
        menu.add_command(label="✕  清除当前水印", command=self.clear_logo)
        if self.config["logo_library"]:
            menu.add_separator()
            for path in list(dict.fromkeys(self.config["logo_library"]))[-6:]: 
                if os.path.exists(path):
                    menu.add_command(label=f"🕒 {os.path.basename(path)}", command=lambda p=path: self.apply_logo(p))
        
        try: menu.post(self.root.winfo_pointerx(), self.root.winfo_pointery())
        except: pass

    def open_logo_settings(self):
        panel = Toplevel(self.root)
        panel.title("水印配置")
        panel.geometry("300x380")
        panel.configure(bg=SIDEBAR_BG)
        panel.resizable(False, False)
        panel.attributes('-topmost', True)
        
        # 居中计算 (Windows 坐标保护)
        root_x = self.root.winfo_x()
        root_y = self.root.winfo_y()
        if root_x < 0: root_x = 0
        if root_y < 0: root_y = 0
        
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

        # 兼容性按钮参数
        btn_args = {"bg": "#444", "fg": "white"}
        if CURRENT_SYSTEM == "Darwin": btn_args["borderless"] = 1
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
        self.config["logo_path"] = path; self.save_settings(); self.realign_all()

    def realign_all(self, event=None):
        if not self.image_paths: self.toggle_placeholder(); return
        self.toggle_placeholder()
        self.root.update_idletasks()
        
        sw = max(self.stage.winfo_width()-60, 100)
        sh = max(self.stage.winfo_height()-40, 100)
        
        try:
            tw, sp, bh = int(self.width_entry.get()), int(self.spacing_entry.get()), int(self.bottom_entry.get())
            bg_hex = self.bg_map[self.bg_var.get()]["hex"]
            total_h = sum(int(tw * r) for r in self.img_ratios) + (len(self.img_ratios)-1)*sp + bh
            scale = min(sw/tw, sh/total_h)
            p_tw, p_sp, p_bh = int(tw * scale), int(sp * scale), int(bh * scale)
            curr_y = (self.stage.winfo_height() - int(total_h * scale)) // 2
            start_x = (self.stage.winfo_width() - p_tw) // 2
            
            self.canvas_bg_frame.config(bg=bg_hex, width=p_tw, height=int(total_h * scale))
            self.canvas_bg_frame.place(x=start_x, y=curr_y)
            
            if p_tw != self.last_p_tw: self.preview_cache.clear(); self.last_p_tw = p_tw
            
            for i, tile in enumerate(self.tile_widgets):
                ph = int(p_tw * self.img_ratios[i])
                if not getattr(tile, 'is_dragging', False):
                    cache_key = tile.image_path
                    if cache_key not in self.preview_cache:
                        self.preview_cache[cache_key] = ImageTk.PhotoImage(tile.raw_pil.resize((p_tw-4, ph-4), Image.Resampling.BICUBIC))
                    
                    tile.inner_frame.config(bg=bg_hex)
                    if self.selected_tile == tile:
                        tile.inner_frame.config(highlightthickness=2, highlightbackground=ACCENT_BLUE)
                    else:
                        tile.inner_frame.config(highlightthickness=0)
                    tile.image_label.config(image=self.preview_cache[cache_key], bg=bg_hex)
                    tile.place(x=start_x, y=curr_y, width=p_tw, height=ph)
                curr_y += ph + p_sp
            
            if self.config["logo_path"] and os.path.exists(self.config["logo_path"]):
                with Image.open(self.config["logo_path"]).convert("RGBA") as l_img:
                    lw = int(p_tw * (self.config["logo_scale"] / 100))
                    if lw <= 0: lw = 1 
                    lh = int(l_img.size[1] * (lw / l_img.size[0]))
                    if lh <= 0: lh = 1
                    
                    tk_l = ImageTk.PhotoImage(l_img.resize((lw, lh), Image.Resampling.LANCZOS))
                    self.logo_label.config(image=tk_l, bg=bg_hex); self.logo_label.image = tk_l
                    
                    base_x = (self.stage.winfo_width() - lw) // 2
                    base_y = curr_y - p_sp + (p_bh - lh) // 2
                    final_x = base_x + int(self.config["logo_offset_x"] * scale)
                    final_y = base_y + int(self.config["logo_offset_y"] * scale)
                    self.logo_label.place(x=final_x, y=final_y)
            else: self.logo_label.place_forget()
        except Exception:
            pass

    def delete_specific(self, index):
        if 0 <= index < len(self.image_paths):
            p = self.image_paths.pop(index); self.img_ratios.pop(index)
            self.tile_widgets.pop(index).destroy()
            if p in self.preview_cache: del self.preview_cache[p]
            self.selected_tile = None
            for i, t in enumerate(self.tile_widgets): t.index = i
            self.realign_all()

    def set_selected(self, tile):
        if self.selected_tile:
            try: self.selected_tile.inner_frame.config(highlightthickness=0)
            except: pass
        self.selected_tile = tile
        if self.selected_tile:
            self.selected_tile.inner_frame.config(highlightthickness=2, highlightbackground=ACCENT_BLUE)

    def delete_selected(self, event=None):
        if self.selected_tile: self.delete_specific(self.selected_tile.index)

    def upload_logo(self):
        # 扩展名分隔符兼容 Win/Mac
        p = filedialog.askopenfilename(initialdir=self.config.get("last_logo_dir"), filetypes=[("Image", "*.png;*.psd;*.jpg;*.jpeg")])
        if p:
            self.config["last_logo_dir"] = os.path.dirname(p)
            self.config["logo_library"].append(p)
            self.apply_logo(p)

    def clear_logo(self): 
        self.config["logo_path"] = ""; self.save_settings(); self.realign_all()

    def handle_drop(self, event):
        raw_data = event.data
        if not raw_data: return
        
        # 增强的路径清洗逻辑 (兼容 Win/Mac 各种奇葩的拖拽格式)
        paths = re.findall(r'{(.*?)}|(\S+)', raw_data)
        clean_paths = []
        for match in paths:
            p = match[0] if match[0] else match[1]
            p = p.strip('\"').strip('\'') # 去除可能存在的引号
            if os.path.isfile(p) and p.lower().endswith(('.jpg', '.jpeg', '.png', '.psd', '.tiff', '.bmp')):
                clean_paths.append(p)

        if clean_paths: 
            self.image_paths.extend(clean_paths)
            self.config["last_img_dir"] = os.path.dirname(clean_paths[0])
            self.init_load_images()

    def add_images(self):
        # 兼容 Windows 的分号分隔符
        ft = [("Images", "*.jpg;*.jpeg;*.png;*.psd;*.tiff;*.bmp")]
        p = filedialog.askopenfilenames(initialdir=self.config.get("last_img_dir"), filetypes=ft)
        if p: 
            self.image_paths.extend(list(p))
            self.config["last_img_dir"] = os.path.dirname(p[0])
            self.init_load_images()

    def init_load_images(self):
        for w in self.tile_widgets: w.destroy()
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
        for w in self.tile_widgets: w.destroy()
        self.image_paths, self.img_ratios, self.preview_cache, self.tile_widgets = [], [], {}, []
        self.logo_label.place_forget(); self.canvas_bg_frame.place_forget(); self.toggle_placeholder()

    def export_action(self):
        if not self.image_paths: return
        self.save_settings()
        try:
            tw, sp, bh = int(self.width_entry.get()), int(self.spacing_entry.get()), int(self.bottom_entry.get())
            bg_rgb = self.bg_map[self.bg_var.get()]["rgb"]
            imgs, th = [], 0
            for p in self.image_paths:
                img = Image.open(p); nh = int(img.size[1] * (tw / img.size[0]))
                imgs.append(img.resize((tw, nh), Image.Resampling.LANCZOS)); th += nh
            canvas = Image.new("RGB", (tw, th + (len(imgs)-1)*sp + bh), bg_rgb)
            y = 0
            for img in imgs: canvas.paste(img, (0, y)); y += img.size[1] + sp
            
            if self.config["logo_path"] and os.path.exists(self.config["logo_path"]):
                logo = Image.open(self.config["logo_path"]).convert("RGBA")
                lw = int(tw * (self.config["logo_scale"] / 100)); lh = int(logo.size[1]*(lw/logo.size[0]))
                l_res = logo.resize((lw, lh), Image.Resampling.LANCZOS)
                
                final_x = (tw - lw) // 2 + self.config["logo_offset_x"]
                final_y = y - sp + (bh - lh) // 2 + self.config["logo_offset_y"]
                canvas.paste(l_res, (final_x, final_y), l_res)
            
            save_p = filedialog.asksaveasfilename(initialdir=self.config.get("last_export_dir"), 
                                                   defaultextension=".jpg", 
                                                   filetypes=[("JPEG Image", "*.jpg")])
            if save_p:
                self.config["last_export_dir"] = os.path.dirname(save_p)
                canvas.save(save_p, quality=95, dpi=(300, 300))
                self.save_settings()
                messagebox.showinfo("成功", "成品已保存")
        except Exception as e: messagebox.showerror("错误", str(e))

if __name__ == "__main__":
    # --- 启动修复 ---
    # 在某些 Intel Mac 或打包后的环境下，需要手动定位 dnd 库
    root = TkinterDnD.Tk()
    
    # 通用 DND 路径修复 (防止 Intel Mac 报错)
    if hasattr(sys, '_MEIPASS'):
        dnd_path = os.path.join(sys._MEIPASS, 'tkinterdnd2')
        if os.path.isdir(dnd_path):
            root.tk.eval(f'lappend auto_path "{dnd_path.replace(os.sep, "/")}"')

    app = AoiStitcher(root)
    root.mainloop()
