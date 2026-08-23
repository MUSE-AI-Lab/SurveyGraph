import sys
from pathlib import Path

FILE_PATH = Path(__file__).absolute()
BASE_DIR = FILE_PATH.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.configs.constants import OUTPUT_DIR
from src.modules.preprocessor.data_cleaner import DataCleaner
from src.modules.preprocessor.utils import parse_arguments_for_integration_test

# python tasks/integration_test/clean_data.py --task_id xxx
if __name__ == "__main__":
    task_id = parse_arguments_for_integration_test()
    
    dc = DataCleaner()
    dc.run(task_id)
