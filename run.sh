# offline run (entire pipeline)
python tasks/offline_run.py --title "Controllable Text Generation for Large Language Models: A Survey" --key_words "controlled text generation, text generation, large language model, LLM" --ref_path "dir/path/to/your/references-markdowns"


# Workflow (step by step, only for debugging)
python tasks/workflow/02_clean_data.py --title "Controllable Text Generation for Large Language Models: A Survey" --key_words "controlled text generation, text generation, large language model, LLM" --ref_path "../refs"
task_id="xxx" # You can check the task_id in the outputs/<task_id>/tmp_config.json of the previous command
python tasks/workflow/03_gen_outlines.py  --task_id $task_id
python tasks/workflow/04_gen_content.py  --task_id $task_id
python tasks/workflow/05_post_refine.py  --task_id $task_id
python tasks/workflow/06_gen_latex.py  --task_id $task_id
