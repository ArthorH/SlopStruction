"""OpenRouter client. Nodes ask for a task; models.toml decides the model."""
import base64
import os
import tomllib
from pathlib import Path

from openai import OpenAI

CONFIG = tomllib.loads((Path(__file__).parent / "models.toml").read_text())
_client = None


def _key():
    if key := os.environ.get("OPENROUTER_API_KEY"):
        return key
    env = Path(__file__).parent / ".env"
    if env.exists():  # OPENROUTER_API_KEY=sk-or-...   (.env is gitignored)
        for line in env.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("OPENROUTER_API_KEY is not set (export it or put it in .env)")


def client():
    global _client
    if _client is None:
        _client = OpenAI(base_url=CONFIG["base_url"], api_key=_key())
    return _client


def image_part(path):
    data = base64.b64encode(Path(path).read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}


def ask(task, system, content, escalate=False):
    """Returns (text, usage dict)."""
    cfg = CONFIG["tasks"][task]
    model = cfg.get("escalate", cfg["model"]) if escalate else cfg["model"]
    extra_body = {"usage": {"include": True}}
    if cfg.get("reasoning"):
        extra_body["reasoning"] = {"effort": cfg["reasoning"]}
    kwargs = dict(model=model, max_tokens=cfg.get("max_tokens", 16000),
                  messages=[{"role": "system", "content": system},
                            {"role": "user", "content": content}],
                  extra_body=extra_body)
    try:
        resp = client().chat.completions.create(**kwargs)
    except Exception:
        if not cfg.get("reasoning"):
            raise
        extra_body.pop("reasoning")  # model may not accept the parameter
        resp = client().chat.completions.create(**kwargs | {"extra_body": extra_body})
    u = resp.usage
    usage = {"task": task, "model": model,
             "in": getattr(u, "prompt_tokens", 0), "out": getattr(u, "completion_tokens", 0),
             "cost": getattr(u, "cost", None)}
    return resp.choices[0].message.content or "", usage
