'use client'

/**
 * 全站 Header。
 *
 * 這支元件負責：
 * - 讀取 app bootstrap payload
 * - 顯示登入狀態
 * - 顯示購物車 / 比較 / 收藏數量
 * - 根據角色顯示 seller / admin 導覽
 *
 * 使用的主要來源：
 * - `next/link`：Next.js 內建 client-side navigation
 * - React hooks：`useState`、`useEffect`、`useCallback`
 * - `frontend/lib/api.ts`：統一的 Django API 呼叫 helper
 */

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'

import { APP_BOOTSTRAP_REFRESH_EVENT, apiFetch, type BootstrapRefreshDetail } from '@/lib/api'
import { clearAllSessionDrafts } from '@/lib/session-drafts'
import type { AppBootstrapPayload } from '@/lib/types'

export function SiteHeader() {
  /**
   * `AppBootstrapPayload | null` 的意思：
   * - 還沒載入完成前先是 `null`
   * - 載入完成後才會是有結構的 payload
   */
  const [data, setData] = useState<AppBootstrapPayload | null>(null)

  /**
   * `useCallback` 來自 React。
   * 這裡用它包住 `loadBootstrap`，是為了讓 effect 依賴穩定，不要每次 render 都被當成新函式。
   */
  const loadBootstrap = useCallback(() => {
    apiFetch<AppBootstrapPayload>('/app/bootstrap/')
      .then(setData)
      .catch(() =>
        setData({
          user: null,
          cart_count: 0,
          compare_count: 0,
          favorite_count: 0,
        }),
      )
  }, [])

  /**
   * 1. 初次掛載時載入 bootstrap
   * 2. 訂閱全站 refresh event
   *
   * `CustomEvent` 來自 DOM Event API。
   * 這裡用它通知 header：某個子頁面剛更新了 cart/favorite/compare 數量。
   */
  useEffect(() => {
    function handleBootstrapRefresh(event: Event) {
      const customEvent = event as CustomEvent<BootstrapRefreshDetail>
      const detail = customEvent.detail || {}

      if (Object.keys(detail).length) {
        setData((current) => ({
          user: current?.user ?? null,
          cart_count: detail.cart_count ?? current?.cart_count ?? 0,
          compare_count: detail.compare_count ?? current?.compare_count ?? 0,
          favorite_count: detail.favorite_count ?? current?.favorite_count ?? 0,
        }))
      }

      void loadBootstrap()
    }

    void loadBootstrap()
    window.addEventListener(APP_BOOTSTRAP_REFRESH_EVENT, handleBootstrapRefresh as EventListener)

    return () => window.removeEventListener(APP_BOOTSTRAP_REFRESH_EVENT, handleBootstrapRefresh as EventListener)
  }, [loadBootstrap])

  /**
   * 登出流程。
   *
   * 這裡用 `await` 先等後端 session 登出完成，再清掉前端 session 草稿。
   */
  async function handleLogout() {
    await apiFetch('/auth/logout/', { method: 'POST' })
    clearAllSessionDrafts()
    window.location.href = '/'
  }

  const isSeller = data?.user?.role === 'seller' || data?.user?.role === 'admin'
  const isAdmin = data?.user?.role === 'admin'

  return (
    <header className="navbar">
      <div className="container navbar-inner">
        <div className="row">
          <Link href="/" style={{ fontWeight: 800 }}>
            Store Frontend
          </Link>

          <nav className="nav-links">
            <Link href="/">首頁</Link>
            <Link href="/products">商品總覽</Link>
            <Link href="/community">社群討論</Link>
            <Link href="/products/compare">商品比較</Link>
            <Link href="/cart">購物車{data ? ` (${data.cart_count})` : ''}</Link>
            <Link href="/orders">我的訂單</Link>
            <Link href="/me/dashboard">會員中心</Link>
            <Link href="/me/profile">會員資料</Link>
            <Link href="/me/addresses">地址管理</Link>
            <Link href="/me/invoice">發票資料</Link>
            {data?.user ? <Link href="/me/promotions">Banner 申請</Link> : null}

            {isSeller ? <Link href="/me/products">賣家商品</Link> : null}
            {isSeller ? <Link href="/me/shipping-rules">運費規則</Link> : null}
            {isSeller ? <Link href="/me/sales">賣家訂單</Link> : null}
            {isSeller ? <Link href="/me/sales/report">銷售報表</Link> : null}

            {isAdmin ? <Link href="/staff/dashboard">管理儀表板</Link> : null}
            {isAdmin ? <Link href="/staff/products">商品管理</Link> : null}
            {isAdmin ? <Link href="/staff/orders">訂單管理</Link> : null}
            {isAdmin ? <Link href="/staff/users">會員管理</Link> : null}
            {isAdmin ? <Link href="/staff/banners">Banner 管理</Link> : null}
            {isAdmin ? <Link href="/staff/reviews">快速審核</Link> : null}

            <Link href="/docs/routes">前端路由文件</Link>
            <span className="muted">比較：{data?.compare_count ?? 0}</span>
            <span className="muted">收藏：{data?.favorite_count ?? 0}</span>
          </nav>
        </div>

        <div className="row">
          {data?.user ? (
            <>
              <span className="muted">Hi, {data.user.display_name}</span>
              <button className="btn btn-secondary" onClick={handleLogout} type="button">
                登出
              </button>
            </>
          ) : (
            <>
              <Link className="btn btn-secondary" href="/login">
                登入
              </Link>
              <Link className="btn" href="/register">
                註冊
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
