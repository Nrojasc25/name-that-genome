"""Freeze novel same-scope ClinVar variants before further model tuning."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import argparse

import pyarrow.parquet as pq
from .dataset_io import digest, write_json
from .normalize import prepare_rows, select_rows
from .labels import CLASS_ORDER

CONFIG=Path(__file__).parent/'config/accuracy_target.json'


def review_stars(status):
    # Exact VCF codes, not a substring inference from classifications.
    if status=='practice_guideline': return 4
    if status=='reviewed_by_expert_panel': return 3
    if status=='criteria_provided,_multiple_submitters,_no_conflicts': return 2
    if status in {'criteria_provided,_single_submitter','criteria_provided,_conflicting_classifications'}: return 1
    return 0


def overlaps(chrom,start,end,spans):
    return any(start < b and end > a for a,b in spans.get(chrom,[]))


def lock(vcf,checksum,old_database,old_dataset,reference,output):
    if output.exists(): raise FileExistsError('Preserve locked evaluation cohort')
    expected=checksum.read_text().split()[0]
    h=hashlib.md5()
    with vcf.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    if h.hexdigest()!=expected: raise ValueError('NCBI checksum mismatch')
    config=json.loads(CONFIG.read_text()); genes=set(config['genes'])
    old=sqlite3.connect(old_database.resolve().as_uri()+'?mode=ro',uri=True)
    ids={str(r[0]) for r in old.execute('SELECT clinvar_variation_id FROM variant')}
    allele_ids={str(r[0]) for r in old.execute('SELECT clinvar_allele_id FROM variant')}
    spans=defaultdict(list)
    for chrom,pos,ref in old.execute("SELECT chromosome,position,ref FROM variant_locus WHERE assembly='GRCh38'"):
        spans[chrom].append((pos-1,pos-1+len(ref)))
    old.close()
    prior=pq.read_table(old_dataset/'variants.parquet',columns=['variant_key']).to_pylist()
    keys={r['variant_key'] for r in prior}
    for key in keys:
        _,chrom,pos,ref,_=key.split(':');spans[chrom].append((int(pos)-1,int(pos)-1+len(ref)))
    counts=Counter(); rows=[]; header_date=None
    with gzip.open(vcf,'rt') as stream:
        for line in stream:
            if line.startswith('##fileDate='):header_date=line.strip().split('=',1)[1]
            if line.startswith('#'):continue
            chrom,pos,identifier,ref,alt,_,_,info=line.rstrip().split('\t')[:8]
            if 'GENEINFO=' not in info:continue
            data=dict(field.split('=',1) if '=' in field else (field,'') for field in info.split(';'))
            variant_genes=[g.split(':')[0] for g in data.get('GENEINFO','').split('|')]
            if not genes.intersection(variant_genes):continue
            counts['in_scope_source_records']+=1
            if identifier in ids or data.get('ALLELEID') in allele_ids:
                counts['previous_source_identity']+=1;continue
            position=int(pos)
            if overlaps(chrom,position-1,position-1+len(ref),spans):
                counts['previous_locus_overlap']+=1;continue
            rows.append({'id':identifier,'clinvar_variation_id':int(identifier),'clinvar_allele_id':int(data['ALLELEID']),
                         'assembly':'GRCh38','chromosome':chrom,'position':position,'ref':ref,'alt':alt,
                         'variant_type':data.get('CLNVC'), 'genes':variant_genes,
                         'consequences':[x.split('|')[-1] for x in data.get('MC','').split(',') if x],
                         'germline_classification':data.get('CLNSIG'),'review_stars':review_stars(data.get('CLNREVSTAT',''))})
    if (header_date or '').replace('-','')!=config['evaluation_release'].replace('-',''):raise ValueError('Unexpected VCF release date')
    policy=json.loads((Path(__file__).parent/'config/dataset.json').read_text())
    prepared=prepare_rows(rows,reference,policy);selected,excluded,_=select_rows(prepared)
    retained=[]
    for r in selected:
        if r['normalized_key'] in keys or overlaps(r['canonical_chromosome'],r['normalized_position']-1,r['normalized_position']-1+len(r['normalized_ref']),spans):
            counts['normalized_previous_overlap']+=1;continue
        retained.append(r)
    counts.update('excluded_'+r['exclusion_reason'] for r in excluded)
    class_counts=Counter(str(r['label']) for r in retained)
    variants=[{'variant_key':r['normalized_key'],'clinvar_variation_id':r['clinvar_variation_id'],'genes':r['genes']} for r in retained]
    labels=[{'variant_key':r['normalized_key'],'label':str(r['label'])} for r in retained]
    output.mkdir(parents=True)
    write_json(output/'variants.json',variants);write_json(output/'labels.sealed.json',labels)
    manifest={'protocol':config,'protocol_sha256':digest(CONFIG),'created_at_utc':datetime.now(timezone.utc).isoformat(),
              'vcf_sha256':digest(vcf),'vcf_md5':expected,'reference_sha256':digest(reference),'old_database_sha256':digest(old_database),
              'old_dataset_manifest_sha256':digest(old_dataset/'dataset_manifest.json'),'code_sha256':digest(Path(__file__)),
              'counts':dict(counts),'reserved_variants':len(retained),'class_counts':{str(c):class_counts[str(c)] for c in CLASS_ORDER},
              'adequate_class_support':all(class_counts[str(c)]>=config['minimum_evaluation_support_each_class'] for c in CLASS_ORDER),
              'access_status':'sealed_not_scored','outputs_sha256':{p.name:digest(p) for p in output.iterdir()},
              'caution':'Sealed is a workflow convention, not encryption. Eligibility and class counts were inspected during reservation; per-variant labels must not be used for tuning.'}
    write_json(output/'cohort_manifest.json',manifest)
    print(json.dumps({k:manifest[k] for k in ['reserved_variants','class_counts','adequate_class_support','access_status']},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for n in ['vcf','checksum','old-database','old-dataset','reference','output']: parser.add_argument('--'+n,type=Path,required=True)
    args=parser.parse_args();lock(args.vcf,args.checksum,args.old_database,args.old_dataset,args.reference,args.output)
