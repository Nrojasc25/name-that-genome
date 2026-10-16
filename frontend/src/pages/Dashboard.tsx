import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Card from '../components/ui/Card'

const codingVariantPattern =
  /^c\.(?:-?\d+|\*\d+)(?:[+-]\d+)?(?:_(?:-?\d+|\*\d+)(?:[+-]\d+)?)?(?:[ACGTN]+>[ACGTN]+|del(?:[ACGTN]+)?(?:ins[ACGTN]+)?|dup(?:[ACGTN]+)?|ins[ACGTN]+|inv)$/i

function Dashboard() {
  const navigate = useNavigate()
  const [variant, setVariant] = useState('')
  const [error, setError] = useState('')

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalizedVariant = variant.trim()

    if (!normalizedVariant || !codingVariantPattern.test(normalizedVariant)) {
      setError('Enter a coding HGVS variant, such as c.76A>T.')
      return
    }

    setError('')
    navigate('/results')
  }

  return (
    <>
      <h1>Dashboard</h1>

      <div className="narrow-wide-grid">
        <Card>
          <h3 className="card-title-centered">Mutation Details</h3>
          <form onSubmit={handleSubmit} noValidate>
            <label htmlFor="variant">Variant (HGVS notation)</label>
            <input
              className="input"
              id="variant"
              type="text"
              placeholder="Enter variant"
              value={variant}
              onChange={(event) => {
                setVariant(event.target.value)
                setError('')
              }}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? 'variant-error' : undefined}
            />
            <p className="small-text">
              Coding-sequence notation, e.g. c.76A&gt;T
            </p>
            {error && (
              <p className="variant-error" id="variant-error" role="alert">
                {error}
              </p>
            )}
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