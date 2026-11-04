import { useOutletContext } from 'react-router-dom'
import { GuestDemo } from '../components/GuestDemo'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Card from '../components/ui/Card'
import { api } from '../lib/api'
import type { Analysis, AnalysisHistory } from '../lib/analysis'
import './Dashboard.css'

function LiveDashboard() {
  const navigate = useNavigate()
  const [variant, setVariant] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [history, setHistory] = useState<AnalysisHistory | null>(null)
  const [historyError, setHistoryError] = useState('')
  useEffect(() => {
    let active = true
    api<AnalysisHistory>('/api/history?limit=4').then(
      data => { if (active) setHistory(data) },
      error => { if (active) setHistoryError(error.message) },
    )
    return () => { active = false }
  }, [])
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setPending(true)
    try {
      const analysis = await api<Analysis>('/api/analyses', { method: 'POST', body: JSON.stringify({ variant: variant.trim() }) })
      navigate(`/results/${analysis.id}`)
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Unable to analyze variant.')
    } finally {
      setPending(false)
    }
  }
  return <>
    <h1>Dashboard</h1>
    <div className="narrow-wide-grid">
      <Card>
        <h3 className="card-title-centered">Mutation Details</h3>
        <form onSubmit={handleSubmit}>
          <label htmlFor="variant">ClinVar ID or genomic HGVS</label>
          <input className="input" id="variant" required maxLength={200} placeholder="576" value={variant} onChange={event => setVariant(event.target.value)} />
          <p className="small-text">Enter a ClinVar ID such as 576 or a full GRCh38 genomic HGVS such as NC_000012.12:g.102840399C&gt;T.</p>
          {error && <p role="alert">{error}</p>}
          <button className="button" type="submit" disabled={pending || !variant.trim()}>{pending ? 'Analyzing…' : 'Analyze Variant'}</button>
        </form>
      </Card>
      <div className="container">
        <Card><div className="card-title-split"><h3>Recent Analyses</h3><Link className="hyperlink" to="/history">View History</Link></div></Card>
        {historyError && <p role="alert">{historyError}</p>}
        {!history && !historyError && <p role="status">Loading recent analyses…</p>}
        {history?.items.length === 0 && <Card><p>No analyses yet.</p></Card>}
        {history?.items.map(item => <Card key={item.id} className="dashboard-prediction-card">
          <div className="dashboard-prediction-details">
            <Link to={`/results/${item.id}`}>{item.input}</Link>
            <p><strong>ClinVar conditions:</strong> {item.variant.source_records[0]?.conditions.map(condition => condition.name).join(', ') || 'None listed'}</p>
            <p>{new Date(item.created_at * 1000).toLocaleString()}</p>
          </div>
        </Card>)}
      </div>
    </div>
  </>
}
export default function Dashboard() {
  const { isGuest } = useOutletContext<{ isGuest: boolean }>()
  return isGuest ? <GuestDemo page="dashboard" /> : <LiveDashboard />
}
