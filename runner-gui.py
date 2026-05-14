import tkinter as tk
from tkinter import messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import subprocess
import threading
import queue
from pathlib import Path

# Path to the Python interpreter inside your virtual environment.
# We use the `python` executable directly instead of the `activate` script,
# which is the standard way to run scripts inside a venv without activating it.
VENV_PYTHON = "/home/govinda/projects/img-gui/venv/bin/python"

class ScriptRunnerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(" Python Script Runner")
        self.root.geometry("650x550")
        self.dropped_file = None

        # --- UI Layout ---
        self.drop_zone = tk.Label(root, text=" Drop a .py file here", relief="solid", bd=2, width=50, height=5, bg="#f0f0f0")
        self.drop_zone.pack(pady=15)
        self.drop_zone.drop_target_register(DND_FILES)
        self.drop_zone.dnd_bind("<<Drop>>", self.on_drop)

        self.file_label = tk.Label(root, text="No file selected", fg="gray", font=("Arial", 10))
        self.file_label.pack()

        self.run_btn = tk.Button(root, text="▶ Run Script", command=self.run_script, state="disabled", bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        self.run_btn.pack(pady=10)

        self.output_frame = tk.Frame(root)
        self.output_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.output_text = tk.Text(self.output_frame, wrap="word", font=("Courier", 9))
        self.output_text.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(self.output_frame, command=self.output_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.output_text.config(yscrollcommand=scrollbar.set)

        # Queue for thread-safe output updates
        self.output_queue = queue.Queue()
        self.root.after(100, self.process_queue)

    def on_drop(self, event):
        raw = event.data.strip()
        # Clean up path wrappers that DND sometimes adds on Linux
        paths = [p.strip("{}") for p in raw.split()]

        if len(paths) == 1 and paths[0].endswith(".py") and Path(paths[0]).is_file():
            self.dropped_file = paths[0]
            self.file_label.config(text=f"📄 Selected: {Path(self.dropped_file).name}", fg="black")
            self.run_btn.config(state="normal")
            self.output_text.delete(1.0, tk.END)
            self.output_text.insert(tk.END, f"Ready to run: {Path(self.dropped_file).name}\n\n")
        else:
            messagebox.showwarning("Invalid Drop", "Please drop exactly one .py file.")
        return event.data

    def run_script(self):
        if not self.dropped_file:
            return

        self.run_btn.config(state="disabled")
        self.file_label.config(text="⏳ Running...", fg="orange")
        self.output_text.insert(tk.END, f"--- Executing {Path(self.dropped_file).name} ---\n")
        self.root.update()

        # Run in background thread to keep GUI responsive
        thread = threading.Thread(target=self._execute_in_thread, daemon=True)
        thread.start()

    def _execute_in_thread(self):
        try:
            # Merge stderr into stdout so we see all output/errors in one stream
            process = subprocess.Popen(
                [VENV_PYTHON, self.dropped_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            for line in process.stdout:
                self.output_queue.put(("output", line))

            process.wait()
            self.output_queue.put(("done", process.returncode))

        except Exception as e:
            self.output_queue.put(("error", str(e)))

    def process_queue(self):
        try:
            while True:
                msg_type, msg = self.output_queue.get_nowait()
                if msg_type == "output":
                    self.output_text.insert(tk.END, msg)
                elif msg_type == "done":
                    self.run_btn.config(state="normal")
                    if msg == 0:
                        self.file_label.config(text="✅ Finished successfully", fg="green")
                        self.output_text.insert(tk.END, "\n✅ Script completed.\n")
                    else:
                        self.file_label.config(text=f"❌ Exited with code {msg}", fg="red")
                        self.output_text.insert(tk.END, f"\n❌ Script exited with code {msg}\n")
                elif msg_type == "error":
                    self.run_btn.config(state="normal")
                    self.file_label.config(text="❌ Execution failed", fg="red")
                    self.output_text.insert(tk.END, f"\n❌ Error: {msg}\n")

                self.output_text.see(tk.END)  # Auto-scroll to bottom
        except queue.Empty:
            pass

        # Check queue again in 50ms
        self.root.after(50, self.process_queue)

if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = ScriptRunnerApp(root)
    root.mainloop()
