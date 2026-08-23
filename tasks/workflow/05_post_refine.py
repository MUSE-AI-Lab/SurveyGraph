import sys
from pathlib import Path

FILE_PATH = Path(__file__).absolute()
BASE_DIR = FILE_PATH.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))  # run code in any path

from src.models.post_refine import PostRefiner
from src.modules.preprocessor.utils import parse_arguments_for_integration_test

if __name__ == '__main__':
    task_id = parse_arguments_for_integration_test()
    post_refiner = PostRefiner(task_id)

    # post refine
    post_refiner.run()


