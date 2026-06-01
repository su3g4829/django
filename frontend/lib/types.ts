/**
 * 前端共用型別定義
 *
 * 目的：
 * - 描述 Django DRF API 回傳 payload 的形狀
 * - 讓頁面與元件在取用資料欄位時有明確型別提示
 * - 降低前後端欄位名稱不一致時的出錯機率
 */

/**
 * 示範會員 / 使用者資料。
 *
 * 來源：
 * - `/api/v1/me/`
 * - `/api/v1/app/bootstrap/`
 * - `/api/v1/staff/users/`
 */
export type DemoUser = {
  /** 使用者主鍵。 */
  id: number
  /** 登入帳號。 */
  username: string
  /** 顯示名稱，用於頁面問候或作者資訊。 */
  display_name: string
  /** 角色，例如 buyer / seller / admin。 */
  role: string
  /** 帳號狀態，例如 active / suspended。 */
  account_status?: string
  /** 賣家申請狀態，例如 pending / approved / rejected。 */
  seller_request_status?: string
  /** 電子郵件。 */
  email?: string
  shipping_rules?: SellerShippingRules
}

export type SellerShippingRules = {
  home_delivery_enabled: boolean
  home_delivery_fee: string
  convenience_store_enabled: boolean
  convenience_store_fee: string
  free_shipping_threshold: string
}

/**
 * 全站初始化資料。
 *
 * 用途：
 * - 提供 header 顯示登入狀態
 * - 顯示購物車、比較清單、收藏數量
 */
export type AppBootstrapPayload = {
  user: DemoUser | null
  cart_count: number
  compare_count: number
  favorite_count: number
}

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

export type BannerListPayload = {
  items: Banner[]
}

/**
 * 商品資料。
 */
export type Product = {
  /** 商品主鍵。 */
  id: number
  /** 商品網址 slug。 */
  slug: string
  /** 商品名稱。 */
  name: string
  /** 基礎售價。 */
  price: number
  /** 原價，用來計算折扣顯示。 */
  compare_at_price?: number | null
  /** 品牌名稱。 */
  brand: string
  /** 分類名稱。 */
  category: string
  /** 標籤清單。 */
  tags?: string[]
  /** 所有圖片路徑。 */
  images?: string[]
  /** 商品主圖。 */
  primary_image?: string
  /** 總庫存。若無固定庫存可能為 null。 */
  stock?: number | null
  /** 庫存狀態字串，例如 in_stock / out_of_stock。 */
  stock_status?: string
  /** 目前 session 是否已收藏此商品。 */
  is_favorite?: boolean
  /** 可用顏色選項。 */
  color_options?: string[]
  /** 可用尺寸選項。 */
  size_options?: string[]
  /** 是否有折扣。 */
  has_discount?: boolean
  /** 折扣百分比。 */
  discount_percent?: number
  /** 價格區間顯示文字。 */
  price_range_label?: string
  /** 後台審核或商品狀態。 */
  status?: string
  /** 狀態的人類可讀標籤。 */
  status_label?: string
  /** 管理員下架商品時留下的附註。 */
  review_note?: string
  /** 前端可直接顯示的庫存文字。 */
  stock_display?: string
  /** 規格摘要文字。 */
  specs_text?: string
  /** 變體摘要文字。 */
  variants_text?: string
  /** 商品變體清單。 */
  variants?: ProductVariant[]
  shipping_profile?: {
    use_seller_rules: boolean
    allow_home_delivery: boolean
    allow_convenience_store: boolean
    override_home_delivery_fee?: number | null
    override_convenience_store_fee?: number | null
  }
  default_variant?: ProductVariant | null
  /** 擁有者使用者 ID。 */
  owner_user_id?: number | null
  owner_username?: string
  owner_display_name?: string
}

export type ProductVariant = {
  id: string
  name: string
  sku?: string
  price: number
  compare_at_price?: number | null
  stock: number
  image?: string
  image_index?: number | null
  attributes?: {
    color?: string
    size?: string
  }
}

/**
 * 商品列表 API 回傳格式。
 */
export type ProductListPayload = {
  /** 商品清單。 */
  items: Product[]
  /** 分頁資訊。 */
  meta: {
    page: number
    total_pages: number
    total_items: number
  }
  /** 篩選 facet 選項。 */
  facets?: {
    categories?: string[]
    brands?: string[]
    colors?: string[]
    sizes?: string[]
    tags?: string[]
  }
  /** 後端回顯目前實際套用的篩選條件。 */
  filters?: Record<string, string>
}

/**
 * 商品比較清單。
 */
