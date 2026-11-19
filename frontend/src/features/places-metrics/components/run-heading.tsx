/** The page title while there is no finished result yet (start, waiting, failure). */
export function RunHeading() {
  return (
    <header className="pm-heading">
      <div className="pm-heading-text">
        <h1 className="pm-h1">
          Which places <em>fit</em> your questions
        </h1>
        <p className="pm-lede">Your own questions about the places nearby, answered with their sources</p>
      </div>
    </header>
  )
}
