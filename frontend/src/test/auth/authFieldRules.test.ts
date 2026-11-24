import {
  checkPasswordRules,
  FIELD_MESSAGES,
  isStrongPassword,
  PASSWORD_SYMBOLS,
  validateAge,
  validateConfirmPassword,
  validateEmail,
  validateLoginEmail,
  validateLoginPassword,
  validateNewPassword,
  validateRequired,
} from '@/features/auth/utils/authFieldRules'

describe('password rules (match Supabase: 10+, lower, upper, digit, symbol)', () => {
  it('accepts a password that meets every rule', () => {
    expect(isStrongPassword('Password123!')).toBe(true)
    expect(validateNewPassword('Password123!')).toBeNull()
  })

  it.each([
    ['Pass12!', 'length'],
    ['PASSWORD123!', 'lowercase'],
    ['password123!', 'uppercase'],
    ['Password!!!!', 'digit'],
    ['Password1234', 'symbol'],
  ])('%s misses only the %s rule', (password, missing) => {
    const unmet = checkPasswordRules(password).filter((rule) => !rule.met).map((rule) => rule.id)
    expect(unmet).toEqual([missing])
    expect(validateNewPassword(password)).toBe(FIELD_MESSAGES.passwordRules)
  })

  it('counts every character of the Supabase symbol set as a symbol', () => {
    for (const symbol of PASSWORD_SYMBOLS) {
      expect(isStrongPassword(`Password12${symbol}`)).toBe(true)
    }
  })

  it('does not count a space or letters with accents as a symbol', () => {
    expect(isStrongPassword('Password12 ')).toBe(false)
    expect(isStrongPassword('Password12é')).toBe(false)
  })

  it('requires a password', () => {
    expect(validateNewPassword('')).toBe(FIELD_MESSAGES.required)
  })
})

describe('confirm password', () => {
  it('passes when it matches a strong password', () => {
    expect(validateConfirmPassword('Password123!', 'Password123!')).toBeNull()
  })

  it('fails on a mismatch', () => {
    expect(validateConfirmPassword('Password123?', 'Password123!')).toBe(
      FIELD_MESSAGES.passwordMismatch,
    )
  })

  it('reports the rules first when it is weak itself', () => {
    expect(validateConfirmPassword('short', 'short')).toBe(FIELD_MESSAGES.passwordRules)
  })
})

describe('sign-in password', () => {
  it('only needs to be present', () => {
    expect(validateLoginPassword('')).toBe(FIELD_MESSAGES.required)
    expect(validateLoginPassword('short')).toBeNull()
  })
})

describe('email (@ and a domain ending in .com)', () => {
  it.each(['name@example.com', '  name@example.com  ', 'Name@Example.COM'])('accepts %j', (email) => {
    expect(validateEmail(email)).toBeNull()
  })

  it.each(['name@example.org', 'name@example.com.de', 'nameexample.com', 'name@homescout.ai'])(
    'rejects %j for missing @ or .com',
    (email) => {
      expect(validateEmail(email)).toBe(FIELD_MESSAGES.emailDotCom)
    },
  )

  it.each(['@example.com', 'na me@example.com', 'name@.com'])('rejects %j as a bad format', (email) => {
    expect(validateEmail(email)).toBe(FIELD_MESSAGES.emailFormat)
  })

  it('requires an email', () => {
    expect(validateEmail('   ')).toBe(FIELD_MESSAGES.required)
  })
})

describe('sign-in email (valid format, any domain)', () => {
  it.each(['demo@homescout.ai', 'name@example.org', '  Name@Example.COM  '])('accepts %j', (email) => {
    expect(validateLoginEmail(email)).toBeNull()
  })

  it.each(['demo@homescout', 'nameexample.com', '@example.com'])('rejects %j as a bad format', (email) => {
    expect(validateLoginEmail(email)).toBe(FIELD_MESSAGES.emailFormat)
  })

  it('requires an email', () => {
    expect(validateLoginEmail('   ')).toBe(FIELD_MESSAGES.required)
  })
})

describe('age (whole number, 16 or older)', () => {
  it.each(['16', '25', ' 40 '])('accepts %j', (age) => {
    expect(validateAge(age)).toBeNull()
  })

  it.each(['15', '0', '-20', '16.5', 'abc'])('rejects %j', (age) => {
    expect(validateAge(age)).toBe(FIELD_MESSAGES.age)
  })

  it('requires an age', () => {
    expect(validateAge('')).toBe(FIELD_MESSAGES.required)
  })
})

describe('required fields', () => {
  it('rejects empty or blank values', () => {
    expect(validateRequired('')).toBe(FIELD_MESSAGES.required)
    expect(validateRequired('   ')).toBe(FIELD_MESSAGES.required)
    expect(validateRequired('10001')).toBeNull()
  })
})
