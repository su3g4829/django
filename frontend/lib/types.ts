/**
 * ?垢?梁?摰儔
 *
 * ?桃?嚗?
 * - ?膩 Django DRF API ? payload ?耦?
 * - 霈??Ｚ??辣?典??刻???雿???蝣箏??交?蝷?
 * - ????蝡舀?雿?蝔曹?銝?湔???舀???
 */

/**
 * 蝷箇?? / 雿輻????
 *
 * 靘?嚗?
 * - `/api/v1/me/`
 * - `/api/v1/app/bootstrap/`
 * - `/api/v1/staff/users/`
 */
export type DemoUser = {
  /** 雿輻?蜓?萸?*/
  id: number
  /** ?餃撣唾???*/
  username: string
  /** 憿舐內?迂嚗?潮??Ｗ???雿?閮?*/
  display_name: string
  /** 閫嚗?憒?buyer / seller / admin??*/
  role: string
  /** 撣唾????靘? active / suspended??*/
  account_status?: string
  /** 鞈?振?唾????靘? pending / approved / rejected??*/
  seller_request_status?: string
  /** ?餃??萎辣??*/
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
 * ?函???????
 *
 * ?券?
 * - ?? header 憿舐內?餃???
 * - 憿舐內鞈潛頠?頛??柴???
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
 * ??鞈???
 */
export type Product = {
  /** ??銝駁??*/
  id: number
  /** ??蝬脣? slug??*/
  slug: string
  /** ???迂??*/
  name: string
  /** ?箇??桀??*/
  price: number
  /** ?嚗靘?蝞???＊蝷箝?*/
  compare_at_price?: number | null
  /** ???迂??*/
  brand: string
  /** ???迂??*/
  category: string
  /** 璅惜皜??*/
  tags?: string[]
  /** ????楝敺?*/
  images?: string[]
  /** ??銝餃???*/
  primary_image?: string
  /** 蝮賢澈摮?∪摰澈摮?賜 null??*/
  stock?: number | null
  /** 摨怠????銝莎?靘? in_stock / out_of_stock??*/
  stock_status?: string
  /** ?桀? session ?臬撌脫?迨????*/
  is_favorite?: boolean
  /** ?舐憿?賊???*/
  color_options?: string[]
  /** ?舐撠箏站?賊???*/
  size_options?: string[]
  /** ?臬?????*/
  has_discount?: boolean
  /** ??曉?瘥?*/
  discount_percent?: number
  /** ?寞??＊蝷箸?摮?*/
  price_range_label?: string
  /** 敺撖拇??????*/
  status?: string
  /** ???鈭粹??航?璅惜??*/
  status_label?: string
  /** 蝞∠??∩??嗅???????閮颯?*/
  review_note?: string
  /** ?垢?舐?仿＊蝷箇?摨怠?????*/
  stock_display?: string
  /** 閬??????*/
  specs_text?: string
  /** 霈???????*/
  variants_text?: string
  /** ??霈?皜??*/
  variants?: ProductVariant[]
  shipping_profile?: {
    use_seller_rules: boolean
    allow_home_delivery: boolean
    allow_convenience_store: boolean
    override_home_delivery_fee?: number | null
    override_convenience_store_fee?: number | null
  }
  default_variant?: ProductVariant | null
  /** ???蝙?刻?ID??*/
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
 * ???” API ??澆???
 */
export type ProductListPayload = {
  /** ??皜??*/
  items: Product[]
  /** ??鞈???*/
  meta: {
    page: number
    total_pages: number
    total_items: number
  }
  /** 蝭拚 facet ?賊???*/
  facets?: {
    categories?: string[]
    brands?: string[]
    colors?: string[]
    sizes?: string[]
    tags?: string[]
  }
  /** 敺垢?＊?桀?撖阡?憟?祟?豢?隞嗚?*/
  filters?: Record<string, string>
}

/**
 * ??瘥?皜??
 */
export type CompareListPayload = {
  /** 瘥?銝剔???摰鞈???*/
  items: Product[]
  /** ????slug ?????殷??嫣噶?垢敹恍?瑟?血歇?瘥???*/
  slugs: string[]
}

/**
 * ??閰???
 */
/**
 * ?桐?憭?瘥蝯???
 *
 * ?桀???mock 鞈?嚗靘內蝭?crawler / price compare 瘚???
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
 * ??瘥蝯? payload??
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
 * 璅⊥??????
 */
export type PriceComparisonRefreshPayload = {
  detail: string
  result: PriceComparisonPayload
}

export type Review = {
  id: number
  product_id: number
  /** ?憿舐內?其???蝔晞?*/
  author: string
  /** 雿董??*/
  author_username?: string | null
  /** 雿蝙?刻?ID??*/
  author_user_id?: number | null
  /** ?????*/
  rating: number
  /** 閰?璅???*/
  title: string
  /** 閰??扳???*/
  body: string
  /** ??撱箇?????*/
  created_at: string
  /** ?澆????舐?仿＊蝷箇?撱箇?????*/
  created_at_display?: string
}

/**
 * ????銝剔?????
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
 * ????銝剔?????
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
  /** ???賊?????*/
  answer_count?: number
  /** 撌脣?????蝑??柴?*/
  answers?: QuestionAnswer[]
}

/**
 * 蝷曄黎????閬?
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
 * 蝷曄黎隢?????
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
  /** ???巨???*/
  votes: number
  created_at: string
  created_at_display?: string
  /** ???賊?????*/
  reply_count?: number
  /** ??閰單??蝙?函?摰???”??*/
  replies?: CommunityReply[]
  can_edit?: boolean
  can_delete?: boolean
}

