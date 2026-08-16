import { SignupForm } from '@/components/signup-form'

/** Signup page with Linear-inspired split layout and hero heading. */
export function SignupPage() {
  return (
    <div className="min-h-svh bg-background text-foreground">
      <div className="grid min-h-svh lg:grid-cols-2">
        <div className="flex flex-col justify-center px-6 py-12 md:px-12 lg:px-16">
          <h1
            className="max-w-xl text-left text-4xl font-medium leading-[1.1] tracking-[-0.03em] text-foreground md:text-5xl lg:text-6xl"
          >
            Build team of Agents for your Home Scout
          </h1>
        </div>
        <div className="flex items-center justify-center px-6 py-12 md:px-10 lg:px-16">
          <div className="w-full max-w-md">
            <SignupForm />
          </div>
        </div>
      </div>
    </div>
  )
}
