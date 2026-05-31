"""Mock core banking service — replaceable with real CBS integration."""

import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)


class BankingService:
    """
    Mock banking data provider.

    Returns deterministic loan/EMI data per customer_id.
    Designed as an interface boundary for future CBS/core banking APIs.
    """

    def get_loan_details(self, customer_id: str) -> dict[str, Any]:
        """Fetch customer loan information."""
        seed = self._seed(customer_id)
        return {
            "loan_id": f"LN{seed:03d}",
            "loan_type": "Personal Loan" if seed % 2 == 0 else "Home Loan",
            "outstanding_amount": 200000 + (seed * 1500),
            "emi_amount": 10000 + (seed * 250),
            "next_due_date": "2026-06-15",
        }

    def check_emi_due(self, customer_id: str) -> dict[str, Any]:
        """Retrieve EMI due information."""
        loan = self.get_loan_details(customer_id)
        statuses = ["PENDING", "OVERDUE", "PAID"]
        status = statuses[self._seed(customer_id) % len(statuses)]
        return {
            "emi_amount": loan["emi_amount"],
            "due_date": loan["next_due_date"],
            "status": status,
            "loan_id": loan["loan_id"],
        }

    def get_payment_link(
        self,
        customer_id: str,
        *,
        base_url: str = "https://abc-bank.com/pay",
    ) -> dict[str, Any]:
        """Generate a payment link for the customer."""
        loan = self.check_emi_due(customer_id)
        base = base_url.rstrip("/")
        return {
            "payment_link": f"{base}/{customer_id}",
            "emi_amount": loan["emi_amount"],
            "due_date": loan["due_date"],
        }

    @staticmethod
    def _seed(customer_id: str) -> int:
        """Deterministic numeric seed from customer_id."""
        digest = hashlib.md5(customer_id.encode()).hexdigest()
        return int(digest[:4], 16) % 100
