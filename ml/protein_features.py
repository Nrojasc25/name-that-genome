"""Experimental label-independent RefSeq coding and splice-context features."""
from datetime import datetime, timezone
import itertools
import json
from pathlib import Path
from urllib.request import urlopen
import argparse

import pyarrow.parquet as pq
import pysam

from .dataset_io import digest, write_json

BASES='TCAG'
AMINO='FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG'
CODONS=dict(zip((''.join(c) for c in itertools.product(BASES,repeat=3)),AMINO,strict=True))
AA='ACDEFGHIKLMNPQRSTVWY*'
NAMES=['transcript_missing','coding_snv_missing','coding_fraction','splice_distance_log1p','splice_context_missing','coding_synonymous','coding_stop_gain','coding_stop_loss']+[f'aa_ref_{a}' for a in AA]+[f'aa_alt_{a}' for a in AA]


def complement(sequence):return sequence.translate(str.maketrans('ACGT','TGCA'))[::-1]


def exons(transcript):
    starts=[int(x) for x in transcript['exonStarts'].rstrip(',').split(',')]
    ends=[int(x) for x in transcript['exonEnds'].rstrip(',').split(',')]
    if len(starts)!=len(ends) or len(starts)!=transcript['exonCount'] or any(a>=b for a,b in zip(starts,ends)):
        raise ValueError('Invalid exon coordinates')
    if any(ends[i]>starts[i+1] for i in range(len(starts)-1)):raise ValueError('Overlapping/unsorted exons')
    return list(zip(starts,ends))


def coding_segments(t):
    return [(max(a,t['cdsStart']),min(b,t['cdsEnd'])) for a,b in exons(t) if max(a,t['cdsStart'])<min(b,t['cdsEnd'])]


def choose_transcript(transcripts,pos):
    candidates=[t for t in transcripts if t['name'].startswith('NM_') and t['txStart']<=pos<t['txEnd'] and t['cdsStartStat']=='cmpl' and t['cdsEndStat']=='cmpl']
    # No gene IDs, clinical labels, or annotation severity influence this fixed policy.
    return min(candidates,key=lambda t:(-sum(b-a for a,b in coding_segments(t)),t['name'])) if candidates else None


def compute(key,transcripts,fasta):
    _,chrom,position,ref,alt=key.split(':'); pos=int(position)-1
    result=dict.fromkeys(NAMES,0.0);result.update(transcript_missing=1.,coding_snv_missing=1.,splice_context_missing=1.)
    t=choose_transcript(transcripts,pos)
    if t is None:return result
    result['transcript_missing']=0.
    boundaries=[coordinate for a,b in exons(t) for coordinate in (a,b) if coordinate not in (t['txStart'],t['txEnd'])]
    if boundaries:
        import math
        result['splice_distance_log1p']=math.log1p(min(abs(pos-boundary) for boundary in boundaries))
        result['splice_context_missing']=0.
    segments=coding_segments(t)
    if len(ref)!=1 or len(alt)!=1 or not any(a<=pos<b for a,b in segments):return result
    sequence=''.join(fasta.fetch('chr'+chrom,a,b).upper() for a,b in segments)
    offset=sum(max(0,min(pos,b)-a) for a,b in segments if a<=pos)
    oriented_ref,oriented_alt=ref,alt
    if t['strand']=='-':
        sequence=complement(sequence);offset=len(sequence)-1-offset
        oriented_ref,oriented_alt=complement(ref),complement(alt)
    elif t['strand']!='+':raise ValueError('Invalid strand')
    if not sequence or len(sequence)%3 or sequence[offset]!=oriented_ref:
        return result  # Explicit missing for unsuitable complete-CDS annotation/reference.
    start=offset-offset%3;codon=sequence[start:start+3]
    if codon not in CODONS:return result
    changed=codon[:offset%3]+oriented_alt+codon[offset%3+1:]
    if changed not in CODONS:return result
    before,after=CODONS[codon],CODONS[changed]
    result.update(coding_snv_missing=0.,coding_fraction=offset/max(1,len(sequence)-1),coding_synonymous=float(before==after),
                  coding_stop_gain=float(before!='*' and after=='*'),coding_stop_loss=float(before=='*' and after!='*'))
    result['aa_ref_'+before]=1.;result['aa_alt_'+after]=1.
    return result


