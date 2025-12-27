import tkinter as tk
from tkinter import filedialog, messagebox, ttk, Menu, Toplevel
try:
    from tkmacosx import Button as MacButton
except ImportError:
    MacButton = tk.Button

from tkinterdnd2 import DND_FILES, TkinterDnD
from PIL import Image, ImageTk
import os
import json
import re

# --- 配置文件路径 ---
CONFIG_FILE = os.path.expanduser("~/Documents/aoi_stitcher_config.json")

# --- iOS 极简配色 ---
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

        self.del_btn = tk.Label(self, text="✕", fg="white", bg="#333", font=("Arial", 9, "bold"), 
                                width=2, height=1, cursor="arrow")
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
        self.config(cursor="closedhand")
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
        self.root.title("AoiStitcher v1.3")
        # --- 已修改：根据最新需求调整为 800x1000 ---
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
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f: self.config.update(json.load(f))
            except: pass

    def save_settings(self):
        self.config.update({
            "width": self.width_entry.get(),
            "spacing": self.spacing_entry.get(),
            "bottom_h": self.bottom_entry.get(),
            "bg_theme": self.bg_var.get()
        })
        try:
            with open(CONFIG_FILE, 'w') as f: json.dump(self.config, f)
            self.update_path_display()
        except: pass

    def setup_ui(self):
        # --- 侧边栏 ---
        self.sidebar = tk.Frame(self.root, bg=SIDEBAR_BG, width=280, padx=25, pady=35)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        tk.Label(self.sidebar, text="AoiStitcher", font=("Avenir Next", 28, "bold"), fg=TEXT_PRIMARY, bg=SIDEBAR_BG).pack(anchor="w")
        tk.Label(self.sidebar, text="ポロ蒼 Edition", font=("PingFang SC", 11), fg=TEXT_SECONDARY, bg=SIDEBAR_BG).pack(anchor="w", pady=(0, 30))

        self.width_entry = self.create_input("画布总宽 (px)", "width")
        self.spacing_entry = self.create_input("照片间距", "spacing")
        self.bottom_entry = self.create_input("留白高度", "bottom_h")

        tk.Label(self.sidebar, text="画布颜色", fg=TEXT_SECONDARY, bg=SIDEBAR_BG, font=("PingFang SC", 10)).pack(anchor="w", pady=(15, 0))
        self.bg_var = tk.StringVar(value=self.config["bg_theme"])
        bg_frame = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
        bg_frame.pack(fill="x", pady=(8, 25))
        for text in ["White", "Black"]:
            tk.Radiobutton(bg_frame, text=text, variable=self.bg_var, value=text, command=self.realign_all, 
                          bg=SIDEBAR_BG, fg=TEXT_PRIMARY, selectcolor="#333", activebackground=SIDEBAR_BG,
                          font=("Helvetica", 11)).pack(side="left", padx=(0, 15))

        MacButton(self.sidebar, text="＋ 导入照片", command=self.add_images, bg=ACCENT_BLUE, fg="white", borderless=1).pack(fill="x", pady=6, ipady=10)
        MacButton(self.sidebar, text="配置水印 ▾", command=self.show_logo_menu, bg="#3A3A3C", fg="white", borderless=1).pack(fill="x", pady=6, ipady=10)
        MacButton(self.sidebar, text="清空画布", command=self.clear_all, bg="#3A3A3C", fg=ACCENT_RED, borderless=1).pack(fill="x", pady=6, ipady=10)

        export_container = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
        export_container.pack(side="bottom", fill="x", pady=(20, 0))
        
        self.exp_btn = MacButton(export_container, text="导出成品", command=self.export_action, bg=ACCENT_GREEN, fg="black", borderless=1, font=("PingFang SC", 15, "bold"))
        self.exp_btn.pack(fill="x", ipady=14)
        
        tk.Label(export_container, text="输出路径", fg=TEXT_PRIMARY, bg=SIDEBAR_BG, font=("PingFang SC", 10, "bold")).pack(anchor="w", pady=(15, 5))
        path_box = tk.Frame(export_container, bg="#252527", padx=10, pady=8)
        path_box.pack(fill="x")
        self.path_label = tk.Label(path_box, text="", fg=TEXT_SECONDARY, bg="#252527", font=("Menlo", 9), anchor="w")
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
                                          fg="#444446", bg="#000000", font=("PingFang SC", 12, "bold"), justify="center")
        self.placeholder_label.place(relx=0.5, rely=0.5, anchor="center")
        
        self.canvas_bg_frame = tk.Frame(self.stage, bd=0)
        self.logo_label = tk.Label(self.stage, bd=0)
        self.logo_label.bind("<Button-1>", lambda e: self.show_logo_menu())
        self.stage.bind("<Configure>", lambda e: self.realign_all())

    def update_path_display(self):
        path = self.config.get("last_export_dir", "未选择路径")
        display_path = (path[:12] + "..." + path[-18:]) if len(path) > 32 else path
        self.path_label.config(text=f"📁 {display_path}")

    def toggle_placeholder(self):
        if not self.image_paths:
            self.placeholder.place(relx=0.05, rely=0.05, relwidth=0.9, relheight=0.9)
            self.canvas_bg_frame.place_forget()
        else:
            self.placeholder.place_forget()

    def create_input(self, label, key):
        tk.Label(self.sidebar, text=label, fg=TEXT_SECONDARY, bg=SIDEBAR_BG, font=("PingFang SC", 10)).pack(anchor="w", pady=(10, 2))
        entry = tk.Entry(self.sidebar, bg=INPUT_BG, fg=TEXT_PRIMARY, insertbackground="white", relief="flat", font=("Helvetica Neue", 12), borderwidth=0)
        entry.insert(0, self.config[key])
        entry.pack(fill="x", ipady=10)
        entry.bind("<KeyRelease>", lambda e: self.realign_all())
        return entry

    def prepare_magnetic_slots(self):
        self.slot_y_centers = [t.winfo_y() + t.winfo_height()/2 for t in self.tile_widgets]
        self.slot_y_coords = [t.winfo_y() for t in self.tile_widgets]

    def preview_magnetic_shift(self, dragging_tile, center_y):
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
        menu = Menu(self.root, tearoff=0, bg=SIDEBAR_BG, fg=TEXT_PRIMARY, activebackground=ACCENT_BLUE, font=("PingFang SC", 11))
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
        
        x = self.root.winfo_x() + (self.root.winfo_width() - 300) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 380) // 2
        panel.geometry(f"+{x}+{y}")

        def create_slider(parent, label, key, from_val, to_val):
            tk.Label(parent, text=label, fg=TEXT_SECONDARY, bg=SIDEBAR_BG, font=("PingFang SC", 10)).pack(pady=(15, 0))
            s = tk.Scale(parent, from_=from_val, to=to_val, orient="horizontal", bg=SIDEBAR_BG, fg=TEXT_PRIMARY,
                         highlightthickness=0, troughcolor="#333", activebackground=ACCENT_BLUE,
                         command=lambda v: self.update_logo_config(key, v))
            s.set(self.config.get(key, 0))
            s.pack(fill="x", padx=30)
            return s

        create_slider(panel, "Logo 比例 (%)", "logo_scale", 5, 80)
        create_slider(panel, "水平偏移 (左右)", "logo_offset_x", -500, 500)
        create_slider(panel, "垂直偏移 (上下)", "logo_offset_y", -500, 500)

        MacButton(panel, text="重置位置", command=lambda: self.reset_logo_pos(panel), 
                  bg="#444", fg="white", borderless=1).pack(pady=30, padx=50, fill="x", ipady=8)

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
        
        sw, sh = max(self.stage.winfo_width()-60, 100), max(self.stage.winfo_height()-60, 100)
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
                    lh = int(l_img.size[1] * (lw / l_img.size[0]))
                    tk_l = ImageTk.PhotoImage(l_img.resize((lw, lh), Image.Resampling.LANCZOS))
                    self.logo_label.config(image=tk_l, bg=bg_hex); self.logo_label.image = tk_l
                    
                    base_x = (self.stage.winfo_width() - lw) // 2
                    base_y = curr_y - p_sp + (p_bh - lh) // 2
                    final_x = base_x + int(self.config["logo_offset_x"] * scale)
                    final_y = base_y + int(self.config["logo_offset_y"] * scale)
                    self.logo_label.place(x=final_x, y=final_y)
            else: self.logo_label.place_forget()
        except: pass

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
        p = filedialog.askopenfilename(initialdir=self.config.get("last_logo_dir"), filetypes=[("Image", "*.png *.psd *.jpg")])
        if p:
            self.config["last_logo_dir"] = os.path.dirname(p)
            self.config["logo_library"].append(p)
            self.apply_logo(p)

    def clear_logo(self): 
        self.config["logo_path"] = ""; self.save_settings(); self.realign_all()

    def handle_drop(self, event):
        paths = re.findall(r'{(.*?)}|(\S+)', event.data)
        new_paths = [p[0] if p[0] else p[1] for p in paths if (p[0] or p[1]).lower().endswith(('.jpg', '.jpeg', '.png', '.psd', '.tiff'))]
        if new_paths: self.image_paths.extend(new_paths); self.config["last_img_dir"] = os.path.dirname(new_paths[0]); self.init_load_images()

    def add_images(self):
        p = filedialog.askopenfilenames(initialdir=self.config.get("last_img_dir"), filetypes=[("Images", "*.jpg *.jpeg *.png *.psd *.tiff")])
        if p: self.image_paths.extend(list(p)); self.config["last_img_dir"] = os.path.dirname(p[0]); self.init_load_images()

    def init_load_images(self):
        for w in self.tile_widgets: w.destroy()
        self.tile_widgets, self.img_ratios, self.preview_cache = [], [], {}
        self.last_p_tw = 0
        for i, p in enumerate(self.image_paths):
            with Image.open(p) as img:
                self.img_ratios.append(img.size[1] / img.size[0])
                prev = img.convert("RGB"); prev.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                self.tile_widgets.append(DraggableTile(self.stage, p, prev, i, self))
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
                                                   filetypes=[("JPEG", "*.jpg")])
            if save_p:
                self.config["last_export_dir"] = os.path.dirname(save_p)
                canvas.save(save_p, quality=95, dpi=(300, 300))
                self.save_settings()
                messagebox.showinfo("成功", "成品已保存")
        except Exception as e: messagebox.showerror("错误", str(e))

if __name__ == "__main__":
    root = TkinterDnD.Tk(); app = AoiStitcher(root); root.mainloop()
