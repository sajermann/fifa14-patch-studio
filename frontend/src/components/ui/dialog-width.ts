/** The app's three dialog widths (max width from the sm breakpoint; below it every dialog takes the screen minus
 * 1 rem on each side). Pick one with `width` on DialogContent / AlertDialogContent, never a max-w class:
 * - sm (448 px): a plain confirmation, text and two buttons (the default)
 * - md (576 px): progress, a short list, three buttons or a picker
 * - lg (672 px): long lists, search, side by side review
 * - picture (up to 90% of the screen): a picture opened to be seen big (the extractor's zoom) */
export type DialogWidth = "sm" | "md" | "lg" | "picture"

export const DIALOG_WIDTH: Record<DialogWidth, string> = {
  sm: "sm:max-w-md",
  md: "sm:max-w-xl",
  lg: "sm:max-w-2xl",
  picture: "sm:max-w-[min(90vw,1200px)]",
}
