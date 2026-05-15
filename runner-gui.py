import tkinter as tk
from tkinter import messagebox, filedialog
from tkinterdnd2 import DND_FILES, TkinterDnD
import subprocess
import threading
import queue
import json
from pathlib import Path
import os
import hashlib
import re

# Path to the Python interpreter inside your virtual environment.
# We use the `python` executable directly instead of the `activate` script,
# which is the standard way to run scripts inside a venv without activating it.
VENV_PYTHON = "/home/govinda/file-cabinet/workspace/projects/img-gui/venv/bin/python"

MAX_HISTORY = 10
# Use absolute path in home directory to ensure write access
HISTORY_FILE = Path.home() / ".py_script_runner_history.json"

class ScriptRunnerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(" Python Script Runner")
        self.root.geometry("650x700")
        self.dropped_file = None
        self.history = self.load_history()  # List of tuples: (path, content_hash, display_name)
        self.selected_history_index = None
        
        # Register window close handler to save history
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # --- UI Layout ---
        self.drop_zone = tk.Label(root, text=" Drop a .py file here", relief="solid", bd=2, width=50, height=5, bg="#f0f0f0")
        self.drop_zone.pack(pady=15)
        self.drop_zone.drop_target_register(DND_FILES)
        self.drop_zone.dnd_bind("<<Drop>>", self.on_drop)

        # File selection button
        self.select_file_btn = tk.Button(root, text="📁 Select File", command=self.select_file, bg="#607D8B", fg="white", font=("Arial", 10))
        self.select_file_btn.pack(pady=5)

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

        # History buttons frame
        self.history_btn_frame = tk.Frame(self.history_frame)
        self.history_btn_frame.pack(fill="x", pady=(5, 0))
        
        self.remove_history_btn = tk.Button(self.history_btn_frame, text="🗑 Remove Entry", command=self.remove_selected_history, state="disabled", bg="#ff9800", fg="white", font=("Arial", 9))
        self.remove_history_btn.pack(side="left", padx=(0, 5))
        
        self.clear_history_btn = tk.Button(self.history_btn_frame, text="🧹 Clear All", command=self.clear_history, state="disabled", bg="#f44336", fg="white", font=("Arial", 9))
        self.clear_history_btn.pack(side="left")

        self.run_history_btn = tk.Button(root, text="▶ Run Selected from History", command=self.run_selected_history, state="disabled", bg="#2196F3", fg="white", font=("Arial", 10, "bold"))
        self.run_history_btn.pack(pady=10)
        
        # Initialize history listbox on startup
        self.update_history_listbox()

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
                    # Handle both old format (just paths) and new format (tuples)
                    result = []
                    for item in data:
                        if isinstance(item, dict):
                            # New format: {"path": ..., "hash": ..., "display_name": ...}
                            path = item.get("path")
                            if path and Path(path).exists():
                                result.append((path, item.get("hash", ""), item.get("display_name", "")))
                        elif isinstance(item, str):
                            # Old format: just path string
                            if Path(item).exists():
                                result.append((item, "", ""))
                    return result
            except (json.JSONDecodeError, IOError):
                pass
        return []

    def save_history(self):
        """Save current history to JSON file."""
        try:
            # Convert tuples to dicts for JSON serialization
            data = [{"path": path, "hash": h, "display_name": name} for path, h, name in self.history]
            with open(HISTORY_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            print(f"Failed to save history: {e}")

    def on_close(self):
        """Handle window close event - save history before closing."""
        self.save_history()
        self.root.destroy()

    def get_file_hash(self, filepath):
        """Calculate MD5 hash of file content."""
        try:
            with open(filepath, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ""
    
    def add_to_history(self, filepath):
        """Add a script to the history, keeping only the last MAX_HISTORY entries.
        Checks content hash to allow same filename with different content."""
        content_hash = self.get_file_hash(filepath)
        filename = Path(filepath).name
        
        # Check if we already have this exact file (same path and same hash)
        for i, (path, h, _) in enumerate(self.history):
            if path == filepath and h == content_hash:
                # Move to front (most recent first)
                entry = self.history.pop(i)
                self.history.insert(0, entry)
                self.update_history_listbox()
                self.save_history()
                return
        
        # Check for same filename but different content - need to add suffix
        display_name = filename
        base_name = Path(filename).stem
        extension = Path(filename).suffix
        
        # Count how many times this filename appears with different hashes
        same_name_count = sum(1 for _, h, name in self.history 
                             if (Path(name).stem == base_name or name == filename) and h != content_hash)
        
        if same_name_count > 0:
            # Add suffix in red-friendly format
            display_name = f"{base_name} ({same_name_count + 1}){extension}"
        
        # Add to front (most recent first)
        self.history.insert(0, (filepath, content_hash, display_name))
        
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
        for i, (filepath, content_hash, display_name) in enumerate(self.history):
            # If no custom display name, use the filename
            if not display_name:
                display_name = Path(filepath).name
            list_display = f"{i+1}. {display_name}"
            self.history_listbox.insert(tk.END, list_display)
            # Check if this has a suffix marker and color it red
            if re.search(r'\s+\(\d+\)\.py$', display_name):
                self.history_listbox.itemconfig(i, fg='red')

    def on_history_select(self, event):
        """Handle selection of a script from history - preview only, doesn't change selected script."""
        selection = self.history_listbox.curselection()
        if selection:
            index = selection[0]
            self.selected_history_index = index
            selected_path, _, _ = self.history[index]
            # Only update output text to show preview, don't change the main selected file
            self.output_text.delete(1.0, tk.END)
            self.output_text.insert(tk.END, f"Preview: {Path(selected_path).name}\n(Hover over or click 'Run Selected from History' to execute)\n\n")
            self.run_history_btn.config(state="normal")
            self.remove_history_btn.config(state="normal")
            self.clear_history_btn.config(state="normal")
        else:
            self.selected_history_index = None
            self.run_history_btn.config(state="disabled")
            self.remove_history_btn.config(state="disabled")
            # Only disable clear button if history is empty
            if not self.history:
                self.clear_history_btn.config(state="disabled")

    def remove_selected_history(self):
        """Remove the selected entry from history."""
        if self.selected_history_index is not None and self.selected_history_index < len(self.history):
            removed_path, _, removed_name = self.history.pop(self.selected_history_index)
            self.selected_history_index = None
            self.update_history_listbox()
            self.save_history()
            # Reset selection state
            self.run_history_btn.config(state="disabled")
            self.remove_history_btn.config(state="disabled")
            self.output_text.delete(1.0, tk.END)
            display_name = removed_name if removed_name else Path(removed_path).name
            self.output_text.insert(tk.END, f"Removed {display_name} from history.\n")
            # Re-enable clear button if history still has entries
            if self.history:
                self.clear_history_btn.config(state="normal")

    def clear_history(self):
        """Clear all history entries."""
        if messagebox.askyesno("Confirm Clear", "Are you sure you want to clear all history?"):
            self.history = []
            self.selected_history_index = None
            self.update_history_listbox()
            self.save_history()
            # Reset selection state
            self.run_history_btn.config(state="disabled")
            self.remove_history_btn.config(state="disabled")
            self.clear_history_btn.config(state="disabled")
            self.output_text.delete(1.0, tk.END)
            self.output_text.insert(tk.END, "History cleared.\n")

    def run_selected_history(self):
        """Run the script selected from history."""
        if self.selected_history_index is not None and self.selected_history_index < len(self.history):
            # Temporarily set dropped_file to run this specific script
            original_file = self.dropped_file
            selected_path, _, _ = self.history[self.selected_history_index]
            self.dropped_file = selected_path
            self.run_script()
            # Restore original file selection after running
            self.dropped_file = original_file

    def select_file(self):
        """Open KDE file selection dialog (kdialog) to select a Python script."""
        filepath = None
        
        # Use kdialog for native KDE file selection dialog
        try:
            result = subprocess.run(
                ["kdialog", "--getopenfilename", str(Path.home()), 
                 "Select Python Script", "*.py"],
                capture_output=True,
                text=True,
                timeout=60
            )
            filepath = result.stdout.strip()
            
            # Check if kdialog was cancelled (empty output) or failed
            if not filepath or result.returncode != 0:
                # User cancelled or kdialog failed - don't show fallback dialog
                return
                
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # kdialog not available or timed out - fall back to tkinter dialog
            filepath = filedialog.askopenfilename(
                title="Select Python Script",
                filetypes=[("Python files", "*.py"), ("All files", "*.*")],
                initialdir=str(Path.home())
            )
        except Exception:
            # Any other unexpected error - don't show fallback, just return
            return
        
        if filepath and filepath.endswith(".py") and Path(filepath).is_file():
            self.dropped_file = filepath
            self.add_to_history(self.dropped_file)
            self.file_label.config(text=f"📄 Selected: {Path(self.dropped_file).name}", fg="black")
            self.run_btn.config(state="normal")
            self.output_text.delete(1.0, tk.END)
            self.output_text.insert(tk.END, f"Ready to run: {Path(self.dropped_file).name}\n\n")

    def on_drop(self, event):
        raw = event.data.strip()
        # Handle paths with spaces by properly parsing quoted paths
        # First try to handle quoted paths (for paths with spaces)
        paths = []
        current_path = ""
        in_quotes = False
        
        for char in raw:
            if char == '"':
                in_quotes = not in_quotes
                current_path += char
            elif char == ' ' and not in_quotes:
                if current_path.strip():
                    paths.append(current_path.strip().strip('"'))
                current_path = ""
            else:
                current_path += char
        
        if current_path.strip():
            paths.append(current_path.strip().strip('"'))
        
        # If no quotes were used, fall back to simple split
        if len(paths) == 0:
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
