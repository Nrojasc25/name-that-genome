import Card from '../components/ui/Card'
import './Results.css'

function Results() {
  return (
    <>
      <h1>Results</h1>
      <div className="narrow-wide-grid">
        <Card>
          <h3 className="card-title-centered">Mutation Details</h3>
          <div className="results-variant-details">
            <div>
              <p className="results-detail-label">Variant</p>
              <p className="results-detail-value">c.1521_1523delCTT</p>
            </div>

            <div>
              <p className="results-detail-label">Gene</p>
              <p className="results-detail-value">CFTR</p>
            </div>

            <div>
              <p className="results-detail-label">Chromosome</p>
              <p className="results-detail-value">7</p>
            </div>

            <div>
              <p className="results-detail-label">Zygosity</p>
              <p className="results-detail-value">Heterozygous</p>
            </div>

            <div>
              <p className="results-detail-label">Consequence</p>
              <p className="results-detail-value">Missense variant</p>
            </div>
          </div>
        </Card>

        <Card>
          <div className="card-title-split">
            <h3>Prediction Result</h3>
            <div className="results-tag">High Confidence</div>
          </div>
          <div className="card-title-split">
            <div className="results-disease">
              <p>Disease A</p>
            </div>
            <div>
              <p className="results-confidence-value">75%</p>
              <p className="results-confidence-label">confidence</p>
            </div>
          </div>
        </Card>
      </div>
      <br />

      <div className="full-width-grid">
        <Card>
          <h3>Why this prediction?</h3>
        </Card>
      </div>
    </>
  )
}

export default Results