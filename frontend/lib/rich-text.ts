'use client'

import DOMPurify from 'dompurify'

const HTML_TAG_PATTERN = /<\/?[a-z][\s\S]*>/i
const RAW_STATIC_PREFIX = '/static/'
const PROXY_STATIC_PREFIX = '/backend-assets/static/'

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

export function sanitizeRichTextHtml(rawHtml: string) {
  return DOMPurify.sanitize(rawHtml, {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'span', 'a', 'ul', 'ol', 'li', 'blockquote', 'h1', 'h2', 'h3', 'img'],
    ALLOWED_ATTR: ['href', 'target', 'rel', 'src', 'alt', 'title', 'style'],
    FORBID_TAGS: ['script', 'iframe', 'object', 'embed'],
  })
}

function rewriteAssetUrls(html: string, mode: 'to-display' | 'to-storage') {
  if (typeof document === 'undefined' || !html) {
    if (mode === 'to-display') {
      return html.replaceAll(RAW_STATIC_PREFIX, PROXY_STATIC_PREFIX)
    }
    return html.replaceAll(PROXY_STATIC_PREFIX, RAW_STATIC_PREFIX)
  }

  const container = document.createElement('div')
  container.innerHTML = html
  container.querySelectorAll('img').forEach((image) => {
    const src = image.getAttribute('src') ?? ''
    if (mode === 'to-display' && src.startsWith(RAW_STATIC_PREFIX)) {
      image.setAttribute('src', src.replace(RAW_STATIC_PREFIX, PROXY_STATIC_PREFIX))
    }
    if (mode === 'to-storage' && src.startsWith(PROXY_STATIC_PREFIX)) {
      image.setAttribute('src', src.replace(PROXY_STATIC_PREFIX, RAW_STATIC_PREFIX))
    }
  })
  return container.innerHTML
}

export function normalizeStoredRichText(rawValue: string) {
  const trimmed = rawValue.trim()
  if (!trimmed) {
    return ''
  }

  if (HTML_TAG_PATTERN.test(trimmed)) {
    return rewriteAssetUrls(sanitizeRichTextHtml(trimmed), 'to-display')
  }

  return rewriteAssetUrls(sanitizeRichTextHtml(escapeHtml(trimmed).replace(/\r?\n/g, '<br />')), 'to-display')
}

export function prepareRichTextForStorage(rawValue: string) {
  const normalized = normalizeStoredRichText(rawValue)
  if (!normalized) {
    return ''
  }
  return rewriteAssetUrls(normalized, 'to-storage')
}

export function hasMeaningfulRichText(rawValue: string) {
  const normalized = normalizeStoredRichText(rawValue)
  if (!normalized) {
    return false
  }

  const textOnly = normalized
    .replace(/<img\b[^>]*>/gi, ' image ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim()

  return textOnly.length > 0
}
