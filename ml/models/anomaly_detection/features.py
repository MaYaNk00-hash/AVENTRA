from typing import Dict, Any, List
from ml.models.anomaly_detection.preprocessing import TransactionRecord


def evaluate_business_rules(rec: TransactionRecord) -> Dict[str, Any]:
    flags = []
    rule_score = 0.0

    # Rule 1: Extreme Amount Spike
    ratio = rec.amount / max(1.0, rec.historical_avg_amount)
    if ratio >= 4.0:
        flags.append(f"Transaction amount is {ratio:.1f}x higher than historical vendor average (${rec.historical_avg_amount:,.2f})")
        rule_score += 0.45
    elif ratio >= 2.5:
        flags.append(f"Transaction amount is elevated ({ratio:.1f}x above baseline)")
        rule_score += 0.20

    # Rule 2: Brand New Vendor with High Disbursement
    if rec.vendor_age_days < 7 and rec.amount > 10000.0:
        flags.append(f"High-value payment (${rec.amount:,.2f}) issued to new vendor (created {rec.vendor_age_days} days ago)")
        rule_score += 0.40

    # Rule 3: Velocity Surge
    if rec.transactions_last_24h > 5:
        flags.append(f"Unusual velocity: {rec.transactions_last_24h} transactions issued within 24 hours")
        rule_score += 0.30

    # Rule 4: Off-hours / Weekend Large Transaction
    if rec.is_weekend and rec.amount > 50000.0:
        flags.append("High-value disbursement initiated outside regular banking hours/weekend")
        rule_score += 0.15

    final_score = min(1.0, rule_score)
    return {
        "rule_flags": flags,
        "rule_score": round(final_score, 3)
    }

