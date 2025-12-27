import tkinter as tk
from tkinter import filedialog, messagebox, ttk
# 注意：这里引入了专门解决 Mac 按钮变色问题的库
try:
    from tkmacosx import Button as MacButton
except ImportError:
    MacButton = tk.Button # 如果没装，就退回普通模式

from tkinterdnd2 import DND_FILES, TkinterDnD
from PIL import Image, ImageTk
import os
import json
import re

# 配置文件路径：记住你的参数
CONFIG_FILE = os.path.expanduser("~/Documents/aoi_config.json")

# --- iOS 极简深色配色 ---
BG_COLOR = "#121212"       # 纯深灰背景
SIDEBAR_BG = "#1E1E1E"    # 侧边栏稍亮
ENTRY_BG = "#2C2C2E"      # 输入框颜色
TEXT_WHITE = "#FFFFFF"    # 纯白文字
TEXT_GRAY = "#8E8E93"     # 辅助文字灰色
ACCENT_BLUE = "#0A84FF"   # 苹果蓝
ACCENT_GREEN = "#30D158"  # 苹果绿

class DraggableLabel(tk.Label):
    def __init__(self, master, image_path, thumbnail, index, on_drop_callback, **kwargs):
        super().__init__(master, image=thumbnail, bg=BG_COLOR, **kwargs)
        self.image_path = image_path
        self.index = index
        self.on_drop_callback = on_drop_callback
        self.bind("<ButtonPress-1>", self.on_start)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_drop)

    def on_start(self, event):
        self.config(bg=ACCENT_BLUE)
        self.lift()

    def on_drag(self, event):
        x = self.winfo_x() + event.x - self.start_x
        y = self.winfo_y() + event.y - self.start_y
        self.place(x=x, y=y)

    def on_drop(self, event):
        self.config(bg=BG_COLOR)
        new_y = self.winfo_y() + event.y
        self.on_drop_callback(self.index, new_y)

