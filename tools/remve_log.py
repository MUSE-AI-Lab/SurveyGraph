import os
import sys
from pathlib import Path

FILE_PATH = Path(__file__).absolute()
BASE_DIR = FILE_PATH.parent.parent
sys.path.insert(0, str(BASE_DIR))  # run code in any path

"""remove log files"""
def delete_log_files(root_dir):
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith('.log'):
                file_path = os.path.join(dirpath, filename)
                os.remove(file_path)
                print(f"removed file: {file_path}")


root_directory = BASE_DIR / "outputs"
delete_log_files(root_directory)