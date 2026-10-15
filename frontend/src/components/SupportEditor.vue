<script setup lang="ts">
import { Ckeditor } from '@ckeditor/ckeditor5-vue'
import {
  Autoformat, AutoLink, BlockQuote, Bold, ClassicEditor, Code, CodeBlock, Essentials, FileRepository,
  Heading, Image, ImageCaption, ImageResize, ImageStyle, ImageToolbar, ImageUpload, Italic, Link, List,
  Paragraph, PasteFromOffice, Strikethrough, Underline,
  type Editor, type EditorConfig, type FileLoader, type UploadAdapter, type UploadResponse,
} from 'ckeditor5'
import 'ckeditor5/ckeditor5.css'
import { extractAPIError, uploadSupportImage } from '../services/api'

defineProps<{ disabled?: boolean; placeholder?: string }>()
const model = defineModel<string>({ required: true })

class SupportImageUploadAdapter implements UploadAdapter {
  private readonly loader: FileLoader

  constructor(loader: FileLoader) {
    this.loader = loader
  }

  async upload(): Promise<UploadResponse> {
    const file = await this.loader.file
    if (!file) throw new Error('No file was selected.')
    try {
      return { default: await uploadSupportImage(file) }
    } catch (error) {
      throw extractAPIError(error, 'The image could not be uploaded.').message
    }
  }

  abort() {
    // Uploads are small and short-lived; an aborted request simply resolves unused.
  }
}

function SupportUploadAdapterPlugin(editor: Editor) {
  editor.plugins.get(FileRepository).createUploadAdapter = (loader) => new SupportImageUploadAdapter(loader)
}

const editor = ClassicEditor
const config: EditorConfig = {
  licenseKey: 'GPL',
  plugins: [
    Essentials, Paragraph, Heading, Bold, Italic, Underline, Strikethrough, Code, Link, AutoLink, List,
    BlockQuote, CodeBlock, Autoformat, PasteFromOffice, Image, ImageUpload, ImageToolbar, ImageCaption,
    ImageStyle, ImageResize,
  ],
  extraPlugins: [SupportUploadAdapterPlugin],
  toolbar: {
    items: [
      'heading', '|', 'bold', 'italic', 'underline', 'strikethrough', 'code', '|', 'link', 'bulletedList',
      'numberedList', 'blockQuote', 'codeBlock', '|', 'uploadImage', '|', 'undo', 'redo',
    ],
    shouldNotGroupWhenFull: false,
  },
  heading: {
    options: [
      { model: 'paragraph', title: 'Paragraph', class: 'ck-heading_paragraph' },
      { model: 'heading2', view: 'h2', title: 'Heading', class: 'ck-heading_heading2' },
      { model: 'heading3', view: 'h3', title: 'Subheading', class: 'ck-heading_heading3' },
    ],
  },
  image: {
    upload: { types: ['png', 'jpeg', 'gif', 'webp'] },
    toolbar: ['imageTextAlternative', 'toggleImageCaption', '|', 'imageStyle:inline', 'imageStyle:block'],
  },
  link: { defaultProtocol: 'https://', addTargetToExternalLinks: false },
}
</script>

<template>
  <div class="support-editor">
    <Ckeditor
      v-model="model"
      :editor="editor"
      :config="{ ...config, placeholder }"
      :disabled="disabled"
    />
  </div>
</template>
