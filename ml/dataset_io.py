"""Read-only source access and reproducible file metadata."""

from collections import defaultdict
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3

DEFAULT_DATABASE = Path('backend/data/variants.sqlite')
DEFAULT_CONFIG = Path(__file__).parent / 'config/dataset.json'


def digest(path: Path, algorithm: str = 'sha256') -> str:
    h = hashlib.new(algorithm)
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + '\n')


@contextmanager
def source_connection(path: Path):
    if Path(str(path) + '-wal').exists() and Path(str(path) + '-wal').stat().st_size:
        raise ValueError('Source has a nonempty WAL; provide a checkpointed standalone snapshot first')
    con = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA query_only=ON')
    try:
        if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('Source SQLite integrity check failed')
        yield con
    finally:
        con.close()


def load_source(path: Path, config: dict) -> tuple[dict, list[dict], dict]:
    with source_connection(path) as con:
        releases = [dict(r) for r in con.execute('SELECT * FROM source_release ORDER BY id')]
        selected = [r for r in releases if r['id'] == config['release_id']]
        if len(selected) != 1:
            raise ValueError('Configured release ID is not present; choose a release explicitly')
        release = selected[0]
        if (release['version'], release['assembly'], release['source']) != (config['release_version'], config['assembly'], 'ClinVar'):
            raise ValueError('Configured source version/assembly does not match release metadata')
        release['details'] = json.loads(release['details'])
        rows = [dict(r) for r in con.execute('''
            SELECT r.*, l.assembly, l.chromosome, l.position, l.ref, l.alt,
                   l.normalization, l.variant_id AS locus_variant_id,
                   v.clinvar_variation_id, v.clinvar_allele_id
            FROM clinvar_record r
            JOIN variant_locus l ON l.id = r.locus_id
            JOIN variant v ON v.id = r.variant_id
            WHERE r.release_id = ? ORDER BY r.id
        ''', (release['id'],))]
        expected = con.execute('SELECT count(*) FROM clinvar_record WHERE release_id=?', (release['id'],)).fetchone()[0]
        if len(rows) != expected:
            raise ValueError('Source contains orphaned records; joined row count differs')
        genes, consequences = defaultdict(list), defaultdict(list)
        for r in con.execute('SELECT g.record_id, g.gene_symbol FROM record_gene g JOIN clinvar_record r ON r.id=g.record_id WHERE r.release_id=? ORDER BY g.record_id,g.gene_symbol', (release['id'],)):
            genes[r[0]].append(r[1])
        for r in con.execute('SELECT g.record_id, g.term FROM record_consequence g JOIN clinvar_record r ON r.id=g.record_id WHERE r.release_id=? ORDER BY g.record_id,g.term', (release['id'],)):
            consequences[r[0]].append(r[1])
        condition_counts = dict(con.execute('SELECT g.record_id,count(*) FROM condition_link g JOIN clinvar_record r ON r.id=g.record_id WHERE r.release_id=? GROUP BY g.record_id', (release['id'],)))
        for row in rows:
            if row['variant_id'] != row.pop('locus_variant_id'):
                raise ValueError('Record and locus point to different variants')
            row['genes'] = genes[row['id']]
            row['consequences'] = consequences[row['id']]
            row['condition_count'] = condition_counts.get(row['id'], 0)
            row['raw_info'] = json.loads(row['raw_info'])
        # Inventory only the ClinVar database, never the application's account/history DB.
        names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        tables = {name: con.execute('SELECT count(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0] for name in names}
        return release, rows, {'tables': tables, 'releases': [{k: v for k, v in r.items() if k != 'details'} for r in releases]}
