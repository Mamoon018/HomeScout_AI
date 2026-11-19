import { render, screen, within } from '@testing-library/react'
import { SearchProgressTimeline } from '@/features/search-progress/components/search-progress-timeline'

function rows() {
  return within(screen.getByRole('list', { name: 'Search progress' })).getAllByRole('listitem')
}

describe('SearchProgressTimeline', () => {
  it('is a panel reachable by its "Scouting your neighborhood" heading', () => {
    render(<SearchProgressTimeline activeStep={0} />)

    const panel = screen.getByRole('region', { name: 'Scouting your neighborhood' })
    expect(within(panel).getByRole('heading', { level: 2, name: 'Scouting your neighborhood' })).toBeInTheDocument()
    expect(within(panel).getByRole('list', { name: 'Search progress' })).toBeInTheDocument()
  })

  it('renders the two steps as pending before a run starts', () => {
    render(<SearchProgressTimeline activeStep={-1} />)

    expect(rows()).toHaveLength(2)
    expect(rows().map((row) => row.dataset.state)).toEqual(['pending', 'pending'])
    expect(rows()[0]).toHaveTextContent('Checking if anything needs clarification')
    expect(rows()[1]).toHaveTextContent('Breaking your needs into higher-level categories')
  })

  it('marks the clarity check completed and the categories step active', () => {
    render(<SearchProgressTimeline activeStep={1} />)

    expect(rows().map((row) => row.dataset.state)).toEqual(['completed', 'active'])
    expect(rows()[1]).toHaveAttribute('aria-current', 'step')
  })

  it('gives each step its own colour and times only the active step', () => {
    render(<SearchProgressTimeline activeStep={1} />)
    const [done, active] = rows()
    const outline = (row: HTMLElement) => row.querySelector('path[pathLength="100"]')
    const connector = (row: HTMLElement) => row.querySelector('line')

    expect(rows().map((row) => row.style.getPropertyValue('--step-color'))).toEqual([
      'var(--color-Step-2)',
      'var(--color-Step-1)',
    ])

    // Tile outline: fully drawn when completed, drawing (3s timer) when active.
    expect(outline(done)).not.toHaveClass('animate-tile-border-draw')
    expect(outline(active)).toHaveClass('animate-tile-border-draw')
    expect(outline(active)).toHaveStyle({ animationDuration: '3000ms' })

    // Connector flows only while the step is active.
    expect(connector(done)).not.toHaveClass('animate-connector-flow')
    expect(connector(active)).toHaveClass('animate-connector-flow')
  })

  it('shows every step completed at the end', () => {
    render(<SearchProgressTimeline activeStep={2} />)
    expect(rows().map((row) => row.dataset.state)).toEqual(['completed', 'completed'])
  })
})
