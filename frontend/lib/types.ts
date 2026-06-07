/**
 * 補充：
 * 這個檔案是前端共用型別中心，描述 API payload 在前端的資料形狀。
 * `type` / `interface` 都只存在於 TypeScript 編譯期，不會直接進到瀏覽器 runtime。
 */
/**
 * 前端共用型別定義。
 *
 * 功能：
 * - 集中描述 Django / DRF API 回傳給前端的資料形狀
 * - 讓 page、component、lib helper 共用同一組 TypeScript 型別
 * - 避免每個頁面自己手寫一份 interface，導致欄位名稱逐漸漂移
 *
 * 來源：
 * - TypeScript `type` 語法：用來定義靜態型別，不會出現在瀏覽器執行後的 JavaScript 內
 * - 欄位後面的 `?`：代表 optional field，對應 API 可能有時給、有時不給
 * - `Array<T>` 或 `T[]`：代表陣列
 * - `Record<K, V>`：代表 key-value 物件，來自 TypeScript 標準型別工具
 *
 * 使用方式：
 * - 頁面抓 API 時，搭配 `apiFetch<T>()` 指定預期 payload
 * - component props 用這裡的型別，確保不同頁面看到同一組欄位語意
 * - `import type { Foo } from '@/lib/types'` 代表只匯入型別，不增加 runtime bundle
 */

/**
 * 會員 / 登入後共用的最小使用者快照。
 *
 * 主要出現在：
 * - `/api/v1/me/`
 * - `/api/v1/app/bootstrap/`
 * - `/api/v1/staff/users/`
 *
 * 這類型別通常只放跨多頁都共用的最小共同欄位。
 */
export type DemoUser = {
  /** 資料庫主鍵。 */
  id: number
  /** 登入帳號。 */
  username: string
  /** 前端顯示用名稱。 */
  display_name: string
  /** 角色，例如 buyer / seller / admin。 */
  role: string
  /** 帳號狀態，例如 active / suspended。 */
  account_status?: string
  /** 賣家申請狀態，例如 pending / approved / rejected。 */
  seller_request_status?: string
  /** 聯絡信箱。 */
  email?: string
  /** 賣家運費規則。 */
  shipping_rules?: SellerShippingRules
}

/**
 * 賣家運費規則。
 *
 * 這是會員中心運費設定頁與 checkout 群組運費試算會共用的資料形狀。
 */
export type SellerShippingRules = {
  home_delivery_enabled: boolean
  home_delivery_fee: string
  convenience_store_enabled: boolean
  convenience_store_fee: string
  free_shipping_threshold: string
}

/**
 * App bootstrap payload。
 *
 * Header、會員登入狀態、購物車數量、比較/收藏數量，都靠這支 API 一次帶回。
 *
 * 這是常見的 bootstrap payload 設計：用一支 API 準備整個頁面殼層初始化資訊。
 */
export type AppBootstrapPayload = {
  user: DemoUser | null
  cart_count: number
  compare_count: number
  favorite_count: number
}

/**
 * 單一 Banner 資料。
 *
 * 同時給：
 * - 首頁公開 Banner 輪播
 * - 會員 Banner 申請頁
 * - 管理端 Banner 審核頁
 */
export type Banner = {
  id: number
  title?: string
  copy_text?: string
  image_path: string
  link_url?: string
  starts_at?: string
  ends_at?: string
  position?: string
  position_label?: string
  note?: string
  sort_order: number
  status?: string
  status_label?: string
  is_active: boolean
  rejection_reason?: string
  applicant_user_id?: number | null
  applicant_username?: string
  applicant_display_name?: string
  reviewed_at?: string
  reviewed_by_username?: string
  reviewed_by_display_name?: string
  created_at?: string
  updated_at?: string
  is_currently_visible?: boolean
}

/**
 * Banner 列表 payload。
 */
export type BannerListPayload = {
  items: Banner[]
}

/**
 * 商品主型別。
 *
 * 這是前端最常用的資料型別之一：
 * - 首頁商品卡片
 * - 商品總覽
 * - 商品詳情
 * - 賣家商品管理
 * - 管理端商品管理
 */
