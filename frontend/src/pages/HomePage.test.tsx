import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { saveAuthUser } from '@/features/auth/utils/authUserStore'
import { HomePage } from '@/pages/HomePage'

describe('HomePage', () => {
  it('shows Welcome {user_name}! when identity is stored', () => {
    saveAuthUser({ user_id: 'user-1', user_name: 'Demo User' })

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    )

    expect(
      screen.getByRole('heading', { name: 'Welcome Demo User!' }),
    ).toBeInTheDocument()
    expect(screen.getByText('You are signed in.')).toBeInTheDocument()
  })

  it('does not show a welcome heading when no user name is stored', () => {
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    )

    expect(screen.queryByRole('heading')).not.toBeInTheDocument()
    expect(screen.getByText('You are signed in.')).toBeInTheDocument()
  })
})