/**
 * 蝷曄黎???” payload??
 */
export type CommunityPostListPayload = {
  items: CommunityPost[]
}

/**
 * 鞈潛頠銝???
 */
export type CartItem = {
  /** ?垢??甇日??桃??臭? key??*/
  key: string
  id: number
  slug: string
  name: string
  /** ?交?霈?嚗＊蝷箇?迂?虜瘥?憪?name ?游??氬?*/
  display_name: string
  price: number
  qty: number
  variant_id?: string
  variant_name?: string
  sku?: string
  /** ?桀?撠???*/
  line_total: number
}

/**
 * 鞈潛頠???payload??
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
  /** 敺垢?舫?鋆?閮??*/
  detail?: string
}

/**
 * ?嗡辣?啣???
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
 * ?潛巨閮剖???
 */
export type InvoiceProfile = {
  /** ?潛巨憿?嚗?憒?personal / company??*/
  invoice_type: string
  carrier_code?: string
  company_name?: string
  tax_id?: string
  updated_at?: string
}

/**
 * checkout ?賊???
 */
export type CheckoutChoice = {
  value: string
  label: string
}

/**
 * checkout ?汗 payload??
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
 * 閮鞈???
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
  tracking_number?: string
  shipping_note?: string
  shipped_at_display?: string
  completed_at_display?: string
  shipping_address?: Address
  shipping_method?: string
  shipping_method_label?: string
  payment_method?: string
  payment_method_label?: string
  pickup_store_brand?: string
  pickup_store_brand_label?: string
  pickup_store_code?: string
  pickup_store_name?: string
  pickup_store_address?: string
  buyer_note?: string
  created_at: string
  created_at_display?: string
  /** 閮??敶蜇??*/
  totals?: Record<string, string>
  /** 鞈?振閬???憿?閬?*/
  seller_totals?: Record<string, string>
  /** 閮???*/
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
  /** ?桀??唾?鞈???*/
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
  can_confirm_completion?: boolean
  /** 靘都摰嗅????拇? / 撅亦?鞈???*/
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
 * ??臭? sandbox 閮剖?????
 *
 * ?券?
 * - 憿舐內敺垢?臬撌脣‵憟?MerchantID / HashKey / HashIV
 * - 憿舐內?桀?瘝拳 gateway ??callback URL 閮剖?
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
 * ??臭? sandbox 皞?蝯???
 *
 * ?券?
 * - ?垢?舀? form_fields 蝯? HTML form 敺?POST ??gateway_url
 * - ?暸?畾萎??舐?仿＊蝷?payload嚗靘蹂犖撌交炎??
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


/**
 * 鞈?振?瑕?梯”??
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
 * 撖拇銝剖?擐?鞈???
 */
export type StaffReviewDashboard = {
  managed_products: Product[]
  seller_requests: DemoUser[]
}

/**
 * 蝞∠??銵冽??鞈???
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
 * ??賊?甈???
 */
export type StatusChoice = {
  value: string
  label: string
}

/**
 * ?銝剖???鞈???
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
