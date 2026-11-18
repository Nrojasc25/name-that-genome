"""Freeze a training-only UCSC phyloP100way experiment; not a serving feature schema."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
from urllib.request import urlopen

import pyarrow.parquet as pq
from .dataset_io import digest, write_json

TRACK='phyloP100way'


def windows(keys):
    positions={}
    for key in keys:
        assembly,chrom,pos,ref,alt=key.split(':')
        if assembly!='GRCh38': raise ValueError('Expected GRCh38')
        if len(ref)==len(alt)==1:
            positions.setdefault(chrom,set()).add(int(pos)-1)
    ranges=[]
    for chrom,values in sorted(positions.items()):
        start=end=None
        for pos in sorted(values):
            if start is None: start=end=pos
            elif pos-end>2000 or pos-start>=20000:
                ranges.append((chrom,start,end+1)); start=end=pos
            else: end=pos
        if start is not None: ranges.append((chrom,start,end+1))
    return ranges


def feature(key, lookup):
    _,chrom,pos,ref,alt=key.split(':')
    # This experiment has a base-level SNV score only; indels remain explicitly missing.
    value=lookup.get((chrom,int(pos)-1)) if len(ref)==len(alt)==1 else None
    if value is not None and not math.isfinite(value): raise ValueError('Nonfinite conservation value')
    return {'phylop100way_snv':value,'phylop100way_snv_missing':float(value is None)}


def fetch(window, directory):
    chrom,start,end=window
    url=f'https://api.genome.ucsc.edu/getData/track?genome=hg38;track={TRACK};chrom=chr{chrom};start={start};end={end}'
    path=directory/f'{chrom}-{start}-{end}.json'
    if not path.exists():
        for attempt in range(3):
            try:
                with urlopen(url,timeout=60) as response: data=response.read()
                parsed=json.loads(data)
                if 'error' in parsed or TRACK not in parsed: raise ValueError('Invalid UCSC response')
                path.write_bytes(data)
                break
            except Exception:
                if attempt==2: raise
                time.sleep(1)
    payload=json.loads(path.read_text())
    if payload.get('genome')!='hg38' or payload.get('chrom')!='chr'+chrom or payload.get('start')!=start or payload.get('end')!=end or payload.get('track')!=TRACK:
        raise ValueError('Response region/source mismatch')
    if payload.get('maxItemsLimit') or payload.get('itemsReturned')!=len(payload[TRACK]):
        raise ValueError('Truncated source response')
    return {'url':url,'file':path.name,'sha256':digest(path),'data_time':payload.get('dataTime'),'download_time':payload.get('downloadTime')},payload


def build(splits,output):
    if (output/'conservation_manifest.json').exists(): raise FileExistsError('Completed annotation already exists')
    split_manifest=json.loads((splits/'split_manifest.json').read_text())
    if digest(splits/'membership.parquet')!=split_manifest['outputs_sha256']['membership.parquet']:
        raise ValueError('Split checksum mismatch')
    keys=sorted(r['variant_key'] for r in pq.read_table(splits/'membership.parquet').to_pylist() if r['partition']=='train')
    output.mkdir(parents=True,exist_ok=True);raw=output/'responses';raw.mkdir(exist_ok=True)
    lookup={};sources=[]
    with ThreadPoolExecutor(max_workers=2) as executor:
        for i,(source,payload) in enumerate(executor.map(lambda w:fetch(w,raw),windows(keys))):
            sources.append(source)
            chrom=payload['chrom'][3:]
            for row in payload[TRACK]:
                if row['chrom']!=payload['chrom'] or not payload['start']<=row['start']<row['end']<=payload['end']:
                    raise ValueError('Invalid source interval')
                value=float(row['value'])
                if not math.isfinite(value): raise ValueError('Nonfinite source score')
                for pos in range(row['start'],row['end']): lookup[chrom,pos]=value
            if (i+1)%10==0: print('Downloaded regions',i+1,flush=True)
    rows={key:feature(key,lookup) for key in keys}
    write_json(output/'features.json',rows)
    write_json(output/'conservation_manifest.json',{'schema':'experimental-phylop-snv-v1','partition':'train','assembly':'GRCh38',
        'track':TRACK,'source':'https://genome.ucsc.edu/goldenPath/help/api.html','retrieved_at':datetime.now(timezone.utc).isoformat(),
        'split_manifest_sha256':digest(splits/'split_manifest.json'),'features_sha256':digest(output/'features.json'),
        'code_sha256':digest(Path(__file__)),'rows':len(rows),'observed':sum(r['phylop100way_snv'] is not None for r in rows.values()),
        'semantics':'UCSC API base-level 100-way phyloP score for SNVs; GRCh38 1-based variant position converted to 0-based half-open source coordinate. Indels and absent scores are null, not zero. API track values may differ in precision from original bigWig.',
        'sources':sources})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--splits',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();build(args.splits,args.output)
