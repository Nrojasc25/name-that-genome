import { useNavigate } from 'react-router-dom'
import Card from '../components/ui/Card'

function Dashboard() {
  const navigate = useNavigate()

  return (
    <>
      <h1>Dashboard</h1>

      <div className="narrow-wide-grid">
        <Card>
          <h3 className="card-title-centered">Mutation Details</h3>
          <label htmlFor="variant">Variant (HGVS notation)</label>
          <input
            className="input"
            id="variant"
            type="text"
            placeholder="Enter variant"
          />
          <p className="small-text">
            Coding-sequence notation, e.g. c.76A&gt;T
          </p>
          <br />
          <button
            className="button"
            onClick={() => navigate('/results')}
          >
            Predict Disease
          </button>
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
          <Card>
            <p>Item 1</p>
          </Card>
          <Card>
            <p>Item 2</p>
          </Card>
          <Card>
            <p>Item 3</p>
          </Card>
          <Card>
            <p>Item 4</p>
          </Card>
        </div>
      </div>
    </>
  )
}

export default Dashboard