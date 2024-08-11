import os, subprocess
from datetime import datetime
import logging

class MemoryHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.logs = []

    def emit(self, record):
        self.logs.append(self.format(record))

class LoggerSetup:
    def __init__(self, basename: str):
        self.logger = logging.getLogger("my_logger")
        self.memory_handler = MemoryHandler()
        self._setup_logging(basename)

    def _setup_logging(self, basename: str):
        self.logger.setLevel(logging.DEBUG)
        now = datetime.now()
        log_base = "."+basename+"-log-"+now.strftime('%Y%m%d-%H%M%S')
        log_info = log_base+".out"
        log_errors = log_base+".err"
        debug_info_handler = logging.FileHandler(log_info)
        debug_info_handler.setLevel(logging.DEBUG)
        warning_error_handler = logging.FileHandler(log_errors)
        warning_error_handler.setLevel(logging.WARNING)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        self.memory_handler.setLevel(logging.WARNING)
        log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        debug_info_handler.setFormatter(log_format)
        warning_error_handler.setFormatter(log_format)
        console_handler.setFormatter(log_format)
        self.memory_handler.setFormatter(log_format)
        self.logger.addHandler(debug_info_handler)
        self.logger.addHandler(warning_error_handler)
        self.logger.addHandler(console_handler)
        self.logger.addHandler(self.memory_handler)

    def get_logger(self):
        return self.logger

    def get_memory_handler(self):
        return self.memory_handler

def open_dir_in_VLC(the_dir: str, sort_choice: str) -> None:
    """Recursively open the files in the directory in VLC, sorted by name or modification time."""
    # List to store files with their modification times
    files_with_times = []
    # Recursively iterate over the files in the directory
    for root, dirs, files in os.walk(the_dir):
        for filename in files:
            file_path = os.path.join(root, filename)
            if os.path.isfile(file_path):
                mod_time = os.path.getmtime(file_path)
                files_with_times.append((mod_time, file_path))
    if sort_choice == "sort_by_name":
        # Sort files by name
        files_with_times.sort(key=lambda x: x[1])
    elif sort_choice == "sort_by_time":
      # Sort files by modification time (earliest first)
      files_with_times.sort(key=lambda x: x[0])
    # Create the .m3u playlist content
    playlist_content = "#EXTM3U\n"
    for _, file_path in files_with_times:
        base_name = os.path.basename(file_path)
        playlist_content += f"#EXTINF:-1,{base_name.replace(',', '').replace('-', '')}\n{file_path}\n"
    # Write the playlist to ./playlist.m3u
    playlist_path = "./playlist.m3u"
    with open(playlist_path, "w") as playlist_file:
        playlist_file.write(playlist_content)
    # Open the playlist in VLC
    subprocess.Popen(["vlc", playlist_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
