'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'next/navigation'

import { apiFetch, dispatchAppBootstrapRefresh } from '@/lib/api'
import { toBackendAssetUrl } from '@/lib/assets'
import { findMatchingVariant, getAvailableSizesForColor, stripManagedSizeSpecs } from '@/lib/product-variants'
import type {
  PriceComparisonPayload,
  PriceComparisonRefreshPayload,
  Product,
  Question,
  Review,
} from '@/lib/types'

/**
 * 商品詳情頁會同時載入多份關聯資料：
 * - 商品本體
 * - 評論
 * - 問答
 * - 推薦商品
 * - 特定商品的比價資料
 *
 * 這頁是互動最重的商品頁，因此把所有局部表單狀態都集中在同一個 client component 管理。
 */
type ProductRecommendationsPayload = {
  similar: Product[]
  also_bought: Product[]
}

type ReviewListPayload = {
  items: Review[]
}

type QuestionListPayload = {
  items: Question[]
}

type ReviewFormState = {
  rating: number
  title: string
  body: string
}

type QuestionFormState = {
  title: string
  body: string
}

const INITIAL_REVIEW_FORM: ReviewFormState = {
  rating: 5,
  title: '',
  body: '',
}

const INITIAL_QUESTION_FORM: QuestionFormState = {
  title: '',
  body: '',
}

/**
 * 商品詳情頁。
 *
 * 頁面責任：
 * 1. 以 slug 載入商品與其周邊內容
 * 2. 管理變體、主圖、數量等購買狀態
 * 3. 提供評論、提問、回答、收藏、比較等互動
 */
