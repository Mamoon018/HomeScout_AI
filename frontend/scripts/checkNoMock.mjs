// Production-leak gate: fails the build when the dev mock (src/mocks) reached the bundle.
// The mock carries a unique marker string; finding it in any built file means mock code ships.
// Usage: node scripts/checkNoMock.mjs [dir]   (default: dist)
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const MARKER = 'HOMESCOUT_DEV_MOCK_BACKEND'
const root = process.argv[2] ?? 'dist'

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    return statSync(path).isDirectory() ? files(path) : [path]
  })
}

const leaks = files(root).filter((path) => readFileSync(path).includes(MARKER))

if (leaks.length > 0) {
  for (const path of leaks) {
    console.error(`[mock_leaked_to_prod] dev mock code found in ${relative(process.cwd(), path)}`)
  }
  process.exit(1)
}
console.log(`[checkNoMock] no mock code in ${root}/`)
