import csv
import sqlite3

import pytest
from infrastructure.scripts.generate_synthetic_company_demo import FIELDS, generate_snapshot


def test_5k_schema_seed_and_aggregate_integrity(tmp_path):
    first=generate_snapshot(tmp_path/'first',5000,42)
    repeated=generate_snapshot(tmp_path/'repeated',5000,42)
    other=generate_snapshot(tmp_path/'other',5000,43)
    assert first['sha256']==repeated['sha256']!=other['sha256']
    assert first['dataset_kind']=='synthetic' and first['imported_rows']==5000
    with (tmp_path/'first'/'companies.csv').open(newline='',encoding='utf-8') as f:
        reader=csv.DictReader(f);assert reader.fieldnames==FIELDS
        rows=list(reader)
    assert len(rows)==5000 and len({row['symbol'] for row in rows})==5000
    assert all(row['company_name'].startswith('Synthetic ') for row in rows)
    with sqlite3.connect(tmp_path/'first'/'companies.sqlite') as db:
        assert db.execute('SELECT COUNT(*) FROM companies').fetchone()[0]==5000
        assert db.execute('SELECT SUM(security_count) FROM sector_counts').fetchone()[0]==5000
        assert db.execute('SELECT COUNT(*) FROM sector_counts').fetchone()[0]==11
    with pytest.raises(FileExistsError):
        generate_snapshot(tmp_path/'first',5000,42)
