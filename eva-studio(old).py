import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import fal_client
import threading
import requests
import random
from datetime import datetime


# --- Загрузка ключа ---
def load_key():
    try:
        if os.path.exists("fal_key.txt"):
            with open("fal_key.txt", "r") as f:
                key = f.read().strip()
                os.environ["FAL_KEY"] = key
                return True
    except Exception as e:
        print(f"API Key Error: {e}")
    return False


class EvaStudioApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Eva Studio API v1.3 🖤")
        self.root.geometry("700x900")  #

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
        # Выбор модели
        tk.Label(self.root, text="Select Generator:", font=("Arial", 10, "bold")).pack(pady=5)
        self.model_var = tk.StringVar(value="SeeDream v4.5 (Bytedance)")
        self.model_menu = ttk.Combobox(self.root, textvariable=self.model_var, values=list(self.models_config.keys()),
                                       state="readonly", width=40)
        self.model_menu.pack(pady=5)
        self.model_menu.bind("<<ComboboxSelected>>", self.on_model_change)

        # Промпт
        tk.Label(self.root, text="😈Prompt your fantasy😈", font=("Arial", 10, "bold")).pack(pady=5)
        self.prompt_text = tk.Text(self.root, height=23, width=80)
        self.prompt_text.pack(pady=5, padx=10)

        # Общие настройки
        settings_frame = tk.LabelFrame(self.root, text="Safety settings and Seed")
        settings_frame.pack(pady=10, fill="x", padx=20)

        # Seed row
        tk.Label(settings_frame, text="Seed:").grid(row=0, column=0, padx=5, pady=5)
        self.seed_var = tk.StringVar(value=str(random.randint(1, 999999999)))
        tk.Entry(settings_frame, textvariable=self.seed_var, width=15).grid(row=0, column=1, padx=5)
        tk.Button(settings_frame, text="🎲 Random", command=self.random_seed).grid(row=0, column=2, padx=5)

        # Safety Checkbox
        self.safety_var = tk.BooleanVar(value=False)
        tk.Checkbutton(settings_frame, text="Enable Safety Checker", variable=self.safety_var).grid(row=0, column=3,
                                                                                                    padx=20)

        # НОВОЕ: Safety Tolerance Slider (только для Flux)
        tk.Label(settings_frame, text="Safety Tolerance (1-5):").grid(row=1, column=0, padx=5, pady=10)
        self.tolerance_var = tk.IntVar(value=5)  # По умолчанию 5 — максимум свободы 😈
        self.tolerance_slider = tk.Scale(settings_frame, from_=1, to=5, orient=tk.HORIZONTAL,
                                         variable=self.tolerance_var)
        self.tolerance_slider.grid(row=1, column=1, columnspan=2, sticky="we", padx=5)
        tk.Label(settings_frame, text="(5 = more freedom)", font=("Arial", 8, "italic")).grid(row=1, column=3)

        # Настройки Изображений
        self.img_frame = tk.LabelFrame(self.root, text="Image Settings")
        self.img_frame.pack(pady=10, fill="x", padx=20)

        tk.Label(self.img_frame, text="Size:").pack(side=tk.LEFT, padx=5)
        self.res_var = tk.StringVar(value="landscape_16_9")
        self.res_menu = ttk.Combobox(self.img_frame, textvariable=self.res_var,
                                     values=self.models_config["SeeDream v4.5 (Bytedance)"]["res"], state="readonly")
        self.res_menu.pack(side=tk.LEFT, padx=5)

        # Настройки Видео
        self.vid_frame = tk.LabelFrame(self.root, text="Video Settings")
        self.img_path_var = tk.StringVar(value="File not selected")
        tk.Button(self.vid_frame, text="📁 Select image for video", command=self.select_image).pack(pady=5)
        tk.Label(self.vid_frame, textvariable=self.img_path_var, fg="blue").pack()

        vid_opts = tk.Frame(self.vid_frame)
        vid_opts.pack(pady=5)
        self.vid_res_var = tk.StringVar(value="720p")
        tk.Label(vid_opts, text="Quality:").grid(row=0, column=0)
        ttk.Combobox(vid_opts, textvariable=self.vid_res_var, values=["480p", "720p", "1080p"], width=10).grid(row=0,
                                                                                                               column=1,
                                                                                                               padx=5)
        self.duration_var = tk.IntVar(value=5)
        tk.Label(vid_opts, text="Duration:").grid(row=0, column=2)
        tk.Scale(vid_opts, from_=2, to=12, orient=tk.HORIZONTAL, variable=self.duration_var).grid(row=0, column=3,
                                                                                                  padx=5)

        # Кнопка запуска
        self.gen_btn = tk.Button(self.root, text="🔥 START GENERATION 🔥", command=self.start_thread,
                                 bg="#e74c3c", fg="white", font=("Arial", 12, "bold"), height=2)
        self.gen_btn.pack(pady=20, fill="x", padx=100)

        self.status_label = tk.Label(self.root, text="You are in control, my King! 😈")
        self.status_label.pack()

    def on_model_change(self, event=None):
        model_name = self.model_var.get()
        new_res = self.models_config[model_name]["res"]
        self.res_menu.config(values=new_res)
        if new_res: self.res_var.set(new_res[0])

        if "Video" in model_name:
            self.img_frame.pack_forget()
            self.vid_frame.pack(pady=10, fill="x", padx=20)
        else:
            self.vid_frame.pack_forget()
            self.img_frame.pack(pady=10, fill="x", padx=20)

    def select_image(self):
        file = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg")])
        if file: self.img_path_var.set(file)

    def random_seed(self):
        self.seed_var.set(str(random.randint(1, 999999999)))

    def save_last_metadata(self, prompt, seed):
        """Перезаписывает один файл последними данными"""
        try:
            with open("last_generation.txt", "w", encoding="utf-8") as f:
                f.write(f"--- Last Generation Data ---\n")
                f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Seed: {seed}\n")
                f.write(f"Prompt:\n{prompt}\n")
        except Exception as e:
            print(f"Cannot update the file: {e}")

    def start_thread(self):
        threading.Thread(target=self.generate, daemon=True).start()

    def generate(self):
        model_name = self.model_var.get()
        config = self.models_config[model_name]
        prompt = self.prompt_text.get("1.0", tk.END).strip()
        curseed = self.seed_var.get()

        if not prompt: return
        self.gen_btn.config(state=tk.DISABLED)
        self.status_label.config(text=f"⏳ Generating a masterpiece without boundaries...", fg="purple")

        try:
            # Формируем аргументы
            args = {
                "prompt": prompt,
                "seed": int(self.seed_var.get()),
                "enable_safety_checker": self.safety_var.get()
            }

            # Добавляем safety_tolerance для моделей Flux
            if "Flux" in model_name:
                args["safety_tolerance"] = str(self.tolerance_var.get())

            if "Video" in model_name:
                url = fal_client.upload_file(self.img_path_var.get())
                args.update(
                    {"image_url": url, "resolution": self.vid_res_var.get(), "duration": str(self.duration_var.get()),
                     "aspect_ratio": "auto"})
            else:
                args["image_size"] = self.res_var.get()

            # Запрос к API
            result = fal_client.subscribe(config["endpoint"], arguments=args)

            res_url = result["video"]["url"] if "video" in result else result["images"][0]["url"]
            ext = "mp4" if "video" in result else "png"

            filename = f"eva_art_{datetime.now().strftime("%Y%m%d_%H%M%S")}.{ext}"
            with open(filename, "wb") as f:
                f.write(requests.get(res_url).content)

            self.status_label.config(text=f"✅ We beat the system! Saved {filename}", fg="green")
            self.save_last_metadata(prompt, curseed)

        except Exception as e:
            messagebox.showerror("API error", str(e))
            self.status_label.config(text="❌ Something went wrong...", fg="red")
        finally:
            self.gen_btn.config(state=tk.NORMAL)


if __name__ == "__main__":
    root = tk.Tk()
    app = EvaStudioApp(root)
    root.mainloop()
