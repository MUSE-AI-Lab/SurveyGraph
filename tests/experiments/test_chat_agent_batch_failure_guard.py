import importlib.util
import sys
import types
from pathlib import Path


def _load_chat_agent_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "models"
        / "LLM"
        / "ChatAgent.py"
    )
    spec = importlib.util.spec_from_file_location(
        "surveygraph_chat_agent_under_test",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module

    originals = {
        name: sys.modules.get(name)
        for name in [
            "src.models",
            "src.models.LLM",
            "src.models.LLM.utils",
            "src.models.monitor",
            "src.models.monitor.token_monitor",
        ]
    }

    models_stub = types.ModuleType("src.models")
    llm_stub = types.ModuleType("src.models.LLM")
    utils_stub = types.ModuleType("src.models.LLM.utils")
    monitor_stub = types.ModuleType("src.models.monitor")
    token_monitor_stub = types.ModuleType("src.models.monitor.token_monitor")

    utils_stub.encode_image = lambda _path: ""

    class TokenMonitor:
        pass

    token_monitor_stub.TokenMonitor = TokenMonitor
    sys.modules["src.models"] = models_stub
    sys.modules["src.models.LLM"] = llm_stub
    sys.modules["src.models.LLM.utils"] = utils_stub
    sys.modules["src.models.monitor"] = monitor_stub
    sys.modules["src.models.monitor.token_monitor"] = token_monitor_stub

    try:
        spec.loader.exec_module(module)
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
    return module


ChatAgent = _load_chat_agent_module().ChatAgent


class FakeBatchAgent:
    batch_workers = 2

    def _ChatAgent__remote_chat(
        self,
        index,
        content,
        temperature=0.5,
        debug=False,
        model=None,
        use_retry=True,
        timeout=120,
    ):
        if content == "bad":
            raise RuntimeError("simulated request failure")
        return index, f"ok:{content}"


def test_batch_remote_chat_keeps_order_and_returns_error_for_failed_future():
    agent = FakeBatchAgent()

    responses = ChatAgent.batch_remote_chat(
        agent,
        ["first", "bad", "third"],
        desc="unit batch",
        workers=2,
        temperature=0.2,
    )

    assert responses[0] == "ok:first"
    assert responses[1].startswith("Error: RuntimeError: simulated request failure")
    assert responses[2] == "ok:third"


class FakeNoRetryBatchAgent:
    batch_workers = 2
    _ChatAgent__remote_chat = ChatAgent._ChatAgent__remote_chat

    def __init__(self):
        self.remote_calls = []
        self.no_retry_calls = []

    def remote_chat(self, *args, **kwargs):
        self.remote_calls.append((args, kwargs))
        raise RuntimeError("retrying remote_chat should not be used")

    def remote_chat_no_retry(self, text_content, **kwargs):
        self.no_retry_calls.append((text_content, kwargs))
        return f"no-retry:{text_content}:timeout={kwargs['timeout']}"


def test_batch_remote_chat_can_use_no_retry_for_cost_capped_batches():
    agent = FakeNoRetryBatchAgent()

    responses = ChatAgent.batch_remote_chat(
        agent,
        ["slow-a", "slow-b"],
        desc="unit no retry batch",
        workers=2,
        temperature=0.2,
        use_retry=False,
        timeout=77,
    )

    assert agent.remote_calls == []
    assert [call[0] for call in agent.no_retry_calls] == ["slow-a", "slow-b"]
    assert all(call[1]["timeout"] == 77 for call in agent.no_retry_calls)
    assert responses == [
        "no-retry:slow-a:timeout=77",
        "no-retry:slow-b:timeout=77",
    ]
