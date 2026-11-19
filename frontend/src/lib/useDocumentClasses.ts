import { useLayoutEffect } from 'react'

/**
 * Adds classes to <html> while the calling component is mounted (page themes).
 * On <html> so portaled overlays pick them up; a layout effect so the first
 * paint is already themed.
 */
export function useDocumentClasses(classes: readonly string[]) {
  const key = classes.join(' ')

  useLayoutEffect(() => {
    if (!key) {
      return
    }
    const list = key.split(' ')
    document.documentElement.classList.add(...list)
    return () => document.documentElement.classList.remove(...list)
  }, [key])
}
