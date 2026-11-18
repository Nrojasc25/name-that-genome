import { useOutletContext } from 'react-router-dom'
import { GuestDemo } from '../components/GuestDemo'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Card from '../components/ui/Card'
import { api } from '../lib/api'
import { CLASS_LABELS, CLASS_ORDER, type Analysis } from '../lib/analysis'
import './Results.css'
import { ExplanationChart } from '../components/ExplanationChart'

function unavailableReason(reason?: string | null) {
  const messages: Record<string, string> = {
    model_missing: 'The local model artifacts are not installed.',
    model_load_failed: 'The local model could not be verified or loaded.',
    unsupported_source: 'This model supports only its frozen GRCh38 source release.',
    ambiguous_source: 'Multiple source coordinates matched; no prediction was selected.',
    unsupported_variant: 'This variant type is outside the supported scope.',
    annotation_missing: 'This variant has no supported annotation in the frozen model cache.',
    features_invalid: 'Required variant features could not be validated.',
    busy: 'The model is busy. Submit a new analysis to try again.',
    prediction_failed: 'The model could not produce a valid result.',
  }
  return messages[reason || ''] || 'No model result was stored in this saved analysis.'
}

function LiveResults() {
  const { analysisId } = useParams()
  const [state, setState] = useState<{ data?: Analysis; error?: string }>({})
  useEffect(() => {
    let active = true
    api<Analysis>(`/api/analyses/${encodeURIComponent(analysisId || '')}`).then(
      data => { if (active) setState({ data }) },
      error => { if (active) setState({ error: error.message }) },
    )
    return () => { active = false }
  }, [analysisId])
  const analysis = state.data
  const prediction = analysis?.prediction
  const sourceId = prediction?.schema_version === 2 ? prediction.source_record_id : undefined
  const record = analysis?.variant.source_records.find(record => record.record_id === sourceId) || analysis?.variant.source_records[0]
  return <>
    <Link className="hyperlink" to="/dashboard">← Back to Dashboard</Link>
    <h1>Results</h1>
    {state.error && <p role="alert">{state.error}</p>}
    {!analysis && !state.error && <p role="status">Loading analysis…</p>}
    {analysis && <>
      <p>{new Date(analysis.created_at * 1000).toLocaleString()}</p>
      <div className="narrow-wide-grid">
        <Card>
          <h3>Mutation Details</h3>
          <dl className="results-variant-details">
            <dt>Submitted variant</dt><dd>{analysis.input}</dd>
            <dt>ClinVar ID</dt><dd>{analysis.variant.clinvar_variation_id}</dd>
            <dt>Genomic HGVS</dt><dd>{record?.hgvs || 'Not available'}</dd>
            <dt>Genes</dt><dd>{record?.genes.join(', ') || 'Not available'}</dd>
            <dt>Location</dt><dd>{record ? `${record.assembly}, chromosome ${record.chromosome}, position ${record.position}` : 'Not available'}</dd>
            <dt>Consequences</dt><dd>{record?.consequences.join(', ') || 'Not available'}</dd>
          </dl>
        </Card>
        <Card>
          <h3>ClinVar Reference Information</h3>
          <p><strong>Classification:</strong> {record?.clinvar_classification || 'Not available'}</p>
          <p><strong>Associated conditions:</strong> {record?.conditions.map(condition => condition.name).join(', ') || 'None listed'}</p>
          <p><strong>Review status:</strong> {record?.review_status || 'Not available'}</p>
          <p><strong>Source release:</strong> {record?.release_version || 'Not available'}</p>
          <p className="small-text">These are reference annotations from ClinVar.</p>
          <h3>Model Prediction</h3>
          {analysis.prediction_status === 'available' && prediction ? <>
            <p><strong>{CLASS_LABELS[prediction.decision]}</strong></p>
            {prediction.schema_version === 2 && prediction.release_status === 'research_candidate_rejected' && <p role="status">Research/demo candidate — this model has not passed its performance criteria. These results are not a clinical classification or diagnosis.</p>}
            {prediction.schema_version === 2 ? <>
              <p>{prediction.probability_kind === 'calibrated' ? 'Class probabilities' : 'Class scores (uncalibrated)'}</p>
              <ul className="score-list">{CLASS_ORDER.map(label => <li key={label}><span>{CLASS_LABELS[label]}: {(prediction.class_scores[label] * 100).toFixed(1)}%</span><meter min={0} max={1} value={prediction.class_scores[label]} aria-label={`${CLASS_LABELS[label]} model score`} /></li>)}</ul>
              <p className="small-text">Scores describe model outputs, not a patient’s probability of disease.</p>
              {prediction.decision === 'uncertain' && <p>Uncertain is a predicted classification learned from uncertain-significance records.</p>}
              {prediction.confidence_status === 'low' && <p>The model has low confidence in this selection. This is separate from the Uncertain category.</p>}
              {prediction.confidence_status === 'not_assessed' && <p>Model confidence has not been assessed.</p>}
            </> : <p>Pathogenic {prediction.probability_kind === 'calibrated' ? 'probability' : 'score (uncalibrated)'}: {(prediction.pathogenic_probability * 100).toFixed(1)}% (saved legacy result)</p>}
            <p>{prediction.model_name} · {prediction.model_version}</p>
          </> : <p>Model prediction unavailable. {unavailableReason(analysis.prediction_reason)}</p>}
        </Card>
      </div>
      <Card>
        <h3>Why this prediction?</h3>
        {prediction?.explanation ? <>
          <ExplanationChart explanation={{ ...prediction.explanation, output_target: prediction.explanation.output_target ?? 'pathogenic' }} />
        </> : <p>{prediction?.schema_version === 2 && prediction.explanation_status === 'failed' ? 'The explanation could not be generated. The prediction above is still available.' : 'No SHAP explanation is stored for this analysis.'}</p>}
      </Card>
    </>}
  </>
}
export default function Results() {
  const { isGuest } = useOutletContext<{ isGuest: boolean }>()
  return isGuest ? <GuestDemo page="results" /> : <LiveResults />
}