export type Product = {
  /** 商品主鍵。 */
  id: number
  /** 商品 slug，用於前端路由與 API 查詢。 */
  slug: string
  /** 商品名稱。 */
  name: string
  /** 單一基準價格。 */
  price: number
  /** 原價或比較價。 */
  compare_at_price?: number | null
  /** 品牌名稱。 */
  brand: string
  /** 類別顯示名稱。 */
  category: string
  /** 類別 canonical slug。 */
  category_slug?: string
  /** 類別顯示標籤。 */
  category_label?: string
  /** 商品 tag 字串。 */
  tags?: string[]
  /** 多圖路徑。 */
  images?: string[]
  /** 首圖。 */
  primary_image?: string
  /** 總庫存；若商品完全以變體控庫，可能為 null。 */
  stock?: number | null
  price_compare_enabled?: boolean
  price_compare_query?: string
  /** 庫存狀態，例如 in_stock / out_of_stock。 */
  stock_status?: string
  /** 目前登入者是否已收藏。 */
  is_favorite?: boolean
  /** 可選顏色。 */
  color_options?: string[]
  /** 可選尺寸。 */
  size_options?: string[]
  /** 是否有折扣。 */
  has_discount?: boolean
  /** 折扣百分比。 */
  discount_percent?: number
  /** 前端已整理好的價格區間顯示。 */
  price_range_label?: string
  /** 審核 / 上架狀態。 */
  status?: string
  /** 狀態文字。 */
  status_label?: string
  /** 管理員審核備註。 */
  review_note?: string
  /** 商品詳情頁可直接顯示的庫存文字。 */
  stock_display?: string
  /** 規格文字快照。 */
  specs_text?: string
  /** 變體文字快照。 */
  variants_text?: string
  /** 結構化變體。 */
  variants?: ProductVariant[]
  /** 單一商品可覆寫賣家運費規則。 */
  shipping_profile?: {
    use_seller_rules: boolean
    allow_home_delivery: boolean
    allow_convenience_store: boolean
    override_home_delivery_fee?: number | null
    override_convenience_store_fee?: number | null
  }
  /** 預設變體。 */
  default_variant?: ProductVariant | null
  /** 擁有者 user id。 */
  owner_user_id?: number | null
  owner_username?: string
  owner_display_name?: string
  created_at?: string
  updated_at?: string
}

/**
 * 類別選項。
 *
 * 給 catalog facet、賣家新增商品、管理端分類管理頁共用。
 */
export type ProductCategoryOption = {
  id?: number
  slug: string
  label: string
  description?: string
  is_active?: boolean
  sort_order?: number
}

/**
 * 商品變體。
 *
 * 注意：
 * - `id` 在前端目前常直接拿來當選項值，所以維持字串較方便
 * - `attributes` 讓顏色/尺寸可結構化，而不只是一串文字
 * - 這個型別同時服務商品詳情頁與賣家編輯頁，所以保留顯示與編輯兩邊都會用到的欄位
 */
export type ProductVariant = {
  id: string
  name: string
  sku?: string
  price: number
  compare_at_price?: number | null
  stock: number
  image?: string
  image_path_snapshot?: string
  image_index?: number | null
  attributes?: {
    color?: string
    size?: string
  }
}

/**
 * 商品列表 API payload。
 */
export type ProductListPayload = {
  /** 目前頁面的商品陣列。 */
  items: Product[]
  /** 分頁資訊。 */
  meta: {
    page: number
    total_pages: number
    total_items: number
  }
  /** facet 選項，供篩選 UI 使用。 */
  facets?: {
    categories?: ProductCategoryOption[]
    brands?: string[]
    colors?: string[]
    sizes?: string[]
    tags?: string[]
  }
  /** 後端回傳的當前 filter 快照。 */
  filters?: Record<string, string>
}

/**
 * 商品比較列表。
 */
export type CompareListPayload = {
  items: Product[]
  /** 目前比較清單裡的 slug，方便快速判斷按鈕狀態。 */
  slugs: string[]
}

