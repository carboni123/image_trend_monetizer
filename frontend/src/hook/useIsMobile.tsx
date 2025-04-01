import { useState, useEffect } from 'react';

export function useIsMobile(threshold: number = 768): boolean {
  // Create the media query string based on the threshold.
  const mediaQuery = `(max-width: ${threshold}px)`;

  // Initialize the state based on the media query.
  const [isMobile, setIsMobile] = useState<boolean>(() => {
    if (typeof window !== 'undefined' && window.matchMedia) {
      return window.matchMedia(mediaQuery).matches;
    }
    return false;
  });

  useEffect(() => {
    if (!window.matchMedia) return;

    // Create a MediaQueryList for the given query.
    const mediaQueryList = window.matchMedia(mediaQuery);

    // Define the handler that updates state based on the query's match.
    const listener = (e: MediaQueryListEvent) => {
      setIsMobile(e.matches);
    };

    // Add the listener for changes.
    if (mediaQueryList.addEventListener) {
      mediaQueryList.addEventListener('change', listener);
    } else {
      // Fallback for Safari and older browsers.
      mediaQueryList.addListener(listener);
    }

    // Cleanup function to remove the listener when the component unmounts.
    return () => {
      if (mediaQueryList.removeEventListener) {
        mediaQueryList.removeEventListener('change', listener);
      } else {
        mediaQueryList.removeListener(listener);
      }
    };
  }, [mediaQuery]);

  return isMobile;
}
