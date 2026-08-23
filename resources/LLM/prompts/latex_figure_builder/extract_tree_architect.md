I am writing an academic review and need help extracting valuable information and organizing it into a hierarchical structure figure, similar to a visual classification chart (e.g. a tree diagram). Please analyze the text for key concepts, implicit relationships, and organizational structure. Focus on:

1. **Clear Categorization:** Identify primary categories (main ideas), subcategories, and details.
2. **Conceptual Relationships:** Highlight how concepts are related and ensure logical flow.
3. **Content Prioritization:** Emphasize significant points while avoiding unnecessary repetition or overly granular details.
4. **Contextual Analysis:** If possible, provide insights into how certain elements connect or contribute to the overall purpose of the review.
5. **Output Format:** Deliver the results in a hierarchical outline that reflects the structure of the source material in json format.
6. **Json Format:** "child" means that this node will be further classified, and "list" means that this node is already a leaf node and starts to list other contents. Your answer should be surrounded by <answer> and </answer> tags. This tree should have three levels, with the third level being the leaf nodes, and only leaf nodes can list.
7. **Extraction Score:** You need to rate the degree of relevance between your extracted content and the original text. Sometimes, the content expressed in a passage may not be suitable for supporting description with such an image, so you need to evaluate its appropriateness, with a maximum score of 100. And the extraction score should be enclosed with <score> and </score> tags. If you think you can't finish that task, just give a low score.
8. **Caption**: Now that you are extracting key info for a hierarchical structure figure, so you also need to generate a caption(as well as a description) of a figure that convey the infomation you extracted. Your caption should be enclosed with <caption> and </caption> tags.
Example: 
<answer>
{{
    "title": "xxx", 
    "child": [
        {{
            "title": "xxx", 
            "child": [
                {{
                    "title": "xxx", 
                    "list_": ["xxx", "xxx", "xxx", ...]
                }}, 
                {{
                    "title": "xxx", 
                    "list_": ["xxx", "xxx", ...]
                }}
            ]
        }}, 
        {{
            "title": "xxx", 
            "child": [
                {{
                    "title": "xxx", 
                    "list_": ["xxx", "xxx", "xxx", ...]
                }}, 
                {{
                    "title": "xxx", 
                    "list_": []
                }}
            ]
        }},
        ...
    ]
}}
</answer>
<score>
55
</score>
<caption>
This figure shows ...
</caption>

Here is the text you need to extract:
{context}