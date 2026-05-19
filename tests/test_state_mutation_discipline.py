"""Phase 1, Gap 3 — guard against raw state mutations on ``ap_items``.

Every state transition on an AP item MUST go through
``SoldenDB.update_ap_item``. That single chokepoint is what
enforces:

* state-machine validation (``ap_states.transition_or_raise``)
* atomic write of the corresponding ``audit_events`` row in the
  same transaction
* the auto-built ``decision_context`` snapshot (Phase 1, Gap 4)

A raw ``UPDATE ap_items SET state = ...`` anywhere else silently
bypasses all three and breaks the system-of-record audit chain.

If this test fails, you've added a state-mutating SQL outside the
canonical path. Either:

1. **Preferred** — route the change through
   ``db.update_ap_item(ap_item_id, state=..., _actor_type=..., ...)``.
2. **Whitelist** — add the file to the allow-list below if the
   write is a one-off migration / DDL / fixture (and add a code
   comment explaining why it doesn't need the audit trail).
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "clearledgr"

# Files that legitimately ``UPDATE ap_items`` — none of them mutate the
# ``state`` column outside ``update_ap_item``.
#
# This whitelist exists for the regex below to skip files where a raw
# UPDATE is acceptable (DDL / metadata-only / fixture). Any new entry
# must come with a code comment in the file explaining why the audit
# bypass is safe.
ALLOWED_FILES = frozenset(
    {
        # update_ap_item itself + metadata-merge helper (metadata only)
        "clearledgr/core/stores/ap_store.py",
        # one-time DDL / data-shape backfills that run pre-state
        "clearledgr/core/migrations.py",
        # SOX archive hash backfill — does not touch state
        "clearledgr/services/invoice_archive.py",
        # vendor master de-dup — only mutates vendor_name
        "clearledgr/services/vendor_dedup.py",
        # synthetic sample-data seeder (dev/demo, not prod)
        "clearledgr/services/sample_data.py",
    }
)

# Match ``UPDATE ap_items SET <columns>`` and capture the SET clause
# up to (but not including) any WHERE, ORDER BY, RETURNING, or
# closing quote. We then check whether the captured columns include
# the literal ``state`` column at word boundary.
_UPDATE_RE = re.compile(
    r"UPDATE\s+ap_items\s+SET\s+(?P<set_clause>[^;\"']+)",
    re.IGNORECASE,
)
_STATE_COL_RE = re.compile(r"\bstate\s*=")


def _state_in_set_clause(set_clause: str) -> bool:
    """Return True iff the SET clause assigns to the literal ``state`` column.

    Stops at WHERE/ORDER BY/RETURNING so we only inspect the columns
    being written, not predicates that happen to mention ``state``.
    """
    head = re.split(
        r"\b(?:WHERE|ORDER\s+BY|RETURNING)\b",
        set_clause,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return bool(_STATE_COL_RE.search(head))


def test_no_raw_state_mutation_outside_update_ap_item():
    failures: list[str] = []
    for py_file in SOURCE_ROOT.rglob("*.py"):
        rel = str(py_file.relative_to(REPO_ROOT))
        if rel in ALLOWED_FILES:
            continue
        text = py_file.read_text(encoding="utf-8")
        for match in _UPDATE_RE.finditer(text):
            set_clause = match.group("set_clause")
            if _state_in_set_clause(set_clause):
                # Find the line number of the offending SQL for a
                # useful failure message.
                line_no = text.count("\n", 0, match.start()) + 1
                failures.append(
                    f"{rel}:{line_no} — raw `UPDATE ap_items SET state = ...` "
                    "bypasses update_ap_item"
                )

    assert not failures, (
        "Raw state mutation found outside SoldenDB.update_ap_item.\n"
        "Route the change through ``db.update_ap_item(ap_item_id, state=...,"
        " _actor_type=..., _actor_id=..., _decision_reason=...)`` so the "
        "state-machine, audit_events row, and decision_context snapshot "
        "all stay in lockstep.\n  "
        + "\n  ".join(failures)
    )
