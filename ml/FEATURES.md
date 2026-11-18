# Feature dictionary

Schema 1.0.0. Ordered numeric columns; targets and identifiers are not features.

All features are float64. Inference uses the same normalized alleles and pinned annotation cache as batch preparation. The table order is the saved matrix column order.

| Feature | Meaning | Source | Units | Missing policy / transform |
|---|---|---|---|---|
| `ref_length` | Number of reference bases including the VCF anchor | Normalized GRCh38 alleles | bases | Never missing; identity |
| `alt_length` | Number of alternate bases including the VCF anchor | Normalized GRCh38 alleles | bases | Never missing; identity |
| `length_change` | Alternate length minus reference length | Normalized GRCh38 alleles | bases | Never missing; identity |
| `absolute_length_change` | Absolute sequence length change | Normalized GRCh38 alleles | bases | Never missing; identity |
| `length_change_mod3` | Absolute length change modulo three; not a reading-frame diagnosis | Normalized GRCh38 alleles | bases | Never missing; identity |
| `is_snv` | Variant is a snv | Normalized GRCh38 alleles | indicator | Never missing; identity |
| `is_insertion` | Variant is a insertion | Normalized GRCh38 alleles | indicator | Never missing; identity |
| `is_deletion` | Variant is a deletion | Normalized GRCh38 alleles | indicator | Never missing; identity |
| `substitution_C_to_A` | SNV substitution C>A after pyrimidine orientation; zero for indels | Normalized GRCh38 alleles | indicator | Never missing; identity |
| `substitution_C_to_G` | SNV substitution C>G after pyrimidine orientation; zero for indels | Normalized GRCh38 alleles | indicator | Never missing; identity |
| `substitution_C_to_T` | SNV substitution C>T after pyrimidine orientation; zero for indels | Normalized GRCh38 alleles | indicator | Never missing; identity |
| `substitution_T_to_A` | SNV substitution T>A after pyrimidine orientation; zero for indels | Normalized GRCh38 alleles | indicator | Never missing; identity |
| `substitution_T_to_C` | SNV substitution T>C after pyrimidine orientation; zero for indels | Normalized GRCh38 alleles | indicator | Never missing; identity |
| `substitution_T_to_G` | SNV substitution T>G after pyrimidine orientation; zero for indels | Normalized GRCh38 alleles | indicator | Never missing; identity |
| `consequence_3_prime_UTR_variant` | NCBI consequence includes 3_prime_UTR_variant | Frozen NCBI MC terms; union across source records | indicator | Never missing; identity |
| `consequence_5_prime_UTR_variant` | NCBI consequence includes 5_prime_UTR_variant | Frozen NCBI MC terms; union across source records | indicator | Never missing; identity |
| `consequence_frameshift_variant` | NCBI consequence includes frameshift_variant | Frozen NCBI MC terms; union across source records | indicator | Never missing; identity |
| `consequence_genic_downstream_transcript_variant` | NCBI consequence includes genic_downstream_transcript_variant | Frozen NCBI MC terms; union across source records | indicator | Never missing; identity |
| `consequence_genic_upstream_transcript_variant` | NCBI consequence includes genic_upstream_transcript_variant | Frozen NCBI MC terms; union across source records | indicator | Never missing; identity |
| `consequence_inframe_deletion` | NCBI consequence includes inframe_deletion | Frozen NCBI MC terms; union across source records | indicator | Never missing; identity |
| `consequence_inframe_indel` | NCBI consequence includes inframe_indel | Frozen NCBI MC terms; union across source records | indicator | Never missing; identity |
| `consequence_inframe_insertion` | NCBI consequence includes inframe_insertion | Frozen NCBI MC terms; union across source records | indicator | Never missing; identity |
| `consequence_initiator_codon_variant` | NCBI consequence includes initiator_codon_variant | Frozen NCBI MC terms; union across source records | indicator | Never missing; identity |
| `consequence_intron_variant` | NCBI consequence includes intron_variant | Frozen NCBI MC terms; union across source records | indicator | Never missing; identity |
| `consequence_missense_variant` | NCBI consequence includes missense_variant | Frozen NCBI MC terms; union across source records | indicator | Never missing; identity |
| `consequence_no_sequence_alteration` | NCBI consequence includes no_sequence_alteration | Frozen NCBI MC terms; union across source records | indicator | Never missing; identity |
| `consequence_non-coding_transcript_variant` | NCBI consequence includes non-coding_transcript_variant | Frozen NCBI MC terms; union across source records | indicator | Never missing; identity |
| `consequence_nonsense` | NCBI consequence includes nonsense | Frozen NCBI MC terms; union across source records | indicator | Never missing; identity |
| `consequence_splice_acceptor_variant` | NCBI consequence includes splice_acceptor_variant | Frozen NCBI MC terms; union across source records | indicator | Never missing; identity |
| `consequence_splice_donor_variant` | NCBI consequence includes splice_donor_variant | Frozen NCBI MC terms; union across source records | indicator | Never missing; identity |
| `consequence_stop_lost` | NCBI consequence includes stop_lost | Frozen NCBI MC terms; union across source records | indicator | Never missing; identity |
| `consequence_synonymous_variant` | NCBI consequence includes synonymous_variant | Frozen NCBI MC terms; union across source records | indicator | Never missing; identity |
| `consequence_missing` | No consequence annotations available | Frozen NCBI MC terms | indicator | Never missing; identity |
| `consequence_other` | At least one consequence term is outside the fixed vocabulary | Frozen NCBI MC terms | indicator | Never missing; identity |
| `af_esp` | Alternate allele frequency from AF_ESP; legacy population source, not patient risk | Frozen ClinVar VCF AF_ESP | fraction [0,1] | Null if absent, malformed, out of range, or conflicting; zero remains observed; training-median imputation |
| `af_esp_missing` | Frequency unavailable or unusable | Frozen ClinVar VCF AF_ESP | indicator | Never missing; identity |
| `af_exac` | Alternate allele frequency from AF_EXAC; legacy population source, not patient risk | Frozen ClinVar VCF AF_EXAC | fraction [0,1] | Null if absent, malformed, out of range, or conflicting; zero remains observed; training-median imputation |
| `af_exac_missing` | Frequency unavailable or unusable | Frozen ClinVar VCF AF_EXAC | indicator | Never missing; identity |
| `af_tgp` | Alternate allele frequency from AF_TGP; legacy population source, not patient risk | Frozen ClinVar VCF AF_TGP | fraction [0,1] | Null if absent, malformed, out of range, or conflicting; zero remains observed; training-median imputation |
| `af_tgp_missing` | Frequency unavailable or unusable | Frozen ClinVar VCF AF_TGP | indicator | Never missing; identity |
| `context_gc_fraction` | GC fraction in the 21-base reference window centered on the VCF anchor | Pinned GRCh38 FASTA | fraction [0,1] | Null if window crosses contig boundary or contains non-ACGT bases; training-median imputation |
| `context_gc_fraction_missing` | Reference context unavailable or ambiguous | Pinned GRCh38 FASTA | indicator | Never missing; identity |

Source version and workflow details are in the annotation manifest. Missing values are filled only by a preprocessor fitted on the explicit training partition; raw export preserves nulls. Gene identity, coordinates, clinical labels, review metadata, and existing pathogenicity predictions are excluded.
