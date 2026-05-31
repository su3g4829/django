'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import { toBackendAssetUrl } from '@/lib/assets'
import type { Banner, BannerListPayload } from '@/lib/types'

const AUTO_ROTATE_MS = 5000

export function HomeBannerCarousel() {
  const [items, setItems] = useState<Banner[]>([])
  const [activeIndex, setActiveIndex] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiFetch<BannerListPayload>('/banners/')
      .then((payload) => setItems(payload.items))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (items.length <= 1) {
      return
    }
    const timer = window.setInterval(() => {
      setActiveIndex((current) => (current + 1) % items.length)
    }, AUTO_ROTATE_MS)
    return () => window.clearInterval(timer)
  }, [items.length])

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
          const body = (
            <>
              <div className="home-banner__content">
                <span className="badge">{banner.position_label || '首頁主打'}</span>
                <h2>{banner.title || '本週活動'}</h2>
                {banner.copy_text ? <p className="muted">{banner.copy_text}</p> : null}
                {banner.link_url ? <span className="btn">立即查看</span> : null}
              </div>
              <div className="home-banner__media">
                <img alt={banner.title || '首頁宣傳圖'} src={toBackendAssetUrl(banner.image_path)} />
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
            ‹
          </button>
          <button
            aria-label="下一張 banner"
            className="home-banner__arrow home-banner__arrow--next"
            onClick={() => setActiveIndex((current) => (current + 1) % items.length)}
            type="button"
          >
            ›
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
        目前輪播：{activeBanner.title || '本週活動'}
        {activeBanner.link_url ? '，點擊圖片可前往活動頁。' : '。'}
      </div>
    </section>
  )
}
