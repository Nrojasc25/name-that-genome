"""Validate REF against FASTA, then normalize with the pinned bcftools implementation."""

from collections import defaultdict
from pathlib import Path
import re
import tempfile

import pysam
import pysam.bcftools

from .labels import classify_label, normalize_label

NORMALIZER_VERSION = 'bcftools 1.23.1 via pysam 0.24.0'
PRIMARY_CHROMOSOMES = {str(i) for i in range(1, 23)} | {'X', 'Y', 'MT'}


def chromosome_alias(chromosome: str) -> str | None:
    value = chromosome.removeprefix('chr')
    if value == 'M':
        value = 'MT'
    return value if value in PRIMARY_CHROMOSOMES else None


def prepare_rows(rows: list[dict], fasta_path: Path, config: dict) -> list[dict]:
    """Annotate each row with stage outcomes; never change the source database."""
    if pysam.__version__ != '0.24.0' or pysam.__samtools_version__ != '1.23.1':
        raise ValueError('Use pinned ml/requirements.txt; changing the normalizer requires a new build version')
    prepared = []
    with pysam.FastaFile(str(fasta_path)) as fasta:
        contigs = set(fasta.references)
        for original in rows:
            row = dict(original)
            result = classify_label(row['germline_classification'], row['review_stars'])
            row.update(label=result.label, class_id=result.class_id, label_reason=result.exclusion_reason,
                       sequence_reason=None, reference_reason=None, normalized_key=None,
                       normalized_changed=False, normalized_ref=None, normalized_alt=None, normalized_position=None)
            chrom = chromosome_alias(row['chromosome'])
            row['canonical_chromosome'] = chrom
            if row['assembly'] != config['assembly']:
                row['sequence_reason'] = 'unsupported_assembly'
            elif chrom is None:
                row['sequence_reason'] = 'unsupported_chromosome'
            elif row['variant_type'] not in config['allowed_source_types']:
                row['sequence_reason'] = 'unsupported_variant_type'
            elif not isinstance(row['ref'], str) or not isinstance(row['alt'], str):
                row['sequence_reason'] = 'missing_allele'
            elif ',' in row['alt']:
                row['sequence_reason'] = 'multiallelic_record'
            elif not re.fullmatch('[ACGT]+', row['ref'], re.I) or not re.fullmatch('[ACGT]+', row['alt'], re.I):
                row['sequence_reason'] = 'symbolic_or_ambiguous_allele'
            elif row['ref'].upper() == row['alt'].upper():
                row['sequence_reason'] = 'no_sequence_change'
            elif type(row['position']) is not int or row['position'] < 1:
                row['sequence_reason'] = 'invalid_position'
            if row['sequence_reason'] is None:
                # Explicit primary-chromosome aliases only; never guess assembly or RefSeq accessions.
                aliases = [chrom, 'chrM' if chrom == 'MT' else 'chr' + chrom]
                row['fasta_contig'] = next((x for x in aliases if x in contigs), None)
                if row['fasta_contig'] is None:
                    row['reference_reason'] = 'reference_contig_missing'
                else:
                    end = row['position'] - 1 + len(row['ref'])
                    if end > fasta.get_reference_length(row['fasta_contig']):
                        row['reference_reason'] = 'reference_out_of_bounds'
                    elif fasta.fetch(row['fasta_contig'], row['position'] - 1, end).upper() != row['ref'].upper():
                        row['reference_reason'] = 'reference_mismatch'
            prepared.append(row)
        candidates = [r for r in prepared if not r['sequence_reason'] and not r['reference_reason']]
        if not candidates:
            return prepared
        with tempfile.TemporaryDirectory(prefix='ntg-normalize-') as directory:
            source = Path(directory) / 'input.vcf'
            output = Path(directory) / 'normalized.vcf'
            with source.open('w') as stream:
                stream.write('##fileformat=VCFv4.2\n')
                for chrom in sorted({r['fasta_contig'] for r in candidates}):
                    stream.write(f'##contig=<ID={chrom},length={fasta.get_reference_length(chrom)}>\n')
                stream.write('#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n')
                for i, row in enumerate(candidates):
                    stream.write(f"{row['fasta_contig']}\t{row['position']}\trow{i}\t{row['ref'].upper()}\t{row['alt'].upper()}\t.\t.\t.\n")
            # REF is checked before and during normalization; never fix a mismatch by swapping alleles.
            pysam.bcftools.norm('-f', str(fasta_path), '-c', 'e', '--no-version', '-Ov', '-o', str(output), str(source), catch_stdout=False)
            seen = set()
            with pysam.VariantFile(str(output)) as normalized:
                for variant in normalized:
                    i = int(variant.id.removeprefix('row'))
                    if i in seen or not 0 <= i < len(candidates) or len(variant.alts or ()) != 1:
                        raise ValueError('Normalizer changed record cardinality')
                    seen.add(i)
                    row = candidates[i]
                    ref, alt, pos = variant.ref, variant.alts[0], variant.pos
                    if fasta.fetch(variant.contig, pos - 1, pos - 1 + len(ref)).upper() != ref:
                        raise ValueError('Normalized REF does not match reference')
                    row.update(normalized_position=pos, normalized_ref=ref, normalized_alt=alt,
                               normalized_key=f"{config['assembly']}:{row['canonical_chromosome']}:{pos}:{ref}:{alt}",
                               normalized_changed=(pos, ref, alt) != (row['position'], row['ref'].upper(), row['alt'].upper()))
                    if len(ref) == len(alt) == 1:
                        row['normalized_type'] = 'snv'
                    elif min(len(ref), len(alt)) == 1 and (ref[0] == alt[0] or (pos == 1 and ref[-1] == alt[-1])):
                        row['normalized_type'] = 'insertion' if len(alt) > len(ref) else 'deletion'
                        if abs(len(ref) - len(alt)) > config['max_indel_length']:
                            row['sequence_reason'] = 'indel_exceeds_max_length'
                    else:
                        row['sequence_reason'] = 'complex_sequence_change'
            if len(seen) != len(candidates):
                raise ValueError('Normalizer lost records')
    return prepared


