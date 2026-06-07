'use client'

/**
 * rich-text 編輯器元件。
 *
 * 這個元件整合了三層能力：
 * 1. React hook 與 JSX
 * 2. Tiptap editor 與 extension 系統
 * 3. 瀏覽器原生圖片處理 API
 *
 * 來源模組：
 * - `@tiptap/core` / `@tiptap/react` / `@tiptap/*`
 *   來自 Tiptap 生態系，用來建立可擴充的編輯器
 * - `react`
 *   提供 `useState`、`useEffect`、`useMemo`、`useRef`
 * - Web API
 *   例如 `File`、`Image`、`Blob`、`canvas`、clipboard、drag-and-drop
 */
import { Extension, mergeAttributes } from '@tiptap/core'
import Color from '@tiptap/extension-color'
import Highlight from '@tiptap/extension-highlight'
import Image from '@tiptap/extension-image'
import Link from '@tiptap/extension-link'
import { TextStyle } from '@tiptap/extension-text-style'
import Underline from '@tiptap/extension-underline'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import { ChangeEvent, ClipboardEvent, DragEvent, useEffect, useMemo, useRef, useState } from 'react'

/**
 * 這些常數屬於編輯器 UI 規則，不是後端 schema。
 *
 * `as const` 來自 TypeScript，
 * 會把陣列元素收窄成 literal type，而不是一般 `string[]`。
 */
const FONT_SIZE_OPTIONS = ['14px', '16px', '18px', '20px', '24px', '28px', '32px'] as const
const COLOR_OPTIONS = ['#1f2937', '#2563eb', '#dc2626', '#16a34a', '#d97706', '#7c3aed'] as const
const IMAGE_WIDTH_OPTIONS = ['33%', '50%', '67%', '100%'] as const
const MAX_IMAGE_DIMENSION = 1600
const IMAGE_COMPRESSION_THRESHOLD_BYTES = 1.5 * 1024 * 1024

/**
 * 自訂字級 extension。
 *
 * Tiptap 預設沒有把 `font-size` 當成第一級 command，
 * 所以這裡用 `Extension.create(...)` 擴充 `textStyle` mark，
 * 讓 HTML 可以保存字級 style。
 */
const FontSize = Extension.create({
  name: 'fontSize',

  addOptions() {
    return {
      types: ['textStyle'],
    }
  },

  addGlobalAttributes() {
    return [
      {
        types: this.options.types,
        attributes: {
          fontSize: {
            default: null,
            parseHTML: (element: HTMLElement) => element.style.fontSize || null,
            renderHTML: (attributes: Record<string, string | null>) => {
              if (!attributes.fontSize) {
                return {}
              }
              return { style: `font-size: ${attributes.fontSize}` }
            },
          },
        },
      },
    ]
  },
})

/**
 * 自訂圖片 extension。
 *
 * 內建 `Image` extension 主要處理 `src` 等基本屬性。
 * 這裡額外保存：
 * - `width`
 * - `align`
 *
 * 這樣 rich-text 內容存回 HTML 後，重新載入仍可還原圖片寬度與對齊方式。
 */
const RichImage = Image.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      width: {
        default: '100%',
        parseHTML: (element: HTMLElement) => element.getAttribute('data-width') || element.style.width || '100%',
      },
      align: {
        default: 'center',
        parseHTML: (element: HTMLElement) => element.getAttribute('data-align') || 'center',
      },
    }
  },

  renderHTML({ HTMLAttributes }: { HTMLAttributes: Record<string, string> }) {
    const align = HTMLAttributes.align || 'center'
    const width = HTMLAttributes.width || '100%'
    const marginStyle =
      align === 'left' ? 'margin: 0 auto 0 0;' : align === 'right' ? 'margin: 0 0 0 auto;' : 'margin: 0 auto;'
    const style = `display: block; width: ${width}; max-width: 100%; height: auto; ${marginStyle}`

    return [
      'img',
      mergeAttributes(HTMLAttributes, {
        style,
        'data-align': align,
        'data-width': width,
      }),
    ]
  },
})

