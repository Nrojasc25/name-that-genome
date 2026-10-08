import Card from '../components/ui/Card'

function AboutUs() {
  return (
    <>
      <h1>About Us</h1>

      <div className="equal-columns-grid">
        <Card>
          <h2>Text1</h2>
        </Card>
        <Card>
          <h2>Text2</h2>
        </Card>
      </div>
      <br />

      <div className="full-width-grid">
        <Card>
          <h2>Text3</h2>
        </Card>
      </div>
    </>
  )
}

export default AboutUs