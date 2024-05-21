import ffmpeg
import os
import logging
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import threading
import time

# Set up logging
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "conversion.log")

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler(log_file),
                        logging.StreamHandler()
                    ])

MAX_FILES = 10  # Set the maximum number of files allowed to be processed at one time
subprocesses = []  # Keep track of all subprocesses

def get_duration(filename):
    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                                 'format=duration', '-of',
                                 'default=noprint_wrappers=1:nokey=1', filename],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True)
        return float(result.stdout)
    except Exception as e:
        logging.error(f"Error probing file {filename}: {e}")
        return 0

def convert_mkv_to_mp4(input_file, output_dir, progress_var, time_var, stop_event):
    output_file = os.path.join(output_dir, os.path.splitext(os.path.basename(input_file))[0] + '.mp4')
    total_duration = get_duration(input_file)
    
    logging.info(f"Starting conversion: {input_file} -> {output_file}")
    
    try:
        process = (
            ffmpeg
            .input(input_file)
            .output(output_file)
            .global_args('-progress', 'pipe:1', '-nostats')
            .run_async(pipe_stdout=True, pipe_stderr=True)
        )
        
        subprocesses.append(process)
        
        start_time = time.time()
        for line in process.stdout:
            if stop_event.is_set():
                process.terminate()
                return
            
            line = line.decode('utf8').strip()
            if 'out_time_ms=' in line:
                value = line.split('=')[1]
                if value.isdigit():
                    elapsed_time = int(value)
                    progress = elapsed_time / (total_duration * 1_000_000) * 100
                    progress_var.set(progress)

                    elapsed_seconds = elapsed_time / 1_000_000
                    time_left = max(0, total_duration - elapsed_seconds)
                    time_var.set(f"Time left: {int(time_left // 60)}m {int(time_left % 60)}s")
        
        process.wait()
        if process.returncode == 0:
            logging.info(f"Conversion successful: {input_file} -> {output_file}")
            progress_var.set(100)
            time_var.set("Completed")
        else:
            logging.error(f"Conversion failed: {input_file}")
            time_var.set("Error")
        
    except Exception as e:
        logging.error(f"Error occurred: {e}")
        time_var.set("Error")

def start_conversion(input_files, output_dir, progress_bars, time_vars):
    if not input_files:
        messagebox.showerror("Error", "No input files selected")
        return
    if not output_dir:
        messagebox.showerror("Error", "No output directory selected")
        return
    
    os.makedirs(output_dir, exist_ok=True)

    stop_events = [threading.Event() for _ in input_files]
    futures = []

    def run_conversion(input_file, output_dir, progress_bar, time_var, stop_event):
        convert_mkv_to_mp4(input_file, output_dir, progress_bar, time_var, stop_event)

    with ThreadPoolExecutor(max_workers=min(4, len(input_files))) as executor:
        for i, input_file in enumerate(input_files):
            future = executor.submit(run_conversion, input_file, output_dir, progress_bars[i], time_vars[i], stop_events[i])
            futures.append(future)
        
        for future in as_completed(futures):
            future.result()

    messagebox.showinfo("Success", "Conversion completed. Check logs for details.")

def browse_files():
    files = filedialog.askopenfilenames(filetypes=[("MKV files", "*.mkv")])
    if len(files) > MAX_FILES:
        messagebox.showwarning("Warning", f"Too many files selected! Please select up to {MAX_FILES} files.")
        files = files[:MAX_FILES]  # Truncate the list to the maximum allowed
    input_files_entry.delete(0, tk.END)
    input_files_entry.insert(0, ';'.join(files))
    create_progress_bars(files)

def browse_directory():
    directory = filedialog.askdirectory()
    output_dir_entry.delete(0, tk.END)
    output_dir_entry.insert(0, directory)

def create_progress_bars(files):
    for widget in progress_frame.winfo_children():
        widget.destroy()
    
    global progress_bars, time_vars
    progress_bars = []
    time_vars = []
    
    for file in files:
        label = tk.Label(progress_frame, text=os.path.basename(file))
        label.pack(fill=tk.X, padx=5, pady=2)
        
        progress_var = tk.DoubleVar()
        time_var = tk.StringVar()
        
        progress_bar = ttk.Progressbar(progress_frame, variable=progress_var, maximum=100)
        progress_bar.pack(fill=tk.X, padx=5, pady=2)
        
        time_label = tk.Label(progress_frame, textvariable=time_var)
        time_label.pack(fill=tk.X, padx=5, pady=2)
        
        progress_bars.append(progress_var)
        time_vars.append(time_var)

def on_closing():
    """Handle application exit and terminate all subprocesses."""
    for process in subprocesses:
        if process.poll() is None:  # Process is still running
            process.terminate()
            try:
                process.wait(timeout=5)  # Wait for the process to terminate
            except subprocess.TimeoutExpired:
                process.kill()  # Force kill if it does not terminate in time
    root.destroy()

# Set up the GUI
root = tk.Tk()
root.title("MKV to MP4 Converter")

frame = tk.Frame(root)
frame.pack(padx=10, pady=10)

input_files_label = tk.Label(frame, text="Input Files:")
input_files_label.grid(row=0, column=0, sticky=tk.W)

input_files_entry = tk.Entry(frame, width=50)
input_files_entry.grid(row=0, column=1, padx=5, pady=5)

browse_files_button = tk.Button(frame, text="Browse", command=browse_files)
browse_files_button.grid(row=0, column=2, padx=5, pady=5)

output_dir_label = tk.Label(frame, text="Output Directory:")
output_dir_label.grid(row=1, column=0, sticky=tk.W)

output_dir_entry = tk.Entry(frame, width=50)
output_dir_entry.grid(row=1, column=1, padx=5, pady=5)

browse_dir_button = tk.Button(frame, text="Browse", command=browse_directory)
browse_dir_button.grid(row=1, column=2, padx=5, pady=5)

convert_button = tk.Button(frame, text="Convert", command=lambda: threading.Thread(target=start_conversion, args=(input_files_entry.get().split(';'), output_dir_entry.get(), progress_bars, time_vars)).start())
convert_button.grid(row=2, columnspan=3, pady=10)

progress_frame = tk.Frame(root)
progress_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

# Handle the application close event
root.protocol("WM_DELETE_WINDOW", on_closing)

root.mainloop()
