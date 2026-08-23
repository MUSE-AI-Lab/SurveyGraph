import re
import shutil
import sys
from pathlib import Path

FILE_PATH = Path(__file__).absolute()
BASE_DIR = FILE_PATH.parent.parent
sys.path.insert(0, str(BASE_DIR))  # run code in any path

def clean_invalid_task_dirs(outputs_dir="outputs"):
    """
    清理无效的task目录（没有survey_wtmk.pdf的目录）
    参数：
        outputs_dir: outputs目录路径，默认为当前目录下的outputs
    """
    outputs_path = Path(outputs_dir)
    if not outputs_path.exists():
        print(f"Warning: {outputs_path} directory not exists")
        return

    # 定义task目录名匹配模式（YYYY-MM-DD-HHMM格式开头）
    task_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}-\d{4}_.+')
    
    deleted_dirs = []
    kept_dirs = []

    for task_dir in outputs_path.iterdir():
        if not task_dir.is_dir():
            continue
            
        # 验证目录名格式
        if not task_pattern.match(task_dir.name):
            continue

        # 检查目标文件是否存在
        target_file = task_dir / "survey_wtmk.pdf"
        if not target_file.exists():
            try:
                shutil.rmtree(task_dir)
                deleted_dirs.append(task_dir.name)
            except Exception as e:
                print(f"Failed to delete {task_dir}: {str(e)}")
        else:
            kept_dirs.append(task_dir.name)

    # 打印清理结果
    print(f"Deleted directories ({len(deleted_dirs)}):")
    for d in sorted(deleted_dirs):
        print(f" - {d}")
    
    print(f"\nKept directories ({len(kept_dirs)}):")
    for d in sorted(kept_dirs):
        print(f" - {d}")

if __name__ == "__main__":
    clean_invalid_task_dirs(BASE_DIR / "outputs")