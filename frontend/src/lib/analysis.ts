export const CLASS_ORDER = ['benign', 'likely_benign', 'uncertain', 'likely_pathogenic', 'pathogenic'] as const
export type VariantClass = typeof CLASS_ORDER[number]
export const CLASS_LABELS: Record<VariantClass, string> = {
  benign: 'Benign',
  likely_benign: 'Likely benign',
  uncertain: 'Uncertain',
  likely_pathogenic: 'Likely pathogenic',
  pathogenic: 'Pathogenic',
}

export interface ShapExplanation {
  base_value: number
  explained_value: number
  output_space: 'probability' | 'log_odds' | 'raw_score'
  output_target: VariantClass
  features: { feature: string; value: string | number | boolean | null; contribution: number }[]
}

export interface Prediction {
  schema_version: 2
  model_name: string
  model_version: string
  feature_schema_version: string
  annotation_version: string
  dataset_version: string
  decision: VariantClass
  class_scores: Record<VariantClass, number>
  probability_kind: 'calibrated' | 'uncalibrated'
  confidence_status: 'not_assessed' | 'low' | 'standard'
  explanation: ShapExplanation | null
}

export interface LegacyPrediction {
  schema_version?: 1
  model_name: string
  model_version: string
  decision: 'benign' | 'pathogenic' | 'uncertain'
  pathogenic_probability: number
  probability_kind: 'calibrated' | 'uncalibrated'
  explanation: (Omit<ShapExplanation, 'output_target'> & { output_target?: 'pathogenic' }) | null
}

export interface Analysis {
  id: string
  created_at: number
  input: string
  variant: {
    clinvar_variation_id: number
    source_records: {
      hgvs: string | null
      genes: string[]
      chromosome: string
      position: number
      assembly: string
      consequences: string[]
      clinvar_classification: string | null
      conditions: { name: string }[]
      review_status: string | null
      release_version: string
    }[]
  }
  prediction_status: 'available' | 'not_available'
  prediction: Prediction | LegacyPrediction | null
}

export interface AnalysisHistory {
  items: Analysis[]
  total: number
  limit: number
  offset: number
}
