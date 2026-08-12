import { SignupForm } from "@/components/auth/signup-form"
import { useSignup } from "@/features/auth/hooks/useSignup"

export default function SignupPage() {
  const signup = useSignup()

  return (
    <div className="dark relative min-h-svh overflow-hidden bg-background text-foreground">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_left,oklch(0.22_0.04_264),transparent_50%)]" />
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,oklch(1_0_0/3%)_1px,transparent_1px),linear-gradient(to_bottom,oklch(1_0_0/3%)_1px,transparent_1px)] bg-size-[4rem_4rem]" />

      <header className="relative z-10 px-6 py-6 md:px-10">
        <span className="text-sm font-medium tracking-wide text-muted-foreground">
          HomeScout AI
        </span>
      </header>

      <main className="relative z-10 mx-auto flex min-h-[calc(100svh-5rem)] max-w-7xl flex-col gap-10 px-6 pb-10 md:flex-row md:items-center md:gap-16 md:px-10">
        <section className="flex flex-1 flex-col justify-center">
          <h1 className="max-w-xl text-4xl leading-[1.05] font-semibold tracking-tight text-balance md:text-5xl lg:text-6xl">
            Build team of Agents for your Home Scout
          </h1>
          <p className="mt-6 max-w-lg text-base text-muted-foreground md:text-lg">
            Create your account to orchestrate intelligent agents that help you
            scout, evaluate, and act on home opportunities faster.
          </p>
        </section>

        <section className="w-full max-w-xl flex-1 md:max-w-md lg:max-w-lg">
          <SignupForm {...signup} />
        </section>
      </main>
    </div>
  )
}