def build(splits,reference,output):
    if (output/'protein_manifest.json').exists():raise FileExistsError('Preserve completed annotation')
    manifest=json.loads((splits/'split_manifest.json').read_text())
    if digest(splits/'membership.parquet')!=manifest['outputs_sha256']['membership.parquet']:raise ValueError('Split checksum mismatch')
    keys=sorted(r['variant_key'] for r in pq.read_table(splits/'membership.parquet').to_pylist() if r['partition']=='train')
    ranges={}
    for key in keys:
        _,chrom,pos,*_=key.split(':');p=int(pos)-1
        a,b=ranges.get(chrom,(p,p+1));ranges[chrom]=(min(a,p),max(b,p+1))
    output.mkdir(parents=True,exist_ok=True);raw=output/'responses';raw.mkdir(exist_ok=True)
    sources=[];transcripts={}
    for chrom,(start,end) in sorted(ranges.items()):
        path=raw/(chrom+'.json')
        url=f'https://api.genome.ucsc.edu/getData/track?genome=hg38;track=ncbiRefSeqCurated;chrom=chr{chrom};start={start};end={end}'
        if not path.exists():
            with urlopen(url,timeout=60) as response:data=response.read()
            payload=json.loads(data)
            if 'ncbiRefSeqCurated' not in payload:raise ValueError('Invalid source response')
            path.write_bytes(data)
        payload=json.loads(path.read_text())
        if payload['genome']!='hg38' or payload['chrom']!='chr'+chrom or payload['start']!=start or payload['end']!=end or payload.get('maxItemsLimit'):
            raise ValueError('Source interval mismatch/truncation')
        transcripts[chrom]=payload['ncbiRefSeqCurated']
        if payload['itemsReturned']!=len(transcripts[chrom]):raise ValueError('Truncated response')
        for t in transcripts[chrom]:
            if t['chrom']!=payload['chrom']:raise ValueError('Transcript chromosome mismatch')
            exons(t)
        sources.append({'url':url,'sha256':digest(path),'data_time':payload.get('dataTime'),'file':path.name})
        print('Transcript chromosome',chrom,'rows',len(transcripts[chrom]),flush=True)
    with pysam.FastaFile(str(reference)) as fasta:
        rows={key:compute(key,transcripts[key.split(':')[1]],fasta) for key in keys}
    write_json(output/'features.json',rows)
    write_json(output/'protein_manifest.json',{'schema':'experimental-refseq-protein-v1','partition':'train','feature_names':NAMES,'rows':len(rows),
        'coding_snv_observed':sum(r['coding_snv_missing']==0 for r in rows.values()),'transcript_observed':sum(r['transcript_missing']==0 for r in rows.values()),
        'split_manifest_sha256':digest(splits/'split_manifest.json'),'reference_sha256':digest(reference),'features_sha256':digest(output/'features.json'),
        'created_at_utc':datetime.now(timezone.utc).isoformat(),'code_sha256':digest(Path(__file__)),'sources':sources,
        'transcript_policy':'Overlapping complete-CDS NM_ transcript with longest spliced CDS, ties by accession. Not MANE canonical. No clinical classification or consequence-severity selection.',
        'limitations':'No domains or modern population annotations. Protein substitution features apply only to reference-matching coding SNVs with a complete translatable CDS; other variants retain missing indicators. Splice distance is a geometric distance to internal exon boundaries, not a splice-effect prediction.'})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['splits','reference','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();build(a.splits,a.reference,a.output)