type RichTextEditorProps = {
  value: string
  onChange: (html: string) => void
  onImageUpload?: (file: File, onProgress?: (percent: number) => void) => Promise<string>
}

/**
 * 上傳進度的本地 state 結構。
 *
 * `type UploadState` 是 TypeScript 型別別名，
 * 用來描述 React state 的資料形狀。
 */
type UploadState = {
  current: number
  total: number
  percent: number
}

/**
 * Toolbar 按鈕的小型共用元件。
 *
 * 這個元件本身不理解 Tiptap，只負責把：
 * - `active`
 * - `disabled`
 * - `onClick`
 * 映射成一致的按鈕樣式。
 */
function ToolbarButton({
  active = false,
  children,
  onClick,
  disabled = false,
}: {
  active?: boolean
  children: string
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <button
      className={active ? 'btn' : 'btn btn-secondary'}
      disabled={disabled}
      type="button"
      onClick={onClick}
      style={{ padding: '0.45rem 0.7rem' }}
    >
      {children}
    </button>
  )
}

function isImageFile(file: File) {
  return file.type.startsWith('image/')
}

/**
 * 替換檔案副檔名。
 *
 * 這裡用 `replace(/\.[^.]+$/, ...)` 這個正規表示式，
 * 是為了把原始副檔名替換成新的，例如：
 * `photo.png` -> `photo.webp`
 */
function fileNameWithExtension(name: string, extension: string) {
  return name.replace(/\.[^.]+$/, '') + extension
}

/**
 * 先把本機圖片檔載成 `HTMLImageElement`。
 *
 * `Promise<HTMLImageElement>` 的意思是：
 * - 這是一段非同步流程
 * - 完成後會得到真正的圖片 DOM 物件
 *
 * 後面的圖片壓縮需要 `naturalWidth / naturalHeight`，
 * 不能只看 `File` metadata。
 */
async function loadImageFromFile(file: File) {
  const objectUrl = URL.createObjectURL(file)
  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const element = new window.Image()
      element.onload = () => resolve(element)
      element.onerror = () => reject(new Error('無法讀取圖片'))
      element.src = objectUrl
    })
    return image
  } finally {
    URL.revokeObjectURL(objectUrl)
  }
}

/**
 * 上傳前先在瀏覽器端壓縮或縮放圖片。
 *
 * 這裡用到的 Web API：
 * - `canvas`
 * - `Blob`
 * - `File`
 *
 * 目的是在 rich-text 圖片上傳前先降低體積，減少傳輸時間。
 */
async function optimizeImageFile(file: File) {
  if (!isImageFile(file) || file.type === 'image/gif') {
    return file
  }

  const image = await loadImageFromFile(file)
  const largestSide = Math.max(image.naturalWidth, image.naturalHeight)
  const shouldResize = largestSide > MAX_IMAGE_DIMENSION
  const shouldCompress = file.size > IMAGE_COMPRESSION_THRESHOLD_BYTES
  if (!shouldResize && !shouldCompress) {
    return file
  }

  const scale = shouldResize ? MAX_IMAGE_DIMENSION / largestSide : 1
  const width = Math.max(1, Math.round(image.naturalWidth * scale))
  const height = Math.max(1, Math.round(image.naturalHeight * scale))
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  if (!context) {
    return file
  }
  context.drawImage(image, 0, 0, width, height)

  const blob = await new Promise<Blob | null>((resolve) => {
    canvas.toBlob((nextBlob) => resolve(nextBlob), 'image/webp', 0.82)
  })

  if (!blob) {
    return file
  }
  if (!shouldResize && blob.size >= file.size) {
    return file
  }

  return new File([blob], fileNameWithExtension(file.name, '.webp'), {
    type: 'image/webp',
    lastModified: Date.now(),
  })
}

