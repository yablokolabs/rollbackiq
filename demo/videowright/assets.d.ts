/**
 * Asset imports that Vite resolves to a URL string at build time.
 *
 * The generated Vite client types declare `*.png` but not the WebP/MP4 assets a
 * video project also pulls in, so they are declared here.
 */
declare module "*.png" {
  const src: string;
  export default src;
}

declare module "*.jpg" {
  const src: string;
  export default src;
}

declare module "*.svg" {
  const src: string;
  export default src;
}

declare module "*.webp" {
  const src: string;
  export default src;
}

declare module "*.mp4" {
  const src: string;
  export default src;
}
