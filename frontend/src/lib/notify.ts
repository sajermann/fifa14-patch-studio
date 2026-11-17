// The app's toasts. Screens import `toast` from here, never from sonner directly: when the app gets its notification
// center, this file starts recording the messages too and no screen has to change.
export { toast } from 'sonner'
