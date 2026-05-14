import tkinter as tk
from tkinter import messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import subprocess
import threading
import queue
import json
from pathlib import Path

# Path to the Python interpreter inside your virtual environment.
# We use the `python` executable directly instead of the `activate` script,
# which is the standard way to run scripts inside a venv without activating it.
VENV_PYTHON = "/home/govinda/projects/img-gui/venv/bin/python"

MAX_HISTORY = 10
HISTORY_FILE = Path(__file__).parent / ".script_history.json"

class ScriptRunnerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(" Python Script Runner")
        self.root.geometry("650x700")
        self.dropped_file = None
        self.history = self.load_history()  # List of recently opened script paths
        self.selected_history_index = None
        
        # Register window close handler to save history
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # --- UI Layout ---
        self.drop_zone = tk.Label(root, text=" Drop a .py file here", relief="solid", bd=2, width=50, height=5, bg="#f0f0f0")
        self.drop_zone.pack(pady=15)
        self.drop_zone.drop_target_register(DND_FILES)
        self.drop_zone.dnd_bind("<<Drop>>", self.on_drop)

        self.file_label = tk.Label(root, text="No file selected", fg="gray", font=("Arial", 10))
        self.file_label.pack()

        self.run_btn = tk.Button(root, text="▶ Run Script", command=self.run_script, state="disabled", bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        self.run_btn.pack(pady=10)

        # --- Recent Scripts History Section ---
        self.history_frame = tk.LabelFrame(root, text="Recent Scripts (Last 10)", font=("Arial", 10, "bold"), padx=10, pady=10)
        self.history_frame.pack(fill="both", expand=False, padx=10, pady=10)

        self.history_listbox = tk.Listbox(self.history_frame, height=6, font=("Arial", 9), selectmode="single")
        self.history_listbox.pack(side="left", fill="both", expand=True)
        self.history_listbox.bind("<<ListboxSelect>>", self.on_history_select)

        history_scrollbar = tk.Scrollbar(self.history_frame, command=self.history_listbox.yview)
        history_scrollbar.pack(side="right", fill="y")
        self.history_listbox.config(yscrollcommand=history_scrollbar.set)

        self.run_history_btn = tk.Button(root, text="▶ Run Selected from History", command=self.run_selected_history, state="disabled", bg="#2196F3", fg="white", font=("Arial", 10, "bold"))
        self.run_history_btn.pack(pady=10)

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

    def load_history(self):
        """Load history from JSON file."""
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, 'r') as f:
                    data = json.load(f)
                    # Filter out files that no longer exist
                    return [path for path in data if Path(path).exists()]
            except (json.JSONDecodeError, IOError):
                pass
        return []

    def save_history(self):
        """Save current history to JSON file."""
        try:
            with open(HISTORY_FILE, 'w') as f:
                json.dump(self.history, f, indent=2)
        except IOError as e:
            print(f"Failed to save history: {e}")

    def on_close(self):
        """Handle window close event - save history before closing."""
        self.save_history()
        self.root.destroy()

    def add_to_history(self, filepath):
        """Add a script to the history, keeping only the last MAX_HISTORY entries."""
        # Remove if already exists to avoid duplicates
        if filepath in self.history:
            self.history.remove(filepath)
        # Add to front (most recent first)
        self.history.insert(0, filepath)
        # Trim to max size
        if len(self.history) > MAX_HISTORY:
            self.history.pop()
        # Update listbox display
        self.update_history_listbox()
        # Save to disk immediately
        self.save_history()

    def update_history_listbox(self):
        """Refresh the history listbox with current history entries."""
        self.history_listbox.delete(0, tk.END)
        for i, filepath in enumerate(self.history):
            display_name = f"{i+1}. {Path(filepath).name}"
            self.history_listbox.insert(tk.END, display_name)

    def on_history_select(self, event):
        """Handle selection of a script from history."""
        selection = self.history_listbox.curselection()
        if selection:
            index = selection[0]
            self.selected_history_index = index
            selected_file = self.history[index]
            self.file_label.config(text=f"📄 Selected: {Path(selected_file).name}", fg="black")
            self.dropped_file = selected_file
            self.run_btn.config(state="normal")
            self.run_history_btn.config(state="normal")
            self.output_text.delete(1.0, tk.END)
            self.output_text.insert(tk.END, f"Ready to run: {Path(selected_file).name}\n\n")
        else:
            self.selected_history_index = None
            self.run_history_btn.config(state="disabled")

    def run_selected_history(self):
        """Run the script selected from history."""
        if self.selected_history_index is not None and self.selected_history_index < len(self.history):
            self.dropped_file = self.history[self.selected_history_index]
            self.run_script()

    def on_drop(self, event):
        raw = event.data.strip()
        # Clean up path wrappers that DND sometimes adds on Linux
        paths = [p.strip("{}") for p in raw.split()]

        if len(paths) == 1 and paths[0].endswith(".py") and Path(paths[0]).is_file():
            self.dropped_file = paths[0]
            self.add_to_history(self.dropped_file)
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
