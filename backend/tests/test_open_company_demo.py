"""Importer checks use explicit synthetic fixtures, never counterfeit fetched data."""
import sqlite3

import pytest
from infrastructure.scripts.import_open_company_demo import build_snapshot


def test_import_preserves_source_and_derives_counts_without_overwriting(tmp_path):
    data=b'Symbol,Security,GICS Sector,Headquarters Location\nAAA,Example One,Industrials,Example City\nBBB,Example Two,Technology,Other City\nCCC,Example Three,Technology,Other City\n'
    package={"licenses":[{"name":"ODC-PDDL-1.0"}]}
    destination=tmp_path/'snapshot'
    manifest=build_snapshot(data,package,destination,limit=2)
    assert (destination/'source.csv').read_bytes()==data
    assert manifest['source_rows']==3 and manifest['imported_rows']==2
    assert 'local demo' in manifest['synthetic_fields']
    with sqlite3.connect(destination/'companies.sqlite') as db:
        assert db.execute('SELECT company_name FROM companies WHERE symbol=?',('AAA',)).fetchone()[0]=='Example One'
        assert db.execute('SELECT SUM(security_count) FROM sector_counts').fetchone()[0]==2
        assert db.execute("SELECT COUNT(*) FROM companies WHERE review_state='unreviewed'").fetchone()[0]==2
    with pytest.raises(FileExistsError):
        build_snapshot(data,package,destination,limit=2)


def test_import_rejects_schema_or_license_changes_before_writing(tmp_path):
    with pytest.raises(ValueError):
        build_snapshot(b'wrong,columns\nA,B\n',{},tmp_path/'bad')
    assert not (tmp_path/'bad').exists()
