/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API base URL; defaults to the local backend in dev. */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
