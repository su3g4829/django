'use client'

/**
 * `use client` 來自 Next.js App Router。
 *
 * 用法：
 * - 讓本頁可以使用 React hook、瀏覽器事件與 `window` API。
 */

/**
 * 賣家商品列表頁。
 *
 * 功能：
 * - 載入自己名下商品
 * - 提供複製、封存、刪除動作
 * - 監聽 bootstrap refresh 事件與視窗 focus，讓多頁操作後可自動重抓最新資料
 */

import { useEffect, useState } from 'react'

import { APP_BOOTSTRAP_REFRESH_EVENT, apiFetch } from '@/lib/api'
import type { Product, StatusChoice } from '@/lib/types'

type SellerProductsPayload = {
  items: Product[]
  status_choices: StatusChoice[]
}

export default function SellerProductsPage() {
  const [items, setItems] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  /**
   * `async function` 是 JavaScript 非同步函式語法。
   *
   * 來源：
   * - ECMAScript Promise / async-await 規範
   *
   * 用法：
   * - 內部可以用 `await` 等待 Promise 結果
   * - 這裡把讀列表流程包成 helper，方便初次載入、事件刷新、操作完成後重抓共用同一套邏輯
   */
  async function loadProducts() {
    setLoading(true)
    setItems([])
    try {
      const payload = await apiFetch<SellerProductsPayload>('/me/products/')
      setItems(payload.items)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入商品列表失敗。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadProducts()

    /**
     * 自訂事件名稱來自 `@/lib/api`。
     * 用途是其他頁面完成重要寫入後，可以通知 header 或同角色頁面重抓 bootstrap 類資料。
     */
    const handleBootstrapRefresh = () => {
      void loadProducts()
    }

    /**
     * `focus` 事件來自瀏覽器 Window API。
     * 切回分頁時重抓一次，避免另一個分頁已修改商品但此頁仍停留舊資料。
     */
    const handleWindowFocus = () => {
      void loadProducts()
    }

    window.addEventListener(APP_BOOTSTRAP_REFRESH_EVENT, handleBootstrapRefresh as EventListener)
    window.addEventListener('focus', handleWindowFocus)

    return () => {
      window.removeEventListener(APP_BOOTSTRAP_REFRESH_EVENT, handleBootstrapRefresh as EventListener)
      window.removeEventListener('focus', handleWindowFocus)
    }
  }, [])

  async function archiveProduct(slug: string) {
    try {
      setSubmitting(true)
      await apiFetch(`/me/products/${slug}/archive/`, { method: 'POST' })
      await loadProducts()
    } catch (err) {
      setError(err instanceof Error ? err.message : '封存商品失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  async function duplicateProduct(slug: string) {
    try {
      setSubmitting(true)
      await apiFetch(`/me/products/${slug}/duplicate/`, { method: 'POST' })
      await loadProducts()
    } catch (err) {
      setError(err instanceof Error ? err.message : '複製商品失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  async function deleteProduct(slug: string) {
    if (!window.confirm('確定要刪除這個商品嗎？')) return
    try {
      setSubmitting(true)
      await apiFetch(`/me/products/${slug}/`, { method: 'DELETE' })
      await loadProducts()
      setError('')
    } catch (err) {
      const message = err instanceof Error ? err.message : '刪除商品失敗。'
      if (message === 'Product not found.') {
        await loadProducts()
        setError('商品可能已被其他操作移除，畫面已重新整理。')
      } else {
        setError(message)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card stack">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div>
          <h1>我的商品</h1>
          <p className="muted">這頁會透過 `/api/v1/me/products/` 顯示賣家自己的商品列表。</p>
        </div>
        <a className="btn" href="/me/products/new">
          新增商品
        </a>
      </div>

      {error ? <div className="notice">{error}</div> : null}

      {loading ? (
        <div className="muted">載入商品列表中...</div>
      ) : !items.length ? (
        <div className="muted">目前還沒有建立任何商品。</div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>商品</th>
              <th>狀態</th>
              <th>價格</th>
              <th>庫存</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.slug}>
                <td>
                  <strong>{item.name}</strong>
                  <div className="muted">
                    {[item.brand, item.category].filter((value) => value && value !== 'none').join(' / ') || '未分類'}
                  </div>
                </td>
                <td>{item.status_label ?? item.status ?? '-'}</td>
                <td>{item.price_range_label ?? `$${item.price.toFixed(2)}`}</td>
                <td>{item.stock_display ?? String(item.stock ?? '-')}</td>
                <td>
                  <div className="row">
                    <a className="btn btn-secondary" href={`/me/products/${item.slug}`}>
                      編輯
                    </a>
                    <button className="btn btn-secondary" disabled={submitting} onClick={() => duplicateProduct(item.slug)} type="button">
                      複製
                    </button>
                    <button className="btn btn-secondary" disabled={submitting} onClick={() => archiveProduct(item.slug)} type="button">
                      封存
                    </button>
                    <button className="btn btn-secondary" disabled={submitting} onClick={() => deleteProduct(item.slug)} type="button">
                      刪除
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
