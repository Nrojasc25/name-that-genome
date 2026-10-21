import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Card from '../components/ui/Card'
import './Dashboard.css'

const recentPredictions = [
  { variant: 'c.76A>T', disease: 'Disease A', confidence: 75 },
  { variant: 'c.1521_1523delCTT', disease: 'Disease B', confidence: 82 },
  { variant: 'c.350G>A', disease: 'Disease C', confidence: 68 },
  { variant: 'c.1652G>A', disease: 'Disease D', confidence: 91 },
]

function Dashboard() {
  const navigate = useNavigate()
  const [variant, setVariant] = useState('')

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    navigate('/results')
  }

  return (
    <>
      <h1>Dashboard</h1>

      <div className="narrow-wide-grid">
        <Card>
          <h3 className="card-title-centered">Mutation Details</h3>
          <form onSubmit={handleSubmit}>
            <label htmlFor="variant">Variant (HGVS notation)</label>
            <input
              className="input"
              id="variant"
              type="text"
              placeholder="Enter variant"
              value={variant}
              onChange={(event) => setVariant(event.target.value)}
            />
            <p className="small-text">
              Coding-sequence notation, e.g. c.76A&gt;T
            </p>
            <button className="button" type="submit">
              Predict Disease
            </button>
          </form>
        </Card>

        <div className="container">
          <Card>
            <div className="card-title-split">
              <h3>Recent Predictions</h3>
              <button 
                className="hyperlink"
                onClick={() => navigate('/history')}
              >
                View History
              </button>
            </div>
          </Card>
          {recentPredictions.map(({ variant, disease, confidence }) => (
            <Card key={variant} className="dashboard-prediction-card">
              <div className="dashboard-prediction-details">
                <p className="dashboard-prediction-variant">
                  <strong>Variant:</strong> {variant}
                </p>
                <p className="dashboard-prediction-disease">
                  <strong>Condition:</strong> {disease}
                </p>
              </div>
              <p className="dashboard-prediction-confidence">
                <strong>{confidence}%</strong>
                <span>Confidence</span>
              </p>
            </Card>
          ))}
        </div>
      </div>
    </>
  )
}

export default Dashboard