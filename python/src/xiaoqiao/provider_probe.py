"""Probe a provider's ``base_url`` + key to prove the configuration works.

The settings UI has a "测试连接" button; without a cheap round trip the only way
to discover a wrong key or a mistyped ``base_url`` is to send a real prompt and
watch it fail.  Probing ``GET {base_url}/models`` costs no tokens and answers the
same question.
"""

from __future__ import annotations

from typing import Any

import httpx

from xiaoqiao.config.schema import ProviderSettings, Settings
from xiaoqiao.settings import effective_key_for_provider

_TIMEOUT = 10.0


def models_url(provider: ProviderSettings) -> str:
    """Model-list endpoint for a provider ("" when ``base_url`` is empty)."""
    base = (provider.base_url or provider.env_value("BASE_URL")).rstrip("/")
    if not base:
        return ""
    if provider.type == "anthropic" and not base.endswith("/v1"):
        return f"{base}/v1/models"
    return f"{base}/models"


def probe_headers(provider: ProviderSettings, api_key: str) -> dict[str, str]:
    """Auth headers for the probe, matching what :func:`build_client` will send."""
    headers = {"Accept": "application/json", **provider.custom_headers}
    if provider.type == "anthropic":
        headers["x-api-key"] = api_key
        headers.setdefault("anthropic-version", "2023-06-01")
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _model_ids(payload: Any) -> list[str]:
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    ids: list[str] = []
    for item in items:
        if isinstance(item, dict):
            identifier = item.get("id") or item.get("name")
            if isinstance(identifier, str) and identifier:
                ids.append(identifier)
    return ids


async def probe_provider(
    settings: Settings,
    provider_id: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """Ask a provider for its model list; never raises.

    Returns ``{ok, url, status?, count?, models?, error?}`` so the UI can show a
    concrete reason instead of a generic failure.
    """
    provider = settings.providers.get(provider_id)
    if provider is None:
        return {"ok": False, "error": f"未找到 AI 服务 {provider_id!r}"}

    url = models_url(provider)
    if not url:
        return {"ok": False, "error": "缺少 base_url，无法测试连接"}

    api_key = effective_key_for_provider(settings, provider_id)
    if not api_key:
        return {"ok": False, "url": url, "error": "没有可用的 API key（api_key 为空，api_key_env 也未设置）"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, transport=transport) as client:
            response = await client.get(url, headers=probe_headers(provider, api_key))
    except httpx.HTTPError as exc:
        return {"ok": False, "url": url, "error": f"无法连接 {url}：{exc}"}

    if response.status_code != 200:
        detail = response.text.strip()[:300] or response.reason_phrase
        error = f"HTTP {response.status_code}：{detail}"
        return {"ok": False, "url": url, "status": response.status_code, "error": error}

    try:
        payload = response.json()
    except ValueError:
        return {"ok": False, "url": url, "status": response.status_code, "error": "返回内容不是 JSON"}
    models = _model_ids(payload)
    return {"ok": True, "url": url, "status": response.status_code, "count": len(models), "models": models[:50]}


__all__ = ["models_url", "probe_headers", "probe_provider"]
