import { afterEach } from "vitest"
import { cleanup } from "@testing-library/react"
import { toast } from "sonner"
import "@testing-library/jest-dom/vitest"

afterEach(() => {
  cleanup()
  toast.dismiss()
})
