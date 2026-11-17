import asyncio

from app.agents import llm_provider


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"message": {"content": '{"decision":"chat","reply":"ok"}'}}


class FakeAsyncClient:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()


def test_ollama_planning_call_uses_configured_context_and_json_mode(monkeypatch):
    FakeAsyncClient.calls = []
    monkeypatch.setattr(llm_provider.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(llm_provider.settings, "ollama_num_ctx", 8192)
    monkeypatch.setattr(llm_provider.settings, "ollama_num_predict", 3072)

    provider = llm_provider.OllamaProvider(
        "http://localhost:11434",
        "llama3.2:latest",
    )
    result = asyncio.run(
        provider._call("planner instructions", "plan this", force_json=True)
    )

    assert result == '{"decision":"chat","reply":"ok"}'
    url, request = FakeAsyncClient.calls[-1]
    assert url == "http://localhost:11434/api/chat"
    assert request["json"]["format"] == "json"
    assert request["json"]["options"] == {
        "temperature": 0.3,
        "num_ctx": 8192,
        "num_predict": 3072,
    }


def test_ollama_synthesis_uses_the_same_context_budget(monkeypatch):
    FakeAsyncClient.calls = []
    monkeypatch.setattr(llm_provider.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(llm_provider.settings, "ollama_num_ctx", 6144)
    monkeypatch.setattr(llm_provider.settings, "ollama_num_predict", 2048)

    provider = llm_provider.OllamaProvider(
        "http://localhost:11434",
        "llama3.2:latest",
    )
    result = asyncio.run(
        provider.synthesize([{"role": "user", "content": "Explain this."}])
    )

    assert result == '{"decision":"chat","reply":"ok"}'
    _, request = FakeAsyncClient.calls[-1]
    assert request["json"]["options"]["num_ctx"] == 6144
    assert request["json"]["options"]["num_predict"] == 2048



def test_ollama_uses_planner_model_for_reasoning_and_chat_model_for_replies(monkeypatch):
    FakeAsyncClient.calls = []
    monkeypatch.setattr(llm_provider.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(llm_provider.settings, "llm_provider", "ollama")
    monkeypatch.setattr(llm_provider.settings, "ollama_base_url", "http://localhost:11434")
    monkeypatch.setattr(llm_provider.settings, "ollama_model", "llama3.2:latest")
    monkeypatch.setattr(llm_provider.settings, "ollama_planner_model", "mistral:latest")
    monkeypatch.setattr(llm_provider.settings, "ollama_num_ctx", 8192)
    monkeypatch.setattr(llm_provider.settings, "ollama_num_predict", 3072)

    provider = llm_provider.get_provider()
    asyncio.run(provider._call("planner instructions", "select tools", force_json=True))
    planner_request = FakeAsyncClient.calls[-1][1]["json"]
    assert planner_request["model"] == "mistral:latest"

    asyncio.run(provider.synthesize([{"role": "user", "content": "Hello"}]))
    chat_request = FakeAsyncClient.calls[-1][1]["json"]
    assert chat_request["model"] == "llama3.2:latest"
