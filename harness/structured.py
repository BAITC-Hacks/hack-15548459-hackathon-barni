"""Structured outputs: получить от модели объект строго по схеме (Pydantic) — с проверкой и повтором.
Работает с любой моделью (и OpenAI, и NVIDIA).

    class Verdict(BaseModel):
        risk: int
        reasons: list[str]

    v = extract("Оцени риск заявки: ...", Verdict)
    v.risk, v.reasons
"""
import json
import re

from pydantic import BaseModel, ValidationError

from .router import ROUTER


class StructuredError(RuntimeError):
    pass


def _find_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"(\{.*\}|\[.*\])", text, flags=re.S)
        if not m:
            raise
        return json.loads(m.group(1))


def extract(prompt: str, schema: type[BaseModel], role="smart", system="", retries=2) -> BaseModel:
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    messages = [
        {"role": "system", "content": (system + "\n\n" if system else "") +
         "Ответь ТОЛЬКО одним JSON-объектом, строго по этой JSON-схеме, без пояснений и без ```:\n" + schema_json},
        {"role": "user", "content": prompt},
    ]
    last_error = None
    for _ in range(retries + 1):
        text = ROUTER.chat(role, messages).text
        try:
            return schema.model_validate(_find_json(text))
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = e
            messages += [{"role": "assistant", "content": text},
                         {"role": "user", "content": f"Ответ не прошёл проверку схемы: {str(e)[:800]}\nИсправь и верни только JSON."}]
    raise StructuredError(f"Модель не вернула корректный JSON: {last_error}")
