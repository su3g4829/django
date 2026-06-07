'use client'

/**
 * 首頁 Banner 輪播元件。
 *
 * 這支元件結合了：
 * - React hooks
 * - Next.js `Link`
 * - 瀏覽器計時器 `setInterval`
 * - 後端 Banner API
 *
 * 因為會用到 `useEffect` 與計時器，所以它必須是 Client Component。
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import { toBackendAssetUrl } from '@/lib/assets'
import type { Banner, BannerListPayload } from '@/lib/types'

/**
 * 自動輪播間隔。
 *
 * 這裡用毫秒是因為瀏覽器的 `setInterval` / `setTimeout` API 都以毫秒為單位。
 */
const AUTO_ROTATE_MS = 5000

export function HomeBannerCarousel() {
  const [items, setItems] = useState<Banner[]>([])
  const [activeIndex, setActiveIndex] = useState(0)
  const [loading, setLoading] = useState(true)

  /**
   * 初次載入 banner。
   *
   * `useEffect(..., [])` 的空依賴陣列代表：
   * 這段副作用只在元件掛載後執行一次。
   */
  useEffect(() => {
    apiFetch<BannerListPayload>('/banners/')
      .then((payload) => setItems(payload.items))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [])

  /**
   * 自動輪播邏輯。
   *
   * `window.setInterval` 來自瀏覽器 Timer API。
   * cleanup 必須用 `window.clearInterval(...)`，避免元件卸載後計時器還在跑。
   */
  useEffect(() => {
    if (items.length <= 1) {
      return
    }

    const timer = window.setInterval(() => {
      /**
       * `setState((current) => next)` 是 React 的 updater function 寫法。
       * 適合這種「新值依賴舊值」的情況。
       */
      setActiveIndex((current) => (current + 1) % items.length)
    }, AUTO_ROTATE_MS)

    return () => window.clearInterval(timer)
  }, [items.length])

  /**
   * 若 banner 長度改變，確保 `activeIndex` 不會超出範圍。
   */
  useEffect(() => {
    if (activeIndex >= items.length) {
      setActiveIndex(0)
    }
  }, [activeIndex, items.length])

  if (loading || !items.length) {
    return null
  }

  const activeBanner = items[activeIndex]

  return (
    <section className="home-banner">
      <div className="home-banner__track" style={{ transform: `translateX(-${activeIndex * 100}%)` }}>
        {items.map((banner) => {
          /**
           * 先組出共同 JSX，再依 `link_url` 決定包成 `Link` 或一般 `article`。
           * 這樣可避免兩份幾乎相同的 JSX 重複維護。
           */
          const body = (
            <>
              <div className="home-banner__content">
                <span className="badge">{banner.position_label || '首頁 Banner'}</span>
                <h2>{banner.title || '精選活動'}</h2>
                {banner.copy_text ? <p className="muted">{banner.copy_text}</p> : null}
                {banner.link_url ? <span className="btn">前往查看</span> : null}
              </div>
              <div className="home-banner__media">
                <img alt={banner.title || '首頁輪播圖片'} src={toBackendAssetUrl(banner.image_path)} />
              </div>
            </>
          )

          return banner.link_url ? (
            <Link className="home-banner__slide" href={banner.link_url} key={banner.id}>
              {body}
            </Link>
          ) : (
            <article className="home-banner__slide" key={banner.id}>
              {body}
            </article>
          )
        })}
      </div>

      {items.length > 1 ? (
        <>
          <button
            aria-label="上一張 banner"
            className="home-banner__arrow home-banner__arrow--prev"
            onClick={() => setActiveIndex((current) => (current - 1 + items.length) % items.length)}
            type="button"
          >
            ←
          </button>
          <button
            aria-label="下一張 banner"
            className="home-banner__arrow home-banner__arrow--next"
            onClick={() => setActiveIndex((current) => (current + 1) % items.length)}
            type="button"
          >
            →
          </button>
          <div className="home-banner__dots">
            {items.map((banner, index) => (
              <button
                aria-label={`切換到第 ${index + 1} 張 banner`}
                className={index === activeIndex ? 'home-banner__dot home-banner__dot--active' : 'home-banner__dot'}
                key={banner.id}
                onClick={() => setActiveIndex(index)}
                type="button"
              />
            ))}
          </div>
        </>
      ) : null}

      <div className="home-banner__caption">
        目前顯示：{activeBanner.title || '精選活動'}
        {activeBanner.link_url ? '，可點擊前往對應內容。' : '。'}
      </div>
    </section>
  )
}
