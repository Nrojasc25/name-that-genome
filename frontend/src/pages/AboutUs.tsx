import Card from '../components/ui/Card'

function AboutUs() {
  return (
    <>
      <h1>About Us</h1>

      <div className="equal-columns-grid">
        <Card>
          <h2>Our Mission</h2>
          <p>
            Name That Genome aims to make genetic information easier to
            understand by connecting genetic variants with potential rare
            genetic diseases. Our goal is to explore how machine learning can
            support disease identification and make genomic information more
            accessible.
          </p>
        </Card>
        <Card>
          <h2>What We Do</h2>
          <p>
            We analyze genetic variants using genomic databases and machine
            learning to identify potential rare monogenic diseases. By
            combining genetic data with computational methods, Name That
            Genome helps narrow down possible disease associations and provides
            insights that can support further investigation.
          </p>
        </Card>
      </div>
      <br />

      <div className="full-width-grid">
        <Card>
          <h2>How It Works</h2>
          <p>
            Users enter a genetic variant in HGVS notation. Our system analyzes
            the variant using genomic reference data, including ClinVar, and a
            machine learning model to generate a shortlist of potential rare
            genetic diseases. Results include SHAP-based explanations that
            highlight which features most influenced the model’s predictions.
            These explanations help users understand why a disease may have
            been ranked higher or lower, with SHAP values indicating whether a
            feature pushes a prediction toward or away from a disease. The
            results provide a starting point for exploring possible
            variant-disease associations, not a definitive diagnosis.
          </p>
        </Card>
      </div>
    </>
  )
}

export default AboutUs