export type CompareListPayload = {
  /** 比較中的商品完整資料。 */
  items: Product[]
  /** 僅保留 slug 的輕量清單，方便前端快速判斷是否已加入比較。 */
  slugs: string[]
}

/**
 * 商品評論。
 */
/**
 * 單一外站比價結果。
 *
 * 目前是 mock 資料，用來示範 crawler / price compare 流程。
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
 * 商品比價結果 payload。
 */
export type PriceComparisonPayload = {
  our_product_slug: string
  our_product_name: string
  our_product_id: number
  our_price: number
  currency: string
  is_mock: boolean
  source_type: string
  last_refreshed_at: string
  last_refreshed_at_display?: string
  lowest_price: number
  our_store_is_lowest: boolean
  items: CompetitorPriceItem[]
}

/**
 * 模擬重新抓價回應。
 */
export type PriceComparisonRefreshPayload = {
  detail: string
  result: PriceComparisonPayload
}

export type Review = {
  id: number
  product_id: number
  /** 頁面顯示用作者名稱。 */
  author: string
  /** 作者帳號。 */
  author_username?: string | null
  /** 作者使用者 ID。 */
  author_user_id?: number | null
  /** 星等分數。 */
  rating: number
  /** 評論標題。 */
  title: string
  /** 評論內文。 */
  body: string
  /** 原始建立時間。 */
  created_at: string
  /** 格式化後可直接顯示的建立時間。 */
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
  body: string
  created_at: string
  created_at_display?: string
  /** 回答數量摘要。 */
  answer_count?: number
  /** 已展開時的回答清單。 */
  answers?: QuestionAnswer[]
}

/**
 * 社群文章的回覆。
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
 * 社群論壇文章。
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
  /** 文章投票分數。 */
  votes: number
  created_at: string
  created_at_display?: string
  /** 回覆數量摘要。 */
  reply_count?: number
  /** 文章詳情頁使用的完整回覆列表。 */
  replies?: CommunityReply[]
  can_edit?: boolean
  can_delete?: boolean
}

/**
 * 社群文章列表 payload。
 */
export type CommunityPostListPayload = {
  items: CommunityPost[]
}

/**
 * 購物車單一項目。
 */
export type CartItem = {
  /** 前端操作此項目的唯一 key。 */
  key: string
  id: number
  slug: string
  name: string
  /** 若有變體，顯示用名稱通常比原始 name 更完整。 */
  display_name: string
  price: number
  qty: number
  variant_id?: string
  variant_name?: string
  sku?: string
  /** 單列小計。 */
  line_total: number
}

/**
 * 購物車完整 payload。
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
  /** 後端可選回傳補充訊息。 */
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
  /** 發票類型，例如 personal / company。 */
  invoice_type: string
  carrier_code?: string
  company_name?: string
  tax_id?: string
  updated_at?: string
}

/**
 * checkout 選項列。
 */
export type CheckoutChoice = {
  value: string
  label: string
}

/**
 * checkout 預覽 payload。
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
 * 訂單資料。
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
  /** 訂單金額彙總。 */
  totals?: Record<string, string>
  /** 賣家視角的金額摘要 */
  seller_totals?: Record<string, string>
  /** 訂單項目。 */
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
  /** 售後申請資訊。 */
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
  /** 依賣家切分的物流 / 履約資訊。 */
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
 * 藍新支付 sandbox 設定摘要。
 *
 * 用途：
 * - 顯示後端是否已填好 MerchantID / HashKey / HashIV
 * - 顯示目前沙箱 gateway 與 callback URL 設定
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
 * 藍新支付 sandbox 準備結果。
 *
 * 用途：
 * - 前端可把 form_fields 組成 HTML form 後 POST 到 gateway_url
 * - 現階段也可直接顯示 payload，方便人工檢查
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

export type NewebpayPaymentDebug = {
  runtime: NewebpaySandboxPaymentSummary
  records: NewebpayPaymentRecord[]
}

/**
 * 藍新物流 sandbox scaffold 設定摘要。
 *
 * 用途：
 * - 顯示物流測試所需的 merchant 與 callback 設定
 * - 若 configured 為 false，可直接提示缺少哪些設定
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
 * 藍新物流 sandbox scaffold 準備結果。
 *
 * 用途：
 * - 顯示訂單被整理後，建議送往物流 API 的 payload
 * - 現階段仍是 scaffold，不直接向藍新送件
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
 * 審核中心首頁資料。
 */
export type StaffReviewDashboard = {
  managed_products: Product[]
  seller_requests: DemoUser[]
}

/**
 * 管理儀表板摘要資料。
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
 * 通用選項欄位。
 */
export type StatusChoice = {
  value: string
  label: string
}

/**
 * 會員中心摘要資料。
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
