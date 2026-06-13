#!/usr/bin/env python3
"""Create a first-owner activation link for a provisioned customer workspace.

Usage:
    python scripts/provision_customer_activation.py \
      --org-id acme-systems \
      --org-name "Acme Systems" \
      --owner-email finance-lead@acme.com

The script is intentionally sales-led: Solden provisions the workspace,
then sends the activation link to the first customer owner. That owner
can sign in with Google/Microsoft or set a password on /activate.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from solden.core.auth import ROLE_OWNER, WORKSPACE_ROLE_OWNER, normalize_workspace_role
from solden.core.database import get_db


def _email_domain(email: str) -> str | None:
    if "@" not in email:
        return None
    return email.rsplit("@", 1)[1].strip().lower() or None


def _active_owner_email(db, organization_id: str) -> str | None:
    for row in db.get_users(organization_id, include_inactive=False) or []:
        role = (
            normalize_workspace_role(row.get("workspace_role"))
            or normalize_workspace_role(row.get("role"))
        )
        if role == WORKSPACE_ROLE_OWNER:
            return str(row.get("email") or "").strip().lower() or None
    return None


def _existing_pending_activation(db, organization_id: str, email: str):
    for invite in db.list_team_invites(organization_id) or []:
        if str(invite.get("status") or "") != "pending":
            continue
        if str(invite.get("email") or "").strip().lower() != email:
            continue
        role = normalize_workspace_role(invite.get("role"))
        if role == WORKSPACE_ROLE_OWNER:
            return invite
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision a Solden customer activation link.")
    parser.add_argument("--org-id", required=True, help="Stable tenant id, e.g. acme-systems")
    parser.add_argument("--org-name", required=True, help="Customer workspace display name")
    parser.add_argument("--owner-email", required=True, help="First customer owner email")
    parser.add_argument("--domain", default="", help="Customer email domain; defaults to owner email domain")
    parser.add_argument("--expires-days", type=int, default=14, help="Activation link TTL in days")
    parser.add_argument("--base-url", default="", help="Workspace base URL; defaults to APP_BASE_URL")
    parser.add_argument("--force-new", action="store_true", help="Create a new link even if a pending one exists")
    args = parser.parse_args()

    organization_id = args.org_id.strip()
    organization_name = args.org_name.strip()
    owner_email = args.owner_email.strip().lower()
    if not organization_id or not organization_name or not owner_email:
        raise SystemExit("--org-id, --org-name, and --owner-email are required")
    if "@" not in owner_email:
        raise SystemExit("--owner-email must be a valid email address")

    db = get_db()
    domain = (args.domain.strip().lower() or _email_domain(owner_email))
    db.ensure_organization(
        organization_id=organization_id,
        organization_name=organization_name,
        domain=domain,
    )

    existing_owner = _active_owner_email(db, organization_id)
    if existing_owner and existing_owner != owner_email:
        raise SystemExit(
            f"{organization_id} already has owner {existing_owner}; "
            "use Settings -> Team to add more users."
        )

    invite = None
    if not args.force_new:
        invite = _existing_pending_activation(db, organization_id, owner_email)

    if invite is None:
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=max(1, args.expires_days))
        ).isoformat()
        invite = db.create_team_invite(
            organization_id=organization_id,
            email=owner_email,
            role=ROLE_OWNER,
            created_by="system:customer_activation",
            expires_at=expires_at,
        )

    base_url = (
        args.base_url.strip()
        or os.getenv("APP_BASE_URL", "").strip()
        or "https://workspace.soldenai.com"
    ).rstrip("/")
    token = invite.get("token")
    print(f"Organization: {organization_name} ({organization_id})")
    print(f"Owner email:  {owner_email}")
    print(f"Activation:   {base_url}/activate?token={token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
