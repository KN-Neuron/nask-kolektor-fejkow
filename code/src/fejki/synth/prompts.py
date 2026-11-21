"""Prompt builders and optional LLM backend for synthetic generation (rule backend is the default).

Safety: only fictional people, brands and reserved TLDs; contact artifacts are placeholders.
"""
from __future__ import annotations

from ..config import env

SAFETY = (
    "Use ONLY fictional people (e.g. 'Osoba Publiczna A'), fictional brands and reserved domains "
    "(.example/.test). No working phone numbers or links. The text is test data for a detector."
)


def variant_prompt(moves: list[str], topic: str, name: str, domain: str = "{DOMAIN}") -> str:
    return (
        f"Napisz krótką reklamę po polsku (3 do 5 zdań) w szkielecie perswazji: {' -> '.join(moves)}. "
        f"Temat: {topic}. Osoba (fikcyjna): {name}. Wstaw dosłownie tekst {domain} jako adres w wezwaniu do działania. "
        f"Zwróć tylko tekst reklamy. {SAFETY}"
    )


def paraphrase_prompt(text: str, level: int) -> str:
    how = "lekko" if level == 1 else "silnie, zmieniając składnię i słownictwo, ale zachowując kolejność ruchów perswazyjnych"
    return f"Sparafrazuj {how} poniższą reklamę (po polsku), zachowaj sens:\n\n{text}\n\n{SAFETY}"


PRESETS = {  # base_url, default model; key needed except for ollama
    "ollama": ("http://localhost:11434", "gemma2"),
    "deepseek": ("https://api.deepseek.com", "deepseek-chat"),
    "kimi": ("https://api.moonshot.ai/v1", "kimi-k2-0905-preview"),
}


def _cache_path(provider: str, model: str, prompt: str, temperature: float):
    import hashlib

    from ..config import path

    h = hashlib.sha1(f"{provider}|{model}|{temperature}|{prompt}".encode()).hexdigest()[:20]
    return path(f"data/raw/llm/{h}.txt")


def llm_generate(prompt: str, temperature: float = 0.9) -> str:
    """Providers: ollama (local, free), deepseek, kimi (OpenAI-compatible), openai_compat (LLM_BASE_URL), anthropic.

    Responses are cached on disk so reruns with the same seed are free and deterministic.
    """
    import httpx

    provider = env("LLM_PROVIDER", "ollama")
    key = env("LLM_API_KEY")
    base, model = PRESETS.get(provider, (env("LLM_BASE_URL"), ""))
    model = env("LLM_MODEL") or model
    base = env("LLM_BASE_URL") or base
    cp = _cache_path(provider, model, prompt, temperature)
    if cp.exists():
        return cp.read_text()
    if provider == "anthropic":
        if not key:
            raise RuntimeError("LLM_API_KEY not set")
        import anthropic

        msg = anthropic.Anthropic(api_key=key).messages.create(
            model=model or "claude-haiku-4-5-20251001", max_tokens=400, temperature=temperature,
            messages=[{"role": "user", "content": prompt}])
        out = msg.content[0].text.strip()
    elif provider == "ollama":
        body = {"model": model, "stream": False, "options": {"temperature": temperature, "num_predict": 300},
                "messages": [{"role": "user", "content": prompt}]}
        if model.startswith("qwen3"):
            body["think"] = False  # other models reject this field
        r = httpx.post(base + "/api/chat", timeout=600, json=body)
        r.raise_for_status()
        out = r.json()["message"]["content"].strip()
    else:  # OpenAI-compatible chat completions (DeepSeek, Kimi, others)
        if not key:
            raise RuntimeError(f"LLM_API_KEY not set for provider {provider}")
        if not base or not model:
            raise RuntimeError("set LLM_BASE_URL and LLM_MODEL for openai_compat")
        r = httpx.post(base.rstrip("/") + "/chat/completions", timeout=120, headers={"Authorization": f"Bearer {key}"}, json={
            "model": model, "temperature": temperature, "max_tokens": 400, "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        out = r.json()["choices"][0]["message"]["content"].strip()
    cp.write_text(out)
    return out
