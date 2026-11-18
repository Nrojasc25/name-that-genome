import unittest
from ml.protein_features import compute, CODONS, complement, choose_transcript
from ml.lock_cohort import overlaps, review_stars

class Fasta:
    def __init__(self,sequence):self.sequence=sequence
    def fetch(self,chrom,start,end):return self.sequence[start:end]


def transcript(strand='+'):
    return {'name':'NM_test','strand':strand,'txStart':0,'txEnd':9,'cdsStart':0,'cdsEnd':9,
            'cdsStartStat':'cmpl','cdsEndStat':'cmpl','exonCount':1,'exonStarts':'0,','exonEnds':'9,'}


class ProteinCohortTests(unittest.TestCase):
    def test_standard_code_and_plus_strand_substitution(self):
        self.assertEqual(CODONS['ATG'],'M');self.assertEqual(CODONS['TGA'],'*');self.assertEqual(CODONS['TGG'],'W')
        r=compute('GRCh38:1:4:G:T',[transcript()],Fasta('ATGGAATAA'))
        self.assertEqual(r['coding_snv_missing'],0)
        self.assertEqual(r['aa_ref_E'],1);self.assertEqual(r['aa_alt_*'],1)
        self.assertEqual(r['coding_stop_gain'],1)

    def test_minus_strand_and_reference_mismatch(self):
        sequence=complement('ATGGAATAA')
        r=compute('GRCh38:1:6:C:A',[transcript('-')],Fasta(sequence))
        self.assertEqual(r['aa_ref_E'],1);self.assertEqual(r['aa_alt_*'],1)
        wrong=compute('GRCh38:1:6:T:A',[transcript('-')],Fasta(sequence))
        self.assertEqual(wrong['coding_snv_missing'],1)

    def test_introns_are_removed_and_indels_marked_missing(self):
        t=transcript();t.update(txEnd=12,cdsEnd=12,exonCount=2,exonStarts='0,6,',exonEnds='3,12,')
        r=compute('GRCh38:1:7:G:T',[t],Fasta('ATGcccGAATAA'))
        self.assertEqual(r['aa_ref_E'],1);self.assertEqual(r['coding_stop_gain'],1)
        r=compute('GRCh38:1:7:GA:G',[t],Fasta('ATGcccGAATAA'))
        self.assertEqual(r['coding_snv_missing'],1)
        self.assertEqual(r['splice_context_missing'],0)

    def test_fixed_transcript_ties_ignore_clinical_metadata(self):
        a=transcript();b=transcript();a['name']='NM_a';b['name']='NM_b'
        b['clinical_significance']='pathogenic'
        self.assertEqual(choose_transcript([b,a],3)['name'],'NM_a')

    def test_overlap_half_open_and_review_codes(self):
        spans={'1':[(10,15)]}
        self.assertTrue(overlaps('1',14,17,spans))
        self.assertFalse(overlaps('1',15,17,spans))
        self.assertEqual(review_stars('criteria_provided,_multiple_submitters,_no_conflicts'),2)
        self.assertEqual(review_stars('reviewed_by_expert_panel'),3)
        self.assertEqual(review_stars('something_unknown'),0)

if __name__=='__main__':unittest.main()

class PopulationTests(unittest.TestCase):
    def test_matching_zero_missing_quality_and_leakage(self):
        from ml.population_features import extract
        record={'FILTER':'PASS','chrom':'chr1','chromStart':9,'chromEnd':10,'_startPos':10,'ref':'A','alt':'G',
                'AF':'0','AN':'100','AF_grpmax':'N/A','AN_grpmax':'0','clinical_significance':'Pathogenic','annot':'missense'}
        key,fields=extract(record,'genomes')
        self.assertEqual(key,'GRCh38:1:10:A:G')
        self.assertEqual(fields,{'gnomad4_genomes_af':0.})
        record['clinical_significance']='Benign'
        self.assertEqual(extract(record,'genomes')[1],fields)
        record['FILTER']='RF'
        self.assertIsNone(extract(record,'genomes'))
        record['FILTER']='PASS';record['_startPos']=11
        with self.assertRaises(ValueError):extract(record,'genomes')

    def test_empty_api_population_response_is_missing_not_error(self):
        import json
        import tempfile
        from pathlib import Path
        from ml.population_features import fetch
        with tempfile.TemporaryDirectory() as temporary:
            raw=Path(temporary)
            payload={'genome':'hg38','track':'gnomadGenomesVariantsV4_1','chrom':'chr1','start':9,'end':10,
                     'gnomadGenomesVariantsV4_1':[]}
            (raw/'genomes-1-9-10.json').write_text(json.dumps(payload))
            _,rows,_=fetch(('genomes','1',9,10),raw)
            self.assertEqual(rows,[])
            payload['gnomadGenomesVariantsV4_1']=[{}]
            (raw/'genomes-1-9-10.json').write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError,'Truncated'):fetch(('genomes','1',9,10),raw)
