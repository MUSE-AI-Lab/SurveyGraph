from typing import List
import re


def are_key_words_contained(content: str, key_words: List[str] = []):
    for one in key_words:
        if one.strip().lower() in content.strip().lower():
            return True
    return False


def list_citation_names(content: str):
    # Regular expression to find patterns like \cite{...}, \citet{...}, \citep{...}
    pattern = r"\\cite[t|p]?{([^}]+)}"
    # Find all occurrences of the pattern
    citations = re.findall(pattern, content)
    return citations
