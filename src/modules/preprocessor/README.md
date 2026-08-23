# src.modules.preprocessor

## File Structure
```
├── data_cleaner.py
├── data_fetcher.py
├── paper_recaller.py
├── README.md
└── utils.py
```

### data_cleaner.py
The implementation of `DataCleaner` class.

Key Features:
- **Load Papers from JSON Directory (`from_json_dir`)**: Loads papers from a directory containing JSON files. Only includes papers that have an md_text field.
- **Complete Missing Titles (`complete_title`)**: Extracts and completes missing titles from the first line of the md_text field.
- **Complete Missing Abstracts (`complete_abstract`)**: Searches the md_text for an "abstract" section and extracts up to 2000 characters for the abstract. If no specific "abstract" section is found, it uses the first 2000 characters of the md_text.
- **Complete BibTeX Information (`complete_bib`)**: Generates BibTeX entries for papers and assigns a bib_name.
- **Classify Paper Type (`get_paper_type`)**: Uses a ChatAgent to classify papers into predefined categories (e.g., method, benchmark, theory, survey) based on their abstract.
- **Extract Attribute Tree (`get_attri`)**: Uses a ChatAgent to extract an attribute tree from the md_text of each paper, based on its type (method, benchmark, etc.).
- **Save Cleaned Papers (`save_papers`)**: Saves the cleaned papers, including fields like title, abstract, BibTeX name, paper type, and attributes, into individual JSON files.
- **Run Full Cleaning Pipeline (`run`)**: Executes the full cleaning process containing all the above functions.


### data_fetcher.py
The implementation of `DataFetcher` class.

Key Features:
- **Authentication Management (`_get_db_authentication`)**: Manages the authentication process for accessing the database.
- **Submit Tasks for Web Crawling (`task_submit`)**: Submits a task to a queue-based system (e.g., Google Scholar search) and returns a unique search_id for tracking.
- **Track Task Progress (`task_track`)**: Monitors the progress of submitted tasks by querying the queue status at regular intervals. It tracks how many active messages (i.e., tasks) are still in the queue.
- **Retrieve Data from Database (`_get_data`)**: Retrieves data from a database collection (e.g., Google Scholar or arXiv papers) using a specified filter and projection.
- **Search on Google Scholar (`search_on_google`)**: Submits a search task to Google Scholar, tracks its progress, and then retrieves the results from the database once the task is completed.
- **Search on arXiv (`search_on_arxiv`)**: Retrieves papers from the arXiv database where the specified keyword appears in the title or abstract.


### paper_recaller.py
The implementation of `PaperRecaller` class.

Key Features:
- **Iterative Paper Recall (`recall_papers_iterative`)**: Recalls papers based on evolving keywords through multiple iterations. Each iteration involves searching for papers, embedding them, clustering, and generating new keywords.
- **Search for Papers (`_search_papers`)**: Searches for papers using specified keywords from arXiv and google scholar.
- **Clean Paper Pool (`_clean_paper_pool`)**: Removes invalid or duplicate papers from the pool by checking titles and abstracts.
- **Embed Papers (`_embed_papers`)**: Uses EmbedAgent to generate embeddings for papers based on their title and abstract. Papers with failed embeddings are removed from the pool.
- **Cluster Papers (`_cluster_papers`)**: Clusters papers based on their embeddings using the KMeans algorithm.
- **Generate Keywords (`_generate_keywords`)**: Uses ChatAgent to generate new keywords from clusters of papers for future recall iterations.
- **Select New Keyword (`_select_new_keyword`)**: Chooses the most relevant keyword from generated ones by comparing their embeddings to existing keywords using cosine distance.


### PaperFilter.py

The `PaperFilter` class is designed for filtering and sorting a collection of research papers based on their relevance to a user-defined topic.

Key Features:
- **Load Papers from Saved Directory (`from_saved`)**: Initializes the `PaperFilter` class by loading papers stored in JSON format from a specified directory. This method ensures only JSON files are processed, and logs the number of papers loaded.
- **Coarse-Grained Sort (`coarse_grained_sort`)**: This method applies a coarse-grained filter to select the top K papers that are most semantically relevant to the user's topic. It’s intended for a quick, broad filtering of papers based on vector similarity.
- **Fine-Grained Sort (`fine_grained_sort`)**: For a more precise selection, this function uses a `ChatAgent` to interact with an LLM for deeper analysis of each paper's abstract against the topic. It filters out only those papers considered highly relevant based on the model's response.
- **Run Filter (`run`)**: Combines both coarse-grained and fine-grained sorting to generate the final list of papers most relevant to the specified topic. It first narrows down the pool with coarse sorting, then refines with fine-grained filtering.

# Surveyx - Preprocess
This step contains two procedure.
1. fetch paper from arxiv and google scholar.
2. clean and complete paper data.

## Fetch paper from arxiv and google scholar.
This step contains two phase, recall and filter.

As for **recall** phase.
Firstly, the input keyword from user is regarded as the initial `key_word pool`.
```python
while len(recalled_papers) < 300 and iter_times < 5:
    recalled_papers += recall_paper_from_arxiv_and_googlescholar(key_word_pool)
    kinds = cluster_papers_by_embedding(recalled_papers, num_kinds=len(key_word_pool)+1) # Cluster to len(keyword_pool)+1 kind.
    new_keyword = generate_new_key_word_to_each_kind(kinds)
    selected_new_keyword = select_new_keyword_using_cosine_distance(new_keyword, key_word_pool)
    key_word_pool += selected_new_keyword
```

As for **filter** phase.
1. coarse-grained sort: sort papers by the similarity between abstract and topic.
2. fine-grained sort: filter papers simply by asking LLM.
