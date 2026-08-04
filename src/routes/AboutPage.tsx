import { Link } from 'react-router-dom'

export function AboutPage() {
  return (
    <section className="flow-layout about-layout">
      <div className="page-heading about-heading">
        <h1>
          <span>AI identifies the item.</span>
          <span>Sorting guidance decides the bin.</span>
        </h1>
        <p>
          The app processes one still image in the browser, maps it to a known waste item, then checks curated disposal guidance. Raw user images are not stored.
        </p>
      </div>
      <div className="about-card-grid">
        <section className="about-card">
          <h2>Local data disclaimer</h2>
          <p>
            This guidance applies to the selected waste station and should be updated when signage or local sorting policy changes.
          </p>
        </section>
        <section className="about-card">
          <h2>Model requirement</h2>
          <p>
            The repository includes the application and AI integration layer. Accurate custom recognition requires a trained ONNX model and labels that match the intended sorting environment.
          </p>
        </section>
      </div>
      <Link className="primary-action large about-cta" to="/">
        Start scanning
      </Link>
    </section>
  )
}
