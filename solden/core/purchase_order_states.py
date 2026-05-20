"""Purchase-order state machine — the third BoxType.

``purchase_order`` is the first AP-*peer* box type (bank_match was
AP-subordinate via a parent FK; a PO stands on its own). It rings a
genuinely independent workflow through the same Box scaffolding —
typed state machine, append-only audit, structured exceptions — which
is what turns "the runtime is general" from architecture into a fact.

The state VALUES are the existing :class:`POStatus` enum
(``solden/services/purchase_orders.py``); this module only adds the
transition graph + validation that the Box lifecycle needs. POs were
previously AP 3-way-match reference data with a free ``status`` column
and no enforced transitions.

Lifecycle::

    DRAFT ──submit──► PENDING_APPROVAL ──approve──► APPROVED
      ▲                    │                          │
      └────reject──────────┘                          ├─► PARTIALLY_RECEIVED ─► FULLY_RECEIVED
      (any non-terminal) ──cancel──► CANCELLED        ├─► PARTIALLY_INVOICED ─► FULLY_INVOICED
                                                       └─► CLOSED

CLOSED and CANCELLED are terminal. Phase 1 of the procurement build
exercises the approval leg (DRAFT → PENDING_APPROVAL → APPROVED →
CLOSED) plus CANCELLED; the receipt/invoice legs are wired here and
exercised when the goods-receipt leg lands.
"""
from __future__ import annotations

from typing import Dict, FrozenSet

from solden.services.purchase_orders import POStatus


VALID_PO_TRANSITIONS: Dict[POStatus, FrozenSet[POStatus]] = {
    POStatus.DRAFT: frozenset({
        POStatus.PENDING_APPROVAL,
        POStatus.CANCELLED,
    }),
    POStatus.PENDING_APPROVAL: frozenset({
        POStatus.APPROVED,
        POStatus.DRAFT,      # rejected back to the requester to revise
        POStatus.CANCELLED,
    }),
    POStatus.APPROVED: frozenset({
        POStatus.PARTIALLY_RECEIVED,
        POStatus.FULLY_RECEIVED,
        POStatus.CLOSED,     # services with no goods-receipt leg close directly
        POStatus.CANCELLED,
    }),
    POStatus.PARTIALLY_RECEIVED: frozenset({
        POStatus.PARTIALLY_RECEIVED,   # further partial receipts
        POStatus.FULLY_RECEIVED,
        POStatus.PARTIALLY_INVOICED,
        POStatus.CLOSED,
        POStatus.CANCELLED,
    }),
    POStatus.FULLY_RECEIVED: frozenset({
        POStatus.PARTIALLY_INVOICED,
        POStatus.FULLY_INVOICED,
        POStatus.CLOSED,
    }),
    POStatus.PARTIALLY_INVOICED: frozenset({
        POStatus.PARTIALLY_INVOICED,   # further partial invoices
        POStatus.FULLY_INVOICED,
        POStatus.CLOSED,
    }),
    POStatus.FULLY_INVOICED: frozenset({
        POStatus.CLOSED,
    }),
    POStatus.CLOSED: frozenset(),      # terminal
    POStatus.CANCELLED: frozenset(),   # terminal
}


PO_TERMINAL_STATES: FrozenSet[POStatus] = frozenset({
    POStatus.CLOSED,
    POStatus.CANCELLED,
})


VALID_PO_STATE_VALUES: FrozenSet[str] = frozenset(s.value for s in POStatus)


# Stamped on every audit_events row for a purchase_order Box so the
# version of the procurement policy that authorized each transition is
# preserved in the timeline. Analogous to CURRENT_BANK_MATCH_POLICY_VERSION.
CURRENT_PO_POLICY_VERSION = "v1"


class IllegalPurchaseOrderTransitionError(ValueError):
    """Raised when a purchase_order state transition violates the machine."""

    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"Illegal purchase_order transition: {current!r} -> {target!r}"
        )


def validate_po_transition(current: str, target: str) -> bool:
    """Whether *current* -> *target* is a legal purchase_order transition."""
    try:
        cur = POStatus(current)
        tgt = POStatus(target)
    except ValueError:
        return False
    return tgt in VALID_PO_TRANSITIONS.get(cur, frozenset())
