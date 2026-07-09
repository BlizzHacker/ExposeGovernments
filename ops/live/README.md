# Live service notes

These files mirror the service scripts currently deployed in CT 170.

Deploy paths:

- `foia-api.py` -> `/opt/foia-api.py`
- `foia-ai-edit.py` -> `/opt/foia-ai-edit.py`
- `exposemiamiok_navigation_update.py` -> `/usr/local/bin/exposemiamiok_navigation_update.py`

Runtime secrets are intentionally not committed:

- Manual admin token: `/root/.exposemiami_admin_token`
- AI editor key, if the OpenAI-compatible backend is used: `/root/.foia_ai_key`

The FOIA AI editor first tries the OpenAI-compatible LiteLLM endpoint and falls back to local Ollama on the chat LXC.