export default function ProductDetailPage() {
  const params = useParams<{ slug: string }>()
  // useParams 回傳的 slug 可能在 render 期間重新建立物件，先 memo 成穩定值。
  const slug = useMemo(() => params.slug, [params.slug])

  // 這幾個 state 分別對應商品頁的主要資料區塊。
  const [product, setProduct] = useState<Product | null>(null)
  const [reviews, setReviews] = useState<Review[]>([])
  const [questions, setQuestions] = useState<Question[]>([])
  const [recommendations, setRecommendations] = useState<ProductRecommendationsPayload>({ similar: [], also_bought: [] })
  const [priceComparison, setPriceComparison] = useState<PriceComparisonPayload | null>(null)

  // 互動狀態：訊息、送出中、比價刷新中、收藏/比較開關。
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [priceRefreshing, setPriceRefreshing] = useState(false)
  const [favoriteActive, setFavoriteActive] = useState(false)
  const [compareActive, setCompareActive] = useState(false)

  const [qty, setQty] = useState(1)
  const [selectedColor, setSelectedColor] = useState('')
  const [selectedSize, setSelectedSize] = useState('')
  const [activeImage, setActiveImage] = useState('')

  // 三種小表單：評論、提問、回答草稿。
  const [reviewForm, setReviewForm] = useState<ReviewFormState>(INITIAL_REVIEW_FORM)
  const [questionForm, setQuestionForm] = useState<QuestionFormState>(INITIAL_QUESTION_FORM)
  const [answerDrafts, setAnswerDrafts] = useState<Record<number, string>>({})

  useEffect(() => {
    /**
     * 首次進頁時平行載入四份資料。
     * 比價只針對特定商品開啟，避免所有商品頁都額外打一次外部比較 API。
     */
    async function load() {
      try {
        setLoading(true)
        setError('')

        const [productPayload, reviewPayload, questionPayload, recommendationPayload] = await Promise.all([
          apiFetch<Product>(`/products/${slug}/`),
          apiFetch<ReviewListPayload>(`/products/${slug}/reviews/`),
          apiFetch<QuestionListPayload>(`/products/${slug}/questions/`),
          apiFetch<ProductRecommendationsPayload>(`/products/${slug}/recommendations/`),
        ])

        const shouldShowPriceComparison = Boolean(productPayload.price_compare_enabled)
        const nextPriceComparison = shouldShowPriceComparison
          ? await apiFetch<PriceComparisonPayload>(`/products/${slug}/price-compare/`)
          : null

        const initialVariant = productPayload.default_variant ?? productPayload.variants?.[0] ?? null

        setProduct(productPayload)
        setReviews(reviewPayload.items ?? [])
        setQuestions(questionPayload.items ?? [])
        setRecommendations(recommendationPayload)
        setPriceComparison(nextPriceComparison)
        setFavoriteActive(Boolean(productPayload.is_favorite))
        setCompareActive(false)
        setQty(1)
        setSelectedColor(initialVariant?.attributes?.color ?? productPayload.color_options?.[0] ?? '')
        setSelectedSize(initialVariant?.attributes?.size ?? productPayload.size_options?.[0] ?? '')
      } catch (err) {
        setError(err instanceof Error ? err.message : '讀取商品資料失敗。')
      } finally {
        setLoading(false)
      }
    }

    void load()
  }, [slug])

  const selectedVariant = useMemo(
    () => findMatchingVariant(product?.variants, selectedSize, selectedColor),
    [product?.variants, selectedColor, selectedSize],
  )

  // 顏色切換後，可選尺寸會跟著改變，因此尺寸選項要從變體即時計算。
  const sizeChoices = useMemo(
    () => getAvailableSizesForColor(product?.variants, selectedColor),
    [product?.variants, selectedColor],
  )

  const colorChoices = product?.color_options ?? []
  // 規格文案會去除由系統自動管理的尺寸庫存片段，避免前端重複顯示。
  const detailSpecsText = useMemo(() => stripManagedSizeSpecs(product?.specs_text ?? ''), [product?.specs_text])

  const selectedColorImage = useMemo(() => {
    if (!product?.images?.length || !selectedColor || !colorChoices.length) {
      return ''
    }

    const normalizedSelectedColor = selectedColor.trim()
    const imageMatchedByName =
      product.images.find((image) => {
        try {
          return decodeURIComponent(image).includes(normalizedSelectedColor)
        } catch {
          return image.includes(normalizedSelectedColor)
        }
      }) ?? ''

    if (imageMatchedByName) {
      return imageMatchedByName
    }

    const colorIndex = colorChoices.findIndex((color) => color.trim() === normalizedSelectedColor)
    return colorIndex >= 0 ? (product.images[colorIndex] ?? '') : ''
  }, [colorChoices, product?.images, selectedColor])

  // 圖庫永遠優先顯示目前選中變體的圖，再接一般商品圖。
  const galleryImages = useMemo(() => {
    const leadImage =
      selectedVariant?.image ||
      selectedVariant?.image_path_snapshot ||
      selectedColorImage ||
      product?.primary_image ||
      product?.images?.[0] ||
      ''
    const ordered = [leadImage, ...(product?.images ?? [])].filter(Boolean)
    return ordered.filter((image, index) => ordered.indexOf(image) === index)
  }, [product?.images, product?.primary_image, selectedColorImage, selectedVariant?.image, selectedVariant?.image_path_snapshot])

  useEffect(() => {
    // 如果顏色切換後原本尺寸已無效，就自動切回第一個合法尺寸。
    if (!sizeChoices.length) {
      return
    }
    if (!selectedSize || !sizeChoices.includes(selectedSize)) {
      setSelectedSize(sizeChoices[0])
    }
  }, [selectedSize, sizeChoices])

  useEffect(() => {
    // 每次圖庫內容改變時，預設主圖跟著切到第一張。
    setActiveImage(galleryImages[0] ?? '')
  }, [galleryImages])

  // 這些 display 變數都是為了讓 JSX 不直接散落太多判斷邏輯。
  const displayPrice = selectedVariant?.price ?? product?.price ?? 0
  const displayCompareAt = selectedVariant ? (selectedVariant.compare_at_price ?? null) : (product?.compare_at_price ?? null)
  const displayDiscountPercent =
    displayCompareAt && displayCompareAt > displayPrice ? Math.round(((displayCompareAt - displayPrice) / displayCompareAt) * 100) : 0
  const displayStock = selectedVariant?.stock ?? product?.stock ?? null
  const variantId = selectedVariant?.external_variant_id || selectedVariant?.id || ''
  const variantName = selectedVariant?.name ?? ''
  const recommendationItems = [...recommendations.similar, ...recommendations.also_bought]
  const sellerLabel =
    product?.owner_display_name || product?.owner_username
      ? `${product?.owner_display_name || product?.owner_username}${product?.owner_username ? ` (@${product.owner_username})` : ''}`
      : ''

  function setSuccess(text: string) {
    setMessage(text)
    setError('')
  }

  /**
   * 加入購物車時會把目前選到的變體資訊一起送出。
   * 如果商品沒有變體，variantId / variantName 會是空值，後端會以商品本體處理。
   */
  async function addToCart() {
    try {
      setSubmitting(true)
      setError('')

      const payload = await apiFetch<{ detail?: string; item_count?: number }>('/cart/items/', {
        method: 'POST',
        body: JSON.stringify({
          slug,
          qty,
          variant_id: variantId,
          variant_name: variantName,
        }),
      })

      dispatchAppBootstrapRefresh({ cart_count: payload.item_count })
      setSuccess(payload.detail ?? '已加入購物車。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '加入購物車失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  // 收藏狀態以後端回傳為準，成功後同步刷新 header 收藏數量。
  async function toggleFavorite() {
    try {
      const payload = await apiFetch<{ active: boolean; favorite_count: number }>(`/products/${slug}/favorite/`, { method: 'POST' })
      setFavoriteActive(payload.active)
      dispatchAppBootstrapRefresh({ favorite_count: payload.favorite_count })
      setSuccess(payload.active ? '已加入收藏。' : '已取消收藏。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新收藏失敗。')
    }
  }

  // 比較清單可能觸發舊商品被擠出，因此 success 訊息會帶出 removed slug。
  async function toggleCompare() {
    try {
      const payload = await apiFetch<{ active: boolean; removed_slug?: string | null }>(`/products/${slug}/compare/`, {
        method: 'POST',
      })
      setCompareActive(payload.active)
      if (payload.removed_slug) {
        setSuccess(`比較清單已滿，已移除 ${payload.removed_slug}。`)
      } else {
        setSuccess(payload.active ? '已加入比較清單。' : '已從比較清單移除。')
      }
      dispatchAppBootstrapRefresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新比較清單失敗。')
    }
  }

  // 評論送出後直接把新評論插到前端清單最上方，避免再重抓全部列表。
  async function submitReview(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      const payload = await apiFetch<Review>(`/products/${slug}/reviews/`, {
        method: 'POST',
        body: JSON.stringify(reviewForm),
      })
      setReviews((current) => [payload, ...current])
      setReviewForm(INITIAL_REVIEW_FORM)
      setSuccess('評論已送出。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '送出評論失敗。')
    }
  }

  // 提問送出後沿用相同模式，把新問題插回目前列表。
  async function submitQuestion(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      const payload = await apiFetch<Question>(`/products/${slug}/questions/`, {
        method: 'POST',
        body: JSON.stringify(questionForm),
      })
      setQuestions((current) => [payload, ...current])
      setQuestionForm(INITIAL_QUESTION_FORM)
      setSuccess('問題已送出。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '送出問題失敗。')
    }
  }

  // 回答只更新單一問題節點，避免整份 questions 重抓。
  async function submitAnswer(questionId: number) {
    const body = (answerDrafts[questionId] || '').trim()
    if (!body) {
      return
    }

    try {
      const payload = await apiFetch<Question>(`/products/${slug}/questions/${questionId}/answers/`, {
        method: 'POST',
        body: JSON.stringify({ body }),
      })
      setQuestions((current) => current.map((question) => (question.id === questionId ? payload : question)))
      setAnswerDrafts((current) => ({ ...current, [questionId]: '' }))
      setSuccess('回答已送出。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '送出回答失敗。')
    }
  }

  // 比價刷新是手動操作，避免商品頁每次 render 都去打外部來源。
  async function refreshPriceComparison() {
    try {
      setPriceRefreshing(true)
      const payload = await apiFetch<PriceComparisonRefreshPayload>(`/products/${slug}/price-compare/refresh/`, {
        method: 'POST',
      })
      setPriceComparison(payload.result)
      setSuccess(payload.detail)
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新比價失敗。')
    } finally {
      setPriceRefreshing(false)
    }
  }

  if (loading) {
    return <section className="card">讀取中...</section>
  }

  if (!product) {
    return <section className="card">找不到商品。</section>
  }

  return (
    <div className="stack">
      <section className="card stack">
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem' }}>
          <div className="stack">
            <h1>{product.name}</h1>
            <div className="muted">
              {product.brand && product.brand.toLowerCase() !== 'none' ? `${product.brand} / ${product.category}` : product.category}
            </div>
            {sellerLabel ? <div className="muted">賣家：{sellerLabel}</div> : null}
            {product.tags?.length ? <div className="muted">標籤：{product.tags.join('、')}</div> : null}
          </div>
          <div className="stack" style={{ alignItems: 'flex-end' }}>
            <div>
              <strong>${displayPrice.toFixed(2)}</strong>
              {displayCompareAt ? <span className="muted"> / 原價 ${displayCompareAt.toFixed(2)}</span> : null}
            </div>
            {displayDiscountPercent ? <span className="badge">-{displayDiscountPercent}%</span> : null}
          </div>
        </div>

        {error ? <div className="notice">{error}</div> : null}
        {message ? <div className="notice success">{message}</div> : null}
      </section>

      <div className="grid grid-2">
        <section className="card stack">
          {activeImage ? <img alt={product.name} className="product-image" src={toBackendAssetUrl(activeImage)} /> : <div className="product-image" />}

          {galleryImages.length > 1 ? (
            <div className="row" style={{ gap: '0.75rem', flexWrap: 'wrap' }}>
              {galleryImages.map((image, index) => {
                const selected = image === activeImage
                return (
                  <button
                    key={`${image}-${index}`}
                    className="btn btn-secondary"
                    style={{ borderWidth: selected ? '2px' : '1px' }}
                    type="button"
                    onClick={() => setActiveImage(image)}
                  >
                    圖 {index + 1}
                  </button>
                )
              })}
            </div>
          ) : null}

          {(selectedVariant?.image || selectedVariant?.image_path_snapshot) ? <div className="muted">目前顏色已切換到對應圖片。</div> : null}
          {colorChoices.length ? <div className="muted">顏色: {colorChoices.join(', ')}</div> : null}
          {detailSpecsText ? <pre className="muted" style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{detailSpecsText}</pre> : null}
        </section>

        <section className="card stack">
          {colorChoices.length ? (
            <div className="stack">
              <span>顏色</span>
              <div className="row" style={{ gap: '0.75rem', flexWrap: 'wrap' }}>
                {colorChoices.map((color) => (
                  <button
                    key={color}
                    className={selectedColor === color ? 'btn-primary' : 'btn btn-secondary'}
                    type="button"
                    onClick={() => setSelectedColor(color)}
                  >
                    {color}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {(sizeChoices.length || product.size_options?.length) ? (
            <div className="stack">
              <span>尺寸</span>
              <div className="row" style={{ gap: '0.75rem', flexWrap: 'wrap' }}>
                {(sizeChoices.length ? sizeChoices : product.size_options ?? []).map((size) => (
                  <button
                    key={size}
                    className={selectedSize === size ? 'btn-primary' : 'btn btn-secondary'}
                    type="button"
                    onClick={() => setSelectedSize(size)}
                  >
                    {size}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          <div className="stack">
            {selectedColor ? <div className="muted">目前顏色：{selectedColor}</div> : null}
            {selectedSize ? <div className="muted">目前尺寸：{selectedSize}</div> : null}
            {displayStock != null ? (
              <div className="muted">庫存：{displayStock}</div>
            ) : product.stock_display ? (
              <div className="muted">{product.stock_display}</div>
            ) : null}
          </div>

          <label className="stack">
            <span>數量</span>
            <input min={1} type="number" value={qty} onChange={(event) => setQty(Math.max(1, Number(event.target.value) || 1))} />
          </label>

          <div className="row" style={{ gap: '0.75rem', flexWrap: 'wrap' }}>
            <button className="btn-primary" disabled={submitting} type="button" onClick={addToCart}>
              {submitting ? '加入中...' : '加入購物車'}
            </button>
            <button className="btn" type="button" onClick={toggleFavorite}>
              {favoriteActive ? '取消收藏' : '加入收藏'}
            </button>
            <button className="btn" type="button" onClick={toggleCompare}>
              {compareActive ? '取消比較' : '加入比較'}
            </button>
          </div>
        </section>
      </div>

      {priceComparison ? (
        <section className="card stack">
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
            <h2>價格比較</h2>
            <button className="btn" disabled={priceRefreshing} type="button" onClick={refreshPriceComparison}>
              {priceRefreshing ? '更新中...' : '重新抓價'}
            </button>
          </div>
          <div className="muted">
            本站：{priceComparison.currency} {priceComparison.our_price} / 最低價：{priceComparison.currency} {priceComparison.lowest_price} / 更新時間：
            {priceComparison.last_refreshed_at_display ?? priceComparison.last_refreshed_at}
          </div>

          {priceComparison.query ? <div className="muted">關鍵字：{priceComparison.query}</div> : null}

          {!priceComparison.items.length ? (
            <div className="muted">目前沒有外站比價資料。</div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>平台</th>
                  <th>商品</th>
                  <th>價格</th>
                  <th>價差</th>
                </tr>
              </thead>
              <tbody>
                {priceComparison.items.map((item) => (
                  <tr key={`${item.site}-${item.url}`}>
                    <td>{item.site_label}</td>
                    <td>
                      {item.url ? (
                        <a href={item.url} rel="noreferrer" target="_blank">
                          {item.title}
                        </a>
                      ) : (
                        <span>{item.title || '未找到符合商品'}</span>
                      )}
                      {item.note ? <div className="muted">{item.note}</div> : null}
                    </td>
                    <td>{item.status === 'matched' ? `${item.currency} ${item.price}` : '-'}</td>
                    <td>{item.status === 'matched' ? `${item.diff_amount > 0 ? '+' : ''}${item.diff_amount} (${item.diff_percent}%)` : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      ) : null}

      <section className="card stack">
        <h2>評論</h2>
        <form className="stack" onSubmit={submitReview}>
          <label className="stack">
            <span>評分</span>
            <select value={reviewForm.rating} onChange={(event) => setReviewForm((current) => ({ ...current, rating: Number(event.target.value) }))}>
              {[5, 4, 3, 2, 1].map((rating) => (
                <option key={rating} value={rating}>
                  {rating}
                </option>
              ))}
            </select>
          </label>
          <label className="stack">
            <span>標題</span>
            <input value={reviewForm.title} onChange={(event) => setReviewForm((current) => ({ ...current, title: event.target.value }))} />
          </label>
          <label className="stack">
            <span>內容</span>
            <textarea rows={4} value={reviewForm.body} onChange={(event) => setReviewForm((current) => ({ ...current, body: event.target.value }))} />
          </label>
          <button className="btn" type="submit">
            送出評論
          </button>
        </form>

        {!reviews.length ? (
          <div className="muted">目前還沒有評論。</div>
        ) : (
          reviews.map((review) => (
            <div className="card stack" key={review.id}>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <strong>{review.title}</strong>
                <span className="badge">{review.rating} / 5</span>
              </div>
              <div className="muted">
                {review.author} / {review.created_at_display ?? review.created_at}
              </div>
              <div>{review.body}</div>
            </div>
          ))
        )}
      </section>

      <section className="card stack">
        <h2>問答</h2>
        <form className="stack" onSubmit={submitQuestion}>
          <label className="stack">
            <span>問題標題</span>
            <input value={questionForm.title} onChange={(event) => setQuestionForm((current) => ({ ...current, title: event.target.value }))} />
          </label>
          <label className="stack">
            <span>問題內容</span>
            <textarea rows={4} value={questionForm.body} onChange={(event) => setQuestionForm((current) => ({ ...current, body: event.target.value }))} />
          </label>
          <button className="btn" type="submit">
            送出問題
          </button>
        </form>

        {!questions.length ? (
          <div className="muted">目前還沒有問答。</div>
        ) : (
          questions.map((question) => (
            <div className="card stack" key={question.id}>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <strong>{question.title}</strong>
                <span className="badge">回答 {question.answer_count ?? question.answers?.length ?? 0}</span>
              </div>
              <div className="muted">
                {question.author} / {question.created_at_display ?? question.created_at}
              </div>
              <div>{question.body}</div>

              {question.answers?.length ? (
                <div className="stack">
                  {question.answers.map((answer) => (
                    <div className="card" key={answer.id}>
                      <strong>{answer.is_seller_reply ? `賣家回覆 (${answer.author})` : answer.author}</strong>
                      <div className="muted">{answer.created_at_display ?? answer.created_at}</div>
                      <div>{answer.body}</div>
                    </div>
                  ))}
                </div>
              ) : null}

              <div className="stack">
                <textarea
                  placeholder="輸入你的回答"
                  rows={3}
                  value={answerDrafts[question.id] || ''}
                  onChange={(event) => setAnswerDrafts((current) => ({ ...current, [question.id]: event.target.value }))}
                />
                <button className="btn" type="button" onClick={() => void submitAnswer(question.id)}>
                  送出回答
                </button>
              </div>
            </div>
          ))
        )}
      </section>

      <section className="card stack">
        <h2>推薦商品</h2>
        {!recommendationItems.length ? (
          <div className="muted">目前沒有推薦商品。</div>
        ) : (
          <div className="grid grid-2">
            {recommendationItems.map((item) => (
              <Link className="card stack" href={`/products/${item.slug}`} key={item.slug}>
                <strong>{item.name}</strong>
                <div className="muted">
                  {item.brand} / {item.category}
                </div>
                <div>{item.price_range_label ?? `$${item.price.toFixed(2)}`}</div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
