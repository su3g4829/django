'use client'

/**
 * 全站導覽列元件
 *
 * 功能：
 * - 讀取 `/api/v1/app/bootstrap/` 取得目前登入者與計數資訊
 * - 顯示前台、賣家、管理者不同角色的導覽入口
 * - 提供登出操作
 */
import Link from 'next/link'
import { useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { AppBootstrapPayload } from '@/lib/types'

/**
 * 全站導覽列。
 */
export function SiteHeader() {
  /**
   * data:
   * - 後端 app bootstrap API 回傳的初始化資料
   * - 包含目前使用者、購物車數量、比較清單數量、收藏數量
   */
  const [data, setData] = useState<AppBootstrapPayload | null>(null)

  useEffect(() => {
    apiFetch<AppBootstrapPayload>('/app/bootstrap/')
      .then(setData)
      .catch(() => setData({ user: null, cart_count: 0, compare_count: 0, favorite_count: 0 }))
  }, [])

  /**
   * 執行登出。
   *
   * 做法：
   * - 呼叫 Django DRF `/api/v1/auth/logout/`
   * - 成功後回到前台首頁
   */
  async function handleLogout() {
    await apiFetch('/auth/logout/', { method: 'POST' })
    window.location.href = '/'
  }

  /** 是否有賣家權限。admin 也視為可用賣家功能。 */
  const isSeller = data?.user?.role === 'seller' || data?.user?.role === 'admin'

  /** 是否為管理者。 */
  const isAdmin = data?.user?.role === 'admin'

  return (
    <header className="navbar">
      <div className="container navbar-inner">
        <div className="row">
          {/* 左側品牌與主導覽區。 */}
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

            {isSeller ? <Link href="/me/products">我的商品</Link> : null}
            {isSeller ? <Link href="/me/sales">賣家訂單</Link> : null}
            {isSeller ? <Link href="/me/sales/report">銷售報表</Link> : null}

            {isAdmin ? <Link href="/staff/dashboard">管理儀表板</Link> : null}
            {isAdmin ? <Link href="/staff/orders">平台訂單</Link> : null}
            {isAdmin ? <Link href="/staff/users">會員管理</Link> : null}
            {isAdmin ? <Link href="/staff/reviews">審核中心</Link> : null}

            <Link href="/docs/routes">前端路由文件</Link>
            <span className="muted">比較：{data?.compare_count ?? 0}</span>
            <span className="muted">收藏：{data?.favorite_count ?? 0}</span>
          </nav>
        </div>

        <div className="row">
          {/* 右側登入狀態與登入/登出操作區。 */}
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
