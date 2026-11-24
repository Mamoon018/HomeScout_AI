import {
  clearAuthUser,
  getAuthUser,
  saveAuthUser,
} from '@/features/auth/utils/authUserStore'

describe('authUserStore', () => {
  it('saves and reads user identity from localStorage', () => {
    saveAuthUser({ user_id: 'user-1', user_name: 'Demo User' })

    expect(getAuthUser()).toEqual({
      user_id: 'user-1',
      user_name: 'Demo User',
    })
  })

  it('clears stored identity', () => {
    saveAuthUser({ user_id: 'user-1', user_name: 'Demo User' })
    clearAuthUser()

    expect(getAuthUser()).toBeNull()
  })

  it('returns null for invalid stored JSON', () => {
    localStorage.setItem('homescout.auth.user', '{not-json')

    expect(getAuthUser()).toBeNull()
  })
})
