/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  readonly VITE_VAPI_PHONE_NUMBER: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
