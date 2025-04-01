import React, { useState, useRef, useCallback, useEffect } from 'react';

interface ImageCompareSliderProps {
    beforeImage: string;
    afterImage: string;
    altBefore?: string;
    altAfter?: string;
    className?: string;
}

const ImageCompareSlider: React.FC<ImageCompareSliderProps> = ({
    beforeImage,
    afterImage,
    altBefore = 'Before image',
    altAfter = 'After image',
    className = '',
}) => {
    const [sliderPosition, setSliderPosition] = useState(50); // Percentage (0-100)
    const [isDragging, setIsDragging] = useState(false);
    const containerRef = useRef<HTMLDivElement>(null);

    // Calculates and updates the slider position based on clientX
    const updateSlider = useCallback((clientX: number) => {
        if (!containerRef.current) return;
        const rect = containerRef.current.getBoundingClientRect();
        // Calculate position relative to the container, clamp between 0 and 1
        const x = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
        setSliderPosition(x * 100);
    }, []); // No dependencies needed as containerRef doesn't change

    // Mouse Handlers
    const handleMouseDown = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
        // Prevent text selection during drag
        e.preventDefault();
        setIsDragging(true);
        updateSlider(e.clientX);
    }, [updateSlider]);

    const handleMouseMove = useCallback((e: MouseEvent) => {
        if (!isDragging) return;
        // No preventDefault needed here as we listen on window
        updateSlider(e.clientX);
    }, [isDragging, updateSlider]);

    const handleMouseUp = useCallback(() => {
        // Check isDragging to avoid setting state unnecessarily
        if (isDragging) {
            setIsDragging(false);
        }
    }, [isDragging]);

    // Touch Handlers
    const handleTouchStart = useCallback((e: React.TouchEvent<HTMLDivElement>) => {
        // Don't prevent default here unless needed to stop scrolling,
        // but usually you want scrolling if not dragging the handle.
        // If preventing scroll IS desired when starting drag: e.preventDefault();
        setIsDragging(true);
        // Check if touches exist
        if (e.touches.length > 0) {
            updateSlider(e.touches[0].clientX);
        }
    }, [updateSlider]);

    const handleTouchMove = useCallback((e: TouchEvent) => {
        if (!isDragging || !e.touches || e.touches.length === 0) return;
        // No preventDefault needed here if window listener is passive
        updateSlider(e.touches[0].clientX);
    }, [isDragging, updateSlider]);

    const handleTouchEnd = useCallback(() => {
        // Check isDragging to avoid setting state unnecessarily
        if (isDragging) {
            setIsDragging(false);
        }
    }, [isDragging]);

    // Effect to add/remove global event listeners for dragging outside the component
    useEffect(() => {
        // Use window listeners for mousemove/mouseup to catch drags ending outside the container
        window.addEventListener('mousemove', handleMouseMove);
        window.addEventListener('mouseup', handleMouseUp);
        // Use window listeners for touchmove/touchend for the same reason
        // passive: true is important for touchmove performance if preventDefault isn't needed
        window.addEventListener('touchmove', handleTouchMove, { passive: true });
        window.addEventListener('touchend', handleTouchEnd);
        window.addEventListener('touchcancel', handleTouchEnd); // Handle cancelled touches

        // Cleanup function to remove listeners
        return () => {
            window.removeEventListener('mousemove', handleMouseMove);
            window.removeEventListener('mouseup', handleMouseUp);
            window.removeEventListener('touchmove', handleTouchMove);
            window.removeEventListener('touchend', handleTouchEnd);
            window.removeEventListener('touchcancel', handleTouchEnd);
        };
    }, [handleMouseMove, handleMouseUp, handleTouchMove, handleTouchEnd]); // Dependencies are the 
    
    // Define base classes excluding max-width and centering
    const baseClasses = "relative w-full aspect-[16/9] overflow-hidden cursor-ew-resize select-none group rounded-lg shadow-lg";

    return (
        <div
            ref={containerRef}
            // --- Container Styling ---
            className={`${baseClasses} ${className}`}
            // --- Event Handlers on Container ---
            onMouseDown={handleMouseDown} // Start drag on mouse down
            onTouchStart={handleTouchStart} // Start drag on touch start
        >
            {/* --- After Image (Bottom Layer) --- */}
            {/* Renders the full "after" image */}
            <img
                src={afterImage}
                alt={altAfter}
                // --- Styling ---
                // absolute inset-0: Positions top/right/bottom/left to 0 relative to container
                // w-full h-full: Takes full width/height of container
                // object-cover: Scales image to cover container, maintaining aspect ratio (may crop)
                // pointer-events-none: Prevents image from interfering with mouse/touch events on container
                // block: Removes extra space below image if it were inline
                className="absolute inset-0 w-full h-full object-cover pointer-events-none block"
                draggable={false} // Prevent native image dragging
            />

            {/* --- Before Image (Top Layer, Clipped) --- */}
            {/* Renders the full "before" image, styled IDENTICALLY to the after image */}
            {/* The `clip-path` dynamically reveals the left portion based on sliderPosition */}
            <img
                src={beforeImage}
                alt={altBefore}
                // --- Styling (Identical to After Image for perfect alignment) ---
                className="absolute inset-0 w-full h-full object-cover pointer-events-none block"
                draggable={false} // Prevent native image dragging
                // --- Dynamic Clipping ---
                // clip-path: inset(top right bottom left)
                // We only want to clip from the right side inwards.
                // The amount to clip from the right is (100% - sliderPosition%)
                // e.g., slider=75% -> clip 25% from right -> inset(0 25% 0 0)
                // e.g., slider=20% -> clip 80% from right -> inset(0 80% 0 0)
                style={{
                    clipPath: `inset(0 ${100 - sliderPosition}% 0 0)`,
                }}
            />

            {/* --- Slider Handle and Line --- */}
            {/* Positioned absolutely based on sliderPosition */}
            <div
                className="absolute top-0 bottom-0 w-1 bg-white bg-opacity-80 pointer-events-none cursor-ew-resize shadow-md"
                // Position the line's left edge based on slider percentage.
                // Subtract half the line width (0.5px ~ 1px) for centering if needed, but calc with % works well.
                style={{ left: `calc(${sliderPosition}% - 1px)` }} // Adjust '-1px' if line width changes
            >
                {/* The draggable-looking handle part */}
                <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-8 h-8 bg-white rounded-full shadow-xl border-2 border-gray-300 flex items-center justify-center cursor-ew-resize group-hover:opacity-100 opacity-80 transition-opacity">
                    {/* Arrows Icon */}
                    <svg className="w-4 h-4 text-gray-600 transform rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 9l4-4 4 4m0 6l-4 4-4-4"></path>
                    </svg>
                </div>
            </div>
        </div>
    );
};

export default ImageCompareSlider;