'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'

import { APP_BOOTSTRAP_REFRESH_EVENT, apiFetch, type BootstrapRefreshDetail } from '@/lib/api'
import { clearAllSessionDrafts } from '@/lib/session-drafts'
import type { AppBootstrapPayload } from '@/lib/types'

export function SiteHeader() {
  const [data, setData] = useState<AppBootstrapPayload | null>(null)

  const loadBootstrap = useCallback(() => {
    apiFetch<AppBootstrapPayload>('/app/bootstrap/')
      .then(setData)
      .catch(() => setData({ user: null, cart_count: 0, compare_count: 0, favorite_count: 0 }))
  }, [])

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
            <Link href="/community">社群論壇</Link>
            <Link href="/products/compare">商品比較</Link>
            <Link href="/cart">購物車{data ? ` (${data.cart_count})` : ''}</Link>
            <Link href="/orders">我的訂單</Link>
            <Link href="/me/dashboard">會員中心</Link>
            <Link href="/me/profile">會員資料</Link>
            <Link href="/me/addresses">地址管理</Link>
            <Link href="/me/invoice">發票設定</Link>
            {data?.user ? <Link href="/me/promotions">宣傳申請</Link> : null}

            {isSeller ? <Link href="/me/products">我的商品</Link> : null}
            {isSeller ? <Link href="/me/shipping-rules">運費設定</Link> : null}
            {isSeller ? <Link href="/me/sales">賣家訂單</Link> : null}
            {isSeller ? <Link href="/me/sales/report">銷售報表</Link> : null}

            {isAdmin ? <Link href="/staff/dashboard">管理儀表板</Link> : null}
            {isAdmin ? <Link href="/staff/products">商品管理</Link> : null}
            {isAdmin ? <Link href="/staff/orders">平台訂單</Link> : null}
            {isAdmin ? <Link href="/staff/users">會員管理</Link> : null}
            {isAdmin ? <Link href="/staff/banners">Banner 管理</Link> : null}
            {isAdmin ? <Link href="/staff/reviews">審核中心</Link> : null}

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
