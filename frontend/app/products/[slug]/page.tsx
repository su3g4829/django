'use client'

/**
 * 商品詳情頁。
 *
 * 這一頁會顯示：
 * - 商品主資訊
 * - 加入購物車
 * - 評論
 * - 問答
 * - 推薦商品
 * - 模擬比價資料
 *
 * 主要 API：
 * - GET `/api/v1/products/:slug/`
 * - GET `/api/v1/products/:slug/recommendations/`
 * - GET/POST `/api/v1/products/:slug/reviews/`
 * - GET/POST `/api/v1/products/:slug/questions/`
 * - POST `/api/v1/products/:slug/questions/:question_id/answers/`
 * - POST `/api/v1/cart/items/`
 * - GET `/api/v1/products/:slug/price-compare/`
 * - POST `/api/v1/products/:slug/price-compare/refresh/`
 */

import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { PriceComparisonPayload, PriceComparisonRefreshPayload, Product, Question, Review } from '@/lib/types'

type ProductDetailPayload = Product & {
  variants?: Array<{ id: string; name: string; price: number; stock: number }>
  specs?: Record<string, string>
}

type RecommendationPayload = {
  similar: Product[]
  also_bought: Product[]
}

type ReviewListPayload = { items: Review[] }
type QuestionListPayload = { items: Question[] }

