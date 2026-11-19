import { BikeIcon, CarIcon, FootprintsIcon, TrainFrontIcon, type LucideProps } from 'lucide-react'

import type { TravelMode } from '@/features/r2-proximity/types/r2'

const ICONS = { walk: FootprintsIcon, cycle: BikeIcon, drive: CarIcon, transit: TrainFrontIcon }

export function ModeIcon({ mode, ...props }: LucideProps & { mode: TravelMode }) {
  const Icon = ICONS[mode]
  return <Icon aria-hidden="true" strokeWidth={1.8} {...props} />
}