/**
 * 單一外部比價結果。
 *
 * 目前即使不完全落 DB，前端仍需要一個穩定型別呈現比較結果。
 */
export type CompetitorPriceItem = {
  site: string
  site_label: string
  title: string
  url: string
  price: number
  original_price?: number | null
  sale_price?: number | null
  currency: string
  captured_at: string
  captured_at_display?: string
  status: string
  note?: string
  diff_amount: number
  diff_percent: number
  is_cheaper_than_our_price: boolean
  is_same_as_our_price: boolean
}

/**
 * 商品比價 payload。
 */
export type PriceComparisonPayload = {
  our_product_slug: string
  our_product_name: string
  our_product_id: number
  our_price: number
  currency: string
  query?: string
  is_mock: boolean
  source_type: string
  last_refreshed_at: string
  last_refreshed_at_display?: string
  lowest_price: number
  our_store_is_lowest: boolean
  items: CompetitorPriceItem[]
}

/**
 * 手動刷新比價後的回應。
 */
export type PriceComparisonRefreshPayload = {
  detail: string
  result: PriceComparisonPayload
}

/**
 * 商品評論。
 */
export type Review = {
  id: number
  product_id: number
  /** 前端公開顯示名稱。 */
  author: string
  author_username?: string | null
  author_user_id?: number | null
  rating: number
  title: string
  body: string
  created_at: string
  created_at_display?: string
}

/**
 * 商品問答中的回答。
 */
export type QuestionAnswer = {
  id: number
  author: string
  author_username?: string | null
  author_user_id?: number | null
  is_seller_reply?: boolean
  is_body_masked?: boolean
  body: string
  created_at: string
  created_at_display?: string
}

/**
 * 商品問答中的問題。
 */
export type Question = {
  id: number
  product_id: number
  author: string
  author_username?: string | null
  author_user_id?: number | null
  title: string
  is_body_masked?: boolean
  body: string
  created_at: string
  created_at_display?: string
  answer_count?: number
  /** 問題詳情頁 / 商品頁可能會直接附帶回答陣列。 */
  answers?: QuestionAnswer[]
}

/**
 * 社群貼文回覆。
 */
export type CommunityReply = {
  id: number
  author: string
  author_username?: string | null
  author_user_id?: number | null
  body: string
  created_at: string
  created_at_display?: string
}

/**
 * 社群貼文。
 */
export type CommunityPost = {
  id: number
  topic: string
  author: string
  author_username?: string | null
  author_user_id?: number | null
  title: string
  body: string
  tags?: string[]
  votes: number
  has_voted?: boolean
  created_at: string
  created_at_display?: string
  reply_count?: number
  replies?: CommunityReply[]
  can_edit?: boolean
  can_delete?: boolean
}

/**
 * 社群貼文列表 payload。
 */
export type CommunityPostListPayload = {
  items: CommunityPost[]
}

/**
 * 購物車單一列。
 */
export type CartItem = {
  /** 前端暫存與更新用的穩定 key。 */
  key: string
  id: number
  slug: string
  name: string
  /** 已帶上變體名稱的顯示名稱。 */
  display_name: string
  price: number
  qty: number
  variant_id?: string
  variant_name?: string
  sku?: string
  line_total: number
}

/**
 * 購物車 payload。
 */
export type CartPayload = {
  items: CartItem[]
  coupon?: string | null
  item_count: number
  totals: {
    subtotal: string
    shipping: string
    discount: string
    total: string
  }
  shipping_methods?: CheckoutChoice[]
  selected_shipping_method?: string
  seller_shipping_groups?: Array<{
    seller_username: string
    seller_display_name: string
    subtotal: string
    shipping_fee: string
    base_shipping_fee: string
    free_shipping_threshold: string
    free_shipping_applied: boolean
    selected_shipping_method: string
    selected_shipping_method_label: string
    selected_shipping_method_supported: boolean
    available_shipping_methods: CheckoutChoice[]
    items: Array<{
      key: string
      slug: string
      display_name: string
      qty: number
      line_total: string
    }>
  }>
  detail?: string
}

/**
 * 收件地址。
 */
