import fs from 'node:fs'
import path from 'node:path'

import { TAXONOMY_GROUPS } from '@/features/r1-interpretation/utils/taxonomyGroups'
import { isTaxonomyNode, taxonomyStyle } from '@/features/r1-interpretation/utils/taxonomyStyle'

/** The backend's own list, read from its source: the one place the taxonomy is defined. */
function backendNodes(): { group: string; node: string }[] {
  const file = path.resolve(
    import.meta.dirname,
    '../../../../../backend/src/services/deep_search/feature_schemas/amenity_taxonomy.py',
  )
  const source = fs.readFileSync(file, 'utf-8')
  const body = source.split('AMENITY_TAXONOMY_NODES: tuple[str, ...] = (')[1].split('\n)')[0]
  const found: { group: string; node: string }[] = []
  let group = ''
  for (const raw of body.split('\n')) {
    const line = raw.trim()
    if (line.startsWith('# ')) {
      group = line.slice(2)
    }
    const node = /^"([a-z0-9_]+)",/.exec(line)?.[1]
    if (node) {
      found.push({ group, node })
    }
  }
  return found
}

describe('taxonomy style', () => {
  it('has the same groups and nodes as the backend taxonomy', () => {
    const backend = backendNodes()
    expect(backend.length).toBeGreaterThan(400)

    const ours = Object.entries(TAXONOMY_GROUPS).flatMap(([group, nodes]) =>
      nodes.map((node) => ({ group, node })),
    )
    expect(ours).toEqual(backend)
  })

  it('gives every backend node an icon and a colour family', () => {
    for (const { node } of backendNodes()) {
      const style = taxonomyStyle(node)
      expect(isTaxonomyNode(node)).toBe(true)
      expect(style.icon).toBeDefined()
      expect(['home', 'go', 'daily', 'calm']).toContain(style.family)
    }
  })

  it('tints a kind of place by its group, with its own icon where one reads better', () => {
    expect(taxonomyStyle('transit_station').family).toBe('go')
    expect(taxonomyStyle('primary_school').family).toBe('home')
    expect(taxonomyStyle('supermarket').family).toBe('daily')
    expect(taxonomyStyle('swimming_pool').icon).not.toBe(taxonomyStyle('gym').icon)
  })

  it('still styles a node the list does not know, by reading its words', () => {
    expect(isTaxonomyNode('rooftop_garden')).toBe(false)
    const style = taxonomyStyle('rooftop_garden')
    expect(style.icon).toBeDefined()
    expect(['home', 'go', 'daily', 'calm']).toContain(style.family)
  })
})
