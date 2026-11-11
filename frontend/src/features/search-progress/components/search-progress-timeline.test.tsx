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

  it('renders all 5 steps as pending before a run starts', () => {
    render(<SearchProgressTimeline activeStep={-1} />)

    expect(rows()).toHaveLength(5)
    expect(rows().map((row) => row.dataset.state)).toEqual(Array(5).fill('pending'))
    expect(screen.queryByRole('img', { name: /Map of the area/ })).not.toBeInTheDocument()
  })

  it('marks earlier steps completed and the current one active', () => {
    render(<SearchProgressTimeline activeStep={2} />)

    expect(rows().map((row) => row.dataset.state)).toEqual([
      'completed',
      'completed',
      'active',
      'pending',
      'pending',
    ])
    expect(rows()[2]).toHaveAttribute('aria-current', 'step')
    expect(rows()[2]).toHaveTextContent('Calling tools one by one to gather more information')
  })

  it('gives each step its own colour and times only the active step', () => {
    render(<SearchProgressTimeline activeStep={1} />)
    const [done, active, pending] = rows()
    const outline = (row: HTMLElement) => row.querySelector('path[pathLength="100"]')
    const connector = (row: HTMLElement) => row.querySelector('line')

    expect(rows().map((row) => row.style.getPropertyValue('--step-color'))).toEqual([
      'var(--color-Step-1)',
      'var(--color-Step-2)',
      'var(--color-Step-3)',
      'var(--color-Step-4)',
      'var(--color-Step-5)',
    ])

    // Tile outline: fully drawn when completed, drawing (3s timer) when active, absent when pending.
    expect(outline(done)).not.toHaveClass('animate-tile-border-draw')
    expect(outline(active)).toHaveClass('animate-tile-border-draw')
    expect(outline(active)).toHaveStyle({ animationDuration: '3000ms' })
    expect(outline(pending)).toBeNull()

    // Connector flows only while the step is active.
    expect(connector(done)).not.toHaveClass('animate-connector-flow')
    expect(connector(active)).toHaveClass('animate-connector-flow')
    expect(connector(pending)).not.toHaveClass('animate-connector-flow')
  })

  it('shows the map preview once step 4 is active and keeps it after', () => {
    const { rerender } = render(<SearchProgressTimeline activeStep={3} />)
    const map = within(rows()[3]).getByRole('img', {
      name: 'Map of the area around the submitted address, with a 2 km search radius',
    })
    expect(map).toBeInTheDocument()

    rerender(<SearchProgressTimeline activeStep={5} />)
    expect(screen.getByRole('img', { name: /Map of the area/ })).toBeInTheDocument()
    expect(rows().map((row) => row.dataset.state)).toEqual(Array(5).fill('completed'))
  })
})
