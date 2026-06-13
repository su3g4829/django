'use client'

/**
 * 商品變體整理 helper。
 *
 * 這支模組集中處理：
 * - 尺寸排序規則
 * - 顏色 / 尺寸規格轉換
 * - 商品編輯頁使用的變體群組資料
 * - 商品詳情頁依顏色/尺寸找對應 variant
 *
 * 來源：
 * - 前端商品表單與商品詳情頁共用
 * - 型別主要對應 `@/lib/types` 裡的 `Product` / `ProductVariant`
 * - `as const` / `Map` / `Set` 這類 TypeScript 與 JavaScript 標準語法
 */
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

/**
 * 依照常見服飾尺寸順序排序，未知尺寸才退回字串排序。
 *
 * `localeCompare()` 來自 JavaScript String API，
 * 用來做字串排序，比直接使用 `>` / `<` 更適合文字欄位。
 */
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

/**
 * 把 specs_text 裡由系統接手管理的尺寸/顏色行移除。
 *
 * 這樣賣家手動輸入的其他規格仍能保留，但顏色與尺寸由結構化資料欄位統一生成。
 */
export function stripManagedSizeSpecs(rawSpecs: string) {
  return rawSpecs
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !isSizeSpecLine(line) && !isColorSpecLine(line))
    .join('\n')
}

/**
 * 從舊的 specs_text 嘗試抽出基礎顏色，用來相容 legacy 商品資料。
 */
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

/**
 * 將尺寸庫存列做正規化、去重與排序。
 *
 * 這一步會處理：
 * - 前後空白
 * - 大小寫不一致
 * - 重複尺寸
 */
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

/**
 * 將顏色群組正規化，確保每組顏色與尺寸資料都有可預期格式。
 *
 * `map(...).filter(...)` 是 JavaScript 常見的陣列管線寫法：
 * - `map` 先轉成標準形狀
 * - `filter` 再移除完全空白的群組
 */
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

/**
 * 把結構化變體資料重新轉成舊版 variants_text。
 *
 * 仍保留這一步是為了和現有表單 / 後端 legacy payload 相容。
 * 也就是前端主要用結構化 state，送出時再轉回舊文字格式。
 */
export function buildManagedVariantsText(
  defaultSizeRows: SizeStockRow[],
  colorGroups: ColorVariantGroup[],
  productName: string,
  basePrice: string,
  baseCompareAtPrice: string,
  baseImageIndex = '',
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
    lines.push(`${variantName}|${sku}|${basePrice}|${stock}|${normalizedBaseColor}|${row.size}|${baseImageIndex}|${baseCompareAtPrice}`)
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

/**
 * 從商品 payload 反推出編輯頁需要的顏色群組與尺寸列。
 *
 * 這是「把後端格式轉回表單格式」的步驟，讓編輯頁可直接回填既有資料。
 */
export function parseVariantConfigFromProduct(product: Product | null) {
  if (!product?.variants?.length) {
    return {
      defaultSizeRows: [] as SizeStockRow[],
      colorGroups: [] as ColorVariantGroup[],
      baseImageIndex: product?.primary_image_index != null ? String(product.primary_image_index) : '',
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
      baseImageIndex:
        colorlessVariants[0]?.image_index != null
          ? String(colorlessVariants[0].image_index)
          : product.primary_image_index != null
            ? String(product.primary_image_index)
            : '',
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
    baseImageIndex:
      colorlessVariants[0]?.image_index != null
        ? String(colorlessVariants[0].image_index)
        : product.primary_image_index != null
          ? String(product.primary_image_index)
          : '',
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

/**
 * 商品詳情頁切換顏色時，用來找該顏色還有哪些可選尺寸。
 *
 * 使用者先選顏色後，前端再依該顏色過濾有效尺寸，避免顯示不存在的組合。
 */
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
