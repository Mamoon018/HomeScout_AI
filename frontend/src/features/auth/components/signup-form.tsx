import { useRef, useState, type FormEvent, type RefObject } from "react";
import { Link } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useSignup } from "@/features/auth/hooks/useSignup";
import { useSignupCaptcha } from "@/features/auth/hooks/useSignupCaptcha";
import { useSignupValidation } from "@/features/auth/hooks/useSignupValidation";
import {
  COUNTRIES,
  getCitiesForCountry,
} from "@/features/auth/utils/locationData";
import { MIN_SIGNUP_AGE } from "@/features/auth/utils/authFieldRules";
import type { SignupField } from "@/features/auth/utils/signupErrors";
import { FieldRulePopover } from "@/features/auth/components/field-rule-popover";
import { PasswordRulesChecklist } from "@/features/auth/components/password-rules-checklist";
import { SignupCaptcha } from "@/features/auth/components/signup-captcha";
import { SubmitHint } from "@/features/auth/components/submit-hint";
import { isCaptchaEnabled } from "@/features/auth/utils/captchaConfig";
import "./signup-form.css";

const SUBMIT_HINT_ID = "signup-submit-hint";

/** The popover id that each field's aria-describedby points at. */
function ruleId(field: SignupField) {
  return `signup-${field}-rule`;
}

/**
 * Sign-up card. Field values live here; useSignupValidation decides which rules each field
 * breaks and which popover is open; useSignup submits.
 *
 * Data path: input → SignupForm → useSignupValidation (rules, popovers, button state)
 *   → submit → useSignup → authApi.signUp → Supabase → useSignup (toasts)
 */
