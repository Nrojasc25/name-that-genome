import { useOutletContext } from 'react-router-dom'
import { GuestDemo } from '../components/GuestDemo'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Card from '../components/ui/Card'
import { api } from '../lib/api'
import type { Analysis } from '../lib/analysis'
import './Results.css'

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
  const record = analysis?.variant.source_records[0]
  const prediction = analysis?.prediction
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
            <p>{prediction.decision}</p>
            <p>Pathogenic {prediction.probability_kind === 'calibrated' ? 'probability' : 'score (uncalibrated)'}: {(prediction.pathogenic_probability * 100).toFixed(1)}%</p>
            <p>{prediction.model_name} · {prediction.model_version}</p>
          </> : <p>Model prediction unavailable. The model has not been connected yet.</p>}
        </Card>
      </div>
      <Card>
        <h3>Why this prediction?</h3>
        {prediction?.explanation ? <>
          <p>Contributions to the pathogenic output in {prediction.explanation.output_space}. Positive values increase the output; negative values decrease it.</p>
          <p>Base value: {prediction.explanation.base_value}. Explained value: {prediction.explanation.explained_value}.</p>
          <ul>{prediction.explanation.features.map((feature, index) => <li key={index}>{feature.feature}: {String(feature.value ?? 'Not available')} — contribution {feature.contribution}</li>)}</ul>
        </> : <p>No SHAP explanation is available for this analysis.</p>}
      </Card>
    </>}
  </>
}
export default function Results() {
  const { isGuest } = useOutletContext<{ isGuest: boolean }>()
  return isGuest ? <GuestDemo page="results" /> : <LiveResults />
}
