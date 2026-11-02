from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class TransactionRecord(BaseModel):
    transaction_id: str
    vendor_id: str
    amount: float
    currency: str = "USD"
    historical_avg_amount: float = 1000.0
    historical_std_amount: float = 200.0
    vendor_age_days: int = 180
    transactions_last_24h: int = 1
    is_weekend: bool = False
    payment_terms_days: int = 30


class PreprocessedTransaction(BaseModel):
    raw: TransactionRecord
    features: list[float]


def preprocess_transaction(data: Dict[str, Any]) -> PreprocessedTransaction:
    rec = TransactionRecord(**data)
    
    amount_ratio = rec.amount / max(1.0, rec.historical_avg_amount)
    z_score = (rec.amount - rec.historical_avg_amount) / max(1.0, rec.historical_std_amount)
    vendor_age_factor = 1.0 if rec.vendor_age_days < 7 else 0.0
    velocity = float(rec.transactions_last_24h)
    weekend_flag = 1.0 if rec.is_weekend else 0.0
    terms_diff = abs(rec.payment_terms_days - 30) / 30.0

    feat_vector = [
        rec.amount,
        amount_ratio,
        z_score,
        vendor_age_factor,
        velocity,
        weekend_flag,
        terms_diff
    ]

    return PreprocessedTransaction(raw=rec, features=feat_vector)