export function SignupForm({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const captcha = useSignupCaptcha();
  const { isSubmitting, submitSignup } = useSignup(captcha);
  const [showPassword, setShowPassword] = useState(false);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [age, setAge] = useState("");
  const [country, setCountry] = useState("");
  const [city, setCity] = useState("");
  const [zipCode, setZipCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const values = { fullName, email, age, country, city, zipCode, password, confirmPassword };
  const validation = useSignupValidation(values);

  // Each popover points at its own field.
  const fullNameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const ageRef = useRef<HTMLInputElement>(null);
  const zipCodeRef = useRef<HTMLInputElement>(null);
  const countryRef = useRef<HTMLButtonElement>(null);
  const cityRef = useRef<HTMLButtonElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmPasswordRef = useRef<HTMLInputElement>(null);

  const passwordInputType = showPassword ? "text" : "password";
  const cityOptions = getCitiesForCountry(country);
  const submitBlocked =
    isSubmitting ||
    !validation.isValid ||
    (isCaptchaEnabled() && !captcha.hasCaptchaToken);

  /** Focus/blur tracking and aria wiring shared by every text input. */
  function fieldProps(field: SignupField) {
    const error = validation.visibleError(field);
    return {
      onFocus: () => validation.fieldFocused(field),
      onBlur: () => validation.fieldLeft(field),
      "aria-invalid": error ? true : undefined,
      "aria-describedby": error ? ruleId(field) : undefined,
    };
  }

  /** Dropdowns have no blur: closing the list counts as leaving the field. */
  function selectOpenChange(field: SignupField) {
    return (open: boolean) =>
      open ? validation.fieldFocused(field) : validation.fieldLeft(field);
  }

  /** The rule popover for a field; shown only while it is the open one. */
  function rulePopover(
    field: SignupField,
    anchor: RefObject<HTMLElement | null>,
    extra?: React.ReactNode,
  ) {
    const error = validation.visibleError(field);
    return (
      <FieldRulePopover
        id={ruleId(field)}
        open={validation.isPopoverOpen(field)}
        anchor={anchor}
        message={error ?? ""}
      >
        {extra}
      </FieldRulePopover>
    );
  }

  function handleCountryChange(value: string | null) {
    const nextCountry = value ?? "";
    setCountry(nextCountry);
    setCity("");
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submitSignup(values);
  }

  return (
    <div className={cn("flex flex-col gap-6", className)} {...props}>
      {/* data-form scopes the compact spacing in signup-form.css to this card. */}
      <Card data-slot="auth-card" data-form="signup" className="border-border/60 bg-card">
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
                  ref={fullNameRef}
                  {...fieldProps("fullName")}
                />
                {rulePopover("fullName", fullNameRef)}
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
                  ref={emailRef}
                  {...fieldProps("email")}
                />
                {rulePopover("email", emailRef)}
              </Field>
              <div className="grid grid-cols-2 gap-4">
                <Field>
                  <FieldLabel htmlFor="age">Age</FieldLabel>
                  <Input
                    id="age"
                    type="number"
                    min={MIN_SIGNUP_AGE}
                    step={1}
                    inputMode="numeric"
                    placeholder="25"
                    required
                    disabled={isSubmitting}
                    value={age}
                    onChange={(e) => setAge(e.target.value)}
                    ref={ageRef}
                    {...fieldProps("age")}
                  />
                  {rulePopover("age", ageRef)}
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
                    ref={zipCodeRef}
                    {...fieldProps("zipCode")}
                  />
                  {rulePopover("zipCode", zipCodeRef)}
                </Field>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <Field>
                  <FieldLabel htmlFor="country">Country</FieldLabel>
                  <Select
                    value={country}
                    onValueChange={handleCountryChange}
                    onOpenChange={selectOpenChange("country")}
                    disabled={isSubmitting}
                  >
                    <SelectTrigger
                      id="country"
                      className="w-full"
                      ref={countryRef}
                      aria-invalid={validation.visibleError("country") ? true : undefined}
                      aria-describedby={
                        validation.visibleError("country") ? ruleId("country") : undefined
                      }
                    >
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
                  {rulePopover("country", countryRef)}
                </Field>
                <Field>
                  <FieldLabel htmlFor="city">City</FieldLabel>
                  <Select
                    value={city}
                    onValueChange={(value) => setCity(value ?? "")}
                    onOpenChange={selectOpenChange("city")}
                    disabled={isSubmitting || !country}
                  >
                    <SelectTrigger
                      id="city"
                      className="w-full"
                      ref={cityRef}
                      aria-invalid={validation.visibleError("city") ? true : undefined}
                      aria-describedby={
                        validation.visibleError("city") ? ruleId("city") : undefined
                      }
                    >
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
                  {rulePopover("city", cityRef)}
                </Field>
              </div>
              <Field>
                <Field className="grid grid-cols-2 gap-4">
                  <Field>
                    <FieldLabel htmlFor="password">Password</FieldLabel>
                    <Input
                      id="password"
                      type={passwordInputType}
                      required
                      disabled={isSubmitting}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      ref={passwordRef}
                      {...fieldProps("password")}
                    />
                    {rulePopover("password", passwordRef, <PasswordRulesChecklist password={password} />)}
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
                      ref={confirmPasswordRef}
                      {...fieldProps("confirmPassword")}
                    />
                    {rulePopover(
                      "confirmPassword",
                      confirmPasswordRef,
                      <PasswordRulesChecklist password={confirmPassword} matchAgainst={password} />,
                    )}
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
                    data-slot="auth-show-password"
                    className="text-sm font-normal text-muted-foreground"
                  >
                    Show password
                  </Label>
                </div>
              </Field>
              <SignupCaptcha disabled={isSubmitting} captcha={captcha} />
              <Field>
                <Button
                  type="submit"
                  data-slot="auth-submit"
                  className="w-full"
                  disabled={submitBlocked}
                  aria-describedby={validation.isValid ? undefined : SUBMIT_HINT_ID}
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="animate-spin" />
                      Creating account...
                    </>
                  ) : (
                    "Create Account"
                  )}
                </Button>
                <SubmitHint id={SUBMIT_HINT_ID} visible={!validation.isValid} />
                <FieldDescription className="text-center">
                  Already have an account? <Link to="/auth/login">Sign in</Link>
                </FieldDescription>
              </Field>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
      <FieldDescription data-slot="auth-legal" className="px-6 text-center">
        By clicking continue, you agree to our <a href="#">Terms of Service</a>{" "}
        and <a href="#">Privacy Policy</a>.
      </FieldDescription>
    </div>
  );
}
