from pathlib import Path

from experiments.tools import scisage_outline_only_live as live


def test_resolve_cli_args_supports_query_and_output_dir():
    query, output_dir = live.resolve_cli_args([
        'script.py',
        'Document Visual Question Answering',
        'outputs/scisage_outline_docvqa_20260525',
    ])
    assert query == 'Document Visual Question Answering'
    assert output_dir == Path('outputs/scisage_outline_docvqa_20260525')
