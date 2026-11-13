import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import { ClarificationPreview } from '@/features/search-progress/components/clarification-preview'
import type { ClarificationQuestion } from '@/features/search-progress/types/clarification'

const DUMMY_CLARIFICATION_QUESTIONS: ClarificationQuestion[] = [
  {
    category_id: 2,
    category: 'somewhere to work out',
    question: 'When you say somewhere to work out, which of these is closest to what you meant?',
    options: [
      'a gym with weights and cardio machines',
      'a yoga or pilates studio',
      'a swimming pool or leisure centre',
      'an outdoor park or running track',
      'other',
    ],
  },
  {
    category_id: 3,
    category: 'a good place for the kids',
    question: 'When you say a good place for the kids, which of these is closest to what you meant?',
    options: [
      'a primary school',
      "a playground or children's park",
      'an after-school club or activity centre',
      'an indoor play centre',
      'other',
    ],
  },
  {
    category_id: 4,
    category: 'somewhere to grab a bite',
    question: 'When you say somewhere to grab a bite, which of these is closest to what you meant?',
    options: [
      'a casual restaurant for sit-down meals',
      'a cafe or coffee shop',
      'a takeaway or fast-food place',
      'a bakery or deli',
      'other',
    ],
  },
]

function renderAsking(onSubmit = vi.fn()) {
  render(
    <ClarificationPreview
      phase="asking"
      questions={DUMMY_CLARIFICATION_QUESTIONS}
      answers={[]}
      onSubmit={onSubmit}
    />,
  )
  return onSubmit
}

const next = () => screen.getByRole('button', { name: 'Next' })

describe('ClarificationPreview — asking', () => {
  it('shows one question at a time with its position', () => {
    renderAsking()

    expect(
      screen.getByRole('radiogroup', { name: /somewhere to work out/ }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('radiogroup', { name: /good place for the kids/ }),
    ).not.toBeInTheDocument()
    expect(screen.getByText('1 of 3')).toBeInTheDocument()
    expect(screen.getAllByRole('radio')).toHaveLength(5)
  })

  it('keeps Next off until an option is picked, and shows Submit only on the last question', () => {
    renderAsking()

    expect(next()).toBeDisabled()
    fireEvent.click(screen.getByRole('radio', { name: 'a yoga or pilates studio' }))
    expect(next()).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Submit' })).not.toBeInTheDocument()

    fireEvent.click(next())
    fireEvent.click(screen.getByRole('radio', { name: 'a primary school' }))
    fireEvent.click(next())
    expect(screen.getByText('3 of 3')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Submit' })).toBeDisabled()
  })

  it('selects options with the number keys', () => {
    renderAsking()

    fireEvent.keyDown(screen.getByRole('radio', { name: 'a yoga or pilates studio' }), { key: '3' })
    expect(screen.getByRole('radio', { name: 'a swimming pool or leisure centre' })).toBeChecked()
  })

  it('needs text for "other" and keeps the field visible', () => {
    renderAsking()

    fireEvent.click(screen.getByRole('radio', { name: 'Other' }))
    const field = screen.getByRole('textbox', { name: /somewhere to work out/ })
    expect(field).toHaveFocus()
    expect(next()).toBeDisabled()

    fireEvent.change(field, { target: { value: '  a climbing wall ' } })
    expect(next()).toBeEnabled()
  })

  it('goes back without losing earlier answers', () => {
    renderAsking()

    fireEvent.click(screen.getByRole('radio', { name: 'a yoga or pilates studio' }))
    fireEvent.click(next())
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(screen.getByRole('radio', { name: 'a yoga or pilates studio' })).toBeChecked()
  })

  it('submits 1-based options with the label, or the typed text for "other"', async () => {
    const onSubmit = renderAsking()

    fireEvent.click(screen.getByRole('radio', { name: 'a yoga or pilates studio' }))
    fireEvent.click(next())
    fireEvent.click(screen.getByRole('radio', { name: 'Other' }))
    fireEvent.change(screen.getByRole('textbox', { name: /good place for the kids/ }), {
      target: { value: ' a scout hall ' },
    })
    fireEvent.click(next())
    fireEvent.click(screen.getByRole('radio', { name: 'a bakery or deli' }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    expect(onSubmit).toHaveBeenCalledWith([
      { category_id: 2, option: 2, description: 'a yoga or pilates studio' },
      { category_id: 3, option: 5, description: 'a scout hall' },
      { category_id: 4, option: 4, description: 'a bakery or deli' },
    ])
  })

  it('shows a retry message and keeps the answers when sending fails', async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error('offline'))
    renderAsking(onSubmit)

    for (const name of ['a gym with weights and cardio machines', 'a primary school']) {
      fireEvent.click(screen.getByRole('radio', { name }))
      fireEvent.click(next())
    }
    fireEvent.click(screen.getByRole('radio', { name: 'a cafe or coffee shop' }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/Couldn.t send your answers/)
    expect(screen.getByRole('button', { name: 'Submit' })).toBeEnabled()
    expect(screen.getByRole('radio', { name: 'a cafe or coffee shop' })).toBeChecked()
  })
})

describe('ClarificationPreview — answered', () => {
  it('lists each phrase with what the renter meant by it', () => {
    render(
      <ClarificationPreview
        phase="answered"
        questions={DUMMY_CLARIFICATION_QUESTIONS}
        answers={[
          { category_id: 2, option: 1, description: 'a gym with weights and cardio machines' },
          { category_id: 3, option: 5, description: 'a scout hall' },
          { category_id: 4, option: 2, description: 'a cafe or coffee shop' },
        ]}
        onSubmit={vi.fn()}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Cleared up' })).toBeInTheDocument()
    expect(screen.getByText('3 of 3')).toBeInTheDocument()
    expect(screen.getByText('somewhere to work out')).toBeInTheDocument()
    expect(screen.getByText('a gym with weights and cardio machines')).toBeInTheDocument()
    expect(screen.getByText('a scout hall')).toBeInTheDocument()
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
  })
})
