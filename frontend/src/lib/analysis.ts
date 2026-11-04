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
  prediction: {
    model_name: string
    model_version: string
    decision: string
    pathogenic_probability: number
    probability_kind: 'calibrated' | 'uncalibrated'
    explanation: {
      base_value: number
      explained_value: number
      output_space: string
      features: { feature: string; value: string | number | boolean | null; contribution: number }[]
    } | null
  } | null
}

export interface AnalysisHistory {
  items: Analysis[]
  total: number
  limit: number
  offset: number
}