export type Address = {
  id: number
  label: string
  recipient: string
  phone: string
  city: string
  district: string
  postal_code?: string
  address_line: string
  created_at?: string
  is_default?: boolean
}

/**
 * 發票設定。
 */
export type InvoiceProfile = {
  invoice_type: string
  carrier_code?: string
  company_name?: string
  tax_id?: string
  updated_at?: string
}

/**
 * checkout 下拉選項。
 */
export type CheckoutChoice = {
  value: string
  label: string
}

/**
 * checkout 預覽 payload。
 *
 * 這支型別直接延伸 `CartPayload`，表示 preview 會把購物車資料一併帶回。
 */
export type CheckoutPreviewPayload = CartPayload & {
  user: DemoUser | null
  requires_login: boolean
  can_confirm: boolean
  addresses: Address[]
  default_address?: Address | null
  invoice_profile: InvoiceProfile
  shipping_methods: CheckoutChoice[]
  payment_methods: CheckoutChoice[]
  convenience_store_brands: CheckoutChoice[]
  selected_address_id?: number | null
  selected_shipping_method?: string
  selected_payment_method?: string
  seller_shipping_groups?: Array<{
    seller_username: string
    seller_display_name: string
    subtotal: string
    shipping_fee: string
    base_shipping_fee: string
    free_shipping_threshold: string
    free_shipping_applied: boolean
    selected_shipping_method: string
    selected_shipping_method_label: string
    selected_shipping_method_supported: boolean
    available_shipping_methods: CheckoutChoice[]
    items: Array<{
      key: string
      slug: string
      display_name: string
      qty: number
      line_total: string
    }>
  }>
}

/**
 * 訂單主型別。
 *
 * 這支型別欄位多，是因為前端目前同時支援：
 * - 買家訂單頁
 * - 賣家訂單頁
 * - 管理端訂單頁
 */
export type Order = {
  id: number
  buyer_user_id?: number | null
  username: string
  display_name: string
  status: string
  status_label?: string
  seller_status?: string
  seller_status_label?: string
  shipping_address?: Address
  shipping_method?: string
  shipping_method_label?: string
  is_convenience_store_shipping?: boolean
  payment_method?: string
  payment_method_label?: string
  payment_status?: string
  payment_status_label?: string
  payment_trade_no?: string
  payment_completed_at?: string
  pickup_store_brand?: string
  pickup_store_brand_label?: string
  pickup_store_code?: string
  pickup_store_name?: string
  pickup_store_address?: string
  buyer_note?: string
  tracking_number?: string
  shipping_note?: string
  created_at: string
  created_at_display?: string
  shipped_at_display?: string
  completed_at_display?: string
  can_confirm_completion?: boolean
  totals?: Record<string, string>
  seller_totals?: Record<string, string>
  items?: Array<{
    id: number
    slug: string
    name: string
    display_name?: string
    qty: number
    price: number
    line_total: string
    seller_status?: string
    seller_status_label?: string
    tracking_number?: string
  }>
  service_request?: {
    type?: string
    type_label?: string
    status?: string
    status_label?: string
    note?: string
    requested_at?: string
    reviewed_at?: string
    is_pending?: boolean
  }
  shipment_groups?: Array<{
    seller_username: string
    seller_display_name: string
    seller_status: string
    seller_status_label: string
    tracking_number?: string
    shipping_note?: string
    items: Array<{
      id: number
      display_name?: string
      qty: number
      line_total: string
    }>
  }>
  seller_shipping_groups?: Array<{
    seller_username: string
    seller_display_name: string
    subtotal: string
    shipping_fee: string
    base_shipping_fee: string
    free_shipping_threshold: string
    free_shipping_applied: boolean
    selected_shipping_method: string
    selected_shipping_method_label: string
    selected_shipping_method_supported: boolean
    available_shipping_methods: CheckoutChoice[]
    items: Array<{
      key?: string
      slug?: string
      display_name: string
      qty: number
      line_total: string
    }>
  }>
}

/**
 * 藍新 sandbox payment runtime 摘要。
 */
