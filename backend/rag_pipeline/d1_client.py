import os
import sys
import logging
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load env variables
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

logger = logging.getLogger("LegalAssistant.D1Client")

class D1Client:
    def __init__(self):
        self.api_token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
        self.account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
        self.database_id = os.getenv("CLOUDFLARE_D1_DATABASE_ID", "9856cabc-fb1d-4c51-a91e-52b60e05b0eb").strip()
        self.timeout_seconds = float(os.getenv("D1_REQUEST_TIMEOUT_SECONDS", "8"))

    def is_configured(self) -> bool:
        """
        Checks if Cloudflare credentials are fully configured and not default values.
        """
        has_token = bool(self.api_token and self.api_token != "your_cloudflare_api_token_here")
        has_account = bool(self.account_id and self.account_id != "your_cloudflare_account_id_here")
        has_db = bool(self.database_id and self.database_id != "your_cloudflare_d1_database_id_here")
        return has_token and has_account and has_db

    def execute(self, sql: str, params: list = None) -> list:
        """
        Executes a SQL query on the Cloudflare D1 database.
        Returns a list of dictionaries representing rows if successful, or empty list.
        """
        if not self.is_configured():
            logger.warning("Cloudflare D1 is not fully configured in environment variables. D1 operations skipped.")
            return []

        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/d1/database/{self.database_id}/query"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "sql": sql,
            "params": params or []
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=self.timeout_seconds)
            response.raise_for_status()
            data = response.json()

            if not data.get("success"):
                errors = data.get("errors", [])
                err_msg = ", ".join([f"{e.get('code')}: {e.get('message')}" for e in errors])
                raise Exception(f"D1 REST API returned failure: {err_msg}")

            # Parse Cloudflare D1 Query API structure
            result_list = data.get("result")
            if isinstance(result_list, list) and len(result_list) > 0:
                first_result = result_list[0]
                if isinstance(first_result, dict):
                    if not first_result.get("success"):
                        errs = first_result.get("errors")
                        logger.error(f"Query-level execution error: {errs}")
                    return first_result.get("results") or []

            if isinstance(data.get("results"), list):
                return data["results"]

            return []

        except Exception as e:
            logger.error(f"Error executing SQL on Cloudflare D1: {e}")
            raise