export default function ProductDetailPage() {
  const params = useParams<{ slug: string }>()
  /** 目前頁面的商品 slug。 */
  const slug = useMemo(() => params.slug, [params.slug])

  /** 商品主資料。 */
  const [product, setProduct] = useState<ProductDetailPayload | null>(null)
  /** 推薦商品資料。 */
  const [recommendations, setRecommendations] = useState<RecommendationPayload | null>(null)
  /** 評論列表。 */
  const [reviews, setReviews] = useState<Review[]>([])
  /** 問答列表。 */
  const [questions, setQuestions] = useState<Question[]>([])
  /** 模擬比價結果。 */
  const [priceCompare, setPriceCompare] = useState<PriceComparisonPayload | null>(null)

  /** 目前選中的變體 id。 */
  const [variantId, setVariantId] = useState('')
  /** 加入購物車數量。 */
  const [qty, setQty] = useState(1)

  /** 全頁訊息。 */
  const [message, setMessage] = useState('')
  /** 全頁錯誤訊息。 */
  const [error, setError] = useState('')
  /** 初始載入狀態。 */
  const [loading, setLoading] = useState(true)
  /** 表單送出或刷新中的狀態。 */
  const [submitting, setSubmitting] = useState(false)

  /** 評論表單。 */
  const [reviewForm, setReviewForm] = useState({ rating: 5, title: '', body: '' })
  /** 發問表單。 */
  const [questionForm, setQuestionForm] = useState({ title: '', body: '' })
  /** 回答表單，key 是 question id。 */
  const [answerForms, setAnswerForms] = useState<Record<number, string>>({})

  /**
   * 一次載入商品頁全部需要的資料。
   *
   * 包含：
   * - 商品主資料
   * - 推薦商品
   * - 評論
   * - 問答
   * - 模擬比價
   */
  async function loadAll() {
    setLoading(true)
    try {
      const [productPayload, recommendationPayload, reviewPayload, questionPayload, comparePayload] = await Promise.all([
        apiFetch<ProductDetailPayload>(`/products/${slug}/`),
        apiFetch<RecommendationPayload>(`/products/${slug}/recommendations/`).catch(() => ({ similar: [], also_bought: [] })),
        apiFetch<ReviewListPayload>(`/products/${slug}/reviews/`).catch(() => ({ items: [] })),
        apiFetch<QuestionListPayload>(`/products/${slug}/questions/`).catch(() => ({ items: [] })),
        apiFetch<PriceComparisonPayload>(`/products/${slug}/price-compare/`).catch(() => null),
      ])

      setProduct(productPayload)
      setRecommendations(recommendationPayload)
      setReviews(reviewPayload.items)
      setQuestions(questionPayload.items)
      setPriceCompare(comparePayload)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入商品資料失敗。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAll()
  }, [slug])

  /**
   * 送出加入購物車。
   *
   * 送出的欄位：
   * - `slug`: 商品 slug
   * - `qty`: 數量
   * - `variant_id`: 目前選中的變體 id
   */
  async function addToCart() {
    try {
      setSubmitting(true)
      setError('')
      const payload = await apiFetch<{ detail?: string }>('/cart/items/', {
        method: 'POST',
        body: JSON.stringify({
          slug,
          qty,
          variant_id: variantId,
        }),
      })
      setMessage(payload.detail ?? '已加入購物車。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '加入購物車失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  /** 送出評論。 */
  async function submitReview() {
    try {
      setSubmitting(true)
      setError('')
      const created = await apiFetch<Review>(`/products/${slug}/reviews/`, {
        method: 'POST',
        body: JSON.stringify(reviewForm),
      })
      setReviews((prev) => [created, ...prev])
      setReviewForm({ rating: 5, title: '', body: '' })
      setMessage('評論已送出。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '送出評論失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  /** 送出發問。 */
  async function submitQuestion() {
    try {
      setSubmitting(true)
      setError('')
      const created = await apiFetch<Question>(`/products/${slug}/questions/`, {
        method: 'POST',
        body: JSON.stringify(questionForm),
      })
      setQuestions((prev) => [created, ...prev])
      setQuestionForm({ title: '', body: '' })
      setMessage('問題已送出。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '送出問題失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  /**
   * 送出單一問題的回答。
   *
   * `questionId`:
   * - 目前正在回答的問題 id
   */
  async function submitAnswer(questionId: number) {
    try {
      setSubmitting(true)
      setError('')
      const updated = await apiFetch<Question>(`/products/${slug}/questions/${questionId}/answers/`, {
        method: 'POST',
        body: JSON.stringify({ body: answerForms[questionId] ?? '' }),
      })
      setQuestions((prev) => prev.map((item) => (item.id === questionId ? updated : item)))
      setAnswerForms((prev) => ({ ...prev, [questionId]: '' }))
      setMessage('回答已送出。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '送出回答失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  /**
   * 模擬重新抓價。
   *
   * 這支功能不會真的連到外站，而是呼叫後端 mock crawler service，
   * 讓更新時間與模擬價格重新計算。
   */
  async function refreshPriceCompare() {
    try {
      setSubmitting(true)
      setError('')
      const payload = await apiFetch<PriceComparisonRefreshPayload>(`/products/${slug}/price-compare/refresh/`, {
        method: 'POST',
      })
      setPriceCompare(payload.result)
      setMessage(payload.detail)
    } catch (err) {
      setError(err instanceof Error ? err.message : '模擬抓價失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <section className="card">載入商品資料中…</section>
  }

  const displayPrice = product?.price_range_label ?? (product ? `$${product.price.toFixed(2)}` : '')

  return (
    <div className="stack">
      {/* 商品主區：圖片、基本資訊、價格與購買操作。 */}
      <div className="grid grid-2">
        <section className="card stack">
          {product?.primary_image ? <img alt={product.name} className="product-image" src={product.primary_image} /> : <div className="product-image" />}
          <div className="stack">
            <h1>{product?.name ?? 'Loading...'}</h1>
            <div className="muted">
              {product?.brand} ・ {product?.category}
            </div>
            <strong>{displayPrice}</strong>
            {product?.compare_at_price ? <span className="muted">原價 ${product.compare_at_price.toFixed(2)}</span> : null}
            <div className="muted">庫存狀態：{product?.stock_status ?? 'unknown'}</div>
          </div>
        </section>

        <section className="card stack">
          <h2>購買資訊</h2>
          {error ? <div className="notice">{error}</div> : null}
          {message ? <div className="notice success">{message}</div> : null}

          {product?.variants?.length ? (
            <label className="field">
              <span>商品變體</span>
              <select value={variantId} onChange={(event) => setVariantId(event.target.value)}>
                <option value="">請選擇變體</option>
                {product.variants.map((variant) => (
                  <option key={variant.id} value={variant.id}>
                    {variant.name} ・ ${variant.price.toFixed(2)} ・ 庫存 {variant.stock}
                  </option>
                ))}
              </select>
            </label>
          ) : null}

          <label className="field">
            <span>數量</span>
            <input min={1} type="number" value={qty} onChange={(event) => setQty(Number(event.target.value) || 1)} />
          </label>

          <button className="btn" disabled={submitting} onClick={addToCart} type="button">
            {submitting ? '處理中…' : '加入購物車'}
          </button>

          <div className="stack">
            <h3>商品規格</h3>
            {product?.specs ? (
              <ul>
                {Object.entries(product.specs).map(([key, value]) => (
                  <li key={key}>
                    {key}: {value}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">目前沒有規格資料。</p>
            )}
          </div>
        </section>
      </div>

      {/* 比價區：展示 mock crawler / mock API 的外站價格比較。 */}
      <section className="card stack">
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2>價格比較</h2>
            <p className="muted">
              這裡顯示的是模擬外站價格資料，用來示範 crawler / 比價功能，不代表即時真實價格。
            </p>
          </div>
          <button className="btn btn-secondary" disabled={submitting} onClick={refreshPriceCompare} type="button">
            模擬重新抓價
          </button>
        </div>

        {priceCompare ? (
          <>
            <div className="grid grid-3">
              <div className="card">
                <strong>本站價格</strong>
                <div>${priceCompare.our_price.toFixed(2)}</div>
              </div>
              <div className="card">
                <strong>最低外站價</strong>
                <div>${priceCompare.lowest_price.toFixed(2)}</div>
              </div>
              <div className="card">
                <strong>更新時間</strong>
                <div>{priceCompare.last_refreshed_at_display || '尚未更新'}</div>
              </div>
            </div>

            <table className="table">
              <thead>
                <tr>
                  <th>來源站點</th>
                  <th>商品名稱</th>
                  <th>價格</th>
                  <th>與本站差額</th>
                  <th>更新時間</th>
                  <th>備註</th>
                </tr>
              </thead>
              <tbody>
                {priceCompare.items.map((item) => (
                  <tr key={item.site}>
                    <td>{item.site_label}</td>
                    <td>
                      <a href={item.url} rel="noreferrer" target="_blank">
                        {item.title}
                      </a>
                    </td>
                    <td>${item.price.toFixed(2)}</td>
                    <td>
                      {item.diff_amount > 0 ? '+' : ''}
                      {item.diff_amount.toFixed(2)} ({item.diff_percent > 0 ? '+' : ''}
                      {item.diff_percent.toFixed(2)}%)
                    </td>
                    <td>{item.captured_at_display}</td>
                    <td>{item.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <p className="muted">目前沒有可顯示的比價資料。</p>
        )}
      </section>

      {/* 評論區：左邊顯示列表，右邊送出新評論。 */}
      <section className="card stack">
        <h2>商品評論</h2>
        <div className="grid grid-2">
          <div className="stack">
            {reviews.length ? (
              reviews.map((review) => (
                <div className="card" key={review.id}>
                  <div className="row" style={{ justifyContent: 'space-between' }}>
                    <strong>{review.title}</strong>
                    <span className="badge">{review.rating} / 5</span>
                  </div>
                  <div className="muted">
                    {review.author} ・ {review.created_at_display}
                  </div>
                  <p>{review.body}</p>
                </div>
              ))
            ) : (
              <div className="muted">目前還沒有評論。</div>
            )}
          </div>

          <div className="stack">
            <label className="field">
              <span>評分</span>
              <select value={reviewForm.rating} onChange={(event) => setReviewForm((prev) => ({ ...prev, rating: Number(event.target.value) }))}>
                {[5, 4, 3, 2, 1].map((score) => (
                  <option key={score} value={score}>
                    {score}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>標題</span>
              <input value={reviewForm.title} onChange={(event) => setReviewForm((prev) => ({ ...prev, title: event.target.value }))} />
            </label>
            <label className="field">
              <span>內容</span>
              <textarea rows={5} value={reviewForm.body} onChange={(event) => setReviewForm((prev) => ({ ...prev, body: event.target.value }))} />
            </label>
            <button className="btn" disabled={submitting} onClick={submitReview} type="button">
              送出評論
            </button>
          </div>
        </div>
      </section>

      {/* 問答區：左邊問題與回答，右邊是新發問表單。 */}
      <section className="card stack">
        <h2>商品問答</h2>
        <div className="grid grid-2">
          <div className="stack">
            {questions.length ? (
              questions.map((question) => (
                <div className="card stack" key={question.id}>
                  <div>
                    <strong>{question.title}</strong>
                  </div>
                  <div className="muted">
                    {question.author} ・ {question.created_at_display}
                  </div>
                  <p>{question.body}</p>

                  <div className="stack">
                    {(question.answers ?? []).map((answer) => (
                      <div className="card" key={answer.id}>
                        <strong>{answer.author}</strong>
                        <div className="muted">{answer.created_at_display}</div>
                        <p>{answer.body}</p>
                      </div>
                    ))}
                  </div>

                  <label className="field">
                    <span>新增回答</span>
                    <textarea
                      rows={3}
                      value={answerForms[question.id] ?? ''}
                      onChange={(event) => setAnswerForms((prev) => ({ ...prev, [question.id]: event.target.value }))}
                    />
                  </label>
                  <button className="btn btn-secondary" disabled={submitting} onClick={() => submitAnswer(question.id)} type="button">
                    送出回答
                  </button>
                </div>
              ))
            ) : (
              <div className="muted">目前還沒有問答。</div>
            )}
          </div>

          <div className="stack">
            <label className="field">
              <span>問題標題</span>
              <input value={questionForm.title} onChange={(event) => setQuestionForm((prev) => ({ ...prev, title: event.target.value }))} />
            </label>
            <label className="field">
              <span>問題內容</span>
              <textarea rows={5} value={questionForm.body} onChange={(event) => setQuestionForm((prev) => ({ ...prev, body: event.target.value }))} />
            </label>
            <button className="btn" disabled={submitting} onClick={submitQuestion} type="button">
              送出問題
            </button>
          </div>
        </div>
      </section>

      {/* 推薦商品區。 */}
      <section className="card stack">
        <h2>你可能也會喜歡</h2>
        <div className="grid grid-3">
          {recommendations?.similar?.map((item) => (
            <Link className="card" href={`/products/${item.slug}`} key={item.slug}>
              <strong>{item.name}</strong>
              <div className="muted">{item.price_range_label ?? `$${item.price.toFixed(2)}`}</div>
            </Link>
          ))}
        </div>
      </section>
    </div>
  )
}
