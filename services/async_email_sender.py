import asyncio
import hashlib
import hmac
import json
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import aiohttp


def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _aws_v4_headers(method: str, url: str, region: str, service: str, access_key: str, secret_key: str, payload: str) -> dict[str, str]:
    now = datetime.utcnow()
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    parsed = urlparse(url)
    host = parsed.netloc
    canonical_uri = parsed.path or "/"
    canonical_query = ""

    payload_hash = _sha256_hex(payload)
    canonical_headers = (
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join(
        [method, canonical_uri, canonical_query, canonical_headers, signed_headers, payload_hash]
    )

    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [
            algorithm,
            amz_date,
            credential_scope,
            _sha256_hex(canonical_request),
        ]
    )

    k_date = _sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    k_signing = _sign(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = (
        f"{algorithm} Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    return {
        "Content-Type": "application/json",
        "Host": host,
        "X-Amz-Date": amz_date,
        "X-Amz-Content-Sha256": payload_hash,
        "Authorization": authorization,
    }


def _parse_retry_after(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        seconds = int(value)
        return max(seconds, 0)
    except (TypeError, ValueError):
        return None


class AsyncEmailSender:
    def __init__(self, provider: str, provider_config: dict[str, Any]):
        self.provider = provider
        self.provider_config = provider_config

    def _build_request(self, item: dict[str, Any]) -> tuple[str, dict[str, str], str]:
        if self.provider == "ses":
            region = self.provider_config.get("region", "us-east-1")
            url = f"https://email.{region}.amazonaws.com/v2/email/outbound-emails"
            payload_dict = {
                "FromEmailAddress": self.provider_config["from_email"],
                "Destination": {"ToAddresses": [item["email"]]},
                "Content": {
                    "Simple": {
                        "Subject": {"Data": item["subject"], "Charset": "UTF-8"},
                        "Body": {
                            "Html": {"Data": item["body_html"], "Charset": "UTF-8"},
                            "Text": {"Data": item.get("body_plain") or "", "Charset": "UTF-8"},
                        },
                    }
                },
            }
            payload = json.dumps(payload_dict, separators=(",", ":"))
            headers = _aws_v4_headers(
                method="POST",
                url=url,
                region=region,
                service="ses",
                access_key=self.provider_config["access_key"],
                secret_key=self.provider_config["secret_key"],
                payload=payload,
            )
            return url, headers, payload

        url = "https://api.brevo.com/v3/smtp/email"
        payload_dict = {
            "sender": {
                "email": self.provider_config["sender_email"],
                "name": self.provider_config["sender_name"],
            },
            "to": [{"email": item["email"], "name": item.get("name") or ""}],
            "subject": item["subject"],
            "htmlContent": item["body_html"],
        }
        if item.get("body_plain"):
            payload_dict["textContent"] = item["body_plain"]
        return (
            url,
            {
                "Content-Type": "application/json",
                "api-key": self.provider_config["api_key"],
            },
            json.dumps(payload_dict, separators=(",", ":")),
        )

    async def _post(self, session: aiohttp.ClientSession, sem: asyncio.Semaphore, item: dict[str, Any]) -> dict[str, Any]:
        url, headers, payload = self._build_request(item)
        async with sem:
            async with session.post(url, headers=headers, data=payload) as response:
                body_text = await response.text()
                parsed_body: Any
                try:
                    parsed_body = json.loads(body_text) if body_text else {}
                except json.JSONDecodeError:
                    parsed_body = {"raw": body_text}
                return {
                    "status_code": response.status,
                    "headers": dict(response.headers),
                    "body": parsed_body,
                }

    async def _send_with_retry_policy(self, session: aiohttp.ClientSession, sem: asyncio.Semaphore, item: dict[str, Any], allow_deferred: bool) -> dict[str, Any]:
        attempts = 0
        while attempts < 2:
            attempts += 1
            try:
                response = await self._post(session, sem, item)
                status_code = response["status_code"]

                if 200 <= status_code < 300:
                    return {
                        "campaign_contact_id": item["campaign_contact_id"],
                        "contact_id": item["contact_id"],
                        "email": item["email"],
                        "subject": item["subject"],
                        "status": "sent",
                        "retry_count": attempts - 1,
                        "provider_response": response["body"],
                        "error": "",
                    }

                if status_code == 429:
                    retry_after = _parse_retry_after(response["headers"].get("Retry-After"))
                    if retry_after is not None and retry_after <= 10 and attempts < 2:
                        await asyncio.sleep(retry_after + 0.5)
                        continue
                    if allow_deferred:
                        return {
                            "campaign_contact_id": item["campaign_contact_id"],
                            "contact_id": item["contact_id"],
                            "email": item["email"],
                            "subject": item["subject"],
                            "status": "retrying",
                            "deferred": True,
                            "retry_count": attempts - 1,
                            "provider_response": response["body"],
                            "error": "Rate limited, deferred to second pass.",
                        }

                if status_code in (500, 502, 503) and attempts < 2:
                    await asyncio.sleep(2)
                    continue

                if status_code == 504 and attempts < 2:
                    await asyncio.sleep(5)
                    continue

                return {
                    "campaign_contact_id": item["campaign_contact_id"],
                    "contact_id": item["contact_id"],
                    "email": item["email"],
                    "subject": item["subject"],
                    "status": "failed",
                    "retry_count": attempts - 1,
                    "provider_response": response["body"],
                    "error": f"HTTP {status_code}",
                }

            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempts < 2:
                    continue
                return {
                    "campaign_contact_id": item["campaign_contact_id"],
                    "contact_id": item["contact_id"],
                    "email": item["email"],
                    "subject": item["subject"],
                    "status": "failed",
                    "retry_count": attempts - 1,
                    "provider_response": {},
                    "error": str(exc),
                }

        return {
            "campaign_contact_id": item["campaign_contact_id"],
            "contact_id": item["contact_id"],
            "email": item["email"],
            "subject": item["subject"],
            "status": "failed",
            "retry_count": 1,
            "provider_response": {},
            "error": "Unknown send failure",
        }

    async def send_all_parallel(
        self,
        payloads: list[dict[str, Any]],
        max_concurrent: int,
        result_callback,
        allow_deferred: bool = True,
    ) -> list[dict[str, Any]]:
        connector = aiohttp.TCPConnector(ttl_dns_cache=300, limit=max_concurrent)
        timeout = aiohttp.ClientTimeout(total=15, connect=5)
        semaphore = asyncio.Semaphore(max_concurrent)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks = [
                self._send_with_retry_policy(session, semaphore, item, allow_deferred=allow_deferred)
                for item in payloads
            ]
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        normalized_results: list[dict[str, Any]] = []
        for item, result in zip(payloads, raw_results):
            if isinstance(result, Exception):
                normalized = {
                    "campaign_contact_id": item["campaign_contact_id"],
                    "contact_id": item["contact_id"],
                    "email": item["email"],
                    "subject": item["subject"],
                    "status": "failed",
                    "retry_count": 1,
                    "provider_response": {},
                    "error": str(result),
                }
            else:
                normalized = result

            normalized_results.append(normalized)
            result_callback(normalized)

        return normalized_results
