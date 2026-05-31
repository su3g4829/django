'use client'

/**
 * 賣家商品列表頁
 *
 * 功能：
 * - 載入目前登入賣家可管理的商品
 * - 提供編輯、複製、封存、刪除操作
 * - 在登入狀態變化或視窗重新聚焦時自動重抓列表，避免看到其他帳號的舊資料
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

  async function loadProducts() {
    setLoading(true)
    setItems([])
    try {
      const payload = await apiFetch<SellerProductsPayload>('/me/products/')
      setItems(payload.items)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入商品列表失敗，請稍後再試。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadProducts()

    const handleBootstrapRefresh = () => {
      void loadProducts()
    }

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
      setError(err instanceof Error ? err.message : '封存商品失敗，請稍後再試。')
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
      setError(err instanceof Error ? err.message : '複製商品失敗，請稍後再試。')
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
      const message = err instanceof Error ? err.message : '刪除商品失敗，請稍後再試。'
      if (message === 'Product not found.') {
        await loadProducts()
        setError('商品不存在，或該商品不屬於目前登入的賣家；列表已重新整理。')
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
          <p className="muted">這裡會透過 `/api/v1/me/products/` 取得目前賣家可管理的商品列表。</p>
        </div>
        <a className="btn" href="/me/products/new">
          新增商品
        </a>
      </div>

      {error ? <div className="notice">{error}</div> : null}

      {loading ? (
        <div className="muted">載入商品列表中…</div>
      ) : !items.length ? (
        <div className="muted">目前尚未建立任何商品。</div>
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
                    {[item.brand, item.category].filter((value) => value && value !== 'none').join(' ｜ ') || '未分類'}
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
