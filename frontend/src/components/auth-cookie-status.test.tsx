import { render, screen } from '@testing-library/react'
import { AuthCookieStatus } from '@/components/auth-cookie-status'

describe('AuthCookieStatus', () => {
  it('shows backend send attributes and browser receive presence', () => {
    render(
      <AuthCookieStatus
        sendStatus={{
          sent: true,
          name: 'access_token',
          http_only: true,
          secure: true,
          same_site: 'Strict',
          path: '/',
        }}
        receiveStatus={{
          present: true,
          matches_expected: true,
          name: 'access_token',
        }}
      />,
    )

    expect(screen.getByText('Cookie probe')).toBeTruthy()
    expect(screen.getByText('Strict')).toBeTruthy()
    expect(screen.getByText('Cookie present on request')).toBeTruthy()
    expect(screen.getByText('Matches server token')).toBeTruthy()
  })

  it('explains a failed session probe', () => {
    render(<AuthCookieStatus probeFailed />)

    expect(
      screen.getByText(
        'Session probe failed. Confirm the Vite proxy and backend are running.',
      ),
    ).toBeTruthy()
  })
})
