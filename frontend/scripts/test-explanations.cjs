// Render the real chart component for all five fixture labels, without a browser.
const fs = require('node:fs')
const path = require('node:path')
const assert = require('node:assert/strict')
const ts = require('typescript')
const React = require('react')
const { renderToStaticMarkup } = require('react-dom/server')
const originalTs = require.extensions['.ts']
const originalTsx = require.extensions['.tsx']
function compile(module, filename) {
  const source = fs.readFileSync(filename, 'utf8')
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } })
  module._compile(output.outputText, filename)
}
require.extensions['.ts'] = compile
require.extensions['.tsx'] = compile
try {
  const { ExplanationChart } = require('../src/components/ExplanationChart.tsx')
  const { CLASS_LABELS } = require('../src/lib/analysis.ts')
  const fixtures = JSON.parse(fs.readFileSync(path.join(__dirname,'../../ml/tests/fixtures/predictions.json'),'utf8'))
  for (const prediction of fixtures.five_class) {
    const html = renderToStaticMarkup(React.createElement(ExplanationChart, { explanation: prediction.explanation }))
    assert.ok(html.includes(CLASS_LABELS[prediction.explanation.output_target]))
    assert.ok(html.includes('<summary>'))
    assert.ok(html.includes('Baseline'))
    assert.ok(!html.includes('NaN'))
  }
  const examples = JSON.parse(fs.readFileSync(path.join(__dirname,'../../ml/reports/shap_examples.json'),'utf8'))
  for (const example of examples) {
    const html = renderToStaticMarkup(React.createElement(ExplanationChart, { explanation: example.explanation }))
    assert.ok(html.includes('Other features'))
    assert.ok(html.includes('value used by model'))
    assert.ok(html.includes('not to the displayed class percentage'))
  }
  console.log('Rendered all five fixture classes and five real grouped SHAP examples.')
} finally {
  require.extensions['.ts'] = originalTs
  require.extensions['.tsx'] = originalTsx
}
