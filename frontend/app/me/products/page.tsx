'use client'

/**
 * 賣家商品列表頁
 *
 * 功能：
 * - 顯示目前賣家的商品列表
 * - 提供新增商品入口
 *
 * 主要 API：
 * - GET `/api/v1/me/products/`
 */

import { useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { Product, StatusChoice } from '@/lib/types'

type SellerProductsPayload = {
  items: Product[]
  status_choices: StatusChoice[]
}

export default function SellerProductsPage() {
  /** 目前賣家擁有的商品列表。 */
  const [items, setItems] = useState<Product[]>([])
  /** 初次載入列表時的狀態。 */
  const [loading, setLoading] = useState(true)
  /** 封存、複製、刪除時的提交狀態。 */
  const [submitting, setSubmitting] = useState(false)
  /** API 錯誤訊息。 */
  const [error, setError] = useState('')

  /** 載入賣家商品列表。 */
  async function loadProducts() {
    setLoading(true)
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
    loadProducts()
  }, [])

  /** 封存商品。 */
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

  /** 複製商品成新草稿。 */
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

  /** 刪除商品。 */
  async function deleteProduct(slug: string) {
    if (!window.confirm('確定要刪除這個商品嗎？')) return
    try {
      setSubmitting(true)
      await apiFetch(`/me/products/${slug}/`, { method: 'DELETE' })
      await loadProducts()
    } catch (err) {
      setError(err instanceof Error ? err.message : '刪除商品失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card stack">
      {/* 頁首與新增商品入口。 */}
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
        <div className="muted">目前沒有任何商品。</div>
      ) : (
        <table className="table">
          {/* 表頭：商品摘要、狀態、價格、庫存與操作。 */}
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
            {/* 每列是一個可管理商品，提供編輯、複製、封存、刪除。 */}
            {items.map((item) => (
              <tr key={item.slug}>
                <td>
                  <strong>{item.name}</strong>
                  <div className="muted">
                    {item.brand} ｜ {item.category}
                  </div>
                </td>
                <td>{item.status_label ?? item.status ?? '-'}</td>
                <td>{item.price_range_label ?? `$${item.price.toFixed(2)}`}</td>
                <td>{item.stock_display ?? String(item.stock ?? '-')}</td>
                <td>
                  <div className="row">
                    {/* 操作列：導向編輯，或直接執行複製 / 封存 / 刪除。 */}
                    <a href={`/me/products/${item.slug}`}>編輯</a>
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