export type NewebpaySandboxPaymentSummary = {
  provider: string
  mode: string
  gateway_url: string
  has_crypto_dependency: boolean
  configured: boolean
  missing_settings: string[]
  merchant_id?: string
  notify_url?: string
  return_url?: string
  client_back_url?: string
}

/**
 * 準備送往藍新的 payment payload。
 */
export type NewebpaySandboxPaymentPrepared = {
  provider: string
  mode: string
  order_id: number
  buyer_username: string
  gateway_url: string
  form_method: string
  merchant_order_no: string
  trade_info_params: Record<string, string | number>
  form_fields: Record<string, string | number>
  note: string
}

/**
 * 藍新付款紀錄。
 */
export type NewebpayPaymentRecord = {
  provider: string
  mode: string
  order_id: number
  buyer_username: string
  merchant_order_no: string
  trade_no: string
  status: string
  status_label: string
  amount: string
  currency: string
  payment_url: string
  return_url?: string
  client_back_url?: string
  created_at: string
  updated_at: string
  paid_at?: string
  note?: string
  callback_count: number
  raw_payload?: Record<string, unknown>
}

/**
 * 藍新 payment debug payload。
 */
export type NewebpayPaymentDebug = {
  runtime: NewebpaySandboxPaymentSummary
  records: NewebpayPaymentRecord[]
}

/**
 * 藍新物流 sandbox runtime 摘要。
 */
export type NewebpaySandboxLogisticsSummary = {
  provider: string
  mode: string
  configured: boolean
  missing_settings?: string[]
  merchant_id?: string
  callback_url?: string
  create_url?: string
  status_url?: string
  note?: string
}

/**
 * 藍新物流 sandbox scaffold payload。
 */
export type NewebpaySandboxLogisticsPrepared = {
  provider: string
  mode: string
  order_id: number
  seller_username: string
  logistics_type: string
  callback_url?: string
  create_url?: string
  status_url?: string
  suggested_payload: Record<string, string | number>
  buyer_shipping_summary?: {
    shipping_method: string
    shipping_method_label?: string
    payment_method: string
    payment_method_label?: string
    pickup_store_brand?: string
    pickup_store_brand_label?: string
    pickup_store_code?: string
    pickup_store_name?: string
    pickup_store_address?: string
    is_convenience_store: boolean
  }
  note: string
}

/**
 * 藍新物流紀錄。
 */
export type NewebpayLogisticsRecord = {
  provider: string
  mode: string
  order_id: number
  seller_username: string
  merchant_order_no?: string
  logistics_no: string
  status: string
  status_label: string
  store_type: string
  temperature: string
  receiver_name: string
  receiver_phone: string
  shipment_note?: string
  created_at: string
  updated_at: string
  callback_count: number
  raw_payload?: Record<string, unknown>
}

/**
 * 賣家銷售報表。
 */
export type SalesReport = {
  order_count: number
  units_sold: number
  revenue: string
  status_counts: {
    pending: number
    shipped: number
    completed: number
  }
  top_products: Array<{
    slug: string
    name: string
    qty: number
    revenue: string
  }>
  filters: {
    date_from: string
    date_to: string
  }
}

/**
 * 管理審核首頁摘要。
 */
export type StaffReviewDashboard = {
  managed_products: Product[]
  seller_requests: DemoUser[]
}

/**
 * 管理端儀表板摘要。
 */
export type AdminDashboard = {
  users: Record<string, string | number>
  products: Record<string, string | number>
  orders: Record<string, string | number>
  content: Record<string, string | number>
  recent_reviews: Array<Record<string, string | number | null>>
  recent_questions: Array<Record<string, string | number | null>>
  recent_posts: Array<Record<string, string | number | null>>
}

/**
 * 共用狀態下拉選項。
 */
export type StatusChoice = {
  value: string
  label: string
}

/**
 * 會員中心首頁摘要。
 */
export type MeDashboard = {
  user: DemoUser
  review_count: number
  question_count: number
  answer_count: number
  post_count: number
  order_count: number
  favorite_products: Product[]
  recent_products: Product[]
  owned_products: Product[]
}
