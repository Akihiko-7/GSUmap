"""Gemma 4 through the Google AI Studio API (google-genai SDK).

Every call asks for JSON that matches a Pydantic model, has a timeout, and raises AIError with a short reason
instead of letting an exception reach the user. If the model refuses structured-output mode, the schema is put
in the prompt instead and the reply is parsed and validated here.
"""
import asyncio
import json
import logging
import re
from typing import TypeVar

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, ValidationError

from . import config

log = logging.getLogger("gemma")
T = TypeVar("T", bound=BaseModel)


class AIError(Exception):
    """A Gemma call that did not produce a usable answer. str(e) is safe to show."""


class Gemma:
    def __init__(self) -> None:
        self.client = genai.Client(api_key=config.GEMINI_API_KEY, http_options=types.HttpOptions(timeout=int(config.AI_TIMEOUT * 1000))) if config.GEMINI_API_KEY else None
        self.model = config.GEMMA_MODEL
        self.available: list[str] = []
        self.schema_mode = True  # turned off for good if the model rejects response_schema

    @property
    def ready(self) -> bool:
        return self.client is not None and bool(self.model)

    def pick_model(self) -> None:
        """List the models this key can use and choose the best Gemma 4 one."""
        if not self.client:
            log.warning("GEMINI_API_KEY is not set: AI features are off, the app falls back to local rules")
            return
        try:
            self.available = [m.name.removeprefix("models/") for m in self.client.models.list()]
        except Exception as e:
            log.error("could not list models: %s", e)
            self.model = self.model or "gemma-4-26b-a4b-it"
            return
        gemma4 = [n for n in self.available if n.startswith("gemma-4")]
        log.info("Gemma 4 models available: %s", ", ".join(gemma4) or "none")
        if self.model:
            if self.model not in self.available:
                log.warning("GEMMA_MODEL=%s is not in the list of available models; trying it anyway", self.model)
            return
        for size in config.GEMMA_PREFERENCE:
            hits = sorted((n for n in gemma4 if size in n), key=lambda n: (not n.endswith("-it"), len(n)))
            if hits:
                self.model = hits[0]
                break
        if not self.model:
            older = sorted((n for n in self.available if n.startswith("gemma-3-27b")), key=len)
            self.model = older[0] if older else "gemma-4-26b-a4b-it"
            log.warning("no Gemma 4 model listed; using %s", self.model)
        log.info("using model %s", self.model)

    async def ask(self, parts: list, schema: type[T], timeout: float | None = None, max_tokens: int = 1500) -> T:
        """max_tokens caps the answer: Gemma sometimes falls into a repeating loop, and the cap ends it quickly."""
        if not self.ready:
            raise AIError("AI is not configured on this server")
        timeout = timeout or config.AI_TIMEOUT
        try:
            return await asyncio.wait_for(self._ask(parts, schema, max_tokens), timeout)
        except asyncio.TimeoutError:
            raise AIError("The AI took too long to answer")
        except AIError:
            raise
        except Exception as e:
            log.exception("gemma call failed")
            raise AIError("The AI service could not be reached") from e

    @property
    def backup(self) -> str | None:
        """The other large Gemma 4 model, tried once when the main one has a server error."""
        others = [n for n in self.available if n.startswith("gemma-4") and n != self.model and ("26b" in n or "31b" in n)]
        return others[0] if others else None

    async def _ask(self, parts: list, schema: type[T], max_tokens: int) -> T:
        """Hedged request: ask the main model; if it fails, or has not answered after HEDGE_AFTER seconds,
        ask the backup model as well and take whichever good answer comes first. Google's free tier is
        sometimes slow or answers 500/504 for a while, and this keeps answers coming."""
        backup = self.backup
        pending = {asyncio.create_task(self._ask_model(self.model, parts, schema, max_tokens))}
        hedged = backup is None
        last_error: Exception | None = None
        try:
            while pending:
                done, pending = await asyncio.wait(pending, timeout=None if hedged else config.HEDGE_AFTER, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    if task.exception() is None:
                        return task.result()
                    last_error = task.exception()
                    log.warning("gemma attempt failed: %s", str(last_error)[:200])
                if not hedged and (done or pending):
                    log.info("asking %s as well", backup)
                    pending.add(asyncio.create_task(self._ask_model(backup, parts, schema, max_tokens)))
                    hedged = True
            raise last_error or AIError("The AI returned no answer")
        finally:
            for task in pending:
                task.cancel()

    async def _ask_model(self, model: str, parts: list, schema: type[T], max_tokens: int) -> T:
        if self.schema_mode:
            try:
                cfg = types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema, temperature=0.2, max_output_tokens=max_tokens)
                resp = await self.client.aio.models.generate_content(model=model, contents=parts, config=cfg)
                return self._parse(resp.text, schema)
            except Exception as e:
                msg = str(e).lower()
                if not isinstance(e, genai_errors.ClientError) or ("json" not in msg and "schema" not in msg and "mime" not in msg):
                    raise
                log.warning("model rejected structured output (%s); putting the schema in the prompt instead", e)
                self.schema_mode = False
        hint = "Reply with ONLY a JSON object, no markdown, matching this JSON schema:\n" + json.dumps(schema.model_json_schema())
        resp = await self.client.aio.models.generate_content(model=model, contents=[*parts, hint], config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=max_tokens))
        return self._parse(resp.text, schema)

    @staticmethod
    def _parse(text: str | None, schema: type[T]) -> T:
        if not text:
            raise AIError("The AI returned an empty answer")
        m = re.search(r"\{.*\}", text, re.S)
        try:
            return schema.model_validate(json.loads(m.group(0) if m else text))
        except (json.JSONDecodeError, ValidationError) as e:
            log.warning("bad JSON from model: %s | %s", e, text[:300])
            raise AIError("The AI answer could not be read")


def image_part(jpeg: bytes) -> types.Part:
    return types.Part.from_bytes(data=jpeg, mime_type="image/jpeg")


def language_rule(lang: str) -> str:
    names = (" In text, call places only by the names given (never by their ids), keep those names exactly as written, "
             "and never invent building names that are not in the list.")
    if lang == "ha":
        return "Write every text value in Hausa (Latin script, as spoken in Gombe and Kano)." + names
    return "Write every text value in simple, friendly English for a Nigerian university student." + names


gemma = Gemma()
