"""
Payment Request Service

Captures ad-hoc payment REQUESTS (not invoices) from multiple sources:
- Email requests ("Please pay $500 to John")
- Slack requests
- Internal requests (employee reimbursements)
- Manual requests via UI

Solden RECORDS and routes these requests for approval; it never executes the
payment. ``mark_paid`` only records an external payment reference once the
customer's ERP/bank has paid. There is no payment-execution path here.

Different from invoices - these are ad-hoc payment requests without formal invoicing.
"""

import re
import json
import uuid
import logging
from datetime import datetime, timezone

from solden.core.money import money_sum, money_to_float
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class RequestSource(Enum):
    """Source of payment request."""
    EMAIL = "email"
    SLACK = "slack"
    UI = "ui"
    API = "api"


class RequestStatus(Enum):
    """Status of payment request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID = "paid"
    CANCELLED = "cancelled"


class RequestType(Enum):
    """Type of payment request."""
    VENDOR_PAYMENT = "vendor_payment"
    REIMBURSEMENT = "reimbursement"
    CONTRACTOR = "contractor"
    REFUND = "refund"
    ADVANCE = "advance"
    OTHER = "other"


@dataclass
class PaymentRequest:
    """A payment request from any source."""
    request_id: str
    source: RequestSource
    source_id: str  # email_id, slack_ts, etc.
    
    # Request details
    requester_name: str
    requester_email: Optional[str]
    request_type: RequestType
    
    # Payment details
    payee_name: str
    payee_email: Optional[str] = None
    amount: float = 0.0
    currency: str = "USD"
    description: str = ""
    
    # Categorization
    gl_code: Optional[str] = None
    cost_center: Optional[str] = None
    
    # Status
    status: RequestStatus = RequestStatus.PENDING
    
    # Approval
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # Organization
    organization_id: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "source": self.source.value,
            "source_id": self.source_id,
            "requester_name": self.requester_name,
            "requester_email": self.requester_email,
            "request_type": self.request_type.value,
            "payee_name": self.payee_name,
            "payee_email": self.payee_email,
            "amount": self.amount,
            "currency": self.currency,
            "description": self.description,
            "gl_code": self.gl_code,
            "cost_center": self.cost_center,
            "status": self.status.value,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "organization_id": self.organization_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "PaymentRequest":
        """Reconstruct a PaymentRequest from a ``payment_requests`` DB row."""
        def _dt(v):
            if not v:
                return None
            try:
                return datetime.fromisoformat(str(v))
            except (ValueError, TypeError):
                return None

        md = row.get("metadata_json")
        if md is None:
            md = row.get("metadata")
        if isinstance(md, str):
            try:
                md = json.loads(md) if md.strip() else {}
            except (ValueError, TypeError):
                md = {}
        if not isinstance(md, dict):
            md = {}
        # payment_id is a column; surface it under metadata too so callers that
        # read metadata["payment_id"] (the pre-persistence contract) still work.
        if row.get("payment_id") and "payment_id" not in md:
            md["payment_id"] = row.get("payment_id")
        return cls(
            request_id=row["id"],
            source=RequestSource(row.get("source") or "api"),
            source_id=row.get("source_id") or "",
            requester_name=row.get("requester_name") or "",
            requester_email=row.get("requester_email"),
            request_type=RequestType(row.get("request_type") or "other"),
            payee_name=row.get("payee_name") or "",
            payee_email=row.get("payee_email"),
            amount=float(row.get("amount") or 0.0),
            currency=row.get("currency") or "USD",
            description=row.get("description") or "",
            gl_code=row.get("gl_code"),
            cost_center=row.get("cost_center"),
            status=RequestStatus(row.get("status") or "pending"),
            approved_by=row.get("approved_by"),
            approved_at=_dt(row.get("approved_at")),
            rejection_reason=row.get("rejection_reason"),
            created_at=_dt(row.get("created_at")) or datetime.now(timezone.utc),
            updated_at=_dt(row.get("updated_at")) or datetime.now(timezone.utc),
            organization_id=row.get("organization_id"),
            metadata=md,
        )


class PaymentRequestService:
    """
    Service for managing payment requests from all sources.
    """
    
    def __init__(self, organization_id: Optional[str] = None):
        from solden.core.org_utils import assert_org_id

        self.organization_id = assert_org_id(
            organization_id, context="PaymentRequestService"
        )

    @property
    def db(self):
        # Resolve the process-wide DB singleton per access rather than caching
        # it: this service is cached per-org in _instances, and a pool reset
        # (RDS failover, test teardown) would otherwise leave a stale handle.
        from solden.core.database import get_db
        return get_db()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_payload(r: PaymentRequest) -> Dict[str, Any]:
        return {
            "id": r.request_id,
            "organization_id": r.organization_id,
            "source": r.source.value,
            "source_id": r.source_id,
            "requester_name": r.requester_name,
            "requester_email": r.requester_email,
            "request_type": r.request_type.value,
            "payee_name": r.payee_name,
            "payee_email": r.payee_email,
            "amount": r.amount,
            "currency": r.currency,
            "description": r.description,
            "gl_code": r.gl_code,
            "cost_center": r.cost_center,
            "status": r.status.value,
            "metadata": r.metadata,
            "created_at": r.created_at.isoformat() if isinstance(r.created_at, datetime) else r.created_at,
            "updated_at": r.updated_at.isoformat() if isinstance(r.updated_at, datetime) else r.updated_at,
        }

    def _persist_new(self, request: PaymentRequest) -> PaymentRequest:
        self.db.create_payment_request(self._to_payload(request))
        return request

    def _emit_audit(
        self,
        request_id: str,
        event_type: str,
        actor_id: Optional[str],
        payload: Dict[str, Any],
    ) -> None:
        """Audit a payment-request lifecycle change as operational memory."""
        try:
            previous_status = payload.pop("_previous_status", None)
            resulting_status = payload.pop("_resulting_status", None)
            reason = (
                payload.get("reason")
                or payload.get("description")
                or event_type.replace("_", " ")
            )
            self.db.append_audit_event({
                "box_id": request_id,
                "box_type": "payment_request",
                "event_type": event_type,
                "from_state": previous_status,
                "to_state": resulting_status,
                "actor_type": "user",
                "actor_id": actor_id or "system",
                "organization_id": self.organization_id,
                "payload_json": {
                    "payment_request": {
                        "id": request_id,
                        "previous_status": previous_status,
                        "resulting_status": resulting_status,
                    },
                    "field_updates": payload,
                    "summary": f"Payment request {request_id} moved to {resulting_status or event_type}.",
                    "reason": reason,
                },
                "source": "payment_request_service",
                "decision_reason": reason,
            })
        except Exception as exc:
            logger.warning("payment_request audit emit failed for %s: %s", request_id, exc)
    
    # =========================================================================
    # CREATE REQUESTS
    # =========================================================================
    
    def create_from_email(
        self,
        email_id: str,
        sender_email: str,
        sender_name: str,
        subject: str,
        body: str,
        extracted_data: Optional[Dict] = None,
    ) -> PaymentRequest:
        """
        Create payment request from an email.
        
        Parses the email content to extract payment details.
        """
        # Extract payment details from email
        amount = 0.0
        payee = "Unknown"
        description = subject
        request_type = RequestType.OTHER
        
        if extracted_data:
            amount = extracted_data.get("amount", 0.0)
            payee = extracted_data.get("payee", sender_name)
            description = extracted_data.get("description", subject)
        else:
            # Parse from body
            amount = self._extract_amount(body) or self._extract_amount(subject)
            payee = self._extract_payee(body) or sender_name
            request_type = self._detect_request_type(subject, body)
        
        request = PaymentRequest(
            request_id=f"REQ-{uuid.uuid4().hex[:8].upper()}",
            source=RequestSource.EMAIL,
            source_id=email_id,
            requester_name=sender_name,
            requester_email=sender_email,
            request_type=request_type,
            payee_name=payee,
            amount=amount,
            description=description,
            organization_id=self.organization_id,
            metadata={
                "subject": subject,
                "body_preview": body[:500],
            }
        )
        
        self._persist_new(request)
        logger.info(f"Created payment request {request.request_id} from email: {subject}")

        return request
    
    def create_from_slack(
        self,
        channel_id: str,
        user_id: str,
        user_name: str,
        message_ts: str,
        text: str,
        parsed_command: Optional[Dict] = None,
    ) -> PaymentRequest:
        """
        Create a payment REQUEST from a Slack message or command (captures it
        for approval — Solden does not execute the payment).

        Supports formats like:
        - /solden pay @john $500 for consulting
        - /pay 1000 to Acme Corp for services
        - @solden please pay $250 to vendor
        """
        # Parse the slack message
        if parsed_command:
            amount = parsed_command.get("amount", 0.0)
            payee = parsed_command.get("payee", "Unknown")
            description = parsed_command.get("description", text)
            request_type = RequestType(parsed_command.get("type", "other"))
        else:
            amount = self._extract_amount(text)
            payee = self._extract_slack_payee(text)
            description = self._clean_slack_text(text)
            request_type = self._detect_request_type(text, "")
        
        request = PaymentRequest(
            request_id=f"REQ-{uuid.uuid4().hex[:8].upper()}",
            source=RequestSource.SLACK,
            source_id=f"{channel_id}:{message_ts}",
            requester_name=user_name,
            requester_email=None,  # Will be filled from Slack profile
            request_type=request_type,
            payee_name=payee,
            amount=amount,
            description=description,
            organization_id=self.organization_id,
            metadata={
                "channel_id": channel_id,
                "user_id": user_id,
                "message_ts": message_ts,
                "original_text": text,
            }
        )
        
        self._persist_new(request)
        logger.info(f"Created payment request {request.request_id} from Slack: {description[:50]}")

        return request
    
    def create_from_ui(
        self,
        user_email: str,
        user_name: str,
        payee_name: str,
        amount: float,
        description: str,
        request_type: str = "other",
        gl_code: Optional[str] = None,
        payee_email: Optional[str] = None,
    ) -> PaymentRequest:
        """
        Create payment request from UI form.
        """
        request = PaymentRequest(
            request_id=f"REQ-{uuid.uuid4().hex[:8].upper()}",
            source=RequestSource.UI,
            source_id=f"ui-{datetime.now(timezone.utc).timestamp()}",
            requester_name=user_name,
            requester_email=user_email,
            request_type=RequestType(request_type),
            payee_name=payee_name,
            payee_email=payee_email,
            amount=amount,
            currency="USD",
            description=description,
            gl_code=gl_code,
            organization_id=self.organization_id,
        )
        
        self._persist_new(request)
        logger.info(f"Created payment request {request.request_id} from UI")

        return request
    
    # =========================================================================
    # MANAGE REQUESTS
    # =========================================================================
    
    def get_request(self, request_id: str) -> Optional[PaymentRequest]:
        """Get a payment request by ID (org-scoped)."""
        row = self.db.get_payment_request(request_id, self.organization_id)
        return PaymentRequest.from_row(row) if row else None

    def get_pending_requests(self) -> List[PaymentRequest]:
        """Get all pending payment requests."""
        rows = self.db.list_payment_requests(
            self.organization_id, status=RequestStatus.PENDING.value,
        )
        return [PaymentRequest.from_row(r) for r in rows]

    def get_requests_by_source(self, source: RequestSource) -> List[PaymentRequest]:
        """Get requests from a specific source."""
        rows = self.db.list_payment_requests(self.organization_id, source=source.value)
        return [PaymentRequest.from_row(r) for r in rows]

    def get_requests_by_requester(self, email: str) -> List[PaymentRequest]:
        """Get requests from a specific requester."""
        rows = self.db.list_payment_requests(self.organization_id, requester_email=email)
        return [PaymentRequest.from_row(r) for r in rows]
    
    def approve_request(
        self,
        request_id: str,
        approved_by: str,
        gl_code: Optional[str] = None,
    ) -> PaymentRequest:
        """
        Approve a payment request.

        Marks the request approved — it does NOT execute payment (Solden never
        moves money). The customer's ERP/bank pays out-of-band; ``mark_paid``
        later records the external payment reference.
        """
        row = self.db.get_payment_request(request_id, self.organization_id)
        if not row:
            raise ValueError(f"Request {request_id} not found")
        if str(row.get("status")) != RequestStatus.PENDING.value:
            raise ValueError(f"Request {request_id} is not pending")

        approved_at = datetime.now(timezone.utc).isoformat()
        updates: Dict[str, Any] = {
            "status": RequestStatus.APPROVED.value,
            "approved_by": approved_by,
            "approved_at": approved_at,
        }
        if gl_code:
            updates["gl_code"] = gl_code
        self.db.update_payment_request(request_id, self.organization_id, **updates)
        self._emit_audit(request_id, "payment_request_approved", approved_by,
                         {
                             "_previous_status": row.get("status"),
                             "_resulting_status": RequestStatus.APPROVED.value,
                             "amount": row.get("amount"),
                             "gl_code": gl_code,
                         })
        logger.info(f"Payment request {request_id} approved by {approved_by}")

        return PaymentRequest.from_row(
            self.db.get_payment_request(request_id, self.organization_id)
        )
    
    def reject_request(
        self,
        request_id: str,
        rejected_by: str,
        reason: str,
    ) -> PaymentRequest:
        """Reject a payment request."""
        row = self.db.get_payment_request(request_id, self.organization_id)
        if not row:
            raise ValueError(f"Request {request_id} not found")

        metadata = dict(row.get("metadata_json") or {})
        metadata["rejected_by"] = rejected_by
        self.db.update_payment_request(
            request_id, self.organization_id,
            status=RequestStatus.REJECTED.value,
            rejection_reason=reason,
            metadata_json=metadata,
        )
        self._emit_audit(request_id, "payment_request_rejected", rejected_by,
                         {
                             "_previous_status": row.get("status"),
                             "_resulting_status": RequestStatus.REJECTED.value,
                             "reason": reason,
                         })
        logger.info(f"Payment request {request_id} rejected: {reason}")

        return PaymentRequest.from_row(
            self.db.get_payment_request(request_id, self.organization_id)
        )
    
    def mark_paid(self, request_id: str, payment_id: str) -> PaymentRequest:
        """Record that an EXTERNAL system paid this request (stores its
        ``payment_id``). Solden does not execute payment; this only reflects a
        payment the ERP/bank already made."""
        row = self.db.get_payment_request(request_id, self.organization_id)
        if not row:
            raise ValueError(f"Request {request_id} not found")

        self.db.update_payment_request(
            request_id, self.organization_id,
            status=RequestStatus.PAID.value,
            payment_id=payment_id,
        )
        self._emit_audit(request_id, "payment_request_marked_paid", None,
                         {
                             "_previous_status": row.get("status"),
                             "_resulting_status": RequestStatus.PAID.value,
                             "payment_id": payment_id,
                         })

        return PaymentRequest.from_row(
            self.db.get_payment_request(request_id, self.organization_id)
        )
    
    # =========================================================================
    # PARSING HELPERS
    # =========================================================================
    
    def _extract_amount(self, text: str) -> float:
        """Extract amount from text."""
        # Match patterns like: $500, $1,500.00, 500 USD, €500
        patterns = [
            r'\$[\d,]+(?:\.\d{2})?',  # $500, $1,500.00
            r'[\d,]+(?:\.\d{2})?\s*(?:USD|EUR|GBP)',  # 500 USD
            r'€[\d,]+(?:\.\d{2})?',  # €500
            r'£[\d,]+(?:\.\d{2})?',  # £500
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Clean and parse
                amount_str = re.sub(r'[^\d.]', '', match.group())
                try:
                    return float(amount_str)
                except ValueError:
                    continue
        
        return 0.0
    
    def _extract_payee(self, text: str) -> str:
        """Extract payee name from text."""
        # Common patterns
        patterns = [
            r'pay\s+(?:to\s+)?([A-Z][a-zA-Z\s]+?)(?:\s+for|\s+\$|\s+\d|$)',
            r'payment\s+(?:to|for)\s+([A-Z][a-zA-Z\s]+?)(?:\s+for|\s+\$|\s+\d|$)',
            r'reimburse\s+([A-Z][a-zA-Z\s]+?)(?:\s+for|\s+\$|\s+\d|$)',
            r'to\s+([A-Z][a-zA-Z\s]+?)\s+for',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return "Unknown"
    
    def _extract_slack_payee(self, text: str) -> str:
        """Extract payee from Slack message (handles @mentions)."""
        # Match @mentions or plain text
        mention_match = re.search(r'<@([A-Z0-9]+)>', text)
        if mention_match:
            return f"@{mention_match.group(1)}"  # Will be resolved later
        
        return self._extract_payee(text)
    
    def _clean_slack_text(self, text: str) -> str:
        """Clean Slack message text."""
        # Remove Slack formatting
        text = re.sub(r'<@[A-Z0-9]+>', '', text)  # Remove mentions
        text = re.sub(r'<#[A-Z0-9]+\|([^>]+)>', r'\1', text)  # Channel links
        text = re.sub(r'<([^|>]+)\|([^>]+)>', r'\2', text)  # URL links
        text = re.sub(r'<([^>]+)>', r'\1', text)  # Plain URLs
        return text.strip()
    
    def _detect_request_type(self, subject: str, body: str) -> RequestType:
        """Detect the type of payment request."""
        text = f"{subject} {body}".lower()
        
        if any(kw in text for kw in ["reimburse", "reimbursement", "expense", "out of pocket"]):
            return RequestType.REIMBURSEMENT
        
        if any(kw in text for kw in ["contractor", "freelancer", "consulting", "consultant"]):
            return RequestType.CONTRACTOR
        
        if any(kw in text for kw in ["refund", "credit", "return"]):
            return RequestType.REFUND
        
        if any(kw in text for kw in ["advance", "prepay", "deposit"]):
            return RequestType.ADVANCE
        
        if any(kw in text for kw in ["vendor", "supplier", "invoice"]):
            return RequestType.VENDOR_PAYMENT
        
        return RequestType.OTHER
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics (org-scoped)."""
        requests = [
            PaymentRequest.from_row(r)
            for r in self.db.list_payment_requests(self.organization_id, limit=1000)
        ]

        pending = [r for r in requests if r.status == RequestStatus.PENDING]
        approved = [r for r in requests if r.status == RequestStatus.APPROVED]
        paid = [r for r in requests if r.status == RequestStatus.PAID]
        
        return {
            "total_requests": len(requests),
            "pending": len(pending),
            "pending_amount": money_to_float(money_sum(r.amount for r in pending)),
            "approved": len(approved),
            "approved_amount": money_to_float(money_sum(r.amount for r in approved)),
            "paid": len(paid),
            "paid_amount": money_to_float(money_sum(r.amount for r in paid)),
            "by_source": {
                "email": len([r for r in requests if r.source == RequestSource.EMAIL]),
                "slack": len([r for r in requests if r.source == RequestSource.SLACK]),
                "ui": len([r for r in requests if r.source == RequestSource.UI]),
            },
            "by_type": {
                t.value: len([r for r in requests if r.request_type == t])
                for t in RequestType
            }
        }


# Singleton instances per organization
_instances: Dict[str, PaymentRequestService] = {}


def get_payment_request_service(organization_id: Optional[str] = None) -> PaymentRequestService:
    """Get or create PaymentRequestService instance."""
    from solden.core.org_utils import assert_org_id

    org = assert_org_id(organization_id, context="get_payment_request_service")
    if org not in _instances:
        _instances[org] = PaymentRequestService(org)
    return _instances[org]
