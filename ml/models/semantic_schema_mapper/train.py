"""
Training and vocabulary fitting for Semantic Schema Mapper.
Builds an enterprise schema mapping dataset of at most 6,000 fields across canonical ERP/CRM concepts,
fits an n-gram TF-IDF vectorizer and logistic classification reranker, and persists the model artifact.
"""

import os
import sys
import pickle
import random
import yaml
import polars as pl
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from ml.models.semantic_schema_mapper.features import normalize_field_name

CONCEPTS_TAXONOMY = {
    "customer_name": [
        "customer_name", "client_name", "company_name", "organization_legal_name",
        "account_name", "cust_nm", "client_legal_title", "buyer_org_name",
        "debtor_name", "subscriber_name", "name1", "companyname", "cust_legal_name",
        "client_registered_name", "account_display_name", "trade_name"
    ],
    "customer_id": [
        "customer_id", "cust_id", "client_id", "account_number", "cust_code",
        "client_ref", "kunnr", "entityid", "customer_uuid", "client_no", "cust_pk",
        "customer_account_id", "debtor_number", "client_urn"
    ],
    "vendor_name": [
        "vendor_name", "supplier_name", "payee_name", "seller_name",
        "contractor_name", "vend_nm", "vendor_legal_entity", "creditor_name",
        "lifnr", "partner_name", "merchant_name", "supplier_legal_title"
    ],
    "vendor_id": [
        "vendor_id", "supplier_id", "vend_num", "seller_code", "supplier_code",
        "lifnr_id", "vendor_account_no", "payee_id", "creditor_code", "vendor_uuid"
    ],
    "billing_address": [
        "billing_address", "billing_street_loc", "bill_to_addr", "invoice_address",
        "billing_location", "stras_bill", "billaddr1", "billing_line1",
        "invoice_street", "billing_postal_loc", "invoicing_street_address"
    ],
    "shipping_address": [
        "shipping_address", "ship_to_address", "delivery_address", "destination_address",
        "ship_street_location", "shipaddr1", "warehouse_delivery_loc", "fulfillment_address"
    ],
    "tax_identifier": [
        "tax_identifier", "tax_id", "vat_number", "gstin_number", "ein_code",
        "fiscal_code", "tax_reg_no", "stceg", "tax_exempt_id", "federal_ein", "po_tax_num"
    ],
    "contact_email": [
        "contact_email", "cust_email", "billing_email", "email_address",
        "electronic_mail", "comm_email", "rep_email", "mail_id", "primary_email"
    ],
    "contact_phone": [
        "contact_phone", "telephone_num", "phone_number", "tel_number",
        "mobile_no", "office_phone", "voice_contact", "contact_cell", "phone_ext"
    ],
    "invoice_number": [
        "invoice_number", "invoice_id", "inv_num", "bill_number", "tranid",
        "belnr", "invoice_code", "voucher_id", "invoice_reference", "inv_no"
    ],
    "invoice_date": [
        "invoice_date", "inv_date", "issuance_date", "billing_date",
        "document_date", "bldat", "trandate", "posting_date", "invoice_timestamp"
    ],
    "total_amount": [
        "total_amount", "inv_total_val", "gross_total", "payable_amount",
        "balance_due", "amount_due", "dmbtr", "net_invoice_sum", "total_balance",
        "charge_total", "grand_total", "invoice_sum"
    ],
    "currency": [
        "currency", "currency_code", "iso_currency", "waers", "currency_id",
        "transaction_currency", "billing_currency", "forex_curr", "doc_curr"
    ]
}

DATA_TYPES = {
    "customer_name": "varchar(255)",
    "customer_id": "varchar(64)",
    "vendor_name": "varchar(255)",
    "vendor_id": "varchar(64)",
    "billing_address": "text",
    "shipping_address": "text",
    "tax_identifier": "varchar(50)",
    "contact_email": "varchar(120)",
    "contact_phone": "varchar(40)",
    "invoice_number": "varchar(64)",
    "invoice_date": "date",
    "total_amount": "decimal(14,2)",
    "currency": "varchar(3)"
}

PREFIXES = ["", "c_", "cust_", "client_", "vendor_", "vend_", "supp_", "inv_", "bill_", "ship_", "tx_", "acc_", "hdr_"]


def generate_schema_dataset(output_path: str = "ml/models/semantic_schema_mapper/data/schema_mappings_6k.parquet",
                            max_samples: int = 6000) -> pl.DataFrame:
    random.seed(42)
    records = []
    concepts = list(CONCEPTS_TAXONOMY.keys())

    for i in range(max_samples):
        concept = concepts[i % len(concepts)]
        seed_names = CONCEPTS_TAXONOMY[concept]
        base_name = random.choice(seed_names)
        prefix = random.choice(PREFIXES) if random.random() < 0.35 else ""
        
        raw_name = f"{prefix}{base_name}"
        if random.random() < 0.2:
            raw_name = raw_name.replace("_", "")
        elif random.random() < 0.2:
            raw_name = raw_name.replace("_", "-")
        elif random.random() < 0.1:
            raw_name = raw_name.upper()

        clean_c = concept.replace("_", " ")
        desc = f"Schema field for {clean_c} in source enterprise ERP/CRM system"
        records.append({
            "field_name": raw_name,
            "datatype": DATA_TYPES[concept],
            "description": desc,
            "canonical_concept": concept,
            "combined_text": f"{normalize_field_name(raw_name)} {desc}"
        })

    df = pl.DataFrame(records)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.write_parquet(output_path)
    print(f"Generated schema mappings dataset: {len(df)} records -> {output_path}")
    return df


def train_model(data_path: str = "ml/models/semantic_schema_mapper/data/schema_mappings_6k.parquet",
                output_path: str = "ml/models/semantic_schema_mapper/artifacts/schema_mapper.pkl"):
    print("Fitting TF-IDF vectorizer and logistic classification reranker on 6k schema fields...")
    if not os.path.exists(data_path):
        df = generate_schema_dataset(data_path)
    else:
        df = pl.read_parquet(data_path)

    X_texts = df["combined_text"].to_list()
    y_labels = df["canonical_concept"].to_list()

    vectorizer = TfidfVectorizer(ngram_range=(1, 3), analyzer="char_wb", min_df=1)
    X_vec = vectorizer.fit_transform(X_texts)

    classifier = LogisticRegression(C=5.0, max_iter=300, random_state=42)
    classifier.fit(X_vec, y_labels)

    bundle = {
        "vectorizer": vectorizer,
        "classifier": classifier,
        "classes": list(classifier.classes_)
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        pickle.dump(bundle, f)
    print(f"Artifact saved to {output_path} (trained on {len(df)} samples)")
    return bundle


if __name__ == "__main__":
    train_model()
