import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useSignup } from '@/features/auth/hooks/useSignup'
import { useSignupCaptcha } from '@/features/auth/hooks/useSignupCaptcha'
import {
  COUNTRIES,
  getCitiesForCountry,
} from '@/features/auth/utils/locationData'
import { SignupCaptcha } from '@/components/signup-captcha'

export function SignupForm({
  className,
  ...props
}: React.ComponentProps<'div'>) {
  const captcha = useSignupCaptcha()
  const { isSubmitting, submitSignup } = useSignup(captcha)
  const [showPassword, setShowPassword] = useState(false)
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [age, setAge] = useState('')
  const [country, setCountry] = useState('')
  const [city, setCity] = useState('')
  const [zipCode, setZipCode] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  const passwordInputType = showPassword ? 'text' : 'password'
  const cityOptions = getCitiesForCountry(country)

  function handleCountryChange(value: string | null) {
    const nextCountry = value ?? ''
    setCountry(nextCountry)
    setCity('')
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    submitSignup({
      fullName,
      email,
      age,
      country,
      city,
      zipCode,
      password,
      confirmPassword,
    })
  }

  return (
    <div className={cn('flex flex-col gap-6', className)} {...props}>
      <Card className="border-border/60 bg-card">
        <CardHeader className="text-center">
          <CardTitle className="text-xl">Create your account</CardTitle>
          <CardDescription>
            Enter your details below to create your account
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit}>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="name">Full Name</FieldLabel>
                <Input
                  id="name"
                  type="text"
                  placeholder="John Doe"
                  required
                  disabled={isSubmitting}
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="email">Email</FieldLabel>
                <Input
                  id="email"
                  type="email"
                  placeholder="m@example.com"
                  required
                  disabled={isSubmitting}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="age">Age</FieldLabel>
                <Input
                  id="age"
                  type="number"
                  min={1}
                  step={1}
                  inputMode="numeric"
                  placeholder="25"
                  required
                  disabled={isSubmitting}
                  value={age}
                  onChange={(e) => setAge(e.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="country">Country</FieldLabel>
                <Select
                  value={country}
                  onValueChange={handleCountryChange}
                  disabled={isSubmitting}
                >
                  <SelectTrigger id="country" className="w-full">
                    <SelectValue placeholder="Select country" />
                  </SelectTrigger>
                  <SelectContent>
                    {COUNTRIES.map((countryName) => (
                      <SelectItem key={countryName} value={countryName}>
                        {countryName}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field>
                <FieldLabel htmlFor="city">City</FieldLabel>
                <Select
                  value={city}
                  onValueChange={(value) => setCity(value ?? '')}
                  disabled={isSubmitting || !country}
                >
                  <SelectTrigger id="city" className="w-full">
                    <SelectValue placeholder="Select city" />
                  </SelectTrigger>
                  <SelectContent>
                    {cityOptions.map((cityName) => (
                      <SelectItem key={cityName} value={cityName}>
                        {cityName}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field>
                <FieldLabel htmlFor="zip-code">Zip code</FieldLabel>
                <Input
                  id="zip-code"
                  type="text"
                  placeholder="10001"
                  required
                  disabled={isSubmitting}
                  value={zipCode}
                  onChange={(e) => setZipCode(e.target.value)}
                />
              </Field>
              <Field>
                <Field className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <Field>
                    <FieldLabel htmlFor="password">Password</FieldLabel>
                    <Input
                      id="password"
                      type={passwordInputType}
                      required
                      disabled={isSubmitting}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="confirm-password">
                      Confirm Password
                    </FieldLabel>
                    <Input
                      id="confirm-password"
                      type={passwordInputType}
                      required
                      disabled={isSubmitting}
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                    />
                  </Field>
                </Field>
                <div className="flex items-center gap-2 pt-2">
                  <Checkbox
                    id="show-password"
                    checked={showPassword}
                    onCheckedChange={(checked) =>
                      setShowPassword(checked === true)
                    }
                    disabled={isSubmitting}
                  />
                  <Label
                    htmlFor="show-password"
                    className="text-sm font-normal text-muted-foreground"
                  >
                    Show password
                  </Label>
                </div>
                <FieldDescription>
                  Must be at least 8 characters long.
                </FieldDescription>
              </Field>
              <SignupCaptcha disabled={isSubmitting} captcha={captcha} />
              <Field>
                <Button
                  type="submit"
                  className="w-full"
                  disabled={isSubmitting || !captcha.hasCaptchaToken}
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="animate-spin" />
                      Creating account...
                    </>
                  ) : (
                    'Create Account'
                  )}
                </Button>
                <FieldDescription className="text-center">
                  Already have an account? <Link to="/auth/login">Sign in</Link>
                </FieldDescription>
              </Field>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
      <FieldDescription className="px-6 text-center">
        By clicking continue, you agree to our <a href="#">Terms of Service</a>{' '}
        and <a href="#">Privacy Policy</a>.
      </FieldDescription>
    </div>
  )
}
