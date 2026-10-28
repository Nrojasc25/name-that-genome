import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Card from './ui/Card'
import '../pages/Dashboard.css'
import '../pages/Results.css'

const examples = [
  { variant: 'c.76A>T', disease: 'Disease A', confidence: 75 },
  { variant: 'c.1521_1523delCTT', disease: 'Disease B', confidence: 82 },
  { variant: 'c.350G>A', disease: 'Disease C', confidence: 68 },
  { variant: 'c.1652G>A', disease: 'Disease D', confidence: 91 },
]

export function GuestDemo({ page }: { page: 'dashboard' | 'results' | 'history' }) {
  const [variant, setVariant] = useState('')
  const navigate = useNavigate()
  const { analysisId } = useParams()
  const selected = examples.find((_, index) => analysisId === `demo-${index}`) || examples[1]
  const cards = examples.map((item, index) => <Card key={item.variant} className="dashboard-prediction-card">
    <div className="dashboard-prediction-details">
      <Link to={`/results/demo-${index}`}><strong>Variant:</strong> {item.variant}</Link>
      <p><strong>Condition:</strong> {item.disease}</p>
    </div>
    <p className="dashboard-prediction-confidence"><strong>{item.confidence}%</strong><span>Demo confidence</span></p>
  </Card>)

  return <>
    <p role="status">Guest demo — all variants, conditions, and confidence values shown here are sample data. Sign in to analyze real variants and save your history.</p>
    {page === 'dashboard' && <>
      <h1>Dashboard</h1>
      <div className="narrow-wide-grid">
        <Card>
          <h3 className="card-title-centered">Mutation Details</h3>
          <form onSubmit={event => {
            event.preventDefault()
            const index = examples.findIndex(item => item.variant === variant.trim())
            navigate(`/results/demo-${index < 0 ? 1 : index}`)
          }}>
            <label htmlFor="variant">Variant (HGVS notation)</label>
            <input className="input" id="variant" placeholder="Enter variant" value={variant} onChange={event => setVariant(event.target.value)} />
            <p className="small-text">Try c.1521_1523delCTT. Submitting any other input opens a sample result; no analysis is performed.</p>
            <button className="button" type="submit">Preview Demo Prediction</button>
          </form>
        </Card>
        <div className="container">
          <Card><div className="card-title-split"><h3>Recent Predictions</h3><Link className="hyperlink" to="/history">View History</Link></div></Card>
          {cards}
        </div>
      </div>
    </>}
    {page === 'history' && <><h1>Demo History</h1>{cards}</>}
    {page === 'results' && <>
      <Link className="hyperlink" to="/dashboard">← Back to Dashboard</Link>
      <h1>Demo Results</h1>
      <div className="narrow-wide-grid">
        <Card>
          <h3 className="card-title-centered">Mutation Details</h3>
          <dl className="results-variant-details">
            <dt>Variant</dt><dd>{selected.variant}</dd>
            <dt>Gene (sample)</dt><dd>CFTR</dd>
            <dt>Chromosome (sample)</dt><dd>7</dd>
            <dt>Zygosity (sample)</dt><dd>Heterozygous</dd>
            <dt>Consequence (sample)</dt><dd>Missense variant</dd>
          </dl>
        </Card>
        <Card>
          <div className="card-title-split"><h3>Prediction Result</h3><div className="results-tag">Demo Only</div></div>
          <div className="card-title-split">
            <div className="results-disease"><p>{selected.disease}</p></div>
            <div><p className="results-confidence-value">{selected.confidence}%</p><p className="results-confidence-label">Sample confidence</p></div>
          </div>
        </Card>
      </div>
      <Card><h3>Why this prediction?</h3><p>This is a hardcoded preview. No model prediction or SHAP explanation has been generated.</p></Card>
    </>}
  </>
}
