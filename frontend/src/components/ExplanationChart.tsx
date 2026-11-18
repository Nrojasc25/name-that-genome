import { CLASS_LABELS, type ShapExplanation } from '../lib/analysis'

export function ExplanationChart({ explanation }: { explanation: ShapExplanation }) {
  const features = explanation.display_features || explanation.features
  const maximum = Math.max(...features.map(feature => Math.abs(feature.contribution)), 0.000001)
  return <>
    <h4>Features influencing the {CLASS_LABELS[explanation.output_target]} model output</h4>
    <p>Output space: {explanation.output_space === 'raw_score' ? 'raw class score (margin)' : explanation.output_space}. Positive contributions increase this output; negative contributions decrease it.</p>
    {explanation.output_space === 'raw_score' && <p>These contributions add to the raw score, not to the displayed class percentage.</p>}
    <p>Baseline {explanation.base_value.toFixed(4)} + contributions = {explanation.explained_value.toFixed(4)}.</p>
    <ul className="shap-list">{features.map((feature, index) => <li key={`${feature.feature}-${index}`}>
      <details>
        <summary>{feature.feature}: {feature.contribution >= 0 ? '+' : ''}{feature.contribution.toFixed(4)} ({feature.contribution >= 0 ? 'increases' : 'decreases'} output)</summary>
        {feature.members?.length ? <ul>{feature.members.map(member => <li key={member.feature}>{member.feature}: {member.value === null ? 'missing' : member.value}; value used by model: {member.model_value}</li>)}</ul> : <p>Value: {String(feature.value ?? 'Not available')}</p>}
      </details>
      <div className="shap-track" aria-hidden="true"><span className={feature.contribution >= 0 ? 'shap-positive' : 'shap-negative'} style={{ width: `${Math.abs(feature.contribution) / maximum * 50}%` }} /></div>
    </li>)}</ul>
    <p className="small-text">SHAP describes model behavior relative to a background dataset, not a causal biological mechanism. Correlated features can share attribution.</p>
    {explanation.background_version && <details><summary>Explanation provenance</summary><p>Model: {explanation.model_version}<br />Background: {explanation.background_version}</p></details>}
  </>
}
