'use client'

import type { Product, ProductVariant } from '@/lib/types'

export const STANDARD_SIZE_OPTIONS = ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'F'] as const

const SIZE_ORDER_INDEX = new Map<string, number>(STANDARD_SIZE_OPTIONS.map((size, index) => [size, index]))
const SIZE_KEYS = new Set(['size', '尺寸'])
const COLOR_KEYS = new Set(['color', '顏色'])

export type SizeStockRow = {
  size: string
  stock: string
}

export type ColorVariantGroup = {
  key: string
  color: string
  price: string
  compareAtPrice: string
  imageIndex: string
  sizeRows: SizeStockRow[]
}

function normalizeSize(value: string) {
  return value.trim().toUpperCase()
}

function normalizeColor(value: string) {
  return value.trim()
}

export function compareSizes(left: string, right: string) {
  const normalizedLeft = normalizeSize(left)
  const normalizedRight = normalizeSize(right)
  const leftIndex = SIZE_ORDER_INDEX.get(normalizedLeft)
  const rightIndex = SIZE_ORDER_INDEX.get(normalizedRight)

  if (leftIndex != null && rightIndex != null) {
    return leftIndex - rightIndex
  }
  if (leftIndex != null) {
    return -1
  }
  if (rightIndex != null) {
    return 1
  }
  return normalizedLeft.localeCompare(normalizedRight)
}

export function sortSizeValues(values: string[]) {
  return [...values].sort(compareSizes)
}

function getSpecKey(line: string) {
  return line.split(':', 1)[0]?.trim() ?? ''
}

function isSizeSpecLine(line: string) {
  const key = getSpecKey(line)
  return SIZE_KEYS.has(key.toLowerCase()) || SIZE_KEYS.has(key)
}

function isColorSpecLine(line: string) {
  const key = getSpecKey(line)
  return COLOR_KEYS.has(key.toLowerCase()) || COLOR_KEYS.has(key)
}

export function stripManagedSizeSpecs(rawSpecs: string) {
  return rawSpecs
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !isSizeSpecLine(line) && !isColorSpecLine(line))
    .join('\n')
}

export function extractBaseColorFromSpecs(rawSpecs: string) {
  const line = rawSpecs
    .split(/\r?\n/)
    .map((item) => item.trim())
    .find((item) => item && isColorSpecLine(item))

  if (!line) {
    return ''
  }

  const [, value = ''] = line.split(':', 2)
  const [firstColor = ''] = value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)

  return firstColor
}

export function sanitizeSizeRows(rows: SizeStockRow[]) {
  const seen = new Set<string>()
  return rows
    .map((row) => ({
      size: normalizeSize(row.size),
      stock: String(row.stock ?? '').trim(),
    }))
    .filter((row) => {
      if (!row.size || seen.has(row.size)) {
        return false
      }
      seen.add(row.size)
      return true
    })
    .sort((left, right) => compareSizes(left.size, right.size))
}

export function sumSizeRowStock(rows: SizeStockRow[]) {
  return sanitizeSizeRows(rows).reduce((total, row) => total + (Number(row.stock) || 0), 0)
}

export function sanitizeColorVariantGroups(groups: ColorVariantGroup[]) {
  return groups
    .map((group, index) => ({
      key: group.key || `color-group-${index + 1}`,
      color: normalizeColor(group.color),
      price: String(group.price ?? '').trim(),
      compareAtPrice: String(group.compareAtPrice ?? '').trim(),
      imageIndex: String(group.imageIndex ?? '').trim(),
      sizeRows: sanitizeSizeRows(group.sizeRows),
    }))
    .filter((group) => group.color || group.sizeRows.length)
}

function collectManagedSizes(defaultSizeRows: SizeStockRow[], colorGroups: ColorVariantGroup[]) {
  const values = new Set<string>()
  sanitizeSizeRows(defaultSizeRows).forEach((row) => values.add(row.size))
  sanitizeColorVariantGroups(colorGroups).forEach((group) => {
    group.sizeRows.forEach((row) => values.add(row.size))
  })
  return sortSizeValues([...values])
}

function collectManagedColors(baseColor: string, colorGroups: ColorVariantGroup[]) {
  const values = new Set<string>()
  const normalizedBaseColor = normalizeColor(baseColor)
  if (normalizedBaseColor) {
    values.add(normalizedBaseColor)
  }
  sanitizeColorVariantGroups(colorGroups).forEach((group) => {
    if (group.color) {
      values.add(group.color)
    }
  })
  return [...values]
}

export function buildManagedSpecsText(
  rawSpecs: string,
  defaultSizeRows: SizeStockRow[],
  colorGroups: ColorVariantGroup[],
  baseColor = '',
) {
  const lines = stripManagedSizeSpecs(rawSpecs)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)

  const colors = collectManagedColors(baseColor, colorGroups)
  if (colors.length) {
    lines.push(`顏色:${colors.join(',')}`)
  }

  const sizes = collectManagedSizes(defaultSizeRows, colorGroups)
  if (sizes.length) {
    lines.push(`尺寸:${sizes.join(',')}`)
  }

  return lines.join('\n')
}

function buildVariantSku(productName: string, color: string, size: string, sequence: number) {
  const normalizedName = productName
    .trim()
    .replace(/\s+/g, '-')
    .replace(/[^\p{L}\p{N}-]+/gu, '')
    .toUpperCase()
  const normalizedColor = color
    .trim()
    .replace(/\s+/g, '-')
    .replace(/[^\p{L}\p{N}-]+/gu, '')
    .toUpperCase()
  const normalizedSize = normalizeSize(size)
  return [normalizedName || 'PRODUCT', normalizedColor || 'BASE', normalizedSize || `ROW${sequence}`].join('-')
}