class AoiStitcherPro:
    def __init__(self, root):
        self.root = root
        self.root.title("aoi拼图 v1.2")
        self.root.geometry("1000x800")
        self.root.configure(bg=BG_COLOR)
        
        self.image_paths = []
        self.thumb_widgets = []
        
        # 参数记忆功能
        self.config = {
            "width": "2000",
            "spacing": "40",
            "bottom_h": "200",
            "logo_path": "",
            "last_save_dir": os.path.expanduser("~/Desktop")
        }
        self.load_settings()
        self.setup_ui()

    def load_settings(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    self.config.update(json.load(f))
            except: pass

    def save_settings(self):
        self.config["width"] = self.width_entry.get()
        self.config["spacing"] = self.spacing_entry.get()
        self.config["bottom_h"] = self.bottom_entry.get()
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f)
        except: pass

    def setup_ui(self):
        # 侧边栏
        self.sidebar = tk.Frame(self.root, bg=SIDEBAR_BG, width=280, padx=20, pady=30)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        tk.Label(self.sidebar, text="aoi拼图", font=("PingFang SC", 26, "bold"), fg=TEXT_WHITE, bg=SIDEBAR_BG).pack(anchor="w", pady=(0, 30))

        # 参数输入
        self.width_entry = self.create_input("统一宽度 (px)", "width")
        self.spacing_entry = self.create_input("图片间距 (px)", "spacing")
        self.bottom_entry = self.create_input("底部Logo高度", "bottom_h")

        # 蓝色功能按钮 - 使用 MacButton 强制变色
        self.add_btn = MacButton(self.sidebar, text="添加照片", command=self.add_images_btn, 
                                 bg=ACCENT_BLUE, fg="white", borderless=1, font=("PingFang SC", 14))
        self.add_btn.pack(fill="x", pady=(20, 10), ipady=10)

        self.logo_btn = MacButton(self.sidebar, text="设置 Logo", command=self.set_logo, 
                                  bg="#3A3A3C", fg="white", borderless=1, font=("PingFang SC", 14))
        self.logo_btn.pack(fill="x", pady=0, ipady=10)

        # 绿色导出按钮
        self.exp_btn = MacButton(self.sidebar, text="完成并导出", command=self.export_action, 
                                 bg=ACCENT_GREEN, fg="black", borderless=1, font=("PingFang SC", 16, "bold"))
        self.exp_btn.pack(side="bottom", fill="x", pady=20, ipady=15)

        # 右侧预览区
        self.preview_area = tk.Frame(self.root, bg=BG_COLOR)
        self.preview_area.pack(side="right", fill="both", expand=True)
        
        # 拖拽支持
        self.preview_area.drop_target_register(DND_FILES)
        self.preview_area.dnd_bind('<<Drop>>', self.handle_drop)

        self.canvas = tk.Canvas(self.preview_area, bg=BG_COLOR, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.preview_area, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = tk.Frame(self.canvas, bg=BG_COLOR)
        
        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True, padx=20, pady=20)

        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1*(e.delta)), "units"))
        self.scroll_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

    def create_input(self, label, key):
        tk.Label(self.sidebar, text=label, fg=TEXT_GRAY, bg=SIDEBAR_BG, font=("PingFang SC", 11)).pack(anchor="w", pady=(10, 5))
        entry = tk.Entry(self.sidebar, bg=ENTRY_BG, fg=TEXT_WHITE, insertbackground="white", relief="flat", font=("Helvetica", 14))
        entry.insert(0, self.config[key])
        entry.pack(fill="x", ipady=8)
        return entry

    def handle_drop(self, event):
        paths = re.findall(r'{(.*?)}|(\S+)', event.data)
        files = [p[0] if p[0] else p[1] for p in paths]
        self.image_paths.extend([f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png', '.psd'))])
        self.refresh_preview()

    def add_images_btn(self):
        paths = filedialog.askopenfilenames(filetypes=[("Images", "*.jpg *.jpeg *.png *.psd")])
        if paths:
            self.image_paths.extend(list(paths))
            self.refresh_preview()

    def set_logo(self):
        path = filedialog.askopenfilename(filetypes=[("Logo Files", "*.png *.psd")])
        if path:
            self.config["logo_path"] = path
            self.logo_btn.config(bg="#2C2C2E", text="Logo 已就绪 ✓")
            self.save_settings()

    def refresh_preview(self):
        for w in self.thumb_widgets: w.destroy()
        self.thumb_widgets = []
        for i, path in enumerate(self.image_paths):
            try:
                img = Image.open(path)
                img.thumbnail((400, 400))
                tk_img = ImageTk.PhotoImage(img)
                lbl = DraggableLabel(self.scroll_frame, path, tk_img, i, self.reorder)
                lbl.image = tk_img
                lbl.pack(pady=10)
                self.thumb_widgets.append(lbl)
            except: continue

    def reorder(self, old_idx, drop_y):
        new_idx = 0
        for i, w in enumerate(self.thumb_widgets):
            if drop_y > w.winfo_y() + w.winfo_height()/2: new_idx = i + 1
        item = self.image_paths.pop(old_idx)
        if new_idx > old_idx: new_idx -= 1
        self.image_paths.insert(new_idx, item)
        self.refresh_preview()

    def export_action(self):
        if not self.image_paths: return
        self.save_settings()
        try:
            tw = int(self.width_entry.get())
            sp = int(self.spacing_entry.get())
            bh = int(self.bottom_entry.get())
            
            imgs = []
            th = 0
            for p in self.image_paths:
                img = Image.open(p)
                nh = int(img.size[1] * (tw / img.size[0]))
                imgs.append(img.resize((tw, nh), Image.Resampling.LANCZOS))
                th += nh
            
            canvas = Image.new("RGB", (tw, th + (len(imgs)-1)*sp + bh), (255, 255, 255))
            y = 0
            for img in imgs:
                canvas.paste(img, (0, y))
                y += img.size[1] + sp
            
            if self.config["logo_path"]:
                logo = Image.open(self.config["logo_path"]).convert("RGBA")
                lw = tw // 4
                lh = int(logo.size[1]*(lw/logo.size[0]))
                logo = logo.resize((lw, lh), Image.Resampling.LANCZOS)
                canvas.paste(logo, ((tw-lw)//2, y-sp+(bh-lh)//2), logo)

            save_p = filedialog.asksaveasfilename(initialdir=self.config["last_save_dir"], defaultextension=".jpg")
            if save_p:
                self.config["last_save_dir"] = os.path.dirname(save_p)
                self.save_settings()
                canvas.save(save_p, quality=95)
                messagebox.showinfo("成功", "拼图已导出！")
        except Exception as e: messagebox.showerror("错误", str(e))

if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = AoiStitcherPro(root)
    root.mainloop()
