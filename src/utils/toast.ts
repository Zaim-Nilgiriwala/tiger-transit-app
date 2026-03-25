/**
 * Toast Utility
 *
 * Simple toast-like feedback using Alert.alert as a Phase 1 placeholder.
 * In future phases this can be replaced with react-native-toast-message
 * or sonner-native for non-blocking inline toasts.
 */
import { Alert } from 'react-native';

/**
 * Show a brief feedback message to the user.
 *
 * @param message - The message to display
 */
export function showToast(message: string): void {
  Alert.alert('', message);
}
