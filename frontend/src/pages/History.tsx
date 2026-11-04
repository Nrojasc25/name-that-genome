import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Card from '../components/ui/Card'
import { api } from '../lib/api'
import type { AnalysisHistory } from '../lib/analysis'

function History() {
  const [offset, setOffset] = useState(0)
  const [state, setState] = useState<{ data?: AnalysisHistory; error?: string }>({})
  useEffect(() => {
    let active = true
    api<AnalysisHistory>(`/api/history?limit=20&offset=${offset}`).then(
      data => { if (active) setState({ data }) },
      error => { if (active) setState({ error: error.message }) },
    )
    return () => { active = false }
  }, [offset])
  function changePage(next: number) {
    setState({})
    setOffset(next)
  }
  return <>
    <h1>History</h1>
    {state.error && <p role="alert">{state.error}</p>}
    {!state.data && !state.error && <p role="status">Loading history…</p>}
    {state.data && <>
      {state.data.items.length === 0 && <Card><p>No analyses yet. Your searches will appear here.</p></Card>}
      {state.data.items.map(item => <Card key={item.id}>
        <Link to={`/results/${item.id}`}>{item.input}</Link>
        <p>{new Date(item.created_at * 1000).toLocaleString()}</p>
        <p>{item.variant.source_records[0]?.conditions.map(condition => condition.name).join(', ') || 'No reference conditions listed'}</p>
      </Card>)}
      <p>{state.data.total} saved analyses</p>
      <button className="button" disabled={offset === 0} onClick={() => changePage(Math.max(0, offset - 20))}>Previous</button>
      <button className="button" disabled={offset + 20 >= state.data.total} onClick={() => changePage(offset + 20)}>Next</button>
    </>}
  </>
}
export default History
