'use client'

const DRAFT_PREFIX = 'store:draft:'

function toDraftKey(key: string) {
  return `${DRAFT_PREFIX}${key}`
}

export function getSessionDraft<T>(key: string): T | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.sessionStorage.getItem(toDraftKey(key))
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

export function setSessionDraft<T>(key: string, value: T) {
  if (typeof window === 'undefined') return
  window.sessionStorage.setItem(toDraftKey(key), JSON.stringify(value))
}

export function clearSessionDraft(key: string) {
  if (typeof window === 'undefined') return
  window.sessionStorage.removeItem(toDraftKey(key))
}

export function clearAllSessionDrafts() {
  if (typeof window === 'undefined') return
  const keys = Object.keys(window.sessionStorage)
  for (const key of keys) {
    if (key.startsWith(DRAFT_PREFIX)) {
      window.sessionStorage.removeItem(key)
    }
  }
}
