import json
import sys
from pathlib import Path

FILE_PATH = Path(__file__).absolute()
BASE_DIR = FILE_PATH.parent.parent
sys.path.insert(0, str(BASE_DIR))  # run code in any path

from src.modules.fig_retrieve.fig_retriever import FigRetriever

image_data_dict = {
    "pic_urls": [
        
    ],
    "paper_ids": [
    ],
    "sources": [
    ],
    "query": "Predictive Climate Modeling Techniques",
    "match_topk": 30,
}


fig_retriever = FigRetriever(is_debug=False)
# fig_retriever.unit_test_for_api_1()
res = fig_retriever.unit_test_for_api_2(image_data_dict)
print(json.dumps(res, indent=4))