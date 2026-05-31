'use client'

import { FormEvent, useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'next/navigation'

import { apiFetch } from '@/lib/api'
import { toBackendAssetUrl } from '@/lib/assets'
import {
  STANDARD_SIZE_OPTIONS,
  type ColorVariantGroup,
  type SizeStockRow,
  buildManagedSpecsText,
  buildManagedVariantsText,
  parseVariantConfigFromProduct,
  sanitizeColorVariantGroups,
  sanitizeSizeRows,
  stripManagedSizeSpecs,
  sumSizeRowStock,
} from '@/lib/product-variants'
import { clearSessionDraft, getSessionDraft, setSessionDraft } from '@/lib/session-drafts'
import type { Product } from '@/lib/types'

type EditableProduct = Product & {
  specs_text?: string
}

type ProductEditForm = {
  name: string
  price: string
  compare_at_price: string
  baseColor: string
  stock: string
  brand: string
  category: string
  tags: string
  specs: string
  defaultSizeRows: SizeStockRow[]
  colorGroups: ColorVariantGroup[]
  useSellerShippingRules: boolean
  allowHomeDelivery: boolean
  allowConvenienceStore: boolean
  overrideHomeDeliveryFee: string
  overrideConvenienceStoreFee: string
}

const EMPTY_FORM: ProductEditForm = {
  name: '',
  price: '',
  compare_at_price: '',
  baseColor: '',
  stock: '0',
  brand: '',
  category: '',
  tags: '',
  specs: '',
  defaultSizeRows: [],
  colorGroups: [],
  useSellerShippingRules: true,
  allowHomeDelivery: true,
  allowConvenienceStore: true,
  overrideHomeDeliveryFee: '',
  overrideConvenienceStoreFee: '',
}

function createEmptyColorGroup(index: number, sizeRows: SizeStockRow[] = []): ColorVariantGroup {
  return {
    key: `color-group-${Date.now()}-${index}`,
    color: '',
    price: '',
    compareAtPrice: '',
    imageIndex: '',
    sizeRows: sanitizeSizeRows(sizeRows),
  }
}

function getAvailableSizes(rows: SizeStockRow[]) {
  const normalized = sanitizeSizeRows(rows)
  return STANDARD_SIZE_OPTIONS.filter((size) => !normalized.some((row) => row.size === size))
}

function buildImageIndexOptions(totalImages: number) {
  return Array.from({ length: totalImages }, (_, index) => String(index + 1))
}

function buildFormFromProduct(product: EditableProduct): ProductEditForm {
  const parsed = parseVariantConfigFromProduct(product)
  return {
    name: product.name ?? '',
    price: product.price != null ? String(product.price) : '',
    compare_at_price: product.compare_at_price != null ? String(product.compare_at_price) : '',
    baseColor: parsed.baseColor,
    stock: String(product.stock ?? 0),
    brand: product.brand ?? '',
    category: product.category ?? '',
    tags: Array.isArray(product.tags) ? product.tags.join(', ') : '',
    specs: stripManagedSizeSpecs(product.specs_text ?? ''),
    defaultSizeRows: parsed.defaultSizeRows,
    colorGroups: parsed.colorGroups,
    useSellerShippingRules: product.shipping_profile?.use_seller_rules ?? true,
    allowHomeDelivery: product.shipping_profile?.allow_home_delivery ?? true,
    allowConvenienceStore: product.shipping_profile?.allow_convenience_store ?? true,
    overrideHomeDeliveryFee:
      product.shipping_profile?.override_home_delivery_fee != null
        ? String(product.shipping_profile.override_home_delivery_fee)
        : '',
    overrideConvenienceStoreFee:
      product.shipping_profile?.override_convenience_store_fee != null
        ? String(product.shipping_profile.override_convenience_store_fee)
        : '',
  }
}

function SizeStockEditor({
  rows,
  onAdd,
  onUpdate,
  onRemove,
}: {
  rows: SizeStockRow[]
  onAdd: (size: string) => void
  onUpdate: (size: string, stock: string) => void
  onRemove: (size: string) => void
}) {
  const normalizedRows = useMemo(() => sanitizeSizeRows(rows), [rows])
  const availableSizes = useMemo<string[]>(() => getAvailableSizes(normalizedRows), [normalizedRows])
  const [sizeToAdd, setSizeToAdd] = useState<string>(availableSizes[0] ?? STANDARD_SIZE_OPTIONS[0])

  useEffect(() => {
    if (availableSizes.length && !availableSizes.includes(sizeToAdd)) {
      setSizeToAdd(availableSizes[0])
    }
  }, [availableSizes, sizeToAdd])

  return (
    <div className="stack" style={{ gap: '0.75rem' }}>
      <div className="row" style={{ gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <select
          disabled={!availableSizes.length}
          style={{ maxWidth: '180px' }}
          value={availableSizes.length ? sizeToAdd : ''}
          onChange={(event) => setSizeToAdd(event.target.value)}
        >
          {availableSizes.length ? (
            availableSizes.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))
          ) : (
            <option value="">沒有可新增的尺寸</option>
          )}
        </select>
        <button className="btn btn-secondary" disabled={!availableSizes.length} type="button" onClick={() => onAdd(sizeToAdd)}>
          新增尺寸
        </button>
      </div>

      {!normalizedRows.length ? <div className="muted">尚未設定尺寸庫存。</div> : null}

      {normalizedRows.map((row) => (
        <div
          key={row.size}
          className="card"
          style={{
            padding: '0.75rem 1rem',
            display: 'grid',
            gridTemplateColumns: '90px minmax(0, 1fr) auto',
            alignItems: 'center',
            gap: '0.75rem',
          }}
        >
          <strong>{row.size}</strong>
          <label className="field" style={{ margin: 0 }}>
            <span>庫存</span>
            <input value={row.stock} onChange={(event) => onUpdate(row.size, event.target.value)} />
          </label>
          <button className="btn btn-secondary" type="button" onClick={() => onRemove(row.size)}>
            移除
          </button>
        </div>
      ))}
    </div>
  )
}

export default function SellerProductEditPage() {
  const params = useParams<{ slug: string }>()
  const searchParams = useSearchParams()
  const slug = useMemo(() => params.slug, [params.slug])
  const returnTo = useMemo(() => searchParams.get('returnTo') || '/me/products', [searchParams])
  const draftKey = useMemo(() => `seller-product-edit-${params.slug}`, [params.slug])

  const [mounted, setMounted] = useState(false)
  const [product, setProduct] = useState<EditableProduct | null>(null)
  const [form, setForm] = useState<ProductEditForm>(EMPTY_FORM)
  const [files, setFiles] = useState<FileList | null>(null)
  const [existingImages, setExistingImages] = useState<string[]>([])
  const [removedImages, setRemovedImages] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [draftReady, setDraftReady] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    if (!draftReady) {
      return
    }
    setSessionDraft(draftKey, form)
  }, [draftKey, draftReady, form])

  useEffect(() => {
    if (!mounted) {
      return
    }

    async function loadProduct() {
      try {
        setLoading(true)
        setDraftReady(false)
        setError('')

        const payload = await apiFetch<EditableProduct>(`/me/products/${slug}`)
        const baseForm = buildFormFromProduct(payload)
        const draft = getSessionDraft<ProductEditForm>(draftKey)

        setProduct(payload)
        setExistingImages(payload.images ?? [])
        setRemovedImages([])
        setFiles(null)
        setForm(draft ? { ...baseForm, ...draft } : baseForm)
      } catch (err) {
        setError(err instanceof Error ? err.message : '讀取商品資料失敗。')
      } finally {
        setDraftReady(true)
        setLoading(false)
      }
    }

    void loadProduct()
  }, [draftKey, mounted, slug])

  const normalizedDefaultSizeRows = useMemo(() => sanitizeSizeRows(form.defaultSizeRows), [form.defaultSizeRows])
  const normalizedColorGroups = useMemo(() => sanitizeColorVariantGroups(form.colorGroups), [form.colorGroups])
  const remainingExistingImages = useMemo(
    () => existingImages.filter((image) => !removedImages.includes(image)),
    [existingImages, removedImages],
  )
  const imageIndexOptions = useMemo(
    () => buildImageIndexOptions(remainingExistingImages.length + (files?.length ?? 0)),
    [files, remainingExistingImages.length],
  )
  const computedStock = useMemo(() => {
    if (normalizedColorGroups.length) {
      return String(normalizedColorGroups.reduce((total, group) => total + sumSizeRowStock(group.sizeRows), 0))
    }
    if (normalizedDefaultSizeRows.length) {
      return String(sumSizeRowStock(normalizedDefaultSizeRows))
    }
    return form.stock
  }, [form.stock, normalizedColorGroups, normalizedDefaultSizeRows])

  function addDefaultSize(size: string) {
    if (!size) {
      return
    }
    setForm((current) => ({
      ...current,
      defaultSizeRows: [...current.defaultSizeRows, { size, stock: '0' }],
    }))
  }

  function updateDefaultSize(size: string, stock: string) {
    setForm((current) => ({
      ...current,
      defaultSizeRows: current.defaultSizeRows.map((row) => (row.size === size ? { ...row, stock } : row)),
    }))
  }

  function removeDefaultSize(size: string) {
    setForm((current) => ({
      ...current,
      defaultSizeRows: current.defaultSizeRows.filter((row) => row.size !== size),
    }))
  }

  function addColorGroup(mode: 'copy' | 'blank') {
    setForm((current) => ({
      ...current,
      colorGroups: [
        ...current.colorGroups,
        createEmptyColorGroup(current.colorGroups.length + 1, mode === 'copy' ? current.defaultSizeRows : []),
      ],
    }))
  }

  function updateColorGroup(groupKey: string, updater: (group: ColorVariantGroup) => ColorVariantGroup) {
    setForm((current) => ({
      ...current,
      colorGroups: current.colorGroups.map((group) => (group.key === groupKey ? updater(group) : group)),
    }))
  }

  function removeColorGroup(groupKey: string) {
    setForm((current) => ({
      ...current,
      colorGroups: current.colorGroups.filter((group) => group.key !== groupKey),
    }))
  }

  function addColorGroupSize(groupKey: string, size: string) {
    if (!size) {
      return
    }
    updateColorGroup(groupKey, (group) => ({
      ...group,
      sizeRows: [...group.sizeRows, { size, stock: '0' }],
    }))
  }

  function updateColorGroupSize(groupKey: string, size: string, stock: string) {
    updateColorGroup(groupKey, (group) => ({
      ...group,
      sizeRows: group.sizeRows.map((row) => (row.size === size ? { ...row, stock } : row)),
    }))
  }

  function removeColorGroupSize(groupKey: string, size: string) {
    updateColorGroup(groupKey, (group) => ({
      ...group,
      sizeRows: group.sizeRows.filter((row) => row.size !== size),
    }))
  }

  function moveImage(index: number, direction: -1 | 1) {
    setExistingImages((current) => {
      const nextIndex = index + direction
      if (nextIndex < 0 || nextIndex >= current.length) {
        return current
      }
      const next = [...current]
      const [target] = next.splice(index, 1)
      next.splice(nextIndex, 0, target)
      return next
    })
  }

  function toggleRemoveImage(image: string) {
    setRemovedImages((current) => (current.includes(image) ? current.filter((item) => item !== image) : [...current, image]))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      setSubmitting(true)
      setError('')
      setMessage('')

      const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null
      const targetStatus = submitter?.value === 'active' ? 'active' : 'draft'
      const payload = new FormData()

      if (normalizedColorGroups.some((group) => !group.color.trim())) {
        throw new Error('每個顏色變體都需要填寫顏色名稱。')
      }
      if (normalizedColorGroups.some((group) => !group.price.trim())) {
        throw new Error('每個顏色變體都需要填寫售價。')
      }
      if (normalizedColorGroups.some((group) => !group.sizeRows.length)) {
        throw new Error('每個顏色變體至少需要一個尺寸。')
      }

      payload.append('name', form.name)
      payload.append('price', form.price)
      payload.append('compare_at_price', form.compare_at_price)
      payload.append('stock', computedStock)
      payload.append('brand', form.brand)
      payload.append('category', form.category)
      payload.append('tags', form.tags)
      payload.append('use_seller_shipping_rules', String(form.useSellerShippingRules))
      payload.append('allow_home_delivery', String(form.allowHomeDelivery))
      payload.append('allow_convenience_store', String(form.allowConvenienceStore))
      payload.append('override_home_delivery_fee', form.overrideHomeDeliveryFee)
      payload.append('override_convenience_store_fee', form.overrideConvenienceStoreFee)
      payload.append('specs', buildManagedSpecsText(form.specs, normalizedDefaultSizeRows, normalizedColorGroups, form.baseColor))
      payload.append(
        'variants',
        buildManagedVariantsText(
          normalizedDefaultSizeRows,
          normalizedColorGroups,
          form.name,
          form.price,
          form.compare_at_price,
          form.baseColor,
        ),
      )
      payload.append('status', targetStatus)

      existingImages.forEach((image) => {
        if (!removedImages.includes(image)) {
          payload.append('existing_image_paths', image)
        }
      })
      removedImages.forEach((image) => payload.append('remove_image_paths', image))
      Array.from(files ?? []).forEach((file) => payload.append('images', file))

      const updated = await apiFetch<EditableProduct>(`/me/products/${slug}`, {
        method: 'PUT',
        body: payload,
      })

      const nextSlug = updated.slug
      clearSessionDraft(draftKey)
      setProduct(updated)
      setExistingImages(updated.images ?? [])
      setRemovedImages([])
      setFiles(null)
      setForm(buildFormFromProduct(updated))
      setMessage(targetStatus === 'active' ? '商品已更新並上架。' : '商品草稿已更新。')

      if (nextSlug !== slug) {
        if (returnTo === '/me/products') {
          window.location.href = `/me/products/${nextSlug}`
        } else {
          window.location.href = returnTo
        }
        return
      }
      if (returnTo !== '/me/products') {
        window.location.href = returnTo
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新商品失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <section className="card">讀取中...</section>
  }

  if (!product) {
    return <section className="card">找不到商品資料。</section>
  }

  return (
    <section className="card stack">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>編輯商品</h1>
        <a className="btn btn-secondary" href={returnTo}>
          返回商品列表
        </a>
      </div>

      {error ? <div className="notice">{error}</div> : null}
      {message ? <div className="notice success">{message}</div> : null}

      <form className="grid grid-2" onSubmit={handleSubmit}>
        <label className="field">
          <span>商品名稱</span>
          <input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} />
        </label>
        <label className="field">
          <span>品牌</span>
          <input value={form.brand} onChange={(event) => setForm((current) => ({ ...current, brand: event.target.value }))} />
        </label>

        <label className="field">
          <span>售價</span>
          <input value={form.price} onChange={(event) => setForm((current) => ({ ...current, price: event.target.value }))} />
        </label>
        <label className="field">
          <span>原價</span>
          <input
            value={form.compare_at_price}
            onChange={(event) => setForm((current) => ({ ...current, compare_at_price: event.target.value }))}
          />
        </label>

        <label className="field">
          <span>主體顏色</span>
          <input
            value={form.baseColor}
            onChange={(event) => setForm((current) => ({ ...current, baseColor: event.target.value }))}
            placeholder="例如：白"
          />
        </label>
        <label className="field">
          <span>總庫存</span>
          <input
            disabled={mounted && draftReady && (normalizedDefaultSizeRows.length > 0 || normalizedColorGroups.length > 0)}
            value={computedStock}
            onChange={(event) => setForm((current) => ({ ...current, stock: event.target.value }))}
          />
          <div className="muted">
            {normalizedColorGroups.length
              ? '已有顏色變體時，總庫存會依各顏色與尺寸自動加總。'
              : normalizedDefaultSizeRows.length
                ? '已有尺寸模板時，總庫存會依尺寸庫存自動加總。'
                : '尚未設定尺寸或顏色變體時，可手動輸入總庫存。'}
          </div>
        </label>

        <label className="field">
          <span>分類</span>
          <input value={form.category} onChange={(event) => setForm((current) => ({ ...current, category: event.target.value }))} />
        </label>
        <label className="field">
          <span>標籤</span>
          <input value={form.tags} onChange={(event) => setForm((current) => ({ ...current, tags: event.target.value }))} />
        </label>

        <div className="field" style={{ gridColumn: '1 / -1' }}>
          <span>配送設定</span>
          <div className="grid grid-2">
            <label className="field">
              <span>運費來源</span>
              <select
                value={form.useSellerShippingRules ? 'seller' : 'product'}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    useSellerShippingRules: event.target.value === 'seller',
                  }))
                }
              >
                <option value="seller">沿用賣家運費規則</option>
                <option value="product">商品覆蓋運費</option>
              </select>
            </label>
            <div className="muted" style={{ alignSelf: 'end' }}>
              checkout 會依不同賣家分組，各自計算運費。
            </div>
            <label className="field">
              <span>宅配</span>
              <select
                value={form.allowHomeDelivery ? 'true' : 'false'}
                onChange={(event) =>
                  setForm((current) => ({ ...current, allowHomeDelivery: event.target.value === 'true' }))
                }
              >
                <option value="true">支援</option>
                <option value="false">不支援</option>
              </select>
            </label>
            <label className="field">
              <span>超商取貨</span>
              <select
                value={form.allowConvenienceStore ? 'true' : 'false'}
                onChange={(event) =>
                  setForm((current) => ({ ...current, allowConvenienceStore: event.target.value === 'true' }))
                }
              >
                <option value="true">支援</option>
                <option value="false">不支援</option>
              </select>
            </label>
            {!form.useSellerShippingRules ? (
              <>
                <label className="field">
                  <span>覆蓋宅配運費</span>
                  <input
                    value={form.overrideHomeDeliveryFee}
                    onChange={(event) =>
                      setForm((current) => ({ ...current, overrideHomeDeliveryFee: event.target.value }))
                    }
                    placeholder="留空則沿用賣家"
                  />
                </label>
                <label className="field">
                  <span>覆蓋超商運費</span>
                  <input
                    value={form.overrideConvenienceStoreFee}
                    onChange={(event) =>
                      setForm((current) => ({ ...current, overrideConvenienceStoreFee: event.target.value }))
                    }
                    placeholder="留空則沿用賣家"
                  />
                </label>
              </>
            ) : null}
          </div>
        </div>

        <label className="field" style={{ gridColumn: '1 / -1' }}>
          <span>其他商品規格</span>
          <textarea rows={4} value={form.specs} onChange={(event) => setForm((current) => ({ ...current, specs: event.target.value }))} />
          <div className="muted">每行一組 `key:value`。尺寸與顏色欄位會由變體自動產生。</div>
        </label>

        <div className="field" style={{ gridColumn: '1 / -1' }}>
          <span>預設尺寸模板</span>
          <SizeStockEditor rows={form.defaultSizeRows} onAdd={addDefaultSize} onRemove={removeDefaultSize} onUpdate={updateDefaultSize} />
          <div className="muted">新增顏色變體時，可沿用這組尺寸與庫存。</div>
        </div>

        <div className="field" style={{ gridColumn: '1 / -1' }}>
          <span>顏色變體</span>
          <div className="row" style={{ gap: '0.75rem', flexWrap: 'wrap' }}>
            <button className="btn btn-secondary" type="button" onClick={() => addColorGroup('copy')}>
              新增顏色變體並帶入尺寸
            </button>
            <button className="btn btn-secondary" type="button" onClick={() => addColorGroup('blank')}>
              新增空白顏色變體
            </button>
          </div>

          {!normalizedColorGroups.length ? <div className="muted">尚未建立顏色變體。</div> : null}

          <div className="stack" style={{ gap: '1rem', marginTop: '0.75rem' }}>
            {normalizedColorGroups.map((group, index) => (
              <div className="card stack" key={group.key}>
                <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                  <strong>顏色變體 {index + 1}</strong>
                  <button className="btn btn-secondary" type="button" onClick={() => removeColorGroup(group.key)}>
                    移除顏色
                  </button>
                </div>

                <div className="grid grid-2">
                  <label className="field">
                    <span>顏色名稱</span>
                    <input
                      value={group.color}
                      placeholder="例如：黑"
                      onChange={(event) => updateColorGroup(group.key, (current) => ({ ...current, color: event.target.value }))}
                    />
                  </label>
                  <label className="field">
                    <span>對應圖片編號</span>
                    <select
                      disabled={!imageIndexOptions.length}
                      value={group.imageIndex}
                      onChange={(event) => updateColorGroup(group.key, (current) => ({ ...current, imageIndex: event.target.value }))}
                    >
                      <option value="">未指定</option>
                      {imageIndexOptions.map((option) => (
                        <option key={option} value={option}>
                          第 {option} 張
                        </option>
                      ))}
                    </select>
                    <div className="muted">若你調整商品圖順序，這裡的編號也會跟著改變對應。</div>
                  </label>
                  <label className="field">
                    <span>此顏色售價</span>
                    <input
                      value={group.price}
                      placeholder="請輸入此顏色售價"
                      onChange={(event) => updateColorGroup(group.key, (current) => ({ ...current, price: event.target.value }))}
                    />
                  </label>
                  <label className="field">
                    <span>此顏色原價</span>
                    <input
                      value={group.compareAtPrice}
                      placeholder="沒有原價可留空"
                      onChange={(event) =>
                        updateColorGroup(group.key, (current) => ({ ...current, compareAtPrice: event.target.value }))
                      }
                    />
                  </label>
                </div>

                <SizeStockEditor
                  rows={group.sizeRows}
                  onAdd={(size) => addColorGroupSize(group.key, size)}
                  onRemove={(size) => removeColorGroupSize(group.key, size)}
                  onUpdate={(size, stock) => updateColorGroupSize(group.key, size, stock)}
                />
              </div>
            ))}
          </div>
        </div>

        <div className="field" style={{ gridColumn: '1 / -1' }}>
          <span>現有圖片順序</span>
          {!existingImages.length ? (
            <div className="muted">目前沒有既有圖片。</div>
          ) : (
            <div className="stack" style={{ gap: '1rem' }}>
              {existingImages.map((image, index) => {
                const removed = removedImages.includes(image)
                return (
                  <div className="card stack" key={`${image}-${index}`}>
                    <div className="muted">第 {index + 1} 張</div>
                    <img alt={product.name} className="product-image" src={toBackendAssetUrl(image)} />
                    <div className="row" style={{ gap: '0.75rem', flexWrap: 'wrap' }}>
                      <button className="btn btn-secondary" disabled={index === 0} type="button" onClick={() => moveImage(index, -1)}>
                        往前
                      </button>
                      <button
                        className="btn btn-secondary"
                        disabled={index === existingImages.length - 1}
                        type="button"
                        onClick={() => moveImage(index, 1)}
                      >
                        往後
                      </button>
                      <button className="btn btn-secondary" type="button" onClick={() => toggleRemoveImage(image)}>
                        {removed ? '取消移除' : '移除圖片'}
                      </button>
                    </div>
                    {removed ? <div className="notice">這張圖片會在儲存時刪除。</div> : null}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        <label className="field" style={{ gridColumn: '1 / -1' }}>
          <span>新增圖片</span>
          <input multiple type="file" onChange={(event) => setFiles(event.target.files)} />
        </label>

        <div className="field" style={{ gridColumn: '1 / -1' }}>
          <span>最終圖片順序預覽</span>
          {!remainingExistingImages.length && !files?.length ? (
            <div className="muted">目前沒有圖片。</div>
          ) : (
            <div className="stack">
              {remainingExistingImages.map((image, index) => (
                <div className="muted" key={`${image}-${index}`}>
                  第 {index + 1} 張：既有圖片
                </div>
              ))}
              {Array.from(files ?? []).map((file, index) => (
                <div className="muted" key={`${file.name}-${index}`}>
                  第 {remainingExistingImages.length + index + 1} 張：{file.name}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="field" style={{ gridColumn: '1 / -1' }}>
          <span>目前狀態</span>
          <div className="muted">{product.status_label ?? product.status ?? '未知'}</div>
        </div>

        <div className="row">
          <button className="btn btn-secondary" disabled={submitting} name="submit_status" type="submit" value="draft">
            {submitting ? '儲存中...' : '更新草稿'}
          </button>
          <button className="btn" disabled={submitting} name="submit_status" type="submit" value="active">
            {submitting ? '送出中...' : '更新並上架'}
          </button>
        </div>
      </form>
    </section>
  )
}
