"""Freeze gnomAD v4.1.1 SNV frequencies; absence never implies a measured zero."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import argparse
import json
import math
from pathlib import Path
import time
from urllib.request import urlopen

import pyarrow.parquet as pq
from .conservation import windows
from .dataset_io import digest, write_json

TRACKS={'genomes':'gnomadGenomesVariantsV4_1','exomes':'gnomadExomesVariantsV4_1'}
FIELDS=['gnomad4_'+kind+'_'+field for kind in TRACKS for field in ['af','grpmax_af']]
NAMES=[n for field in FIELDS for n in [field,field+'_missing']]


def extract(record,kind):
    if record.get('FILTER')!='PASS':return None
    ref,alt=record.get('ref',''),record.get('alt','')
    if len(ref)!=1 or len(alt)!=1 or set(ref+alt)-set('ACGT'):return None
    pos=record['_startPos']
    if int(pos)!=int(record['chromStart'])+1 or int(record['chromEnd'])!=int(record['chromStart'])+1:
        raise ValueError('SNV coordinate disagreement')
    key=f"GRCh38:{record['chrom'].removeprefix('chr')}:{pos}:{ref}:{alt}"
    result={}
    for source,name,denominator in [('AF','af','AN'),('AF_grpmax','grpmax_af','AN_grpmax')]:
        try:value=float(record[source]);an=float(record[denominator])
        except (ValueError,KeyError,TypeError):continue
        if math.isfinite(value) and math.isfinite(an) and 0<=value<=1 and an>0:
            result['gnomad4_'+kind+'_'+name]=value
    return key,result


def fetch(task,raw):
    kind,chrom,start,end=task;track=TRACKS[kind]
    path=raw/f'{kind}-{chrom}-{start}-{end}.json'
    url=f'https://api.genome.ucsc.edu/getData/track?genome=hg38;track={track};chrom=chr{chrom};start={start};end={end}'
    if not path.exists():
        for attempt in range(3):
            try:
                with urlopen(url,timeout=60) as response:data=response.read()
                payload=json.loads(data)
                if track not in payload:raise ValueError('Invalid gnomAD response')
                path.write_bytes(data);break
            except Exception:
                if attempt==2:raise
                time.sleep(1)
    p=json.loads(path.read_text())
    if p.get('genome')!='hg38' or p.get('track')!=track or p.get('chrom')!='chr'+chrom or p.get('start')!=start or p.get('end')!=end:
        raise ValueError('Wrong population source interval')
    if p.get('maxItemsLimit') or p.get('itemsReturned',0 if not p[track] else -1)!=len(p[track]):raise ValueError('Truncated frequency response')
    return kind,p[track],{'url':url,'file':path.name,'sha256':digest(path),'big_data_url':p.get('bigDataUrl'),'download_time':p.get('downloadTime')}


def build(splits,output):
    if (output/'population_manifest.json').exists():raise FileExistsError('Preserve completed population annotation')
    manifest=json.loads((splits/'split_manifest.json').read_text())
    if digest(splits/'membership.parquet')!=manifest['outputs_sha256']['membership.parquet']:raise ValueError('Split checksum mismatch')
    keys=sorted(r['variant_key'] for r in pq.read_table(splits/'membership.parquet').to_pylist() if r['partition']=='train')
    lookup={k:{} for k in keys};sources=[];conflicts=set()
    output.mkdir(parents=True,exist_ok=True);raw=output/'responses';raw.mkdir(exist_ok=True)
    tasks=[(kind,*window) for kind in TRACKS for window in windows(keys)]
    with ThreadPoolExecutor(max_workers=2) as executor:
        for i,(kind,records,source) in enumerate(executor.map(lambda task:fetch(task,raw),tasks)):
            sources.append(source)
            for record in records:
                extracted=extract(record,kind)
                if extracted is None:continue
                key,values=extracted
                if key not in lookup:continue
                for field,value in values.items():
                    if field in lookup[key] and lookup[key][field]!=value:conflicts.add((key,field))
                    lookup[key][field]=value
            if (i+1)%20==0:print('Population regions',i+1,'/',len(tasks),flush=True)
    rows={}
    for key,values in lookup.items():
        row={}
        for field in FIELDS:
            value=values.get(field) if (key,field) not in conflicts else None
            row[field]=value if value is not None else 0.
            row[field+'_missing']=float(value is None)
        rows[key]=row
    write_json(output/'features.json',rows)
    write_json(output/'population_manifest.json',{'schema':'experimental-gnomad411-snv-v1','partition':'train','feature_names':NAMES,
        'split_manifest_sha256':digest(splits/'split_manifest.json'),'features_sha256':digest(output/'features.json'),
        'created_at_utc':datetime.now(timezone.utc).isoformat(),'code_sha256':digest(Path(__file__)),'sources':sources,'rows':len(keys),
        'observed':{n:sum(r[n+'_missing']==0 for r in rows.values()) for n in FIELDS},'conflicting_values':len(conflicts),
        'semantics':'Only exact GRCh38 SNV allele matches with PASS and positive allele-number denominator. Overall AF and ancestry-group maximum AF for genomes/exomes; no clinical labels or pathogenicity scores. Missing/unmatched/indel values use numeric zero plus missing=1; measured zero has missing=0. Original source responses retain full precision and provenance.'})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--splits',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();build(a.splits,a.output)
