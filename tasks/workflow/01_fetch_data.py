import sys
from pathlib import Path

FILE_PATH = Path(__file__).absolute()
BASE_DIR = FILE_PATH.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.modules.preprocessor.preprocessor import single_preprocessing
from src.models.LLM import ChatAgent
from src.modules.preprocessor.utils import parse_arguments_for_preprocessor

# python tasks/integration_test/fetch_data.py --title "Controllable Text Generation for Large Language Models: A Survey" --key_words "controlled text generation, text generation, large language model, LLM" --page 5 --time_s 2017 --time_e 2024 --enable_cache True
if __name__ == "__main__":
    args = parse_arguments_for_preprocessor()
    single_preprocessing(args)