export function buildManagedVariantsText(
  defaultSizeRows: SizeStockRow[],
  colorGroups: ColorVariantGroup[],
  productName: string,
  basePrice: string,
  baseCompareAtPrice: string,
  baseColor = '',
) {
  const normalizedDefaultRows = sanitizeSizeRows(defaultSizeRows)
  const normalizedColorGroups = sanitizeColorVariantGroups(colorGroups)
  const normalizedBaseColor = normalizeColor(baseColor)
  const lines: string[] = []

  normalizedDefaultRows.forEach((row, index) => {
    const variantName = normalizedBaseColor ? `${productName}-${normalizedBaseColor}-${row.size}` : `${productName}-${row.size}`
    const sku = buildVariantSku(productName, normalizedBaseColor, row.size, index + 1)
    const stock = row.stock || '0'
    lines.push(`${variantName}|${sku}|${basePrice}|${stock}|${normalizedBaseColor}|${row.size}||${baseCompareAtPrice}`)
  })

  normalizedColorGroups.forEach((group, groupIndex) => {
      const colorLabel = group.color || `Color${groupIndex + 1}`
      group.sizeRows.forEach((row, rowIndex) => {
        const variantName = `${productName}-${colorLabel}-${row.size}`
        const sku = buildVariantSku(productName, colorLabel, row.size, rowIndex + 1)
        const stock = row.stock || '0'
        lines.push(`${variantName}|${sku}|${group.price}|${stock}|${colorLabel}|${row.size}|${group.imageIndex}|${group.compareAtPrice}`)
      })
  })

  return lines.join('\n')
}

export function parseVariantConfigFromProduct(product: Product | null) {
  if (!product?.variants?.length) {
    return {
      defaultSizeRows: [] as SizeStockRow[],
      colorGroups: [] as ColorVariantGroup[],
      baseColor: extractBaseColorFromSpecs(product?.specs_text ?? ''),
    }
  }

  const colorBuckets = new Map<string, ProductVariant[]>()
  const colorlessVariants: ProductVariant[] = []

  product.variants.forEach((variant) => {
    const color = normalizeColor(variant.attributes?.color ?? '')
    if (!color) {
      colorlessVariants.push(variant)
      return
    }
    const bucket = colorBuckets.get(color) ?? []
    bucket.push(variant)
    colorBuckets.set(color, bucket)
  })

  const colorGroups = [...colorBuckets.entries()].map(([color, variants], index) => ({
    key: `color-group-${index + 1}`,
    color,
    price: variants[0]?.price != null ? String(variants[0].price) : '',
    compareAtPrice: variants[0]?.compare_at_price != null ? String(variants[0].compare_at_price) : '',
    imageIndex: variants[0]?.image_index != null ? String(variants[0].image_index) : '',
    sizeRows: sanitizeSizeRows(
      variants.map((variant) => ({
        size: variant.attributes?.size?.trim() ?? '',
        stock: String(variant.stock ?? 0),
      })),
    ),
  }))

  if (colorGroups.length) {
    return {
      defaultSizeRows: sanitizeSizeRows(
        colorlessVariants.map((variant) => ({
          size: variant.attributes?.size?.trim() ?? '',
          stock: String(variant.stock ?? 0),
        })),
      ),
      colorGroups: sanitizeColorVariantGroups(colorGroups),
      baseColor: extractBaseColorFromSpecs(product.specs_text ?? ''),
    }
  }

  return {
    defaultSizeRows: sanitizeSizeRows(
      colorlessVariants.map((variant) => ({
        size: variant.attributes?.size?.trim() ?? '',
        stock: String(variant.stock ?? 0),
      })),
    ),
    colorGroups: [] as ColorVariantGroup[],
    baseColor: extractBaseColorFromSpecs(product.specs_text ?? ''),
  }
}

function normalizeChoice(value: string) {
  return value.trim().toLowerCase()
}

export function findMatchingVariant(
  variants: ProductVariant[] | undefined,
  selectedSize: string,
  selectedColor: string,
) {
  if (!variants?.length) {
    return null
  }

  const normalizedSize = normalizeChoice(selectedSize)
  const normalizedColor = normalizeChoice(selectedColor)

  return (
    variants.find((variant) => {
      const variantSize = normalizeChoice(variant.attributes?.size ?? '')
      const variantColor = normalizeChoice(variant.attributes?.color ?? '')

      const sizeMatches = !normalizedSize || variantSize === normalizedSize
      const colorMatches = !normalizedColor || variantColor === normalizedColor
      return sizeMatches && colorMatches
    }) ?? null
  )
}

export function getAvailableSizesForColor(variants: ProductVariant[] | undefined, selectedColor: string) {
  if (!variants?.length) {
    return []
  }

  const normalizedColor = normalizeChoice(selectedColor)
  const sizes = new Set<string>()
  variants.forEach((variant) => {
    const variantColor = normalizeChoice(variant.attributes?.color ?? '')
    const variantSize = variant.attributes?.size?.trim() ?? ''
    if (!variantSize) {
      return
    }
    if (normalizedColor && variantColor !== normalizedColor) {
      return
    }
    sizes.add(variantSize)
  })
  return sortSizeValues([...sizes])
}
