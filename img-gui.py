import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path
import subprocess
import os
import shlex
import json

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_OK = True
except ImportError:
    DND_OK = False

class ImageProcessorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🖼️ Cherry AI Image Studio")
        self.root.geometry("1100x800")
        self.files = []
        self.input_folder = ""
        self.output_folder = ""
        self.button_widgets = []

        # --- ALLOW ROOT & MAIN FRAME TO EXPAND HORIZONTALLY ---
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # --- SCROLLABLE MAIN CONTAINER ---
        self.main_canvas = tk.Canvas(root)
        main_scrollbar = ttk.Scrollbar(root, orient="vertical", command=self.main_canvas.yview)
        self.main_frame = ttk.Frame(self.main_canvas)

        self.main_frame.bind("<Configure>", lambda e: self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all")))
        self.main_canvas.create_window((0, 0), window=self.main_frame, anchor="nw")
        self.main_canvas.configure(yscrollcommand=main_scrollbar.set)
        self.main_frame.columnconfigure(0, weight=1)

        # Linux/Windows mousewheel support
        self.root.bind_all("<Button-4>", lambda e: self.main_canvas.yview_scroll(-1, "units"))
        self.root.bind_all("<Button-5>", lambda e: self.main_canvas.yview_scroll(1, "units"))
        self.root.bind_all("<MouseWheel>", lambda e: self.main_canvas.yview_scroll(-1*(e.delta//120), "units"))

        self.main_canvas.pack(side="left", fill="both", expand=True)
        main_scrollbar.pack(side="right", fill="y")

        # --- HEADER ---
        ttk.Label(self.main_frame, text="🖼️ Cherry AI Image Studio", font=("Arial", 16, "bold")).pack(pady=10)

        # --- TOP ACTION ROW ---
        top_frame = ttk.Frame(self.main_frame)
        top_frame.pack(pady=5, fill="x", expand=True, padx=10)

        ttk.Button(top_frame, text="📂 Select Input Folder", command=self.pick_folder).pack(side="left", padx=5)
        ttk.Button(top_frame, text="📄 Select Files", command=self.pick_files).pack(side="left", padx=5) # NEW
        ttk.Button(top_frame, text="📂 Open GIMP File", command=self.open_gimp_file).pack(side="left", padx=5)

        output_frame = ttk.Frame(top_frame)
        output_frame.pack(side="left", padx=10, fill="x", expand=True)
        ttk.Label(output_frame, text="Output Dir:").pack(side="left")
        self.output_display = ttk.Label(output_frame, text="Same as input", foreground="gray", width=25)
        self.output_display.pack(side="left", padx=5)
        ttk.Button(output_frame, text="Choose", command=self.choose_output_folder).pack(side="left")

        # --- DROP ZONE ---
        self.drop_zone = tk.Label(self.main_frame, text="📥 Drop images or folders here", relief="solid", borderwidth=2, width=70, height=4, bg="#e8e8e8", anchor="center")
        self.drop_zone.pack(padx=20, pady=10, fill="x", expand=True)
        if DND_OK:
            self.drop_zone.drop_target_register(DND_FILES)
            self.drop_zone.dnd_bind("<<Drop>>", self.on_drop)

        # --- SCROLLABLE PRESETS (LARGER) ---
        ttk.Label(self.main_frame, text="Presets:", font=("Arial", 10, "bold")).pack(pady=(10, 0))
        preset_container = ttk.Frame(self.main_frame)
        preset_container.pack(pady=5, padx=10, fill="x", expand=True)

        preset_scrollbar = ttk.Scrollbar(preset_container, orient=tk.VERTICAL)
        preset_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.preset_canvas = tk.Canvas(preset_container, yscrollcommand=preset_scrollbar.set, height=220)
        self.preset_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        preset_scrollbar.config(command=self.preset_canvas.yview)

        self.preset_buttons_frame = ttk.Frame(self.preset_canvas)
        self.preset_canvas.create_window((0, 0), window=self.preset_buttons_frame, anchor="nw")

        def update_preset_scroll(event):
            self.preset_canvas.configure(scrollregion=self.preset_canvas.bbox("all"))
        self.preset_buttons_frame.bind("<Configure>", update_preset_scroll)

        self.presets = {
            "1. True B&W": 'magick {file} -colorspace gray -threshold 50% "{base}-bw{ext}"',
            "2. Contrast Stretch": 'magick {file} -colorspace gray -contrast-stretch 10%x10% "{base}-stretch{ext}"',
            "3. Edge Cleanup": 'magick {file} -channel A -threshold 50% +channel -fuzz 10% -trim +repage -morphology Close Disk:1 "{base}-cleaned{ext}"',
            "4. Edge Cleanup 1px": 'magick {file} -morphology Erode Diamond:1 -channel A -threshold 50% +channel "{base}-shaved{ext}"',
            "5. Invert Colors": 'magick {file} -channel RGB -negate "{base}-inverted{ext}"',
            "6. Solid Black Fill": 'magick {file} -fill "#000000" -colorize 100% "{base}-black{ext}"',
            "7. Duotone Map": 'magick {file} +level-colors "#123456,#ABCDEF" "{base}-duotone{ext}"',
            "8. Downscale 50% (Lanczos)": 'magick {file} -resize 50% -filter Lanczos "{base}-smooth-lanczos{ext}"',
            "9. Downscale 50% (Mitchell)": 'magick {file} -resize 50% -filter Mitchell "{base}-smooth-mitchell{ext}"',
            "10. Remove White": 'magick {file} -fuzz 5% -transparent white "{base}-trans{ext}"',
            "11. Remove Black + Erode": 'magick {file} -fuzz 15% -transparent "#000000" -morphology Erode Diamond:1 "{base}-eroded{ext}"',
            "12. Flatten to Black BG": 'magick {file} -background black -alpha remove -alpha off "{base}-black-bg{ext}"',
            "13. Set 300 PPI": 'magick {file} -units PixelsPerInch -density 300 "{base}-300dpi{ext}"',
            "14. 75% Downsize": 'magick {file} -resize 75% "{base}-resized{ext}"',
            "15. Crop + 10px Pad": 'magick {file} -trim +repage -bordercolor none -border 10 "{base}-cropped{ext}"',
            "16. Canvas 4096x4096": 'magick {file} -gravity center -extent 4096x4096 "{base}-canvas{ext}"',
            "17. Thicken Lines": 'magick {file} -background white -alpha background -channel A -morphology Dilate Disk:1.5 +channel "{base}-thicker{ext}"',
            "18. Thicken Clean": 'magick {file} -channel A -morphology Dilate Disk:1.5 -threshold 50% +channel "{base}-thickened-clean{ext}"',
            "19. Rounded Corners": 'magick {file} \\( +clone -alpha extract -draw "fill black polygon 0,0 0,15 15,0 fill white circle 15,15 15,0" \\( +clone -flip \\) -compose Multiply -composite \\( +clone -flop \\) -compose Multiply -composite \\) -alpha off -compose CopyOpacity -composite "{base}-rounded{ext}"',
            "20. 1.5x AI Upscale": '~/go/bin/upscayl-cli run -i {file} -o temp-{base}-4x.png -n digital-art-4x && magick temp-{base}-4x.png -filter Lanczos -resize 37.5% "{base}-1.5x{ext}" && rm -f temp-{base}-4x.png',
            "21. 2x AI Upscale": '~/go/bin/upscayl-cli run -i {file} -o temp-{base}-4x.png -n digital-art-4x && magick temp-{base}-4x.png -resize 50% "{base}-2x{ext}" && rm -f temp-{base}-4x.png',
            "22. 3x AI Upscale": '~/go/bin/upscayl-cli run -i {file} -o temp-{base}-4x.png -n digital-art-4x && magick temp-{base}-4x.png -resize 75% "{base}-3x{ext}" && rm -f temp-{base}-4x.png',
            "23. 4x AI Upscale (Native)": '~/go/bin/upscayl-cli run -i {file} -o "{base}-4x{ext}" -n digital-art-4x'
        }
        self._build_preset_buttons()

        # --- SEARCH BAR ---
        ttk.Label(self.main_frame, text="🔍 Filter Presets:", font=("Arial", 10, "bold")).pack(pady=(10, 0))
        search_frame = ttk.Frame(self.main_frame)
        search_frame.pack(pady=5, padx=10, fill="x", expand=True)
        self.search_entry = ttk.Entry(search_frame)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.search_entry.bind("<KeyRelease>", lambda e: self.auto_filter_commands())

        # --- MULTI-LINE COMMAND EDITOR ---
        ttk.Label(self.main_frame, text="Command:", font=("Arial", 10, "bold")).pack(pady=(10, 0))
        cmd_frame = ttk.Frame(self.main_frame)
        cmd_frame.pack(pady=5, padx=10, fill="x", expand=True)
        
        cmd_scrollbar = ttk.Scrollbar(cmd_frame, orient="vertical")
        cmd_scrollbar.pack(side="right", fill="y")
        
        self.cmd_text = tk.Text(cmd_frame, font=("Courier", 10), wrap="word", height=4, 
                                yscrollcommand=cmd_scrollbar.set, bg="#f8f8f8")
        self.cmd_text.pack(side="left", fill="x", expand=True)
        cmd_scrollbar.config(command=self.cmd_text.yview)
        self.cmd_text.insert("1.0", self.presets["1. True B&W"])

        # --- SAVE PRESET ---
        ttk.Button(self.main_frame, text="💾 Save Current Command as Preset", command=self.save_preset).pack(pady=5)

        # --- PRESET MANAGEMENT ---
        mgmt_frame = ttk.Frame(self.main_frame)
        mgmt_frame.pack(pady=5)
        ttk.Button(mgmt_frame, text="📤 Export", command=self.export_presets).pack(side="left", padx=5)
        ttk.Button(mgmt_frame, text="📥 Import", command=self.import_presets).pack(side="left", padx=5)
        ttk.Button(mgmt_frame, text="🗑️ Delete", command=self.delete_preset).pack(side="left", padx=5)

        # --- RUN BUTTONS ---
        run_frame = ttk.Frame(self.main_frame)
        run_frame.pack(pady=10)
        ttk.Button(run_frame, text="▶ Run Selected", command=self.run_selected_preset).pack(side="left", padx=10)
        self.run_btn = ttk.Button(run_frame, text="▶ Run on All Files", command=self.run_all_files)
        self.run_btn.pack(side="left", padx=10)

        # --- STATUS & PROGRESS ---
        self.status = ttk.Label(self.main_frame, text="Ready", foreground="green")
        self.status.pack(pady=5)
        self.progress = ttk.Progressbar(self.main_frame, length=600, mode="determinate")
        self.progress.pack(pady=5)

    def _build_preset_buttons(self):
        for widget in self.button_widgets:
            widget.destroy()
        self.button_widgets.clear()

        num_cols = 4
        total_items = len(self.presets)
        num_rows = (total_items + num_cols - 1) // num_cols

        for idx, name in enumerate(self.presets):
            col = idx // num_rows
            row = idx % num_rows
            btn = ttk.Button(self.preset_buttons_frame, text=name, command=lambda n=name: self.select_preset(n))
            btn.grid(row=row, column=col, padx=4, pady=3, sticky="ew")
            self.button_widgets.append(btn)

        for c in range(num_cols):
            self.preset_buttons_frame.columnconfigure(c, weight=1)

    def auto_filter_commands(self, event=None):
        search_text = self.search_entry.get().lower()
        for widget in self.button_widgets:
            widget.destroy()
        self.button_widgets.clear()

        visible_presets = [name for name in self.presets if search_text in name.lower()]
        
        if not visible_presets:
            ttk.Label(self.preset_buttons_frame, text="No matches found", foreground="gray").grid(row=0, column=0, pady=10)
            self.preset_canvas.configure(scrollregion=self.preset_canvas.bbox("all"))
            return

        num_cols = 4
        num_rows = (len(visible_presets) + num_cols - 1) // num_cols

        for idx, name in enumerate(visible_presets):
            col = idx // num_rows
            row = idx % num_rows
            btn = ttk.Button(self.preset_buttons_frame, text=name, command=lambda n=name: self.select_preset(n))
            btn.grid(row=row, column=col, padx=4, pady=3, sticky="ew")
            self.button_widgets.append(btn)

        for c in range(num_cols):
            self.preset_buttons_frame.columnconfigure(c, weight=1)
        
        self.preset_canvas.configure(scrollregion=self.preset_canvas.bbox("all"))

    def export_presets(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            title="Export Presets Configuration"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.presets, f, indent=2, ensure_ascii=False)
                messagebox.showinfo("✅ Success", f"Presets exported to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("❌ Error", f"Failed to export:\n{str(e)}")

    def import_presets(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            title="Import Presets Configuration"
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    imported = json.load(f)
                if not isinstance(imported, dict):
                    raise ValueError("Invalid format")
                self.search_entry.delete(0, tk.END)
                self.presets = imported
                self._build_preset_buttons()
                messagebox.showinfo("✅ Success", "Presets imported successfully!")
            except json.JSONDecodeError:
                messagebox.showerror("❌ Error", "Invalid JSON file.")
            except Exception as e:
                messagebox.showerror("❌ Error", f"Failed to import:\n{str(e)}")

    def delete_preset(self):
        if not self.presets:
            messagebox.showwarning("⚠️ Empty", "No presets to delete.")
            return
        preset_names = list(self.presets.keys())
        preset_to_delete = simpledialog.askstring("Delete Preset", f"Enter exact name to delete:", initialvalue=preset_names[0])
        if not preset_to_delete: return
        preset_to_delete = preset_to_delete.strip()
        if preset_to_delete in self.presets:
            del self.presets[preset_to_delete]
            self.search_entry.delete(0, tk.END)
            self._build_preset_buttons()
            messagebox.showinfo("✅ Deleted", f"Preset '{preset_to_delete}' removed.")
        else:
            messagebox.showerror("❌ Not Found", f"No preset named '{preset_to_delete}' found.")

    def save_preset(self):
        current_cmd = self.cmd_text.get("1.0", tk.END).strip()
        if not current_cmd:
            messagebox.showwarning("⚠️ No Command", "Type a command first.")
            return
        preset_name = simpledialog.askstring("Save Preset", "Enter a name:", initialvalue="")
        if not preset_name: return
        preset_name = preset_name.strip()
        if not preset_name: return
        if preset_name in self.presets:
            if not messagebox.askyesno("⚠️ Exists", f"Overwrite '{preset_name}'?"): return
        self.presets[preset_name] = current_cmd
        self.search_entry.delete(0, tk.END)
        self._build_preset_buttons()
        messagebox.showinfo("✅ Saved", f"Preset '{preset_name}' added!")

    def on_drop(self, event):
        raw = event.data.strip().strip('{}')
        paths = []
        if '\n' in raw:
            paths = [p.strip() for p in raw.split('\n') if p.strip()]
        else:
            paths = [p.strip() for p in raw.split() if p.strip()]

        new_files = []
        for p in paths:
            path = Path(p)
            if path.is_dir():
                new_files.extend(path.glob("*.png"))
            elif path.is_file() and path.suffix.lower() == ".png":
                new_files.append(path)

        self.files = new_files
        if self.files:
            self.input_folder = ""
            self.drop_zone.config(text=f"✅ {len(self.files)} file(s) loaded")
        else:
            self.drop_zone.config(text="❌ No valid PNG files/folders dropped")
        return event.data

    def select_folder_native(self, initial_dir=""):
        start_path = initial_dir or os.path.expanduser("~")
        try:
            result = subprocess.run(["kdialog", "--getexistingdirectory", start_path], capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return filedialog.askdirectory(initialdir=start_path)

    def select_files_native(self):
        """Open native file picker (kdialog/Dolphin) for individual files."""
        try:
            result = subprocess.run(
                ["kdialog", "--getopenfilename", "--multiple", os.path.expanduser("~"), "*.png *.jpg *.jpeg *.tiff *.bmp"],
                capture_output=True, text=True, check=True
            )
            raw = result.stdout.strip()
            if not raw:
                return []
            # kdialog returns newline-separated paths, sometimes quoted
            paths = [p.strip().strip('"').strip("'") for p in raw.split('\n') if p.strip()]
            return paths
        except (subprocess.CalledProcessError, FileNotFoundError):
            return filedialog.askopenfilenames(
                title="Select Image Files",
                filetypes=[("Images", "*.png *.jpg *.jpeg *.tiff *.bmp"), ("All Files", "*.*")]
            )

    def pick_files(self):
        """Handle 'Select Files' button click."""
        selected = self.select_files_native()
        if selected:
            self.files = [Path(p) for p in selected if Path(p).is_file()]
            self.input_folder = ""  # Clear folder tracking when manually selecting files
            self.drop_zone.config(text=f"✅ {len(self.files)} file(s) loaded")
        elif not self.files:
            self.drop_zone.config(text="❌ No files selected")

    def pick_folder(self):
        # Open native Dolphin-style file picker instead of folder tree
        try:
            result = subprocess.run(
                ["kdialog", "--getopenfilename", os.path.expanduser("~"), "*.png"],
                capture_output=True, text=True, check=True
            )
            selected_file = result.stdout.strip().strip('"').strip("'")
            if not selected_file:
                return  # User cancelled
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback to Tkinter file dialog if kdialog isn't available
            selected_file = filedialog.askopenfilename(
                title="Select any PNG in the target folder",
                filetypes=[("PNG Images", "*.png"), ("All Files", "*.*")]
            )
            if not selected_file:
                return

        # Extract the parent directory from the selected file
        folder = Path(selected_file).parent
        self.input_folder = str(folder)

        # Load ALL PNGs from that directory
        self.files = sorted(list(folder.glob("*.png")))

        # Update UI
        self.drop_zone.config(text=f"📁 Loaded {len(self.files)} PNGs from {folder.name}")

        # Auto-set output folder if not manually chosen
        if not self.output_folder:
            self.output_folder = str(folder)
            self.output_display.config(text=folder.name, foreground="black")

    def choose_output_folder(self):
        folder = self.select_folder_native(self.output_folder or "")
        if folder:
            self.output_folder = folder
            self.output_display.config(text=Path(folder).name, foreground="black")
        else:
            self.output_folder = ""
            self.output_display.config(text="Same as input", foreground="gray")

    def select_preset(self, name):
        self.cmd_text.delete("1.0", tk.END)
        self.cmd_text.insert("1.0", self.presets[name])

    def run_selected_preset(self):
        if not self.files:
            messagebox.showwarning("⚠️ No Files", "Drop files/folders or select a folder first.")
            return
        if not self.cmd_text.get("1.0", tk.END).strip():
            messagebox.showwarning("⚠️ No Command", "Select a preset or type a command.")
            return
        self.process_files()

    def run_all_files(self):
        """Run on All Files: Prioritizes selected input folder, infers folder from dropped/selected files."""
        if self.input_folder:
            self.files = list(Path(self.input_folder).glob("*.png"))
            if not self.files:
                messagebox.showwarning("⚠️ Empty", f"No PNG files found in {Path(self.input_folder).name}")
                return
        elif self.files:
            folder = self.files[0].parent
            self.files = list(folder.glob("*.png"))
            self.input_folder = str(folder)
            self.drop_zone.config(text=f"📁 Loaded {len(self.files)} PNGs from {Path(folder).name}")
        else:
            messagebox.showwarning("⚠️ No Files", "Drop files/folders or select a folder first.")
            return

        if not self.cmd_text.get("1.0", tk.END).strip():
            messagebox.showwarning("⚠️ No Command", "Select a preset or type a command.")
            return

        self.process_files()

    def process_files(self):
        if not self.files:
            messagebox.showwarning("⚠️ No Files", "Drop files/folders or select a folder first.")
            return
        template = self.cmd_text.get("1.0", tk.END).strip()
        if not template: return

        self.run_btn.config(state="disabled")
        self.status.config(text="🔄 Processing...", foreground="orange")
        self.progress["value"] = 0
        self.root.update()

        total = len(self.files)
        errors = []
        env = os.environ.copy()
        env["PATH"] = f"{os.path.expanduser('~/go/bin')}:{env.get('PATH', '')}"
        output_dir = Path(self.output_folder) if self.output_folder else self.files[0].parent

        for i, f in enumerate(self.files):
            base_name = f.stem
            ext_name = f.suffix
            cmd = template.replace("{file}", shlex.quote(str(f)))
            cmd = cmd.replace("{base}", base_name)
            cmd = cmd.replace("{ext}", ext_name)

            try:
                args = shlex.split(cmd)
                output_arg = None
                for idx in range(len(args) - 1, -1, -1):
                    arg = args[idx]
                    if arg.endswith(ext_name):
                        if idx > 0 and args[idx-1] == 'rm': continue
                        output_arg = arg
                        break
                if output_arg:
                    out_path = output_dir / output_arg
                    unique_name = output_arg
                    counter = 1
                    while out_path.exists():
                        stem = Path(output_arg).stem
                        ext = Path(output_arg).suffix
                        unique_name = f"{stem}({counter}){ext}"
                        out_path = output_dir / unique_name
                        counter += 1
                    cmd = cmd.replace(output_arg, unique_name)
            except Exception as e:
                print(f"Warning: Overwrite check skipped: {e}")

            try:
                subprocess.run(cmd, shell=True, env=env, capture_output=True, text=True, check=True, cwd=str(output_dir))
                display_name = unique_name if 'unique_name' in locals() else "processed"
                self.status.config(text=f"✅ {f.name} -> {display_name}", foreground="green")
                self.progress["value"] = (i + 1) / total * 100
                self.root.update()
            except subprocess.CalledProcessError as e:
                errors.append(f"❌ {f.name}: {e.stderr.strip()}")
                self.status.config(text=f"❌ {f.name} failed", foreground="red")
                self.progress["value"] = (i + 1) / total * 100
                self.root.update()

        self.run_btn.config(state="normal")
        if errors:
            messagebox.showerror("⚠️ Errors", "\n".join(errors[:5]) + ("\n..." if len(errors) > 5 else ""))
        else:
            self.status.config(text="✅ All done!", foreground="green")
            messagebox.showinfo("✨ Success", f"Processed {total} file(s)!\nSaved to:\n{output_dir}")

    def open_gimp_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("GIMP/PSD Files", "*.xcf *.gbr *.psd *.jpg *.png")])
        if file_path:
            self.status.config(text=f"📂 Opened: {Path(file_path).name}", foreground="blue")
            self.root.update()

if __name__ == "__main__":
    root = TkinterDnD.Tk() if DND_OK else tk.Tk()
    if not DND_OK:
        messagebox.showwarning("⚠️ Missing DND", "tkinterdnd2 not found.\nRun: pip install tkinterdnd2")
    app = ImageProcessorApp(root)
    root.mainloop()
