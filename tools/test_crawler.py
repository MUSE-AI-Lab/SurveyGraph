import requests
import json
import sys
from pathlib import Path

FILE_PATH = Path(__file__).absolute()
BASE_DIR = FILE_PATH.parent.parent
sys.path.insert(0, str(BASE_DIR))  # run code in any path

from src.modules.preprocessor.data_fetcher import DataFetcher

url = ""

def main1():
	payload = json.dumps({
		"abstract": "We show that",
		"title": "^We show that",
		"start_id": "463a8fd2b404b53850660b696bb5e1c6", 
		"projection": "title, authors, detail_url, abstract, md_text, reference",
		"limit": "10"
	})

	headers = {
		'token': '',
		'Content-Type': 'application/json'
	}

	response = requests.request("POST", url, headers=headers, data=payload)

	data_l = response.json().get("data", {}).get("datas", [])
	papers = []
	for data in data_l:
		paper = data.get("_source", {})
		paper["_id"] = data.get("_id", "")
		papers.append(paper)



df = DataFetcher(enable_cache=False)

papers = df.search_on_arxiv("attention head")

print(len(papers))
