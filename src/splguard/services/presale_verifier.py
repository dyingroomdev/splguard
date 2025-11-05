from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class VerificationOutcome:
    ok: bool
    reason: str | None = None
    amount: float | None = None
    currency: str | None = None
    xp_awarded: int = 0


class PresaleVerifier:
    def __init__(self, rpc_url: str | None = None) -> None:
        self._rpc_url = rpc_url or settings.solana_rpc_url
        self._program_ids = {pid.lower() for pid in settings.presale_smithii_program_ids}
        self._vaults = {vault.lower() for vault in settings.presale_vault_addresses}
        self._token_mints = {mint.lower() for mint in settings.presale_token_mints}
        self._tdl_mint = (settings.tdl_mint or "").lower()
        self._sol_threshold = max(0, settings.presale_min_sol_lamports)
        self._usdc_threshold = max(0, settings.presale_min_usdc_amount)

    async def verify(self, tx_signature: str, buyer_wallet: str | None) -> VerificationOutcome:
        if not self._rpc_url:
            return VerificationOutcome(ok=False, reason="rpc_not_configured")
        if not buyer_wallet:
            return VerificationOutcome(ok=False, reason="wallet_not_linked")

        buyer_wallet_lower = buyer_wallet.lower()

        payload = {
            "jsonrpc": "2.0",
            "id": "splguard",
            "method": "getTransaction",
            "params": [
                tx_signature,
                {"encoding": "jsonParsed", "commitment": "confirmed"},
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(self._rpc_url, json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch transaction %s: %s", tx_signature, exc)
            return VerificationOutcome(ok=False, reason="rpc_error")
        except Exception:
            logger.exception("Unexpected error while fetching transaction %s", tx_signature)
            return VerificationOutcome(ok=False, reason="rpc_error")

        tx = body.get("result")
        if not tx:
            return VerificationOutcome(ok=False, reason="tx_not_found")

        transaction = tx.get("transaction") or {}
        message = transaction.get("message") or {}
        account_keys = message.get("accountKeys") or []
        if not account_keys:
            return VerificationOutcome(ok=False, reason="invalid_transaction")

        accounts_lower = [self._extract_pubkey(entry).lower() for entry in account_keys]
        signers = {
            self._extract_pubkey(entry).lower()
            for entry in account_keys
            if isinstance(entry, dict) and entry.get("signer")
        }

        if buyer_wallet_lower not in signers:
            return VerificationOutcome(ok=False, reason="buyer_not_signer")

        if self._program_ids:
            if not self._has_program(message, tx.get("meta") or {}, self._program_ids):
                return VerificationOutcome(ok=False, reason="no_smithii_program")

        if self._vaults:
            if not any(account in self._vaults for account in accounts_lower):
                return VerificationOutcome(ok=False, reason="vault_not_involved")

        meta = tx.get("meta") or {}
        pre_balances = meta.get("preBalances") or []
        post_balances = meta.get("postBalances") or []

        try:
            buyer_index = accounts_lower.index(buyer_wallet_lower)
        except ValueError:
            return VerificationOutcome(ok=False, reason="wallet_missing")

        sol_paid = 0
        if (
            self._sol_threshold > 0
            and buyer_index < len(pre_balances)
            and buyer_index < len(post_balances)
        ):
            sol_paid = (pre_balances[buyer_index] or 0) - (post_balances[buyer_index] or 0)

        token_balances = self._token_differences(meta, buyer_wallet_lower)
        token_spent_raw = 0
        token_decimals = 0
        token_mint_used: str | None = None
        if self._token_mints:
            for mint, diff in token_balances.items():
                if mint in self._token_mints and diff["spent_raw"] > token_spent_raw:
                    token_spent_raw = diff["spent_raw"]
                    token_decimals = diff["decimals"]
                    token_mint_used = mint

        sol_ok = self._sol_threshold == 0 or sol_paid >= self._sol_threshold
        token_ok = (
            (self._usdc_threshold == 0)
            or (token_spent_raw >= self._usdc_threshold)
            if self._token_mints
            else self._usdc_threshold == 0
        )

        if self._sol_threshold > 0 and not sol_ok and self._usdc_threshold == 0:
            return VerificationOutcome(ok=False, reason="insufficient_sol")
        if self._usdc_threshold > 0 and not token_ok and self._sol_threshold == 0:
            return VerificationOutcome(ok=False, reason="insufficient_usdc")
        if self._sol_threshold > 0 and self._usdc_threshold > 0 and not (sol_ok or token_ok):
            return VerificationOutcome(ok=False, reason="insufficient_payment")

        if self._tdl_mint:
            if not self._tdl_minted(meta, buyer_wallet_lower, self._tdl_mint):
                return VerificationOutcome(ok=False, reason="tdl_not_minted")

        if token_mint_used:
            amount = token_spent_raw / (10**token_decimals) if token_decimals else float(token_spent_raw)
            return VerificationOutcome(
                ok=True,
                amount=amount,
                currency=token_mint_used,
                xp_awarded=settings.zealy_presale_xp_reward,
            )

        amount_in_sol = sol_paid / 1_000_000_000 if sol_paid else None
        return VerificationOutcome(
            ok=True,
            amount=amount_in_sol,
            currency="SOL" if amount_in_sol is not None else None,
            xp_awarded=settings.zealy_presale_xp_reward,
        )

    @staticmethod
    def _extract_pubkey(entry: Any) -> str:
        if isinstance(entry, dict):
            return entry.get("pubkey") or ""
        if isinstance(entry, str):
            return entry
        return ""

    @staticmethod
    def _has_program(message: dict[str, Any], meta: dict[str, Any], program_ids: set[str]) -> bool:
        instructions = message.get("instructions") or []
        for instr in instructions:
            program_id = instr.get("programId")
            if isinstance(program_id, str) and program_id.lower() in program_ids:
                return True

        for inner in meta.get("innerInstructions") or []:
            for instr in inner.get("instructions") or []:
                program_id = instr.get("programId")
                if isinstance(program_id, str) and program_id.lower() in program_ids:
                    return True
        return False

    @staticmethod
    def _token_differences(
        meta: dict[str, Any],
        owner: str,
    ) -> dict[str, dict[str, Any]]:
        pre = PresaleVerifier._token_balance_map(meta.get("preTokenBalances") or [])
        post = PresaleVerifier._token_balance_map(meta.get("postTokenBalances") or [])
        differences: dict[str, dict[str, Any]] = {}
        keys = set(pre.keys()) | set(post.keys())
        for key in keys:
            mint, entry_owner = key
            if entry_owner != owner:
                continue
            pre_entry = pre.get(key, {"raw": 0, "decimals": 0})
            post_entry = post.get(key, {"raw": 0, "decimals": pre_entry["decimals"]})
            spent_raw = max(0, pre_entry["raw"] - post_entry["raw"])
            decimals = post_entry.get("decimals", pre_entry.get("decimals", 0))
            differences[mint] = {
                "spent_raw": spent_raw,
                "decimals": decimals,
            }
        return differences

    @staticmethod
    def _token_balance_map(entries: list[Any]) -> dict[tuple[str, str], dict[str, Any]]:
        mapping: dict[tuple[str, str], dict[str, Any]] = {}
        for entry in entries:
            mint = entry.get("mint")
            owner = entry.get("owner")
            ui_amount = entry.get("uiTokenAmount") or {}
            if not mint or not owner:
                continue
            amount_raw = ui_amount.get("amount")
            decimals = ui_amount.get("decimals", 0)
            try:
                raw_int = int(amount_raw)
            except (TypeError, ValueError):
                raw_int = 0
            mapping[(mint.lower(), owner.lower())] = {
                "raw": raw_int,
                "decimals": decimals,
            }
        return mapping

    @staticmethod
    def _tdl_minted(meta: dict[str, Any], owner: str, mint: str) -> bool:
        pre = PresaleVerifier._token_balance_map(meta.get("preTokenBalances") or [])
        post = PresaleVerifier._token_balance_map(meta.get("postTokenBalances") or [])
        key = (mint.lower(), owner)
        post_entry = post.get(key)
        if not post_entry:
            return False
        pre_entry = pre.get(key, {"raw": 0})
        return post_entry["raw"] > pre_entry["raw"]
