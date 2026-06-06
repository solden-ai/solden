from solden.services.teams_notifications import build_finance_summary_reply_activity


def _card_body(activity):
    return activity["attachments"][0]["content"]["body"]


def test_finance_summary_reply_activity_includes_operational_memory_facts():
    activity = build_finance_summary_reply_activity(
        {
            "id": "ap-memory-1",
            "vendor_name": "Cisco Systems",
            "amount": 12400,
            "currency": "USD",
            "invoice_number": "INV-124",
            "memory": {
                "waiting_on": "Operations Director",
                "waiting_reason": "Finance requested a budget reallocation.",
                "next_step": "Controller sign-off",
                "context_summary": {
                    "who_owns_it": "Operations Director",
                    "why_it_is_happening": "Finance requested a budget reallocation.",
                    "next_action": "Controller sign-off",
                    "latest_decision": {
                        "summary": "Finance requested a budget reallocation.",
                    },
                },
            },
            "agent_next_action": {
                "label": "Legacy next action",
            },
        },
        ["Budget needs review."],
    )

    fact_sets = [
        block["facts"]
        for block in _card_body(activity)
        if block.get("type") == "FactSet"
    ]
    flat_facts = {
        fact["title"]: fact["value"]
        for facts in fact_sets
        for fact in facts
    }

    assert flat_facts["Next"] == "Controller sign-off"
    assert flat_facts["Owner"] == "Operations Director"
    assert flat_facts["Why"] == "Finance requested a budget reallocation."
    assert flat_facts["Decision"] == "Finance requested a budget reallocation."