def select_rows(rows: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """Quarantine normalized label disagreements, retain one deterministic row per key."""
    groups = defaultdict(list)
    for row in rows:
        if row['normalized_key']:
            groups[row['normalized_key']].append(row)
    conflicts = {key for key, group in groups.items()
                 if len({normalize_label(r['germline_classification'] or '') for r in group}) > 1}
    eligible = defaultdict(list)
    excluded = []
    for row in rows:
        reason = row['label_reason'] or row['sequence_reason'] or row['reference_reason']
        if row['normalized_key'] in conflicts:
            reason = 'duplicate_label_disagreement'
        if reason:
            excluded.append({**row, 'exclusion_reason': reason})
        else:
            if not row['normalized_key']:
                raise ValueError('Eligible record has not been normalized')
            eligible[row['normalized_key']].append(row)
    selected = []
    for key in sorted(eligible):
        group = sorted(eligible[key], key=lambda r: (-r['review_stars'], r['clinvar_variation_id'] or 0, r['id']))
        winner = dict(group[0])
        winner['source_record_ids'] = sorted(r['id'] for r in groups[key])
        winner['clinvar_variation_ids'] = sorted({r['clinvar_variation_id'] for r in groups[key] if r['clinvar_variation_id'] is not None})
        winner['clinvar_allele_ids'] = sorted({r['clinvar_allele_id'] for r in groups[key] if r['clinvar_allele_id'] is not None})
        winner['genes'] = sorted({g for r in group for g in r['genes']})
        winner['consequences'] = sorted({g for r in group for g in r['consequences']})
        selected.append(winner)
        excluded.extend({**r, 'exclusion_reason': 'duplicate_same_label'} for r in group[1:])
    assert len(selected) + len(excluded) == len(rows)
    assert len({r['normalized_key'] for r in selected}) == len(selected)
    return selected, sorted(excluded, key=lambda r: r['id']), {
        'normalized_unique_keys': len(groups), 'duplicate_groups': sum(len(g) > 1 for g in groups.values()),
        'label_disagreement_groups': len(conflicts),
        'normalized_changed_records': sum(r['normalized_changed'] for r in rows),
    }
