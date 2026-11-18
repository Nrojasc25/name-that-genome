"""Verify the downloaded reference archive, unpack it, and create a FASTA index."""

import argparse
from datetime import date, datetime, timezone
import gzip
import json
from pathlib import Path
import shutil

import pysam

from .dataset_io import DEFAULT_CONFIG, digest, write_json


def prepare(archive: Path, config_path: Path = DEFAULT_CONFIG, download_date: str | None = None) -> Path:
    if download_date is not None:
        date.fromisoformat(download_date)
    config = json.loads(config_path.read_text())
    spec = config['reference']
    if digest(archive, 'md5') != spec['compressed_md5']:
        raise ValueError('Downloaded reference does not match the pinned official MD5')
    fasta = archive.with_suffix('')
    manifest_path = fasta.with_suffix('.manifest.json')
    if fasta.exists() or manifest_path.exists():
        raise FileExistsError('Reference output exists; reuse it or choose a fresh directory')
    partial = fasta.with_suffix('.partial')
    with gzip.open(archive, 'rb') as src, partial.open('wb') as dst:
        shutil.copyfileobj(src, dst, 8 * 1024 * 1024)
    partial.replace(fasta)
    pysam.faidx(str(fasta))
    write_json(manifest_path, {
        'assembly': config['assembly'], 'name': spec['name'], 'source_url': spec['url'],
        'checksum_url': spec['checksum_url'], 'compressed_md5': spec['compressed_md5'],
        'compressed_sha256': digest(archive), 'fasta_sha256': digest(fasta),
        'fai_sha256': digest(Path(str(fasta) + '.fai')),
        'verified_at_utc': datetime.now(timezone.utc).isoformat(),
        'download_date': download_date, 'download_date_note': 'Transfer date supplied by the operator; verified_at_utc is preparation time.',
        'pysam_version': pysam.__version__,
    })
    return manifest_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--download-date', help='Known transfer date in YYYY-MM-DD form; omit if unknown')
    args = parser.parse_args()
    print(prepare(args.archive, args.config, args.download_date))


if __name__ == '__main__':
    main()
