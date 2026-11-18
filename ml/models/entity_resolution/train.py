"""
Training pipeline for AVENTRA Entity Resolution model.
Loads open-source Amazon ML enterprise benchmark data, extracts 16 features on at most 6,000 candidate pairs,
trains a LightGBM gradient boosted trees classifier, and persists the artifact.
"""

import os
import sys
import pickle
import random
import numpy as np
import polars as pl
import lightgbm as lgb

os.environ['LOKY_MAX_CPU_COUNT'] = '4'

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from ml.models.entity_resolution.features import clean, get_tokens, get_nums, extract_features


def prepare_6k_dataset(data_output_path: str = "ml/models/entity_resolution/data/train_6k.parquet", max_samples: int = 6000) -> pl.DataFrame:
    print(f"Preparing up to {max_samples} candidate pairs from open source benchmark...")
    random.seed(42)

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
    s1_path = os.path.join(root, "amazon_ml", "s1_eval_sample.parquet")
    s2_path = os.path.join(root, "amazon_ml", "s2_eval_sample.parquet")
    s3_path = os.path.join(root, "amazon_ml", "s3_eval_sample.parquet")
    gt_path = os.path.join(root, "amazon_ml", "gt_eval_sample.parquet")

    s1 = pl.read_parquet(s1_path)
    s2 = pl.read_parquet(s2_path)
    s3 = pl.read_parquet(s3_path)
    gt = pl.read_parquet(gt_path)

    s1_dict = {r['entity_id']: r for r in s1.iter_rows(named=True)}
    targets = {}
    target_keys = []
    for r in s2.iter_rows(named=True):
        targets[r['entity_id']] = (r, True)
        target_keys.append(r['entity_id'])
    for r in s3.iter_rows(named=True):
        targets[r['entity_id']] = (r, False)
        target_keys.append(r['entity_id'])

    half_samples = max_samples // 2

    pos_pairs = []
    gt_set = set()
    for row in gt.iter_rows(named=True):
        s1_id = row['source1_entity_id']
        if s1_id not in s1_dict:
            continue
        matched = [m.strip() for m in row['matched_entity_ids'].split(',') if m.strip() in targets]
        for tid in matched:
            pos_pairs.append((s1_id, tid))
            gt_set.add((s1_id, tid))
            if len(pos_pairs) >= half_samples:
                break
        if len(pos_pairs) >= half_samples:
            break

    neg_pairs = []
    s1_keys = list(s1_dict.keys())
    while len(neg_pairs) < half_samples:
        s1_id = random.choice(s1_keys)
        tid = random.choice(target_keys)
        if (s1_id, tid) not in gt_set:
            neg_pairs.append((s1_id, tid))

    data_records = []
    for is_match, pair_list in [(1, pos_pairs), (0, neg_pairs)]:
        for s1_id, tid in pair_list:
            s1_rec = s1_dict[s1_id]
            c_rec, is_s2 = targets[tid]
            s1_cn = clean(s1_rec['business_name'])
            s1_ca = clean(s1_rec['business_address'])
            c_cn = clean(c_rec['business_name'])
            c_ca = clean(c_rec['business_address'])
            feat = extract_features(
                s1_cn, s1_ca, get_tokens(s1_cn), get_tokens(s1_ca), get_nums(s1_ca),
                c_cn, c_ca, get_tokens(c_cn), get_tokens(c_ca), get_nums(c_ca),
                is_s2=is_s2
            )
            rec = {f'f_{i}': feat[i] for i in range(16)}
            rec['label'] = is_match
            rec['source1_id'] = s1_id
            rec['target_id'] = tid
            data_records.append(rec)

    df = pl.DataFrame(data_records)
    os.makedirs(os.path.dirname(data_output_path), exist_ok=True)
    df.write_parquet(data_output_path)
    print(f"Dataset generated with {len(df)} records and saved to {data_output_path}")
    return df


def train_model(data_path: str = "ml/models/entity_resolution/data/train_6k.parquet",
                output_path: str = "ml/models/entity_resolution/artifacts/matching_lgb_model.pkl"):
    print("Initiating LightGBM training pipeline on feature matrix...")
    if not os.path.exists(data_path):
        df = prepare_6k_dataset(data_path)
    else:
        df = pl.read_parquet(data_path)

    X = df.select([f'f_{i}' for i in range(16)]).to_numpy()
    y = df['label'].to_numpy()

    clf = lgb.LGBMClassifier(
        n_estimators=100,
        num_leaves=31,
        learning_rate=0.05,
        random_state=42,
        verbose=-1,
        n_jobs=2
    )
    clf.fit(X, y)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        pickle.dump(clf, f)
    print(f"LightGBM artifact saved to {output_path} (trained on {len(df)} samples)")
    return clf


if __name__ == "__main__":
    train_model()
