"""Reference-backed tests use tiny synthetic FASTA/SQLite inputs, never account data."""

import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import pyarrow.parquet as pq
import pysam

from ml.build_dataset import build
from ml.dataset_io import DEFAULT_CONFIG, digest, load_source, source_connection, write_json
from ml.normalize import chromosome_alias, prepare_rows, select_rows


class DatasetTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fasta = self.root / 'reference.fa'
        self.fasta.write_text('>chr1\nCAAAAAGTCG' + 'A' * 100 + '\n')
        pysam.faidx(str(self.fasta))
        self.config = json.loads(DEFAULT_CONFIG.read_text())
        self.config.pop('source_database_sha256', None)
        self.config['release_id'] = 'release-one'
        self.config['minimum_examples_per_class'] = 1
        self.config_path = self.root / 'config.json'
        write_json(self.config_path, self.config)
        self.reference_manifest = self.root / 'reference.json'
        write_json(self.reference_manifest, {
            'assembly': 'GRCh38', 'source_url': self.config['reference']['url'],
            'compressed_md5': self.config['reference']['compressed_md5'],
            'fasta_sha256': digest(self.fasta), 'fai_sha256': digest(Path(str(self.fasta) + '.fai')),
        })

    def row(self, identifier='one', **overrides):
        row = dict(id=identifier, release_id='release-one', variant_id=identifier, locus_id=identifier,
                   chromosome='1', assembly='GRCh38', position=7, ref='G', alt='T',
                   variant_type='single_nucleotide_variant', germline_classification='Benign',
                   review_stars=1, review_status='criteria_provided,_single_submitter',
                   clinvar_variation_id=1, clinvar_allele_id=2, genes=['TEST'], consequences=['missense_variant'],
                   condition_count=0, raw_info={}, raw_vcf_line='', normalization='source_vcf', origin='1')
        row.update(overrides)
        return row

    def prepared(self, *rows):
        return prepare_rows(list(rows), self.fasta, self.config)

    def test_primary_aliases_only(self):
        self.assertEqual(chromosome_alias('chr1'), '1')
        self.assertEqual(chromosome_alias('chrM'), 'MT')
        self.assertIsNone(chromosome_alias('NC_000001.11'))
        self.assertIsNone(chromosome_alias('chr1_alt'))

    def test_snv_and_indel_left_alignment(self):
        rows = self.prepared(self.row(), self.row('insertion', position=4, ref='A', alt='AA', variant_type='Insertion'))
        self.assertEqual(rows[0]['normalized_key'], 'GRCh38:1:7:G:T')
        self.assertEqual(rows[1]['normalized_key'], 'GRCh38:1:1:C:CA')
        self.assertTrue(rows[1]['normalized_changed'])
        self.assertEqual(rows[1]['normalized_type'], 'insertion')

    def test_equivalent_indels_deduplicate_preserving_ids(self):
        rows = self.prepared(self.row('a', position=3, ref='AA', alt='A', variant_type='Deletion', clinvar_variation_id=3),
                             self.row('b', position=5, ref='AA', alt='A', variant_type='Deletion', review_stars=2, clinvar_variation_id=4))
        selected, excluded, stats = select_rows(rows)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['id'], 'b')
        self.assertEqual(selected[0]['clinvar_variation_ids'], [3, 4])
        self.assertEqual(excluded[0]['exclusion_reason'], 'duplicate_same_label')
        self.assertEqual(stats['duplicate_groups'], 1)

    def test_duplicate_label_disagreements_quarantine_all(self):
        selected, excluded, _ = select_rows(self.prepared(self.row('a'), self.row('b', germline_classification='Pathogenic')))
        self.assertFalse(selected)
        self.assertEqual([r['exclusion_reason'] for r in excluded], ['duplicate_label_disagreement'] * 2)

    def test_ineligible_conflicting_duplicate_also_quarantines(self):
        selected, excluded, _ = select_rows(self.prepared(self.row('a'), self.row('b', germline_classification='Conflicting_classifications_of_pathogenicity')))
        self.assertFalse(selected)
        self.assertEqual(len(excluded), 2)

    def test_reference_failures_never_get_corrected(self):
        for changes, reason in [({'ref': 'A'}, 'reference_mismatch'), ({'position': 1000}, 'reference_out_of_bounds'), ({'chromosome': '2'}, 'reference_contig_missing')]:
            with self.subTest(changes=changes):
                row = self.prepared(self.row(**changes))[0]
                self.assertEqual(row['reference_reason'], reason)
                self.assertIsNone(row['normalized_key'])
                self.assertEqual(select_rows([row])[1][0]['exclusion_reason'], reason)

    def test_unsupported_sequence_reasons(self):
        cases = [({'alt': 'A,C'}, 'multiallelic_record'), ({'alt': '<DEL>'}, 'symbolic_or_ambiguous_allele'),
                 ({'ref': 'N'}, 'symbolic_or_ambiguous_allele'), ({'alt': 'G'}, 'no_sequence_change'),
                 ({'assembly': 'GRCh37'}, 'unsupported_assembly'), ({'variant_type': 'Inversion'}, 'unsupported_variant_type'),
                 ({'position': 0}, 'invalid_position'), ({'chromosome': 'chrUn'}, 'unsupported_chromosome'),
                 ({'position': 7, 'ref': 'GT', 'alt': 'AC', 'variant_type': 'Indel'}, 'complex_sequence_change'),
                 ({'position': 10, 'ref': 'G', 'alt': 'G' + 'A' * 50, 'variant_type': 'Insertion'}, 'indel_exceeds_max_length')]
        for changes, reason in cases:
            with self.subTest(changes=changes):
                row = self.prepared(self.row(**changes))[0]
                self.assertEqual(row['sequence_reason'], reason)
                self.assertFalse(select_rows([row])[0])

    def make_database(self):
        path = self.root / 'source.sqlite'
        with sqlite3.connect(path) as c:
            c.executescript('''
              CREATE TABLE source_release(id TEXT,source TEXT,version TEXT,assembly TEXT,source_url TEXT,sha256 TEXT,details TEXT,imported_at TEXT);
              CREATE TABLE variant(id TEXT,clinvar_variation_id INTEGER,clinvar_allele_id INTEGER);
              CREATE TABLE variant_locus(id TEXT,variant_id TEXT,assembly TEXT,chromosome TEXT,position INTEGER,ref TEXT,alt TEXT,normalization TEXT);
              CREATE TABLE clinvar_record(id TEXT,release_id TEXT,variant_id TEXT,locus_id TEXT,germline_classification TEXT,review_stars INTEGER,review_status TEXT,variant_type TEXT,raw_info TEXT);
              CREATE TABLE record_gene(record_id TEXT,gene_symbol TEXT);
              CREATE TABLE record_consequence(record_id TEXT,term TEXT);
              CREATE TABLE condition_link(record_id TEXT,name TEXT);
            ''')
            c.execute('INSERT INTO source_release VALUES(?,?,?,?,?,?,?,?)', ('release-one','ClinVar',self.config['release_version'],'GRCh38','https://example.test/source','unverified',json.dumps({'imported_genes':['TEST']}),'2026-01-01'))
            for i, label in enumerate(['Benign','Likely_benign','Uncertain_significance','Likely_pathogenic','Pathogenic']):
                ident = str(i)
                c.execute('INSERT INTO variant VALUES(?,?,?)', (ident,i+1,i+101))
                c.execute('INSERT INTO variant_locus VALUES(?,?,?,?,?,?,?,?)',(ident,ident,'GRCh38','1',i+2,'A','T','source_vcf'))
                c.execute('INSERT INTO clinvar_record VALUES(?,?,?,?,?,?,?,?,?)',(ident,'release-one',ident,ident,label,1,'criteria_provided','single_nucleotide_variant','{}'))
                c.execute('INSERT INTO record_gene VALUES(?,?)',(ident,'TEST'))
        return path

    def test_database_is_read_only_and_release_is_explicit(self):
        path = self.make_database()
        before = digest(path)
        release, rows, _ = load_source(path, self.config)
        self.assertEqual(len(rows), 5)
        with source_connection(path) as con, self.assertRaises(sqlite3.OperationalError):
            con.execute('DELETE FROM variant')
        bad = copy.deepcopy(self.config); bad['release_id'] = 'not-present'
        with self.assertRaises(ValueError):
            load_source(path, bad)
        self.assertEqual(before, digest(path))

    def test_full_build_is_deterministic_and_has_typed_empty_exclusions(self):
        database = self.make_database()
        manifests = []
        for suffix in ['first', 'second']:
            output = self.root / suffix
            manifests.append(build(database, self.fasta, self.reference_manifest, output, self.config_path))
            self.assertEqual(pq.read_table(output / 'variants.parquet').num_rows, 5)
            rejected = pq.read_table(output / 'exclusions.parquet')
            self.assertEqual(rejected.num_rows, 0)
            self.assertIn('exclusion_reason', rejected.column_names)
            self.assertEqual(pq.read_table(output / 'source_membership.parquet').num_rows, 5)
            self.assertEqual(manifests[-1]['build_status'], 'ready_for_feature_development')
        self.assertEqual(manifests[0]['outputs_sha256'], manifests[1]['outputs_sha256'])
        with self.assertRaises(FileExistsError):
            build(database, self.fasta, self.reference_manifest, self.root / 'first', self.config_path)

    def test_modified_reference_or_snapshot_is_rejected(self):
        database = self.make_database()
        bad = json.loads(self.config_path.read_text()); bad['source_database_sha256'] = 'wrong'
        write_json(self.config_path, bad)
        with self.assertRaisesRegex(ValueError, 'snapshot checksum'):
            build(database, self.fasta, self.reference_manifest, self.root / 'bad', self.config_path)
        self.fasta.write_text(self.fasta.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'Reference checksum'):
            build(database, self.fasta, self.reference_manifest, self.root / 'bad', self.config_path)

    def test_empty_candidate_set_is_auditable(self):
        selected, excluded, stats = select_rows(self.prepared(self.row(alt='<DEL>')))
        self.assertEqual(selected, [])
        self.assertEqual(len(excluded), 1)
        self.assertEqual(stats['normalized_unique_keys'], 0)


if __name__ == '__main__':
    unittest.main()
