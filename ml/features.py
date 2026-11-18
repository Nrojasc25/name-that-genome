"""Label-independent, fixed-schema features shared by offline and online inference."""

import json
import math
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / 'config/features.json'
CONFIG = json.loads(CONFIG_PATH.read_text())
SCHEMA_VERSION = CONFIG['schema_version']
SUBSTITUTIONS = ('C>A', 'C>G', 'C>T', 'T>A', 'T>C', 'T>G')


def feature_dictionary() -> list[dict]:
    entries = []

    def add(name, meaning, source, units='indicator', missing='Never missing', transform='identity'):
        entries.append({'name': name, 'dtype': 'float64', 'meaning': meaning, 'source': source,
                        'units': units, 'missing_policy': missing, 'transform': transform,
                        'inference_availability': 'Computed from normalized alleles or the pinned local annotation cache.'})

    for name, meaning in [('ref_length', 'Number of reference bases including the VCF anchor'),
                          ('alt_length', 'Number of alternate bases including the VCF anchor'),
                          ('length_change', 'Alternate length minus reference length'),
                          ('absolute_length_change', 'Absolute sequence length change'),
                          ('length_change_mod3', 'Absolute length change modulo three; not a reading-frame diagnosis')]:
        add(name, meaning, 'Normalized GRCh38 alleles', 'bases')
    for kind in ['snv', 'insertion', 'deletion']:
        add('is_' + kind, 'Variant is a ' + kind, 'Normalized GRCh38 alleles')
    for substitution in SUBSTITUTIONS:
        add('substitution_' + substitution.replace('>', '_to_'), 'SNV substitution ' + substitution + ' after pyrimidine orientation; zero for indels', 'Normalized GRCh38 alleles')
    for consequence in CONFIG['consequences']:
        add('consequence_' + consequence, 'NCBI consequence includes ' + consequence, 'Frozen NCBI MC terms; union across source records')
    add('consequence_missing', 'No consequence annotations available', 'Frozen NCBI MC terms')
    add('consequence_other', 'At least one consequence term is outside the fixed vocabulary', 'Frozen NCBI MC terms')
    for field in CONFIG['frequency_fields']:
        name = field.lower()
        add(name, f'Alternate allele frequency from {field}; legacy population source, not patient risk', 'Frozen ClinVar VCF ' + field,
            'fraction [0,1]', 'Null if absent, malformed, out of range, or conflicting; zero remains observed', 'training-median imputation')
        add(name + '_missing', 'Frequency unavailable or unusable', 'Frozen ClinVar VCF ' + field)
    add('context_gc_fraction', 'GC fraction in the 21-base reference window centered on the VCF anchor', 'Pinned GRCh38 FASTA',
        'fraction [0,1]', 'Null if window crosses contig boundary or contains non-ACGT bases', 'training-median imputation')
    add('context_gc_fraction_missing', 'Reference context unavailable or ambiguous', 'Pinned GRCh38 FASTA')
    return entries


FEATURE_DICTIONARY = feature_dictionary()
FEATURE_NAMES = tuple(item['name'] for item in FEATURE_DICTIONARY)
NULLABLE_FEATURES = tuple(item['name'] for item in FEATURE_DICTIONARY if item['transform'] == 'training-median imputation')


def fraction(value, name):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f'Invalid cached fraction: {name}')
    return float(value)


def build_features(variant: dict, annotation: dict) -> dict[str, float | None]:
    """Read only allowlisted fields, ignoring targets and clinical metadata if present."""
    ref, alt = variant['ref'], variant['alt']
    if variant['assembly'] != CONFIG['assembly'] or variant['variant_key'] != annotation['variant_key']:
        raise ValueError('Variant/reference identity mismatch')
    if type(variant['position']) is not int or variant['position'] < 1:
        raise ValueError('Invalid normalized position')
    expected = f"{variant['assembly']}:{variant['chromosome']}:{variant['position']}:{ref}:{alt}"
    if expected != variant['variant_key']:
        raise ValueError('Variant key and normalized allele disagree')
    if not ref or not alt or set(ref + alt) - set('ACGT') or ref == alt:
        raise ValueError('Expected normalized sequence-resolved alleles')
    delta = len(alt) - len(ref)
    kind = 'snv' if len(ref) == len(alt) == 1 else 'insertion' if delta > 0 else 'deletion'
    if kind != 'snv' and (min(len(ref), len(alt)) != 1 or not 1 <= abs(delta) <= 49
                           or not (ref[0] == alt[0] or (variant['position'] == 1 and ref[-1] == alt[-1]))):
        raise ValueError('Unsupported sequence change')
    result = dict.fromkeys(FEATURE_NAMES, 0.0)
    result.update(ref_length=float(len(ref)), alt_length=float(len(alt)), length_change=float(delta),
                  absolute_length_change=float(abs(delta)), length_change_mod3=float(abs(delta) % 3))
    result['is_' + kind] = 1.0
    if kind == 'snv':
        if ref in 'AG':
            complement = str.maketrans('ACGT', 'TGCA')
            ref, alt = ref.translate(complement), alt.translate(complement)
        result[f'substitution_{ref}_to_{alt}'] = 1.0
    terms = annotation['consequences']
    if not isinstance(terms, list) or any(not isinstance(term, str) for term in terms):
        raise ValueError('Consequences must be a list of terms')
    terms = set(terms)
    for term in CONFIG['consequences']:
        result['consequence_' + term] = float(term in terms)
    result['consequence_missing'] = float(not terms)
    result['consequence_other'] = float(bool(terms - set(CONFIG['consequences'])))
    for field in CONFIG['frequency_fields']:
        name = field.lower()
        value = fraction(annotation['frequencies'][field], field)
        result[name], result[name + '_missing'] = value, float(value is None)
    value = fraction(annotation['context_gc_fraction'], 'context_gc_fraction')
    result['context_gc_fraction'], result['context_gc_fraction_missing'] = value, float(value is None)
    return result
