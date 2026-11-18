import Card from '../components/ui/Card'

export default function AboutUs() {
  return <>
    <h1>About Us</h1>
    <Card><h2>What this project does</h2>
      <p>Name That Genome explores five-class genetic variant classification using a frozen ClinVar dataset covering eight target genes. Enter a ClinVar ID or supported GRCh38 genomic HGVS to look up reference information and request a model prediction.</p>
      <p>The model predicts Benign, Likely benign, Uncertain, Likely pathogenic, or Pathogenic from variant features. ClinVar classifications and associated conditions are shown separately as reference information; the model does not rank or diagnose diseases.</p>
      <h2>Understanding the results</h2>
      <p>The current model is a research/demo candidate that has not passed its performance criteria. Its scores are uncalibrated and its predictions are flagged low confidence. SHAP explains how features influence a named raw class score, not a patient’s disease risk or a causal biological mechanism.</p>
      <p>Only variants supported by the frozen annotation cache can receive model results. Saved analyses preserve the original model output and explanation. Guest demonstrations use fixed sample data.</p>
    </Card>
  </>
}
