import { z } from 'zod'

export const INVALID_INPUT_MESSAGE = 'Invalid Input'

export const loginSchema = z.object({
  email: z.string().min(1).email(),
  password: z.string().min(1),
})

export type LoginFormData = z.infer<typeof loginSchema>
