from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional


def base_url(env: str) -> str:
    if env == "testnet":
        return "https://testnet.zklighter.elliot.ai"
    return "https://mainnet.zklighter.elliot.ai"


@dataclass
class LighterPublicClient:
    env: str = "mainnet"
    timeout_s: float = 10.0

    def accounts_by_l1_address(self, l1_address: str) -> Dict[str, Any]:
        url = f"{base_url(self.env)}/api/v1/accountsByL1Address"
        qs = urllib.parse.urlencode({"l1_address": l1_address})
        return self._get_json(f"{url}?{qs}")

    def resolve_account_index(self, l1_address: str) -> Optional[int]:
        data = self.accounts_by_l1_address(l1_address)
        sub_accounts = data.get("sub_accounts")
        if isinstance(sub_accounts, list) and sub_accounts:
            first = sub_accounts[0]
            if isinstance(first, dict):
                if isinstance(first.get("index"), int):
                    return int(first["index"])
                if isinstance(first.get("account_index"), int):
                    return int(first["account_index"])
        if isinstance(data.get("account_index"), int):
            return int(data["account_index"])
        return None

    def _get_json(self, url: str) -> Dict[str, Any]:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            raw = resp.read().decode("utf-8")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("响应不是对象")
        return parsed

