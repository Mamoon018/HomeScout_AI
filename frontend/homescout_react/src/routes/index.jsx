import { createBrowserRouter } from "react-router-dom"
import SignupPage from "@/pages/SignupPage"

/**
 * Maps application URLs to page components.
 */
export const router = createBrowserRouter([
  {
    path: "/signup",
    element: <SignupPage />,
  },
])
