#!/usr/bin/env python3
"""AI FOIA Editor — proxies to chat.moveweight.com for professional rewriting."""
import json
import os
import sys
import urllib.request
from pathlib import Path

CHAT_API = os.environ.get("FOIA_AI_CHAT_API", "http://192.168.0.137:4000/v1/chat/completions")
CHAT_KEY_PATH = Path(os.environ.get("FOIA_AI_KEY_FILE", "/root/.foia_ai_key"))
OLLAMA_API = os.environ.get("FOIA_AI_OLLAMA_API", "http://192.168.0.137:11434/api/chat")
OLLAMA_MODEL = os.environ.get("FOIA_AI_OLLAMA_MODEL", "llama3.2:3b")


def read_chat_key():
    key = os.environ.get("FOIA_AI_CHAT_KEY", "").strip()
    if key:
        return key
    try:
        return CHAT_KEY_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        return ""

PROMPT = """You are a professional open records request writer for the Move Weight Foundation, a 501(c)(3) transparency organization. Rewrite the following FOIA request to be professional, legally sound, and reference the Oklahoma Open Records Act (51 O.S. 24A.1). Keep all the original requests and details intact. Output ONLY the rewritten request text, no commentary."""


def call_openai_compat(text):
    chat_key = read_chat_key()
    if not chat_key:
        raise RuntimeError("OpenAI-compatible key is not configured.")

    payload = json.dumps({
        "model": os.environ.get("FOIA_AI_MODEL", "gpt-4o"),
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": "Rewrite this FOIA request professionally:\n\n" + text},
        ],
        "temperature": 0.3,
    }).encode()

    req = urllib.request.Request(CHAT_API, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + chat_key,
    })
    resp = urllib.request.urlopen(req, timeout=60)
    data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"].strip()


def call_ollama(text):
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": "Rewrite this FOIA request professionally:\n\n" + text},
        ],
        "options": {"temperature": 0.2},
    }).encode()

    req = urllib.request.Request(OLLAMA_API, data=payload, headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=120)
    data = json.loads(resp.read().decode())
    return (data.get("message", {}).get("content") or data.get("response") or "").strip()


text = sys.stdin.read().strip()
errors = []
for backend in (call_openai_compat, call_ollama):
    try:
        edited = backend(text)
        if edited:
            print(edited)
            sys.exit(0)
        errors.append(f"{backend.__name__}: empty response")
    except Exception as exc:
        errors.append(f"{backend.__name__}: {exc}")

print("Error: " + " | ".join(errors), file=sys.stderr)
sys.exit(1)
