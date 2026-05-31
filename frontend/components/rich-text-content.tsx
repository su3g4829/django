'use client'

import { useMemo } from 'react'

import { normalizeStoredRichText } from '@/lib/rich-text'

type RichTextContentProps = {
  html: string
  className?: string
}

export function RichTextContent({ html, className = '' }: RichTextContentProps) {
  const safeHtml = useMemo(() => normalizeStoredRichText(html), [html])

  if (!safeHtml) {
    return null
  }

  return <div className={className} dangerouslySetInnerHTML={{ __html: safeHtml }} />
}