export function RichTextEditor({ value, onChange, onImageUpload }: RichTextEditorProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [uploadState, setUploadState] = useState<UploadState | null>(null)
  const [uploadError, setUploadError] = useState('')
  const [dragActive, setDragActive] = useState(false)

  /**
   * 這幾個 hook 狀態的分工：
   * - `useRef`: 指向隱藏 file input，方便 toolbar 按鈕主動觸發
   * - `uploadState`: 控制進度條
   * - `uploadError`: 顯示上傳錯誤
   * - `dragActive`: 控制拖拉覆蓋層樣式
   */

  /**
   * `useMemo` 用來保存 editor extension 陣列。
   *
   * 如果每次 render 都重新建立 extensions，
   * Tiptap editor 可能被迫重建，造成游標位置或編輯狀態不穩。
   */
  const extensions = useMemo(
    () => [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
      }),
      TextStyle,
      FontSize,
      Underline,
      Color,
      Highlight,
      Link.configure({
        openOnClick: false,
        autolink: true,
        defaultProtocol: 'https',
        HTMLAttributes: {
          rel: 'noopener noreferrer nofollow',
          target: '_blank',
        },
      }),
      RichImage.configure({
        inline: false,
      }),
    ],
    [],
  )

  const editor = useEditor({
    extensions,
    content: value || '<p></p>',
    immediatelyRender: false,
    onUpdate: ({ editor: nextEditor }) => {
      onChange(nextEditor.getHTML())
    },
    editorProps: {
      attributes: {
        class: 'rich-text-editor__content',
      },
    },
  })

  /**
   * 當外部 `value` 改變時，把最新 HTML 同步回 editor。
   *
   * `useEffect` 來自 React，專門處理 render 後的副作用。
   * 這件事不能直接寫在 render 階段，不然每次 render 都會觸發內容重設。
   */
  useEffect(() => {
    if (!editor) {
      return
    }
    const currentHtml = editor.getHTML()
    const nextHtml = value || '<p></p>'
    if (currentHtml !== nextHtml) {
      editor.commands.setContent(nextHtml, { emitUpdate: false })
    }
  }, [editor, value])

  if (!editor) {
    return <div className="card muted">編輯器載入中...</div>
  }

  const activeEditor = editor
  const currentColor = activeEditor.getAttributes('textStyle').color ?? COLOR_OPTIONS[0]
  const currentFontSize = activeEditor.getAttributes('textStyle').fontSize ?? FONT_SIZE_OPTIONS[1]
  const selectedImageAttributes = activeEditor.getAttributes('image')
  const selectedImageWidth = selectedImageAttributes.width ?? '100%'
  const selectedImageAlign = selectedImageAttributes.align ?? 'center'
  const imageSelected = activeEditor.isActive('image')

  /**
   * 這些值不是獨立 state，而是從 editor 即時讀出的衍生值。
   * 這樣可避免維護第二份同步狀態。
   */

  /**
   * 核心圖片上傳流程。
   *
   * 流程：
   * 1. 過濾出圖片檔
   * 2. 先做前端優化
   * 3. 呼叫外部傳入的 `onImageUpload`
   * 4. 拿到 URL 後插回 editor
   */
  async function uploadAndInsertImages(files: File[]) {
    if (!files.length || !onImageUpload) {
      return
    }

    const imageFiles = files.filter(isImageFile)
    if (!imageFiles.length) {
      return
    }

    try {
      setUploadError('')
      for (const [index, file] of imageFiles.entries()) {
        setUploadState({ current: index + 1, total: imageFiles.length, percent: 0 })
        const optimizedFile = await optimizeImageFile(file)
        const imageUrl = await onImageUpload(optimizedFile, (percent) =>
          setUploadState({ current: index + 1, total: imageFiles.length, percent }),
        )
        activeEditor
          .chain()
          .focus()
          .setImage({ src: imageUrl, alt: optimizedFile.name, width: '100%', align: 'center' } as any)
          .run()
      }
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : '圖片上傳失敗')
    } finally {
      setUploadState(null)
      setDragActive(false)
    }
  }

  /**
   * `Record<string, string>` 是 TypeScript 內建 utility type。
   * 這裡表示呼叫端會傳一組字串鍵值對，例如：
   * - `{ width: '50%' }`
   * - `{ align: 'left' }`
   */
  function updateSelectedImage(attrs: Record<string, string>) {
    activeEditor.chain().focus().updateAttributes('image', attrs).run()
  }

  /**
   * 套用字級。
   *
   * Tiptap 的 command chain API 會回傳可串接物件，
   * 最後靠 `.run()` 真正執行。
   */
  function setFontSize(fontSize: string) {
    ;(activeEditor.chain().focus().setMark('textStyle', { fontSize }) as any).run()
  }

  function handleSetLink() {
    const previousUrl = activeEditor.getAttributes('link').href ?? ''
    const url = window.prompt('請輸入連結 URL', previousUrl)
    if (url == null) {
      return
    }
    const trimmed = url.trim()
    if (!trimmed) {
      activeEditor.chain().focus().extendMarkRange('link').unsetLink().run()
      return
    }
    activeEditor.chain().focus().extendMarkRange('link').setLink({ href: trimmed }).run()
  }

  function handleInsertImageByUrl() {
    const src = window.prompt('請輸入圖片 URL')
    if (!src) {
      return
    }
    activeEditor.chain().focus().setImage({ src: src.trim(), alt: '', width: '100%', align: 'center' } as any).run()
  }

  /**
   * 處理從本機檔案選擇圖片。
   *
   * `ChangeEvent<HTMLInputElement>` 來自 React 型別系統，
   * generic 指出事件來源是 `<input>`。
   */
  async function handleImageFileChange(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? [])
    event.target.value = ''
    await uploadAndInsertImages(files)
  }

  /**
   * 處理使用者直接貼上圖片。
   *
   * `ClipboardEvent` 來自 React 對瀏覽器 clipboard event 的型別包裝。
   */
  async function handlePaste(event: ClipboardEvent<HTMLDivElement>) {
    const files = Array.from(event.clipboardData.files ?? []).filter(isImageFile)
    if (!files.length) {
      return
    }
    event.preventDefault()
    await uploadAndInsertImages(files)
  }

  /**
   * 處理使用者拖拉圖片進編輯區。
   *
   * `DragEvent` 來自 React 對瀏覽器 drag-and-drop API 的型別包裝。
   */
  async function handleDrop(event: DragEvent<HTMLDivElement>) {
    const files = Array.from(event.dataTransfer.files ?? []).filter(isImageFile)
    setDragActive(false)
    if (!files.length) {
      return
    }
    event.preventDefault()
    await uploadAndInsertImages(files)
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    /**
     * 這裡一定要 `preventDefault()`，不然瀏覽器可能直接打開檔案，
     * 而不是把拖進來的圖片交給編輯器處理。
     */
    if (!Array.from(event.dataTransfer.items ?? []).some((item) => item.kind === 'file')) {
      return
    }
    event.preventDefault()
    setDragActive(true)
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>) {
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) {
      return
    }
    setDragActive(false)
  }

  return (
    <div className="rich-text-editor">
      {/* 主要文字格式工具列。每個按鈕都對應一個 Tiptap command。 */}
      <div className="rich-text-toolbar">
        <ToolbarButton active={activeEditor.isActive('bold')} onClick={() => activeEditor.chain().focus().toggleBold().run()}>
          粗體
        </ToolbarButton>
        <ToolbarButton active={activeEditor.isActive('italic')} onClick={() => activeEditor.chain().focus().toggleItalic().run()}>
          斜體
        </ToolbarButton>
        <ToolbarButton active={activeEditor.isActive('underline')} onClick={() => activeEditor.chain().focus().toggleUnderline().run()}>
          底線
        </ToolbarButton>
        <ToolbarButton active={activeEditor.isActive('bulletList')} onClick={() => activeEditor.chain().focus().toggleBulletList().run()}>
          項目符號
        </ToolbarButton>
        <ToolbarButton active={activeEditor.isActive('orderedList')} onClick={() => activeEditor.chain().focus().toggleOrderedList().run()}>
          編號清單
        </ToolbarButton>
        <ToolbarButton active={activeEditor.isActive('heading', { level: 2 })} onClick={() => activeEditor.chain().focus().toggleHeading({ level: 2 }).run()}>
          標題
        </ToolbarButton>
        <ToolbarButton active={activeEditor.isActive('blockquote')} onClick={() => activeEditor.chain().focus().toggleBlockquote().run()}>
          引用
        </ToolbarButton>
        <ToolbarButton active={activeEditor.isActive('highlight')} onClick={() => activeEditor.chain().focus().toggleHighlight().run()}>
          螢光
        </ToolbarButton>
        <ToolbarButton active={activeEditor.isActive('link')} onClick={handleSetLink}>
          連結
        </ToolbarButton>
        <ToolbarButton disabled={Boolean(uploadState) || !onImageUpload} onClick={() => fileInputRef.current?.click()}>
          {uploadState ? `上傳中 ${uploadState.current}/${uploadState.total}` : '上傳圖片'}
        </ToolbarButton>
        <ToolbarButton onClick={handleInsertImageByUrl}>圖片網址</ToolbarButton>
        <ToolbarButton onClick={() => activeEditor.chain().focus().unsetAllMarks().clearNodes().run()}>清除格式</ToolbarButton>

        <label className="rich-text-toolbar__control">
          <span>字級</span>
          <select value={currentFontSize} onChange={(event) => setFontSize(event.target.value)}>
            {FONT_SIZE_OPTIONS.map((fontSize) => (
              <option key={fontSize} value={fontSize}>
                {fontSize}
              </option>
            ))}
          </select>
        </label>

        <label className="rich-text-toolbar__control">
          <span>顏色</span>
          <input type="color" value={currentColor} onChange={(event) => activeEditor.chain().focus().setColor(event.target.value).run()} />
        </label>
      </div>

      {imageSelected ? (
        /* 只有在選到圖片節點時，才顯示圖片專用工具列。 */
        <div className="rich-text-toolbar rich-text-toolbar--secondary">
          <label className="rich-text-toolbar__control">
            <span>圖片寬度</span>
            <select value={selectedImageWidth} onChange={(event) => updateSelectedImage({ width: event.target.value })}>
              {IMAGE_WIDTH_OPTIONS.map((width) => (
                <option key={width} value={width}>
                  {width}
                </option>
              ))}
            </select>
          </label>
          <div className="row">
            <ToolbarButton active={selectedImageAlign === 'left'} onClick={() => updateSelectedImage({ align: 'left' })}>
              靠左
            </ToolbarButton>
            <ToolbarButton active={selectedImageAlign === 'center'} onClick={() => updateSelectedImage({ align: 'center' })}>
              置中
            </ToolbarButton>
            <ToolbarButton active={selectedImageAlign === 'right'} onClick={() => updateSelectedImage({ align: 'right' })}>
              靠右
            </ToolbarButton>
          </div>
        </div>
      ) : null}

      <div
        className={dragActive ? 'rich-text-dropzone rich-text-dropzone--active' : 'rich-text-dropzone'}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        onPaste={handlePaste}
      >
        <EditorContent editor={activeEditor} />
        {dragActive ? <div className="rich-text-dropzone__hint">放開即可插入圖片</div> : null}
      </div>

      <input accept="image/*" hidden multiple ref={fileInputRef} type="file" onChange={handleImageFileChange} />

      {uploadState ? (
        <div className="rich-text-upload">
          <div className="muted">
            上傳中 {uploadState.current}/{uploadState.total}，{uploadState.percent}%
          </div>
          <div className="rich-text-upload__bar">
            <div className="rich-text-upload__bar-fill" style={{ width: `${uploadState.percent}%` }} />
          </div>
        </div>
      ) : null}

      {uploadError ? <div className="notice">{uploadError}</div> : null}
      <div className="muted">支援直接貼上、拖拉圖片或從本機上傳，圖片會先嘗試壓縮再送往後端。</div>
    </div>
  )
}
