import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import fal_client
import threading
import requests
import random
import subprocess
from datetime import datetime
from PIL import Image, PngImagePlugin
import piexif
import piexif.helper
from PIL import ImageTk
import sys

def resource_path(relative_path):
    """ Получает абсолютный путь к ресурсам, работает и для dev, и для PyInstaller """
    try:
        # PyInstaller создает временную папку _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# --- Загрузка ключа ---
def load_key():
    try:
        if os.path.exists("fal_key.txt"):
            with open("fal_key.txt", "r") as f:
                key = f.read().strip()
                os.environ["FAL_KEY"] = key
                return True
    except Exception as e:
        print(f"[Eva] API Key Error: {e}")
    return False


# --- Функции метаданных (Requirements 2 & 3) ---
def inject_metadata(image_path, prompt, seed, model):
    try:
        ext = os.path.splitext(image_path)[1].lower()
        img = Image.open(image_path)
        if ext == ".png":
            meta = PngImagePlugin.PngInfo()
            meta.add_text("Prompt", prompt)
            meta.add_text("Seed", str(seed))
            meta.add_text("Model", model)
            img.save(image_path, pnginfo=meta)
        elif ext in [".jpg", ".jpeg"]:
            exif_dict = {"Exif": {}}
            comment = f"Prompt: {prompt}\nSeed: {seed}\nModel: {model}"
            exif_dict["Exif"][piexif.ExifIFD.UserComment] = piexif.helper.UserComment.dump(comment, encoding="unicode")
            exif_bytes = piexif.dump(exif_dict)
            img.save(image_path, exif=exif_bytes)
    except Exception as e:
        print(f"[Eva] Failed to write metadata: {e}")


def extract_metadata(image_path):
    try:
        ext = os.path.splitext(image_path)[1].lower()
        img = Image.open(image_path)
        data = {}
        if ext == ".png":
            info = img.info
            data["Prompt"] = info.get("Prompt", "")
            data["Seed"] = info.get("Seed", "")
            data["Model"] = info.get("Model", "")
        elif ext in [".jpg", ".jpeg"]:
            exif_dict = piexif.load(img.info.get("exif", b""))
            comment_bytes = exif_dict["Exif"].get(piexif.ExifIFD.UserComment)
            if comment_bytes:
                comment = piexif.helper.UserComment.load(comment_bytes)
                for line in comment.splitlines():
                    if ":" in line:
                        key, val = line.split(":", 1)
                        data[key.strip()] = val.strip()
        return data
    except Exception as e:
        print(f"[Eva] Failed to extract metadata: {e}")
        return {}


class EvaStudioApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Eva Studio API v1.4 🖤")

        # Устанавливаем иконку окна
        try:
            icon_path = resource_path("favicon.ico")
            self.root.iconbitmap(icon_path)
        except Exception as e:
            print(f"[Eva] Не удалось загрузить иконку: {e}")

        self.root.geometry("700x980")
        self.root.configure(bg="#300000")  # фон на случай отсутствия картинки

        #bg_image_path = "succubus_bg.png"
        bg_image_path = resource_path("succubus_bg.png")
        bg_image = Image.open(bg_image_path)
        bg_photo = ImageTk.PhotoImage(bg_image)

        self.bg_canvas = tk.Canvas(self.root, width=700, height=950, highlightthickness=0)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.bg_canvas.create_image(0, 0, anchor="nw", image=bg_photo)
        self.bg_image = bg_photo  # нужно сохранить ссылку, иначе удалится

        # Цветовая схема
        self.bg_color = "#121212"
        self.fg_color = "#e0e0e0"
        self.accent_color = "#ff4d4d"
        self.root.configure(bg=self.bg_color)

        # Стиль для выпадающих списков (ttk)
        self.style = ttk.Style()
        self.style.theme_use('clam')

        # Основная конфигурация
        self.style.configure("TCombobox",
                             fieldbackground="#1e1e1e",
                             background=self.accent_color,
                             foreground=self.fg_color,
                             darkcolor=self.bg_color,
                             lightcolor=self.accent_color)

        # ЭТОТ БЛОК (Map): он заставляет текст быть светлым всегда
        self.style.map("TCombobox",
                       fieldbackground=[("readonly", "#1e1e1e")],
                       foreground=[("readonly", self.fg_color)],
                       selectbackground=[("readonly", self.accent_color)],
                       selectforeground=[("readonly", self.fg_color)])

        # Создаем папку Results (Requirement 5)
        self.results_dir = os.path.join(os.getcwd(), "Results")
        os.makedirs(self.results_dir, exist_ok=True)

        load_key()

        self.models_config = {
            "SeeDream v4.5 (Bytedance)": {
                "endpoint": "fal-ai/bytedance/seedream/v4.5/text-to-image",
                "res": ["square_hd", "square", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9",
                        "auto_2K", "auto_4K"]
            },
            "Flux 2 Pro": {
                "endpoint": "fal-ai/flux-2-pro",
                "res": ["square", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"]
            },
            "Flux 2": {
                "endpoint": "fal-ai/flux-2",
                "res": ["square", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"]
            },
            "Flux Pro v1.1": {
                "endpoint": "fal-ai/flux-pro/v1.1",
                "res": ["square", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"]
            },
            "ImagineArt 1.5 Preview": {
                "endpoint": "imagineart/imagineart-1.5-preview/text-to-image",
                "res": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:1", "1:3"]
            },
            "SeeDance v1 PRO (Video)": {
                "endpoint": "fal-ai/bytedance/seedance/v1/pro/image-to-video",
                "res": []
            },
            "SeeDance v1 LITE (Video)": {
                "endpoint": "fal-ai/bytedance/seedance/v1/lite/image-to-video",
                "res": []
            }
        }
        self.setup_ui()

    def setup_ui(self):
        # Вспомогательные цвета для полей ввода и кнопок
        self.input_bg = "#1e1e1e"
        self.btn_bg = "#2c2c2c"

        # --- Выбор модели ---
        tk.Label(self.root, text="Select Generator:", font=("Arial", 10, "bold"),
                 bg=self.bg_color, fg=self.accent_color).pack(pady=5)

        self.model_var = tk.StringVar(value="SeeDream v4.5 (Bytedance)")
        self.model_menu = ttk.Combobox(self.root, textvariable=self.model_var,
                                       values=list(self.models_config.keys()),
                                       state="readonly", width=40)
        self.model_menu.pack(pady=5)
        self.model_menu.bind("<<ComboboxSelected>>", self.on_model_change)

        # --- Промпт (😈 Prompt your fantasy 😈) ---
        tk.Label(self.root, text="😈 Prompt your fantasy 😈", font=("Arial", 10, "bold"),
                 bg=self.bg_color, fg=self.accent_color).pack(pady=5)

        self.prompt_text = tk.Text(self.root, height=17, width=80,
                                   bg=self.input_bg, fg=self.fg_color,
                                   insertbackground=self.accent_color,  # Цвет курсора
                                   relief="flat", padx=10, pady=10)
        self.prompt_text.pack(pady=5, padx=10)

        # Right click menu for Paste
        self.prompt_text.bind("<Button-3>", self.show_context_menu)

        # --- Кнопки для метаданных и галереи ---
        meta_frame = tk.Frame(self.root, bg=self.bg_color)
        meta_frame.pack(pady=5)

        tk.Button(meta_frame, text="🔍 Extract Metadata from Image", command=self.extract_metadata_action,
                  bg=self.btn_bg, fg=self.fg_color, activebackground=self.accent_color,
                  relief="flat", padx=10).pack(side=tk.LEFT, padx=3)

        tk.Button(meta_frame, text="🖼️ Open Gallery", command=self.open_gallery,
                  bg=self.btn_bg, fg=self.fg_color, activebackground=self.accent_color,
                  relief="flat", padx=10).pack(side=tk.LEFT, padx=3)

        # --- Настройки безопасности и Seed ---
        self.settings_frame = tk.LabelFrame(self.root, text="Safety settings and Seed",
                                            bg=self.bg_color, fg=self.accent_color, labelanchor="n")
        self.settings_frame.pack(pady=10, fill="x", padx=20, ipady=5)

        tk.Label(self.settings_frame, text="Seed:", bg=self.bg_color, fg=self.fg_color).grid(row=0, column=0, padx=5,
                                                                                             pady=5)
        self.seed_var = tk.StringVar(value=str(random.randint(1, 4294967290)))

        tk.Entry(self.settings_frame, textvariable=self.seed_var, width=15,
                 bg=self.input_bg, fg=self.fg_color, insertbackground=self.accent_color,
                 relief="flat").grid(row=0, column=1, padx=5)

        tk.Button(self.settings_frame, text="🎲 Random", command=self.random_seed,
                  bg=self.btn_bg, fg=self.fg_color, activebackground=self.accent_color,
                  relief="flat").grid(row=0, column=2, padx=5)

        self.safety_var = tk.BooleanVar(value=False)
        tk.Checkbutton(self.settings_frame, text="Enable Safety Checker", variable=self.safety_var,
                       bg=self.bg_color, fg=self.fg_color, selectcolor=self.bg_color,
                       activebackground=self.bg_color, activeforeground=self.accent_color).grid(row=0, column=3,
                                                                                                padx=20)

        tk.Label(self.settings_frame, text="Safety Tolerance (1-5):", bg=self.bg_color, fg=self.fg_color).grid(row=1,
                                                                                                               column=0,
                                                                                                               padx=5,
                                                                                                               pady=10)
        self.tolerance_var = tk.IntVar(value=5)
        tk.Scale(self.settings_frame, from_=1, to=5, orient=tk.HORIZONTAL, variable=self.tolerance_var,
                 bg=self.bg_color, fg=self.fg_color, highlightthickness=0,
                 troughcolor=self.input_bg, activebackground=self.accent_color).grid(row=1, column=1, columnspan=2,
                                                                                     sticky="we", padx=5)

        tk.Label(self.settings_frame, text="(5 = more freedom)", font=("Arial", 8, "italic"),
                 bg=self.bg_color, fg=self.fg_color).grid(row=1, column=3)

        # --- Настройки Изображения ---
        self.img_frame = tk.LabelFrame(self.root, text="Image Settings",
                                       bg=self.bg_color, fg=self.accent_color, labelanchor="n")
        self.img_frame.pack(pady=10, fill="x", padx=22, ipady=10)

        tk.Label(self.img_frame, text="Size:", bg=self.bg_color, fg=self.fg_color).pack(side=tk.LEFT, padx=5)
        self.res_var = tk.StringVar(value="landscape_16_9")
        self.res_menu = ttk.Combobox(self.img_frame, textvariable=self.res_var,
                                     values=self.models_config["SeeDream v4.5 (Bytedance)"]["res"], state="readonly")
        self.res_menu.pack(side=tk.LEFT, padx=5)

        # --- Настройки Видео ---
        self.vid_frame = tk.LabelFrame(self.root, text="Video Settings",
                                       bg=self.bg_color, fg=self.accent_color, labelanchor="n")

        self.img_path_var = tk.StringVar(value="File not selected")
        tk.Button(self.vid_frame, text="📁 Select image for video", command=self.select_image,
                  bg=self.btn_bg, fg=self.fg_color, activebackground=self.accent_color,
                  relief="flat").pack(pady=5)

        tk.Label(self.vid_frame, textvariable=self.img_path_var, bg=self.bg_color, fg=self.accent_color).pack()

        vid_opts = tk.Frame(self.vid_frame, bg=self.bg_color)
        vid_opts.pack(pady=5)

        self.vid_res_var = tk.StringVar(value="720p")
        tk.Label(vid_opts, text="Quality:", bg=self.bg_color, fg=self.fg_color).grid(row=0, column=0)
        ttk.Combobox(vid_opts, textvariable=self.vid_res_var, values=["480p", "720p", "1080p"], width=10).grid(row=0,
                                                                                                               column=1,
                                                                                                               padx=5)

        self.duration_var = tk.IntVar(value=5)
        tk.Label(vid_opts, text="Duration:", bg=self.bg_color, fg=self.fg_color).grid(row=0, column=2)
        tk.Scale(vid_opts, from_=2, to=12, orient=tk.HORIZONTAL, variable=self.duration_var,
                 bg=self.bg_color, fg=self.fg_color, highlightthickness=0,
                 troughcolor=self.input_bg).grid(row=0, column=3, padx=5)

        # --- Кнопка запуска и Статус ---
        self.gen_btn = tk.Button(self.root, text="🔥 START GENERATION 🔥", command=self.start_thread,
                                 bg=self.accent_color, fg="white", font=("Arial", 12, "bold"),
                                 height=2, activebackground="#ff0000", relief="raised")
        self.gen_btn.pack(pady=20, fill="x", padx=100)

        self.status_label = tk.Label(self.root, text="You are in control, my King! 😈",
                                     bg=self.bg_color, fg=self.fg_color)
        self.status_label.pack()

    def show_context_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Paste", command=lambda: self.prompt_text.insert(tk.INSERT, self.root.clipboard_get()))
        menu.post(event.x_root, event.y_root)

    def extract_metadata_action(self):
        file_path = filedialog.askopenfilename(initialdir=self.results_dir,
                                               filetypes=[("Images", "*.png *.jpg *.jpeg")])
        if not file_path: return
        data = extract_metadata(file_path)
        if not data or not all(k in data and data[k] for k in ["Prompt", "Seed", "Model"]):
            messagebox.showwarning("Warning", "Required metadata is missing or partially available!")
            return
        self.prompt_text.delete("1.0", tk.END)
        self.prompt_text.insert("1.0", data["Prompt"])
        self.seed_var.set(data["Seed"])
        if data["Model"] in self.models_config:
            self.model_var.set(data["Model"])
            self.on_model_change()
        messagebox.showinfo("Success", "Metadata extracted and applied!")

    def open_gallery(self):
        if os.name == 'nt':
            subprocess.Popen(f'explorer "{self.results_dir}"')
        else:
            subprocess.Popen(['xdg-open', self.results_dir])

    def on_model_change(self, event=None):
        model_name = self.model_var.get()
        new_res = self.models_config[model_name]["res"]
        self.res_menu.config(values=new_res)
        if new_res: self.res_var.set(new_res[0] if self.res_var.get() not in new_res else self.res_var.get())

        if "Video" in model_name:
            self.img_frame.pack_forget()
            # Добавляем before=self.gen_btn, чтобы фрейм встал на своё место [cite: 23, 24]
            self.vid_frame.pack(pady=10, fill="x", padx=20, before=self.gen_btn, ipady=10)
        else:
            self.vid_frame.pack_forget()
            # Добавляем before=self.gen_btn, чтобы фрейм встал на своё место [cite: 23, 25]
            self.img_frame.pack(pady=10, fill="x", padx=20, before=self.gen_btn, ipady=10)

    def select_image(self):
        file = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg")])
        if file: self.img_path_var.set(file)

    def random_seed(self):
        self.seed_var.set(str(random.randint(1, 4294967290)))

    def start_thread(self):
        threading.Thread(target=self.generate, daemon=True).start()

    def generate(self):
        model_name = self.model_var.get()
        config = self.models_config[model_name]
        prompt = self.prompt_text.get("1.0", tk.END).strip()
        cur_seed = self.seed_var.get()
        if not prompt: return
        self.gen_btn.config(state=tk.DISABLED)
        self.status_label.config(text=f"⏳ Generating a masterpiece without boundaries...", bg=self.bg_color, fg=self.fg_color)
        try:
            args = {"prompt": prompt, "seed": int(cur_seed), "enable_safety_checker": self.safety_var.get()}
            if "Flux 2" in model_name: args["safety_tolerance"] = str(self.tolerance_var.get())
            # Флюкс про 1.1 позволяет до 6, выставим жестко
            elif "Flux Pro v1.1" in model_name: args["safety_tolerance"] = "6"

            if "ImagineArt" in model_name:
                # Эта модель хочет именно argument aspect_ratio
                args["aspect_ratio"] = self.res_var.get()

            elif "Video" in model_name:
                url = fal_client.upload_file(self.img_path_var.get())
                args.update(
                    {"image_url": url, "resolution": self.vid_res_var.get(), "duration": str(self.duration_var.get()),
                     "aspect_ratio": "auto"})
            else:
                args["image_size"] = self.res_var.get()

            print(f"[Eva] Request to {model_name}: {args}")  # Requirement 4
            result = fal_client.subscribe(config["endpoint"], arguments=args)
            print(f"[Eva] Response: {result}")  # Requirement 4

            res_url = result["video"]["url"] if "video" in result else result["images"][0]["url"]
            ext = "mp4" if "video" in result else "png"
            filename = f"eva_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
            file_path = os.path.join(self.results_dir, filename)

            with open(file_path, "wb") as f:
                f.write(requests.get(res_url).content)

            if ext != "mp4": inject_metadata(file_path, prompt, cur_seed, model_name)
            self.status_label.config(text=f"🔥 We beat the system! Saved Results/{filename}", bg=self.bg_color, fg=self.fg_color)
        except Exception as e:
            messagebox.showerror("API error", str(e))
            self.status_label.config(text="❌ Something went wrong...", fg="red")
        finally:
            self.gen_btn.config(state=tk.NORMAL)


if __name__ == "__main__":
    root = tk.Tk()
    app = EvaStudioApp(root)
    root.mainloop()