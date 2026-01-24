/// <reference types="vitest/globals" />
/// <reference types="@testing-library/jest-dom" />

declare global {
  namespace Vi {
    interface Matchers<R = void> {
      toBeInTheDocument(): R
      toBeDisabled(): R
      toBeEnabled(): R
      toBeVisible(): R
      toHaveTextContent(text: string | RegExp): R
      toHaveAttribute(attr: string, value?: string): R
      toHaveClass(className: string): R
      toBeChecked(): R
      toBeInvalid(): R
      toBeValid(): R
      toHaveValue(value: string | number | string[]): R
      toHaveDisplayValue(value: string | RegExp | Array<string | RegExp>): R
      toBePartiallyChecked(): R
      toHaveDescription(text: string | RegExp): R
      toHaveErrorMessage(text: string | RegExp): R
      toBeRequired(): R
      toBeEmptyDOMElement(): R
      toContainElement(element: Element | null): R
      toContainHTML(html: string): R
    }
  }
}
